"""Unit tests for Step 3b — in-silico mutagenesis."""

import re
from pathlib import Path
import polars as pl
from src.tarsus.steps.step03b_make_peptides import (
    _load_substitution_matrix,
    _single_substitutions,
    make_peptide_candidates,
)


class TestLoadSubstitutionMatrix:
    """The CSV is COLUMN=origin, ROW=destination (reference README + make_peptides.py).

    These tests previously encoded the TRANSPOSED reading and so locked the bug in
    (D-061). Given `,A,D` / `E,FALSE,TRUE`: column A and D are ORIGINS, row E is a
    DESTINATION. So the cell (row E, col A) is A->E.
    """

    def test_column_is_origin_and_row_is_destination(self, tmp_path: Path) -> None:
        csv = tmp_path / "subs.csv"
        csv.write_text(",A,D\nE,FALSE,TRUE\nK,TRUE,FALSE\n")
        matrix = _load_substitution_matrix(csv)
        assert matrix["A"]["E"] is False   # (row E, col A) -> A->E
        assert matrix["D"]["E"] is True    # (row E, col D) -> D->E
        assert matrix["A"]["K"] is True    # (row K, col A) -> A->K
        assert matrix["D"]["K"] is False   # (row K, col D) -> D->K

    def test_normalizes_i_slash_l_in_the_origin_column(self, tmp_path: Path) -> None:
        csv = tmp_path / "subs.csv"
        csv.write_text(",I/L,D\nE,FALSE,TRUE\n")
        matrix = _load_substitution_matrix(csv)
        assert "I" in matrix and "I/L" not in matrix

    def test_normalizes_i_slash_l_in_the_destination_row(self, tmp_path: Path) -> None:
        csv = tmp_path / "subs.csv"
        csv.write_text(",A,D\nI/L,FALSE,TRUE\n")
        matrix = _load_substitution_matrix(csv)
        assert "I" in matrix["A"] and "I/L" not in matrix["A"]


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

    def test_i_slash_l_normalized_in_sequence(self) -> None:
        result = _single_substitutions("AIC", "I", "I/L")
        assert result == [("AIC", 1)]  # I/L → I, not "I/L" in sequence


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
        # COLUMN=origin, ROW=destination: ",A,D / E,FALSE,FALSE" allows A->E and D->E.
        # PEPTIDE has D at index 5, so D->E must be generated.
        assert ">PEPTIDE_D5E" in content
        assert "PEPTIEE" in content          # PEPTIDE with D5 -> E
        # E->A is NOT allowed here (that would be the transposed reading, D-061)
        assert "PAPTIDE" not in content

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


class TestExclusionMatrixOrientation:
    """Regression (D-061): the matrix was TRANSPOSED — catastrophic.

    The reference README states plainly:

        "Columns are origin amino acids, rows are destination amino acids.
         True value excludes origin->destination mutation."

    and `make_peptides.py` does `pd.read_csv(...).to_dict()` — which yields
    `{COLUMN: {ROW: value}}` — then indexes `subs_allowed[origin][dest]`.
    So: **origin = column, destination = row.**

    We built `matrix[ROW][COLUMN]`, i.e. `matrix[dest][origin]`, and then used it
    as `matrix[origin][dest]`. Every one of the 20 asymmetric pairs was inverted.

    Consequences on real data:
      - F->M: reference excludes it; we generated **15,004 candidates**, and it
        became our single largest "result" (38 of 248 localized = 15%).
      - T->S: reference ALLOWS it, and it is the reference's *dominant*
        substitution (**422 of its 697 localized = 61%**). We generated **ZERO**.
        We were structurally incapable of finding it.
    """

    def test_origin_is_the_column_and_destination_is_the_row(self) -> None:
        from src.tarsus.assets import SUBS_EXCLUDE_CSV
        m = _load_substitution_matrix(SUBS_EXCLUDE_CSV)
        # Ground truth read straight off the reference's own convention.
        assert m["F"]["M"] is True, "reference EXCLUDES F->M (it is an oxidised-Met artifact)"
        assert m["M"]["F"] is False, "reference ALLOWS M->F"
        assert m["S"]["T"] is True, "reference EXCLUDES S->T"
        assert m["T"]["S"] is False, "reference ALLOWS T->S — its most common substitution"

    def test_generates_T_to_S_and_not_F_to_M(self, tmp_path: Path) -> None:
        """End-to-end on the real matrix: the two substitutions that mattered."""
        from src.tarsus.assets import SUBS_EXCLUDE_CSV
        peptides = tmp_path / "peptide.tsv"
        peptides.write_text("Peptide\tIntensity\nTFTFSK\t1000\n")
        out = tmp_path / "cand.fa"
        make_peptide_candidates(peptides, SUBS_EXCLUDE_CSV, out)
        headers = [h for h in out.read_text().splitlines() if h.startswith(">")]

        t_to_s = [h for h in headers if re.search(r"_T\d+S$", h)]
        f_to_m = [h for h in headers if re.search(r"_F\d+M$", h)]
        assert t_to_s, "T->S must be generated — it is the reference's dominant substitution"
        assert not f_to_m, "F->M must NOT be generated — the reference excludes it"
