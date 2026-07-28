"""Unit tests for the pure eval helpers (no fixtures, no tools).

Every test calls the real function under test - none re-implement its logic
inline (lessons.md: a test that does not call the code is not a test).
"""
from __future__ import annotations

import polars as pl
import pytest

from tests.eval import eval_lib as L


def _minimal_subs(**overrides) -> pl.DataFrame:
    """A 2-row frame carrying just the columns the guards/compare touch."""
    data = {
        "spectrum_title": ["f:1:2", "f:2:2"],
        "Spectrum": ["f:1:2", "f:2:2"],
        "Charge": [2, 2],
        "origin": ["C", "M"],
        "destination": ["G", "A"],
        "misProt": [10, 20],
        "mistranslatedPos": [3, 4],
        "dpbp": [-1.5, 0.5],
        "Protein": ["PEP_C3G", "PEP2_M4A"],
        "Protein_right": ["sp|PEP", "sp|PEP2"],
        "SpectralSim": [0.9, 0.8],
        "RTScore": [0.7, 0.6],
        "base": ["PEPC", "PEPM"],
        "dependent": ["PEPG", "PEPA"],
    }
    data.update(overrides)
    return pl.DataFrame(data)


# --------------------------- canonicalize ---------------------------------- #

def test_canonicalize_is_row_order_independent():
    df = _minimal_subs()
    shuffled = df[::-1]
    assert L.canonicalize(df).equals(L.canonicalize(shuffled))


def test_canonicalize_rounds_floats():
    df = _minimal_subs(dpbp=[1.23456789, -2.0])
    out = L.canonicalize(df)
    assert out.filter(pl.col("origin") == "C")["dpbp"].item() == pytest.approx(1.234568)


def test_assert_snapshot_equal_passes_on_reordered_equal():
    df = _minimal_subs()
    L.assert_snapshot_equal(df[::-1], df)  # must not raise


def test_assert_snapshot_equal_fails_on_value_change():
    a = _minimal_subs()
    b = _minimal_subs(dpbp=[-1.5, 0.6])  # 0.5 -> 0.6
    with pytest.raises(AssertionError):
        L.assert_snapshot_equal(a, b)


def test_assert_snapshot_equal_fails_on_column_set_change():
    a = _minimal_subs()
    b = a.drop("Protein")
    with pytest.raises(AssertionError):
        L.assert_snapshot_equal(a, b)


# ----------------------------- invariants ---------------------------------- #

def test_check_no_decoys_passes_clean():
    L.check_no_decoys(_minimal_subs())  # must not raise


def test_check_no_decoys_fails_on_rev_protein_right():
    df = _minimal_subs(Protein_right=["rev_sp|PEP", "sp|PEP2"])
    with pytest.raises(AssertionError, match="decoy leak"):
        L.check_no_decoys(df)


def test_check_no_decoys_fails_on_rev_protein():
    df = _minimal_subs(Protein=["rev_PEP_C3G", "PEP2_M4A"])
    with pytest.raises(AssertionError, match="decoy leak"):
        L.check_no_decoys(df)


def test_check_scores_nonnull_fails_on_null():
    df = _minimal_subs(SpectralSim=[0.9, None])
    with pytest.raises(AssertionError, match="SpectralSim"):
        L.check_scores_nonnull(df)


def test_check_dpbp_finite_fails_on_inf():
    df = _minimal_subs(dpbp=[float("inf"), 0.5])
    with pytest.raises(AssertionError, match="non-finite"):
        L.check_dpbp_finite(df)


def test_check_dpbp_finite_fails_on_nan():
    df = _minimal_subs(dpbp=[float("nan"), 0.5])
    with pytest.raises(AssertionError, match="non-finite"):
        L.check_dpbp_finite(df)


def test_check_schema_fails_when_documented_column_missing():
    df = _minimal_subs()  # lacks most of the 73 documented columns
    with pytest.raises(AssertionError, match="missing documented columns"):
        L.check_schema(df)


# ---------------------------- slava_compare -------------------------------- #

def test_slava_compare_identical_is_perfect():
    ref = _minimal_subs()
    ours = _minimal_subs()
    res = L.slava_compare(ours, ref)
    assert res.n_shared_spectra == 2
    assert res.identity_fraction == 1.0
    assert res.dpbp_pearson_r == pytest.approx(1.0)
    res.assert_ok()  # must not raise


def test_slava_compare_catches_dropped_cys_row():
    """A Cys-origin spectrum in the reference but missing from ours (the D-070
    failure mode) drops shared-spectra identity below 100%."""
    ref = _minimal_subs()
    ours = _minimal_subs().filter(pl.col("origin") != "C")  # lost the Cys row
    res = L.slava_compare(ours, ref)
    # Only the Met spectrum is shared now; the Cys spectrum is ours-missing.
    assert res.n_shared_spectra == 1
    # Identity on the shared (Met) spectrum is still fine, but assert a mismatch
    # scenario too:
    ours2 = _minimal_subs(destination=["G", "V"])  # Met dest A -> V (wrong)
    res2 = L.slava_compare(ours2, ref)
    assert res2.identity_fraction < 1.0
    with pytest.raises(AssertionError, match="identity"):
        res2.assert_ok()


def test_slava_compare_no_shared_raises():
    ref = _minimal_subs()
    ours = _minimal_subs(spectrum_title=["z:9:2", "z:8:2"], Spectrum=["z:9:2", "z:8:2"])
    res = L.slava_compare(ours, ref)
    assert res.n_shared_spectra == 0
    with pytest.raises(AssertionError, match="no shared spectra"):
        res.assert_ok()
