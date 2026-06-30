"""Unit tests for Step 4 — PSM extraction for PepQuery."""

from pathlib import Path
import csv
from src.tarsus.steps.step04_extract_psm import extract_psm


def _make_psm(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("Spectrum\tPeptide\tCharge\tIntensity\n")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


class TestExtractPsm:
    def test_simple_row(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "sample_sub.100.100.2", "Peptide": "PEPTIDE", "Charge": "2", "Intensity": "1000"},
        ])
        out = tmp_path / "psm_input4pepquery.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert lines[0] == "PEPTIDE"

    def test_multiple_rows(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "500"},
            {"Spectrum": "b_sub.50.50.3", "Peptide": "PEP2", "Charge": "3", "Intensity": "200"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2
        assert "PEP1" in lines
        assert "PEP2" in lines

    def test_filters_zero_intensity(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "0"},
            {"Spectrum": "b_sub.2.2.2", "Peptide": "PEP2", "Charge": "2", "Intensity": "100"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 1
        assert "PEP1" not in lines[0]

    def test_filters_negative_intensity(self, tmp_path: Path) -> None:
        psm = tmp_path / "psm.tsv"
        _make_psm(psm, [
            {"Spectrum": "a_sub.1.1.2", "Peptide": "PEP1", "Charge": "2", "Intensity": "-5"},
        ])
        out = tmp_path / "out.tsv"
        extract_psm(psm, out)
        assert out.read_text().strip() == ""

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
