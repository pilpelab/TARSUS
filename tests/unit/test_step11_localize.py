"""Unit tests for Step 11 — PyAscore localization."""

import numpy as np
import polars as pl
import pytest
from src.tarsus.steps.step11_localize import (
    mz_diff,
    ascore_to_probability,
    SUBSTITUTION_SHIFTS,
    get_var_mod_positions,
    _parse_aux_mods,
    _nonbase_hits,
    _expected_position,
    _strip_mod_suffix,
)


class TestStripModSuffix:
    """Step 8 writes `_M<pos>[_<pos>]C<pos>[_<pos>]` onto fake spectrum titles."""

    def test_simple_suffix(self) -> None:
        assert _strip_mod_suffix("f:1:2_M0C0") == "f:1:2"

    def test_single_positions(self) -> None:
        assert _strip_mod_suffix("HouYM:270212:3_M0C1") == "HouYM:270212:3"

    def test_multi_position_met(self) -> None:
        # The reference regex `_[^_]*$` mangles this to `..._M6` (D-048).
        assert _strip_mod_suffix("HouYM:327129:3_M6_14C0") == "HouYM:327129:3"

    def test_multi_position_both(self) -> None:
        assert _strip_mod_suffix("f:1:2_M3_7C1_5") == "f:1:2"

    def test_leaves_unsuffixed_title_alone(self) -> None:
        assert _strip_mod_suffix("f:1:2") == "f:1:2"

    def test_does_not_eat_underscores_in_filename(self) -> None:
        assert _strip_mod_suffix("my_file_sub:1:2_M0C0") == "my_file_sub:1:2"


class TestParseAuxMods:
    """Reference localize.py parses aux mods out of psmrankall's `modification`."""

    def test_single_mod(self) -> None:
        pos, mass = _parse_aux_mods("Oxidation of M@3[15.9949]")
        assert list(pos) == [3]
        assert mass == pytest.approx([15.9949])

    def test_multiple_mods(self) -> None:
        pos, mass = _parse_aux_mods("Oxidation of M@3[15.9949];Acetyl@1[42.0106]")
        assert list(pos) == [3, 1]
        assert mass == pytest.approx([15.9949, 42.0106])

    def test_no_modification(self) -> None:
        pos, mass = _parse_aux_mods("-")
        assert list(pos) == []
        assert list(mass) == []

    def test_non_string(self) -> None:
        pos, mass = _parse_aux_mods(None)
        assert list(pos) == []
        assert list(mass) == []

    def test_dtypes_are_pyascore_compatible(self) -> None:
        pos, mass = _parse_aux_mods("X@2[1.5]")
        assert pos.dtype == np.uint32
        assert mass.dtype == np.float32


class TestExpectedPosition:
    """subs.ipc stores a 0-based `mistranslated_pos`; PyAscore reports 1-based."""

    def test_zero_based_to_one_based(self) -> None:
        assert _expected_position({"mistranslated_pos": 20}) == 21

    def test_missing_column_raises_loudly(self) -> None:
        # Regression: a silent .get(..., 0) default made expected_pos always 1,
        # which Step 7's `mistranslated_pos > 0` filter can never satisfy —
        # Step 11 then returned zero rows on every run.
        with pytest.raises(KeyError):
            _expected_position({"mistranslatedPos": 20})


class TestNonBaseHits:
    def _deps(self) -> pl.DataFrame:
        return pl.DataFrame({
            "peptide": ["VAR1", "VAR2", "VAR3"],
            "spectrum_title": ["f:1:2", "f:2:2", "f:3:2"],
            "score": [10.0, 10.0, 10.0],
        })

    def _base(self) -> pl.DataFrame:
        # Step 8 appends a Met/Cys mod-state suffix to fake titles; it is stripped.
        # `_M6_14C0` is a multi-position suffix the reference regex would mangle.
        return pl.DataFrame({
            "peptide": ["BASE1", "BASE2"],
            "spectrum_title": ["f:1:2_M6_14C0", "f:2:2_M0C0"],
            "score": [4.0, 12.0],
        })

    def test_keeps_variant_beating_base(self) -> None:
        out = _nonbase_hits(self._deps(), self._base())
        assert out["spectrum_title"].to_list() == ["f:1:2"]
        assert out["delta_score"][0] == pytest.approx(6.0)

    def test_drops_variant_losing_to_base(self) -> None:
        out = _nonbase_hits(self._deps(), self._base())
        assert "f:2:2" not in out["spectrum_title"].to_list()

    def test_drops_variant_with_no_base_comparison(self) -> None:
        # Regression: a left join + fill_null(0) admitted variants that were
        # never rescored against their reference peptide, inflating results.
        out = _nonbase_hits(self._deps(), self._base())
        assert "f:3:2" not in out["spectrum_title"].to_list()


