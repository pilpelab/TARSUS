"""Unit tests for Step 3b — in-silico mutagenesis."""

import re
from pathlib import Path

import pytest
import polars as pl
from src.tarsus.steps.step03b_make_peptides import (
    _load_substitution_matrix,
    _single_substitutions,
    check_library_spectrum,
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


class TestIsobaricCollapse:
    """Ile and Leu are isobaric (113.08406 Da) and collapse onto one class, `I`.

    The CSV names the pair inconsistently — one merged `I/L` *origin column*, but
    separate `I` and `L` *destination rows*. All three mean the same residue. See
    D-064.
    """

    def test_L_is_never_an_origin_or_a_destination(self) -> None:
        from src.tarsus.assets import SUBS_EXCLUDE_CSV
        matrix = _load_substitution_matrix(SUBS_EXCLUDE_CSV)
        assert "L" not in matrix
        assert all("L" not in dests for dests in matrix.values())
        assert "I" in matrix

    def test_merged_destination_rows_take_the_exclusion(self, tmp_path: Path) -> None:
        """Where the `I` and `L` rows disagree, **the exclusion wins.**

        Exactly one of the 19 origins disagrees in the real matrix: `A->I` is
        excluded while `A->L` is allowed. That is incoherent — Ala->Ile/Leu is
        +42.04695 Da, *exactly trimethylation*, which is precisely why `A->I` is
        excluded. Taking the exclusion also drops the 41,085 `A->L`
        trimethylation-artifact candidates.
        """
        csv = tmp_path / "subs.csv"
        csv.write_text(",A,T\nI,TRUE,FALSE\nL,FALSE,FALSE\n")
        matrix = _load_substitution_matrix(csv)
        assert matrix["A"]["I"] is True    # excluded by the I row -> exclusion wins
        assert matrix["T"]["I"] is False   # both rows allow it -> allowed

    def test_real_matrix_excludes_A_to_isobaric_trimethylation(self) -> None:
        from src.tarsus.assets import SUBS_EXCLUDE_CSV
        matrix = _load_substitution_matrix(SUBS_EXCLUDE_CSV)
        assert matrix["A"]["I"] is True     # +42.04695 Da == trimethylation
        assert matrix["T"]["S"] is False    # D-061 — must stay allowed
        assert matrix["F"]["M"] is True     # D-062 — oxidised-Met artifact


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

    def test_origin_I_matches_a_LEU_residue(self) -> None:
        """**The bug this fixes.** Ile and Leu are isobaric — one origin class.

        The reference generates *no* substitution from any I or L position: its
        `rename(index={'I/L': 'I'})` renames the row axis while `I/L` is a column,
        so it silently does nothing and `'I/L' not in peptide` is always true. We
        matched Ile only, which is half-right and internally incoherent — the same
        mass, yet Leu positions were never searched.
        """
        assert _single_substitutions("ALC", "I", "V") == [("AVC", 1)]
        assert _single_substitutions("AIC", "I", "V") == [("AVC", 1)]

    def test_origin_I_matches_ILE_and_LEU_in_the_same_peptide(self) -> None:
        assert _single_substitutions("ILK", "I", "V") == [("VLK", 0), ("IVK", 1)]

    def test_only_the_substituted_position_changes(self) -> None:
        """Other Leu residues keep their real letter — the candidate stays accurate."""
        assert _single_substitutions("LTL", "T", "S") == [("LSL", 1)]


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


class TestLibrarySpectrumGuard:
    """The guard that would have caught BOTH catastrophes on day one.

    Step 3b decides the ENTIRE search space. A substitution absent from the
    library can never be found by any downstream step, and **nothing anywhere
    reports its absence**. It has silently invalidated every result twice:

      D-057  library built 76 min before its own I/L fix -> 0 of 7.37M `->Ile`
             variants. Two weeks of results computed against a search space that
             could not contain the answer.
      D-061  exclusion matrix transposed -> F->M (an oxidised-Met artifact,
             excluded by the reference) got 15,004 candidates and became our
             single largest "finding"; T->S (the reference's DOMINANT
             substitution, 422 of its 697 localized) got ZERO.
    """

    def test_raises_when_an_excluded_substitution_is_present(self, tmp_path: Path) -> None:
        """D-061's signature: a library containing F->M."""
        fa = tmp_path / "cand.fa"
        fa.write_text(">PEPTIDEF_F7M\nPEPTIDEM\n>PEPTIDET_T7S\nPEPTIDES\n")
        matrix = {"F": {"M": True}, "T": {"S": False}}   # F->M excluded, T->S allowed
        with pytest.raises(RuntimeError, match="forbids"):
            check_library_spectrum(fa, matrix, required={("T", "S")})

    def test_raises_when_a_required_substitution_is_missing(self, tmp_path: Path) -> None:
        """D-057/D-061's signature: the dominant substitution absent entirely."""
        fa = tmp_path / "cand.fa"
        fa.write_text(">PEPTIDEV_V7P\nPEPTIDEP\n")          # no T->S at all
        matrix = {"F": {"M": True}, "T": {"S": False}}
        with pytest.raises(RuntimeError, match="T->S"):
            check_library_spectrum(fa, matrix, required={("T", "S")})

    def test_passes_on_a_healthy_library(self, tmp_path: Path) -> None:
        fa = tmp_path / "cand.fa"
        fa.write_text(">PEPTIDET_T7S\nPEPTIDES\n>PEPTIDEV_V7P\nPEPTIDEP\n")
        matrix = {"F": {"M": True}, "T": {"S": False}, "V": {"P": False}}
        spectrum = check_library_spectrum(fa, matrix, required={("T", "S")})
        assert spectrum[("T", "S")] == 1

    def test_raises_on_a_stray_L(self, tmp_path: Path) -> None:
        """`L` must never reach a header — and the matrix check CANNOT catch it.

        `matrix["L"]` does not exist after the collapse, so the forbidden-lookup
        `matrix.get("L", {}).get(d, False)` returns False and a stray `L` would
        sail straight through. It needs its own check. This test fails if that
        check is ever removed.
        """
        fa = tmp_path / "cand.fa"
        fa.write_text(">PEPTIDET_T7S\nPEPTIDES\n>PEPTIDEV_V7L\nPEPTIDEL\n")
        matrix = {"T": {"S": False}, "V": {"I": False}}   # note: no "L" key at all
        with pytest.raises(RuntimeError, match="isobaric"):
            check_library_spectrum(fa, matrix, required={("T", "S")})

    def test_library_built_from_the_real_matrix_satisfies_every_contract(
        self, tmp_path: Path,
    ) -> None:
        """Build a library with the REAL bundled matrix and assert the full contract.

        This exercises `make_peptide_candidates` itself rather than a run artifact
        on disk: a test that reads `output/trial/...` passes or fails on the state
        of the last run, not on the state of the code. (On-disk staleness is what
        `provenance.stale_artifacts()` is for — D-063.)
        """
        peptides = tmp_path / "peptide.tsv"
        peptides.write_text(
            "Peptide\tIntensity\n"
            "PEPTIDEK\t100\n"      # Ile  -> the `I` class
            "PEPTLDEK\t100\n"      # Leu  -> the SAME class (was never searched)
            "AAATTTK\t100\n"       # Ala + Thr -> A->I (excluded) and T->S (required)
        )
        fa = tmp_path / "cand.fa"
        make_peptide_candidates(peptides, output_fasta=fa)   # guard runs inside

        headers = [ln[1:] for ln in fa.read_text().splitlines() if ln.startswith(">")]
        subs = {(m.group(1), m.group(3))
                for h in headers
                if (m := re.search(r"_([A-Z])(\d+)([A-Z])$", h))}

        assert not any("L" in pair for pair in subs), "L must not survive the collapse"
        assert ("A", "I") not in subs, "A->I/L is +42.04695 Da — exactly trimethylation"
        assert ("F", "M") not in subs, "D-062 — oxidised-Met artifact"
        assert ("T", "S") in subs, "D-061 — the reference's dominant substitution"
        assert ("I", "V") in subs, "substitutions FROM the I/L class must be generated"

        # The Leu peptide must contribute — this is the whole point of the collapse.
        assert any(h.startswith("PEPTLDEK_I") for h in headers), \
            "a Leu position generated no candidate: the isobaric collapse regressed"
