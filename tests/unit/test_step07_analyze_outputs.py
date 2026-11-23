"""Unit tests for Step 7 — analyze_outputs pure functions."""

from pathlib import Path
import polars as pl
from src.tarsus.steps.step07_analyze_outputs import (
    extract_pdv_ions,
    _parse_modification,
    _normalize_il,
    filter_single_sav_psms,
    _compute_expected_ions,
    _spectrum_to_title,
    _extract_base_name,
    _drop_decoy_rows,
    load_ptm_details,
)


class TestExtractPdvIons:
    def test_basic_ions(self) -> None:
        assert extract_pdv_ions("[b3, y4+++, b5]") == ["b3", "b5", "y4"]

    def test_no_ions(self) -> None:
        assert extract_pdv_ions("[]") == []

    def test_non_string(self) -> None:
        assert extract_pdv_ions(123) == -1


class TestParseModification:
    def test_standard(self) -> None:
        result = _parse_modification("Ala->Gly@42[")
        assert result is not None
        assert result["origin"] == "A"
        assert result["dest"] == "G"
        assert result["position"] == 42

    def test_unmapped_aa(self) -> None:
        result = _parse_modification("Sec->Ala@5[")
        assert result is not None
        assert result["origin"] == "Sec"

    def test_no_match(self) -> None:
        assert _parse_modification("nothing") is None

    def test_substitution_preceded_by_another_modification(self) -> None:
        """The substitution is rarely first — PepQuery lists fixed mods before it.

        `re.match` anchors at position 0 and returned None for every one of these,
        silently dropping essentially every Cys- and Met-containing PSM (D-070).
        Parsing must be unanchored, as the reference's `str.extract` is.
        """
        result = _parse_modification(
            "Carbamidomethylation of C@5[57.0215];Gly->Ala of G@3[14.0157]",
        )
        assert result is not None
        assert result["origin"] == "G"
        assert result["dest"] == "A"
        assert result["position"] == 3

    def test_oxidation_prefix_with_xle_destination(self) -> None:
        """Same shape, Met-oxidation prefix, and an Xle destination (I/L class)."""
        result = _parse_modification(
            "Carbamidomethylation of C@11[57.0215];Asp->Xle of D@7[-1.9429]",
        )
        assert result is not None
        assert result["origin"] == "D"
        assert result["dest"] == "I"
        assert result["position"] == 7


class TestNormalizeIL:
    def test_no_il(self) -> None:
        assert _normalize_il("PEPTADE") == "PEPTADE"

    def test_with_il(self) -> None:
        assert _normalize_il("PIL") == "PJJ"

    def test_only_i(self) -> None:
        assert _normalize_il("PEPTIDE") == "PEPTJDE"


class TestComputeExpectedIons:
    """Every b and y ion that contains the substituted residue, and no other.

    ``position`` is 0-based (Step 3b writes ``enumerate`` indices into the header).
    b_k holds residues 0..k-1, so it contains the residue iff k >= position + 1.
    y_k holds the last k residues, so it contains it iff k >= n - position. Until
    D-078 the y range started at n - position + 2, so the two shortest containing
    y ions, often the clearest peaks, were never counted (Liz, 2026-11-10).
    """

    def test_position_zero(self) -> None:
        # Only y4, the whole peptide, contains residue 0.
        assert _compute_expected_ions("ABCD", 0) == ["b1", "b2", "b3", "b4", "y4"]

    def test_position_one(self) -> None:
        # y3 = BCD and y4 = ABCD contain residue 1 (B).
        assert _compute_expected_ions("ABCD", 1) == ["b2", "b3", "b4", "y3", "y4"]

    def test_position_middle(self) -> None:
        # Residue 2 (C): y4 = CDEF is the shortest y ion containing it; y3 = DEF is not.
        assert _compute_expected_ions("ABCDEF", 2) == [
            "b3", "b4", "b5", "b6", "y4", "y5", "y6",
        ]

    def test_shortest_containing_y_ions_counted(self) -> None:
        """Liz's example: in FPMMXTFK, y4 = XTFK and y5 = MXTFK carry the substitution."""
        ions = _compute_expected_ions("FPMMXTFK", 4)
        assert [i for i in ions if i.startswith("y")] == ["y4", "y5", "y6", "y7", "y8"]

    def test_near_n_terminal_substitution_keeps_y_ions(self) -> None:
        """Liz's example: WXPELNEAIPNDER had no y ion at all under the old range."""
        ions = _compute_expected_ions("WXPELNEAIPNDER", 1)
        assert [i for i in ions if i.startswith("y")] == ["y13", "y14"]


class TestSpectrumToTitle:
    def test_basic_strips_sub_suffix(self) -> None:
        # PepQuery indexes the original mzML, whose titles carry no `_sub` (D-047).
        assert _spectrum_to_title("file_sub.100.100.2") == "file:100:2"

    def test_leading_zeros_strips_sub_suffix(self) -> None:
        assert _spectrum_to_title("file_sub.00100.00100.2") == "file:100:2"

    def test_no_sub_suffix(self) -> None:
        assert _spectrum_to_title("file.50.50.3") == "file:50:3"