class TestMzDiff:
    def test_basic(self) -> None:
        theo_mz, delta_da, delta_ppm, delta_neutral = mz_diff("PEPTIDE", 500.0, 2)
        assert theo_mz > 0
        assert isinstance(delta_da, float)
        assert isinstance(delta_ppm, float)
        assert isinstance(delta_neutral, float)

    def exact_match(self) -> None:
        theo_mz, delta_da, _, _ = mz_diff("PEPTIDE", 500.0, 2)
        # At exact match, delta should be ~theoretical - observed
        assert abs(delta_da) < 0.01  # near zero if mass happens to be ~500

    def test_unknown_aa_raises(self) -> None:
        with pytest.raises(ValueError):
            mz_diff("PEX", 500.0, 2)

    def test_charge_one(self) -> None:
        theo_mz, _, _, _ = mz_diff("PEPTIDE", 500.0, 1)
        assert theo_mz > 0


class TestAscoreToProbability:
    def test_zero_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(0.0))
        assert prob == pytest.approx(1.0)

    def test_positive_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(10.0))
        assert prob < 1.0
        assert prob > 0.0

    def test_large_ascore(self) -> None:
        prob = ascore_to_probability(np.float64(20.0))
        assert prob == pytest.approx(0.01, rel=0.01)


class TestSubstitutionShifts:
    def test_ala_to_gly(self) -> None:
        # A: 71.03711, G: 57.02146
        shift = SUBSTITUTION_SHIFTS["A"]["G"]
        assert abs(shift - (57.02146 - 71.03711)) < 0.001

    def test_not_self(self) -> None:
        assert "A" not in SUBSTITUTION_SHIFTS["A"]

    def test_all_amino_acids(self) -> None:
        for aa in AA_MONO:
            assert aa in SUBSTITUTION_SHIFTS


AA_MONO = {
    "A": 71.03711, "R": 156.10111, "N": 114.04293, "D": 115.02694,
    "C": 103.00919, "E": 129.04259, "Q": 128.05858, "G": 57.02146,
    "H": 137.05891, "I": 113.08406, "L": 113.08406, "K": 128.09496,
    "M": 131.04049, "F": 147.06841, "P": 97.05276, "S": 87.03203,
    "T": 101.04768, "W": 186.07931, "Y": 163.06333, "V": 99.06841,
}


class TestGetVarModPositions:
    def test_no_modifications(self) -> None:
        positions = get_var_mod_positions(
            "PEPTIDE", 0.0,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == []

    def test_simple_mod_match(self) -> None:
        # Simulate a best_seq with one [mass] annotation
        mod_mass = 15.9949
        positions = get_var_mod_positions(
            f"P[+{mod_mass:.4f}]EPTIDE", mod_mass,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == [1]

    def test_with_aux_mod(self) -> None:
        mod_mass = 15.9949
        # P has var mod + aux mod at same position
        positions = get_var_mod_positions(
            f"P[+{mod_mass * 2:.4f}]EPTIDE", mod_mass,
            np.array([1], dtype=np.uint32),
            np.array([mod_mass], dtype=np.float32),
            0.05,
        )
        # total mass = 15.9949*2 = 31.9898, aux = 15.9949, var = 31.9898-15.9949 = 15.9949
        assert 1 in positions

    def test_too_large_tolerance_excludes(self) -> None:
        mod_mass = 15.9949
        positions = get_var_mod_positions(
            f"P[+{mod_mass:.4f}]EPTIDE", mod_mass + 1.0,
            np.array([], dtype=np.uint32),
            np.array([], dtype=np.float32),
            0.05,
        )
        assert positions == []

    def test_unbalanced_brackets(self) -> None:
        with pytest.raises(ValueError, match="Unbalanced brackets"):
            get_var_mod_positions(
                "P[EPTIDE", 0.0,
                np.array([], dtype=np.uint32),
                np.array([], dtype=np.float32),
                0.05,
            )
