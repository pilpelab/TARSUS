"""Unit tests for Step 4 — targeted PSM extraction for PepQuery."""

from pathlib import Path
import csv
from src.tarsus.steps.step04_extract_psm import extract_psm, _spectrum_to_title


def _make_psm(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("Spectrum\tPeptide\tCharge\tIntensity\n")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


class TestSpectrumToTitle:
    def test_strips_sub_suffix(self) -> None:
        assert _spectrum_to_title("file_sub.100.100.2", "2") == "file:100:2"

    def test_strips_leading_zeros(self) -> None:
        assert _spectrum_to_title("file_sub.00100.00100.2", "2") == "file:100:2"

    def test_without_sub_suffix(self) -> None:
        assert _spectrum_to_title("file.50.50.3", "3") == "file:50:3"

    def test_charge_comes_from_charge_column(self) -> None:
        # The reference takes charge from the Charge column, not the Spectrum field.
        assert _spectrum_to_title("file_sub.7.7.2", "3") == "file:7:3"

    def test_filename_with_dots_and_sub(self) -> None:
        assert _spectrum_to_title("HouYM-25-G140_sub.02863.02863.2", "2") == (
            "HouYM-25-G140:2863:2"
        )


class TestExtractPsm:
    def test_simple_row_is_two_columns(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "sample_sub.100.100.2", "Peptide": "PEPTIDE",
             "Charge": "2", "Intensity": "1000"},
        ])
        out = tmp_path / "psm_input4pepquery.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert lines[0] == "PEPTIDE\tsample:100:2"
        assert len(lines[0].split("\t")) == 2

    def test_multiple_rows(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "500"},
            {"Spectrum": "b_sub.50.50.3", "Peptide": "PEP2", "Charge": "3", "Intensity": "200"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert lines == ["PEP1\ta:1:2", "PEP2\tb:50:3"]

    def test_does_not_deduplicate(self, tmp_path: Path) -> None:
        """Reference writes one row per positive-intensity PSM, duplicates included."""
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP", "Charge": "2", "Intensity": "500"},
            {"Spectrum": "a_sub.2.2.2", "Peptide": "PEP", "Charge": "2", "Intensity": "600"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert lines == ["PEP\ta:1:2", "PEP\ta:2:2"]

    def test_filters_zero_intensity(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "0"},
            {"Spectrum": "b_sub.2.2.2", "Peptide": "PEP2", "Charge": "2", "Intensity": "100"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert lines == ["PEP2\tb:2:2"]

    def test_filters_negative_intensity(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "-5"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        assert out.read_text().strip() == ""

    def test_empty_psm(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        assert out.read_text().strip() == ""

    def test_missing_intensity_column(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        psm.write_text("Spectrum\tPeptide\tCharge\nfile.1.1.2\tPEP\t2\n")
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        assert out.read_text().strip() == ""

    def test_malformed_spectrum_is_skipped(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "garbage", "Peptide": "PEP1", "Charge": "2", "Intensity": "500"},
            {"Spectrum": "b_sub.2.2.2", "Peptide": "PEP2", "Charge": "2", "Intensity": "100"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        assert out.read_text().strip().split("\n") == ["PEP2\tb:2:2"]
