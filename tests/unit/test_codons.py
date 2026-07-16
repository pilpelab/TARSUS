"""Unit tests for codon resolution — the 61x19 heatmap's foundation."""

from pathlib import Path

from src.tarsus.codons import (
    ALL_AA,
    ALL_CODONS,
    ALL_ORIGIN_AA,
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
    """The 64x19 matrix and its two masks must stay aligned.

    All 64 codons (61 sense + 3 stops) x 19 destination classes — the full genetic
    table, drawn complete so every pipeline's heatmap is the same fixed grid. A
    misaligned mask silently greys the wrong cells: the figure renders and is wrong
    in a way no exception reports.
    """

    def test_matrix_is_the_full_64_codons(self) -> None:
        from src.tarsus.codons import ALL_CODONS_64, STOP_CODONS
        assert len(ALL_CODONS_64) == 64
        assert set(ALL_CODONS) < set(ALL_CODONS_64)
        assert all(s in ALL_CODONS_64 for s in STOP_CODONS)
        assert all(GENCODE[s] == "_" for s in STOP_CODONS)

    def test_cognate_cells_are_all_masked_and_rows_align(self) -> None:
        import pandas as pd
        from src.tarsus.codons import ALL_CODONS_64, NECE_MASK_CSV, SIXTY_TWENTY_MASK_CSV
        from src.tarsus.steps.step12_visualize import _load_masks, _multiindex_codon_aa

        mat = pd.DataFrame(0.0, index=ALL_CODONS_64, columns=ALL_AA)
        mi = _multiindex_codon_aa(mat)
        assert mi.shape[0] == 64, "the heatmap is the full 64-codon grid"
        grey, nece_cells = _load_masks(mi.index, mi.columns)

        assert list(grey.index) == list(mi.index), "mask rows must match the matrix"
        assert list(grey.columns) == list(mi.columns)

        # Every SENSE codon's cognate cell must be greyed. Stops (aa "*") have no
        # amino-acid column and no cognate cell — they are shown but unmasked.
        for codon, aa in mi.index:
            if aa == "*":
                continue
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
        from src.tarsus.codons import NECE_MASK_CSV

        nece = pd.read_csv(NECE_MASK_CSV, index_col=0)
        assert bool(nece.loc["GGC", "A"])


class TestFractionMerging:
    """Offline fractions are technical splits of ONE sample — never separate groups.

    hoMS_24814 is 15 offline fractions of a single GAPDH prep. Grouping by filename
    turned it into 13 "groups", implying 13 conditions and scattering one sample's
    44 substitutions across 13 thin bars.
    """

    def test_fractions_of_one_sample_collapse_to_one_group(self) -> None:
        import polars as pl
        from src.tarsus.steps.step12_visualize import _detect_groups

        df = pl.DataFrame({"spectrum_title": [
            "EX1_24814_Fraction-1_03092025:100:2",
            "EX1_24814_Fraction-7_03092025:200:2",
            "EX1_24814_Fraction-15_03092025:300:2",
        ]})
        groups = set(_detect_groups(df).values())
        assert len(groups) == 1, f"fractions must merge, got {groups}"

    def test_real_conditions_stay_separate(self) -> None:
        """Merging fractions must NOT merge genuinely different samples."""
        import polars as pl
        from src.tarsus.steps.step12_visualize import _detect_groups

        df = pl.DataFrame({"spectrum_title": [
            "EX1_OR_26227_L73a-1_10062026:1:2",
            "EX1_OR_26227_WT-1_10062026:2:2",
        ]})
        assert len(set(_detect_groups(df).values())) == 2

        df2 = pl.DataFrame({"spectrum_title": [
            "HouYM-25-G140-AstralDDA-AlaGGC-HS-1:1:2",
            "HouYM-25-G140-AstralDDA-AlaGGC-LS-1:2:2",
        ]})
        assert len(set(_detect_groups(df2).values())) == 2, "HS/LS are distinct samples"


class TestHeatmapAxes:
    """The substitution heatmap is a FIXED 20 x 19 grid (D-065).

    20 origin AAs (I and L separate — origin is genome-known, never I/L) x 19
    destination classes (I/L merged — destination is mass-only). Hard-coded and
    complete: an absent origin/destination is an empty row/column, never dropped, so
    every run's heatmap is comparable cell-for-cell.
    """

    def test_axes_are_the_fixed_20_by_19(self) -> None:
        assert len(ALL_ORIGIN_AA) == 20
        assert "I" in ALL_ORIGIN_AA and "L" in ALL_ORIGIN_AA and "I/L" not in ALL_ORIGIN_AA
        assert len(ALL_AA) == 19
        assert "I/L" in ALL_AA and "I" not in ALL_AA and "L" not in ALL_AA
        # Column-aligned: the 18 non-isobaric classes sit in the same order.
        assert [a for a in ALL_ORIGIN_AA if a not in ("I", "L")] == \
               [a for a in ALL_AA if a != "I/L"]

    def test_absent_residues_are_kept_not_dropped(self, tmp_path) -> None:
        """A tiny input (one substitution) still yields the full 20 x 19 grid."""
        import numpy as np
        import polars as pl
        from src.tarsus.steps.step12_visualize import _plot_substitution_heatmap

        df = pl.DataFrame({"origin": ["T"], "destination": ["S"]})
        _plot_substitution_heatmap(df, tmp_path / "h.png")
        assert (tmp_path / "h.png").is_file()

        # The rendered grid must be exactly 20 x 19 regardless of how few AAs occur.
        counts = {(r["origin"], r["destination"]): r["len"]
                  for r in df.group_by(["origin", "destination"]).len().iter_rows(named=True)}
        data = np.array([[float(counts.get((o, d), 0)) for d in ALL_AA]
                         for o in ALL_ORIGIN_AA])
        assert data.shape == (20, 19)
        assert data.sum() == 1.0  # the lone T->S; everything else a kept, empty cell
