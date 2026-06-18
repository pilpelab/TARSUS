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


class TestNormalizeIL:
    def test_no_il(self) -> None:
        assert _normalize_il("PEPTADE") == "PEPTADE"

    def test_with_il(self) -> None:
        assert _normalize_il("PIL") == "PJJ"

    def test_only_i(self) -> None:
        assert _normalize_il("PEPTIDE") == "PEPTJDE"


class TestComputeExpectedIons:
    def test_position_early(self) -> None:
        result = _compute_expected_ions("ABCD", 0)
        assert "b1" in result
        assert "b2" in result
        assert "b3" in result
        assert "b4" in result
        assert result == ["b1", "b2", "b3", "b4"]

    def test_position_one(self) -> None:
        result = _compute_expected_ions("ABCD", 1)
        assert "b2" in result
        assert "b3" in result
        assert "b4" in result
        assert "y4" not in result

    def test_position_middle(self) -> None:
        result = _compute_expected_ions("ABCDEF", 2)
        assert "b3" in result
        assert "b4" in result
        assert "b5" in result
        assert "b6" in result
        assert "y6" in result
        assert "y3" not in result


class TestSpectrumToTitle:
    def test_basic(self) -> None:
        assert _spectrum_to_title("file_sub.100.100.2") == "file:100:2"

    def test_leading_zeros(self) -> None:
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
            "mistranslated_pos": pl.Int64,
        })
        result = filter_single_sav_psms(empty)
        assert len(result) == 0


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
        assert "mistranslated_pos" in result.columns
        assert result["origin"][0] == "A"
        assert result["dest"][0] == "G"
        assert result["mistranslated_pos"][0] == 0
