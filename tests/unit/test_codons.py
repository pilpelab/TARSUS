"""Unit tests for codon resolution — the 61x19 heatmap's foundation."""

from pathlib import Path

from src.tarsus.codons import (
    ALL_AA,
    ALL_CODONS,
    GENCODE,
    UNRESOLVED,
    codon_counts,
    fetch_codon,
    load_cds,
    rna_to_dna,
    translate,
)


class TestGeneticCode:
    def test_sixty_one_sense_codons(self) -> None:
        assert len(ALL_CODONS) == 61
        assert len(set(ALL_CODONS)) == 61
        assert all(GENCODE[c] != "_" for c in ALL_CODONS), "no stop codons"

    def test_stops_excluded(self) -> None:
        for stop in ("TAA", "TAG", "TGA"):
            assert GENCODE[stop] == "_"
            assert stop not in ALL_CODONS

    def test_destination_axis_merges_ile_and_leu(self) -> None:
        """**19, not 20.** The lab's own axis merges I and L — see D-064.

        This heatmap literally cannot be drawn without the isobaric collapse, which is
        independent confirmation that D-064 matches what the analysis has always
        assumed. Step 11 emits `I/L`, so its output drops straight in.
        """
        assert len(ALL_AA) == 19
        assert "I/L" in ALL_AA
        assert "I" not in ALL_AA and "L" not in ALL_AA

    def test_translate(self) -> None:
        assert translate("ATGGGCACCTAA") == "MGT_"

    def test_rna_to_dna(self) -> None:
        # The two mask files disagree on alphabet; this reconciles them.
        assert rna_to_dna("UUU") == "TTT"
        assert rna_to_dna("GGC") == "GGC"


class TestFetchCodon:
    #: MGTS -> ATG GGC ACC TCT
    _CDS = [("ATGGGCACCTCT", "MGTS")]

    def test_resolves_each_offset(self) -> None:
        assert fetch_codon("MGTS", 0, self._CDS) == "ATG"
        assert fetch_codon("MGTS", 1, self._CDS) == "GGC"
        assert fetch_codon("MGTS", 2, self._CDS) == "ACC"

    def test_peptide_not_in_cds(self) -> None:
        assert fetch_codon("WWWW", 0, self._CDS) == UNRESOLVED

    def test_ambiguous_across_proteins_is_not_guessed(self) -> None:
        """Two proteins, same peptide, different codons -> refuse to pick one.

        Silently choosing one would fabricate a codon assignment. Return the sentinel
        so the caller can COUNT and REPORT it (see `codon_counts`).
        """
        cds = [("ATGGGCACCTCT", "MGTS"), ("ATGGGTACCTCT", "MGTS")]  # GGC vs GGT
        assert fetch_codon("MGTS", 1, cds) == UNRESOLVED

    def test_agreeing_duplicates_still_resolve(self) -> None:
        cds = [("ATGGGCACCTCT", "MGTS"), ("ATGGGCACCTCT", "MGTS")]
        assert fetch_codon("MGTS", 1, cds) == "GGC"


class TestCodonCounts:
    _CDS = [("ATGGGCACCTCT", "MGTS")]

    def test_counts_codon_destination_pairs(self) -> None:
        rows = [("MGTS", 1, "A"), ("MGTS", 1, "A"), ("MGTS", 2, "S")]
        counts, unresolved = codon_counts(rows, self._CDS)
        assert counts[("GGC", "A")] == 2
        assert counts[("ACC", "S")] == 1
        assert unresolved == 0

    def test_unresolved_are_counted_not_silently_dropped(self) -> None:
        """A dropped row that nobody reports is the D-057 failure mode."""
        rows = [("MGTS", 1, "A"), ("WWWW", 0, "A")]
        counts, unresolved = codon_counts(rows, self._CDS)
        assert unresolved == 1
        assert sum(counts.values()) == 1


class TestLoadCds:
    def test_reads_records(self, tmp_path: Path) -> None:
        f = tmp_path / "cds.fasta"
        f.write_text(">g1\nATGGGCACC\n>g2\nATGTCTTAA\n")
        cds = load_cds(f)
        assert len(cds) == 2
        assert cds[0] == ("ATGGGCACC", "MGT")

    def test_skips_records_not_divisible_by_three(self, tmp_path: Path) -> None:
        """A partial CDS cannot be codonized — reading it would shift every codon."""
        f = tmp_path / "cds.fasta"
        f.write_text(">good\nATGGGC\n>truncated\nATGGG\n")
        cds = load_cds(f)
        assert len(cds) == 1
        assert cds[0][0] == "ATGGGC"

    def test_multiline_sequences(self, tmp_path: Path) -> None:
        f = tmp_path / "cds.fasta"
        f.write_text(">g1\nATG\nGGC\nACC\n")
        assert load_cds(f)[0] == ("ATGGGCACC", "MGT")


class TestSixtyTwentyMatrix:
    """The 61x19 matrix and its two masks must stay aligned.

    A misaligned mask silently greys out the wrong cells — the figure still renders,
    and it is wrong in a way no exception reports.
    """

    def test_cognate_cells_are_all_masked_and_rows_align(self) -> None:
        import pandas as pd
        from src.tarsus.assets import NECE_MASK_CSV, SIXTY_TWENTY_MASK_CSV
        from src.tarsus.steps.step12_visualize import _load_masks, _multiindex_codon_aa

        mat = pd.DataFrame(0.0, index=ALL_CODONS, columns=ALL_AA)
        mi = _multiindex_codon_aa(mat)
        grey, nece_cells = _load_masks(mi.index, mi.columns)

        assert list(grey.index) == list(mi.index), "mask rows must match the matrix"
        assert list(grey.columns) == list(mi.columns)

        # Every codon's own amino acid (its cognate cell) must be greyed out.
        for codon, aa in mi.index:
            col = "I/L" if aa in ("I", "L") else aa
            assert bool(grey.loc[(codon, aa), col]), f"{codon} cognate cell not masked"

        assert nece_cells, "near-cognate-error cells must be marked"
        assert SIXTY_TWENTY_MASK_CSV.is_file() and NECE_MASK_CSV.is_file()

    def test_GGC_to_A_is_a_near_cognate_cell(self) -> None:
        """The AlaGGC experiment's target cell is reachable in ONE base change.

        GGC (Gly) -> GCC (Ala): a single substitution at position 2. So a zero there is
        a real biological zero, not an unreachable cell.
        """
        import pandas as pd
        from src.tarsus.assets import NECE_MASK_CSV

        nece = pd.read_csv(NECE_MASK_CSV, index_col=0)
        assert bool(nece.loc["GGC", "A"])
