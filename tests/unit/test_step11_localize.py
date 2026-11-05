"""Unit tests for Step 11 — PyAscore localization."""

from pathlib import Path
import numpy as np
import polars as pl
import pytest
from src.tarsus.steps.step11_localize import (
    mz_diff,
    ascore_to_probability,
    AA_MONO,
    SUBSTITUTION_SHIFTS,
    get_var_mod_positions,
    _parse_aux_mods,
    _nonbase_hits,
    _expected_position,
    _strip_mod_suffix,
    _read_psmrank,
    _label_isobaric_il,
)

_PSMRANK_HEADER = (
    "peptide\tmodification\tn\tspectrum_title\tcharge\texp_mass\ttol_ppm\ttol_da\t"
    "isotope_error\tpep_mass\tmz\tscore\tn_db\ttotal_db\tn_random\ttotal_random\t"
    "pvalue\trank\tn_ptm\tconfident\tref_delta_score\tmod_delta_score"
)
_GOOD = (
    "PEPTIDE\t-\t1\tf:1:2\t2\t100.0\t0.1\t0.001\t0.0\t100.0\t51.0\t12.5\t"
    "0\t201\t0\t10000\t1e-4\t1\t60\tYes\t3.6\t-3.1"
)
# PepQuery 2.0.2 occasionally repeats the final four fields verbatim, producing a
# 26-field line against its own 22-column header (4 of 19,913 rows on the trial
# dataset). Fields 1-22 remain a complete, valid record.
_RAGGED = _GOOD + "\t60\tYes\t3.6\t-3.1"


class TestReadPsmrank:
    def test_reads_clean_file(self, tmp_path: Path) -> None:
        p = tmp_path / "psmrankall.txt"
        p.write_text(f"{_PSMRANK_HEADER}\n{_GOOD}\n")
        df = _read_psmrank(p)
        assert df.height == 1
        assert df["spectrum_title"][0] == "f:1:2"

    def test_truncates_pepquery_duplicated_tail(self, tmp_path: Path) -> None:
        p = tmp_path / "psmrankall.txt"
        p.write_text(f"{_PSMRANK_HEADER}\n{_GOOD}\n{_RAGGED}\n")
        df = _read_psmrank(p)
        assert df.height == 2, "ragged 26-field row must not abort the read"
        assert df["score"].to_list() == [12.5, 12.5]
        assert df["confident"].to_list() == ["Yes", "Yes"]


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
    """subs.ipc stores a 0-based `mistranslatedPos`; PyAscore reports 1-based."""

    def test_zero_based_to_one_based(self) -> None:
        assert _expected_position({"mistranslatedPos": 20}) == 21

    def test_missing_column_raises_loudly(self) -> None:
        # Regression: a silent .get(..., 0) default made expected_pos always 1,
        # which Step 7's `mistranslatedPos > 0` filter can never satisfy —
        # Step 11 then returned zero rows on every run.
        with pytest.raises(KeyError):
            _expected_position({"some_other_column": 20})


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


