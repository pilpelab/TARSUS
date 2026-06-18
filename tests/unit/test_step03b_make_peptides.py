"""Unit tests for Step 3b — in-silico mutagenesis."""

from pathlib import Path
import polars as pl
from src.tarsus.steps.step03b_make_peptides import (
    _load_substitution_matrix,
    _single_substitutions,
    make_peptide_candidates,
)


class TestLoadSubstitutionMatrix:
    def test_loads_basic_csv(self, tmp_path: Path) -> None:
        csv = tmp_path / "subs.csv"
        csv.write_text(",A,D\nE,FALSE,TRUE\nK,TRUE,FALSE\n")
        matrix = _load_substitution_matrix(csv)
        assert matrix["E"]["A"] is False
        assert matrix["E"]["D"] is True
        assert matrix["K"]["A"] is True
        assert matrix["K"]["D"] is False

    def test_normalizes_i_slash_l(self, tmp_path: Path) -> None:
        csv = tmp_path / "subs.csv"
        csv.write_text(",A,D\nI/L,FALSE,TRUE\n")
        matrix = _load_substitution_matrix(csv)
        assert "I" in matrix
        assert "I/L" not in matrix


class TestSingleSubstitutions:
    def test_single_origin_appears_once(self) -> None:
        result = _single_substitutions("ABC", "B", "X")
        assert result == [("AXC", 1)]

    def test_multiple_occurrences(self) -> None:
        result = _single_substitutions("ABCB", "B", "X")
        assert result == [("AXCB", 1), ("ABCX", 3)]

    def test_origin_not_in_peptide(self) -> None:
        result = _single_substitutions("ABC", "X", "Y")
        assert result == []

    def test_same_origin_and_dest(self) -> None:
        result = _single_substitutions("ABC", "B", "B")
        assert result == [("ABC", 1)]


class TestMakePeptideCandidates:
    def test_generates_fasta(self, tmp_path: Path) -> None:
        matrix = tmp_path / "subs.csv"
        matrix.write_text(",A,D\nE,FALSE,FALSE\n")

        peptide_tsv = tmp_path / "peptide.tsv"
        pl.DataFrame({"Peptide": ["PEPTIDE"], "Intensity": [100]}).write_csv(
            peptide_tsv, separator="\t",
        )

        output = tmp_path / "pep_candidates.fa"
        make_peptide_candidates(peptide_tsv, matrix, output)

        content = output.read_text()
        # PEPTIDE has E at pos 1, and E→A is not excluded → should generate
        assert ">PEPTIDE_E1A" in content
        assert "PAPTIDE" in content

    def test_skips_excluded_substitutions(self, tmp_path: Path) -> None:
        matrix = tmp_path / "subs.csv"
        matrix.write_text(",A,D\nE,TRUE,FALSE\n")

        peptide_tsv = tmp_path / "peptide.tsv"
        pl.DataFrame({"Peptide": ["PEPTIDE"], "Intensity": [100]}).write_csv(
            peptide_tsv, separator="\t",
        )

        output = tmp_path / "pep_candidates.fa"
        make_peptide_candidates(peptide_tsv, matrix, output)

        content = output.read_text()
        # E→A is TRUE (excluded) → should NOT generate
        assert ">PEPTIDE_E1A" not in content

    def test_skips_existing_variants(self, tmp_path: Path) -> None:
        matrix = tmp_path / "subs.csv"
        matrix.write_text(",A,D\nE,FALSE,FALSE\n")

        peptide_tsv = tmp_path / "peptide.tsv"
        # Both PEPTIDE and PAPTIDE (PEPTIDE with E→A) are observed
        pl.DataFrame(
            {"Peptide": ["PEPTIDE", "PAPTIDE"], "Intensity": [100, 50]},
        ).write_csv(peptide_tsv, separator="\t")

        output = tmp_path / "pep_candidates.fa"
        make_peptide_candidates(peptide_tsv, matrix, output)

        content = output.read_text()
        # PAPTIDE is already observed → should NOT appear as candidate
        assert ">PEPTIDE_E1A" not in content

    def test_empty_peptides(self, tmp_path: Path) -> None:
        matrix = tmp_path / "subs.csv"
        matrix.write_text(",A,D\nE,FALSE,FALSE\n")

        peptide_tsv = tmp_path / "peptide.tsv"
        pl.DataFrame(
            {"Peptide": pl.Series([], dtype=pl.String), "Intensity": pl.Series([], dtype=pl.Int64)},
        ).write_csv(peptide_tsv, separator="\t")

        output = tmp_path / "pep_candidates.fa"
        make_peptide_candidates(peptide_tsv, matrix, output)

        assert output.read_text() == ""