class TestExtractBaseName:
    def test_standard(self) -> None:
        assert _extract_base_name("sp|P12345|GENE_HUMAN") == "sp|P12345|GENE"

    def test_basic(self) -> None:
        assert _extract_base_name("ENSP01234_GENE") == "ENSP01234"


class TestFilterSingleSavPsms:
    def _make_ptm(self) -> pl.DataFrame:
        data = {
            "peptide": ["PEPTIDE"],
            "modification": [""],
            "n": [1],
            "spectrum_title": ["spec1"],
            "charge": [2],
            "exp_mass": [1000.0],
            "tol_ppm": [5.0],
            "tol_da": [0.01],
            "isotope_error": [0.0],
            "pep_mass": [1000.0],
            "mz": [500.0],
            "score": [0.9],
            "n_db": [1],
            "total_db": [1000],
            "n_random": [0],
            "total_random": [500],
            "pvalue": [0.001],
            "rank": [1],
            "ptm_spectrum_title": ["extra_spec"],
            "ptm_peptide": ["PEPTIDE"],
            "ptm_charge": [2],
            "ptm_exp_mass": [1000.0],
            "ptm_pep_mass": [1000.0],
            "ptm_tol_ppm": [5.0],
            "ptm_tol_da": [0.01],
            "ptm_isotope_error": [0.0],
            "ptm_modification": ["Ala->Gly@1["],
            "ptm_score": [0.95],
        }
        return pl.DataFrame(data)

    def test_empty_input(self) -> None:
        empty = pl.DataFrame(schema={
            "peptide": pl.String,
            "modification": pl.String,
            "n": pl.Int64,
            "spectrum_title": pl.String,
            "charge": pl.Int64,
            "exp_mass": pl.Float64,
            "tol_ppm": pl.Float64,
            "tol_da": pl.Float64,
            "isotope_error": pl.Float64,
            "pep_mass": pl.Float64,
            "mz": pl.Float64,
            "score": pl.Float64,
            "n_db": pl.Int64,
            "total_db": pl.Int64,
            "n_random": pl.Int64,
            "total_random": pl.Int64,
            "pvalue": pl.Float64,
            "rank": pl.Int64,
            "ptm_spectrum_title": pl.String,
            "ptm_peptide": pl.String,
            "ptm_charge": pl.Int64,
            "ptm_exp_mass": pl.Float64,
            "ptm_pep_mass": pl.Float64,
            "ptm_tol_ppm": pl.Float64,
            "ptm_tol_da": pl.Float64,
            "ptm_isotope_error": pl.Float64,
            "ptm_modification": pl.String,
            "ptm_score": pl.Float64,
            "origin": pl.String,
            "dest": pl.String,
            "mistranslatedPos": pl.Int64,
        })
        result = filter_single_sav_psms(empty)
        assert len(result) == 0


class TestDropDecoyRows:
    """`_drop_decoy_rows` strips reverse-decoy-anchored rows (rev_ prefix)."""

    def test_drops_decoy_in_protein_right(self) -> None:
        df = pl.DataFrame({
            "Protein": ["PEPK_T6S", "AAAK_G3S", "CCCK_M1T"],
            "Protein_right": ["sp|P1|A_ECOLI", "rev_sp|P2|B_ECOLI", "sp|P3|C_ECOLI"],
            "dpbp": [0.1, 0.2, 0.3],
        })
        out = _drop_decoy_rows(df)
        assert out.height == 2
        assert "rev_sp|P2|B_ECOLI" not in out["Protein_right"].to_list()

    def test_drops_decoy_in_protein(self) -> None:
        df = pl.DataFrame({
            "Protein": ["rev_PEPK_T6S", "AAAK_G3S"],
            "Protein_right": ["sp|P1|A_ECOLI", "sp|P2|B_ECOLI"],
        })
        out = _drop_decoy_rows(df)
        assert out.height == 1
        assert out["Protein"].to_list() == ["AAAK_G3S"]

    def test_keeps_all_when_no_decoys(self) -> None:
        df = pl.DataFrame({
            "Protein": ["AAAK_G3S", "BBBK_S2N"],
            "Protein_right": ["sp|P1|A_ECOLI", "sp|P2|B_ECOLI"],
        })
        assert _drop_decoy_rows(df).height == 2

    def test_no_protein_columns_returns_unchanged(self) -> None:
        df = pl.DataFrame({"dpbp": [0.1, 0.2]})
        assert _drop_decoy_rows(df).height == 2


class TestLoadPtmDetails:
    def test_loads_simple_file(self, tmp_path: Path) -> None:
        ptm_file = tmp_path / "ptmall.txt"
        ptm_file.write_text(
            "PEPTIDE\t-\t1\tspec1\t2\t1000.0\t5.0\t0.01\t0.0\t"
            "1000.0\t500.0\t0.9\t1\t1000\t0\t500\t0.001\t1\t"
            "extra_spec\tPEPTIDE\t2\t1000.0\t1000.0\t5.0\t0.01\t0.0\t"
            "Ala->Gly@1[\t0.95\n"
        )
        result = load_ptm_details(ptm_file)
        assert len(result) > 0
        assert "origin" in result.columns
        assert "dest" in result.columns
        assert "mistranslatedPos" in result.columns
        assert result["origin"][0] == "A"
        assert result["dest"][0] == "G"
        assert result["mistranslatedPos"][0] == 0