class TestIsobaricIlLabel:
    """Origin is KNOWN (I or L), destination is ambiguous (I/L) — D-065.

    Ile and Leu share a mass, but the two ends of a substitution differ. The ORIGIN
    is the reference residue at the substituted position — fixed by the genome codon,
    so it is a definite `I` or `L`, recovered from `base[mistranslatedPos]`. The
    DESTINATION is the misincorporated residue, seen only by mass, so it is genuinely
    `I/L`. (D-064 wrongly collapsed both; Slava corrected it.)

    The relabel must still run AFTER `localize_shift`: the `/` fails **silently**
    upstream, in the `.get() -> None -> continue` mode behind D-048/D-049/D-057.
    """

    def _df(self, origin: list[str], dest: list[str], base: list[str],
            pos: list[int]) -> pl.DataFrame:
        return pl.DataFrame({
            "origin": origin, "destination": dest,
            "base": base, "mistranslatedPos": pos,
        })

    def test_origin_recovered_from_base_destination_becomes_IL(self) -> None:
        # base[pos]: THR at 1 -> T; ILE at 0 -> I; base "PEPTLDE" at 4 -> L
        df = self._df(
            origin=["I", "I", "I"],          # header class — should be overridden
            dest=["S", "V", "V"],
            base=["FTGQ", "IEK", "PEPTLDE"],
            pos=[1, 0, 4],
        )
        out = _label_isobaric_il(df)
        assert out["origin"].to_list() == ["T", "I", "L"], "origin = real base residue"
        assert out["destination"].to_list() == ["S", "V", "V"], "no I dest -> no I/L"

    def test_leu_origin_is_labelled_L_not_IL_and_not_I(self) -> None:
        out = _label_isobaric_il(self._df(["I"], ["S"], ["PEPTLDE"], [4]))
        assert out["origin"][0] == "L"
        assert out["origin"][0] not in ("I/L", "I")

    def test_destination_I_becomes_IL(self) -> None:
        out = _label_isobaric_il(self._df(["V"], ["I"], ["VEK"], [0]))
        assert out["destination"][0] == "I/L"

    def test_non_isobaric_origin_untouched(self) -> None:
        out = _label_isobaric_il(self._df(["T"], ["S"], ["TEST"], [0]))
        assert out["origin"][0] == "T" and out["destination"][0] == "S"

    def test_drops_no_rows(self) -> None:
        df = self._df(["I", "T", "I"], ["V", "S", "S"],
                      ["IEK", "TEST", "PEPTLDE"], [0, 0, 4])
        assert _label_isobaric_il(df).height == df.height == 3

    def test_idempotent(self) -> None:
        """Guards the in-place relabel of existing outputs: applying twice == once.

        Origin is recomputed from `base` regardless of its current value, so a second
        pass reproduces the same letter rather than mangling `I/L` back into a lookup.
        """
        df = self._df(["I", "T"], ["V", "S"], ["PEPTLDE", "TEST"], [4, 0])
        once = _label_isobaric_il(df)
        twice = _label_isobaric_il(once)
        assert twice["origin"].to_list() == once["origin"].to_list() == ["L", "T"]
        assert twice["destination"].to_list() == once["destination"].to_list()

    def test_the_landmine_relabelling_early_would_silently_drop_every_IL_row(self) -> None:
        """**Why the relabel must come last.** This is the regression test.

        `localize_shift` does:

            mod_mass = SUBSTITUTION_SHIFTS.get(origin, {}).get(dest)
            if mod_mass is None:
                continue          # <- silently drops the row

        `AA_MONO` has no `I/L` key, so `SUBSTITUTION_SHIFTS` has no `I/L` entry. Had
        the relabel run before that lookup, every I/L substitution would have
        vanished from the results with no error and no warning — a "harmless
        cosmetic change" that quietly deletes data.

        The collapsed letter `I` resolves; the label `I/L` does not. That asymmetry
        is the whole reason for the ordering.
        """
        assert SUBSTITUTION_SHIFTS.get("T", {}).get("I") is not None, \
            "the collapsed letter must resolve — the lookup runs on `I`"
        assert SUBSTITUTION_SHIFTS.get("T", {}).get("I/L") is None, \
            "if this ever resolves, the landmine is disarmed and this test is moot"
        assert "I/L" not in AA_MONO, \
            "AA_MONO must stay free of `I/L`: the label never reaches the mass lookup"
        assert AA_MONO["I"] == AA_MONO["L"] == 113.08406, \
            "Ile and Leu are isobaric — that is why they collapse to one letter"


class TestLocalizeTolerance:
    """D-073: the PyAscore fragment tolerance defaults to Slava's 0.01 Da."""

    def test_default_is_slavas_published_value(self) -> None:
        from src.tarsus.steps.step11_localize import DEFAULT_LOCALIZE_TOL_DA
        assert DEFAULT_LOCALIZE_TOL_DA == 0.01

    def test_both_entry_points_use_the_constant(self) -> None:
        import inspect
        from src.tarsus.steps.step11_localize import (
            DEFAULT_LOCALIZE_TOL_DA, localize, localize_shift,
        )
        for fn in (localize, localize_shift):
            default = inspect.signature(fn).parameters["precursor_tol"].default
            assert default == DEFAULT_LOCALIZE_TOL_DA, fn.__name__

    @pytest.mark.parametrize("bad", [0.0, -0.01])
    def test_nonpositive_tolerance_raises(self, tmp_path: Path, bad: float) -> None:
        from src.tarsus.steps.step11_localize import localize_shift
        with pytest.raises(ValueError, match="must be > 0"):
            localize_shift(pl.DataFrame(), tmp_path / "unused.mgf", bad)
