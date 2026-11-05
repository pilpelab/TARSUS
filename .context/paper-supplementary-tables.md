# Paper supplementary tables: contents and gotchas

How to get the 18 Supplementary Tables of Tretyachenko et al. (Nature 2026) as TSV, what each one is, and the traps found while profiling them. Claims and definitions: `paper-digest.md`.

## Get the data

```bash
uv run python scripts/fetch_paper_supplements.py      # writes data/paper/ (gitignored)
```

Outputs: `data/paper/raw/` (SI PDF, Reporting Summary, Peer Review File, tables ZIP), `data/paper/xlsx/`, `data/paper/tsv/Supplementary_TableN__<sheet>.tsv`. Load with `pl.read_csv(path, separator="\t", infer_schema_length=None)`. Every workbook has a `legend` sheet except ST6 (header embedded in the grid) and ST18 (legend rows appended below the data, after a blank row).

## Gotchas that apply to many tables

- `mistranslated_position_peptide` is **0-based** (verified: alt/ref differ at exactly that index in 13,910/13,910 ST1 rows). Position 0 never occurs because N-terminal subs are filtered.
- Origins use both `I` and `L` (from the reference protein); destinations use only `I` in ST1/ST4. ST2 (MaxQuant) uses `L` as destination. ST6 uses `I/L` as a destination column but separate I and L origin rows.
- `abundance_ratio_rna = -7` is a sentinel for log10(0); 8,787 ST1 rows carry it, but only 7,890 have `alt_aa_rnaseq = 0`. Use `alt_aa_rnaseq`, `ref_aa_rnaseq` and `coverage` to classify genetic support, not the sentinel.
- `SpectralSim` is MSBooster's spectral-entropy similarity (0 to 1; one ST1 row is exactly 0). `RTScore` is MSBooster's RT score, not a minute difference.
- Tissue names differ: ST1/ST4/ST5 use short names (`adrenal`, `gall`, `fat`, 27 tissues); ST2/ST3 use long names (`adrenal_gland`, `gallbladder`) and include tissues absent from ST1 (ST2 has `liver`, `kidney`, `bone_marrow`, `pituitary`).
- "Unique" in the paper is unique `alt_peptide` for ST1 (7,215) but unique protein-site for ST4 (5,257). Recompute with the unit you need.
- `ensembl` is an Ensembl r112 protein ID (ENSP); `mistranslated_position_protein` indexes that protein.

## Catalog

| ST | Sheet(s) | Rows | Unique `alt_peptide` | Content | Notes |
|---|---|---|---|---|---|
| 1 | Supplementary_Table1, legend | 13,910 | 7,215 (7,544 protein-sites) | Extended set, healthy tissues, 27 tissues, 24 columns incl. RNA counts, MSBooster scores, flags | `ambiguous=1`: 3,564 rows, exactly the 5 classes C>A 1,153, C>S 736, H>D 687, W>D 534, M>D 454. `immunoglobulin=1`: 3,894 rows (1,552 peptides). `mutational_distance` 1/2/3 = 9,943/2,858/1,109. 1,676 rows with abundance_ratio > 0 |
| 2 | MaxQuant results, legend | 9,090 | 4,308 | MaxQuant dependent-peptide subs on the same tissues | paper Venn says 4,168 unique (PepQuery2-revalidated); top classes also C>A, C>S, W>D, H>D, M>D |
| 3 | deTEL detections, legend | 20,524 | 3,235 | deTEL subs on the same tissues | `abundance` is 0 in 16,598 rows (deTEL often has no MS1 quantification) |
| 4 | Supplementary_Table4, legend | 10,121 | 4,978 (5,257 protein-sites) | Filtered (quantification) set; strict subset of ST1 | Reconstructed rule below |
| 5 | gnomad analysis, legend | 3,544 | 1,407 | RNA-supported subs matched to gnomAD v4.1 SNPs | `FREQ` is log10 allele frequency; 66% of 5,358 RNA-supported subs |
| 6 | substitution counts | 20 x 19 | n/a | Counts of non-ambiguous ST1 subs, origin rows x destination columns, with totals | Grand total 10,346 = ST1 rows with `ambiguous=0`; ambiguous cells are 0 |
| 7 | starvation data, legend | 6,599 | 4,397 | Arg (`Rdep`), Leu (`Ldep`), Trp/Tyr (`WYdep`) starvation, MB-231 and MD55A3 | `sample`: control1-3, R-1..3, L-1..2, W-1..2, Y-1..2. Depleted-only top classes: Rdep R>H 160, R>K 123; Ldep M>T 318, L>V 109; WYdep Y>F 587, W>F 114. Rdep/Ldep controls led by L>N (+0.959 Da), W>D, W>S, I>N; WYdep controls by W>D, M>T, C>S |
| 8 | Supplementary_Table8, overlaps, legend | 38 | 38 | W>D peptides in the 18O-water HeLa experiment | `alt_peptide_modified` shows the C-terminal 18O label; overlaps: labelled vs healthy 14 (p 3.1e-10), vs starvation 8 (4.8e-7), healthy vs starvation 18 |
| 9 | AlphaMissense pathogenicity, legend | 6,710 | 3,408 | Subs with AlphaMissense class/score | benign 3,541, pathogenic 2,574, ambiguous 595. Legend swaps `ref_peptide`/`alt_peptide` descriptions; the data columns are correct (ref = reference) |
| 10 | Supplementary_Table10, legend | 7,210 | 4,727 | Trulsson U2OS ubiquitinome, +-proteasome inhibition | `sample` ctrl1-3, pr1-3, mg1-3 (MG-132), mln1-3; `pr`/`mln` undefined in the legend. The `Protein name` column holds peptide labels like `LGEHNIEVLEGNEQFINAAK_H3M`, not names. Top class V>P (-2.016 Da, mass of 2H) |
| 11 | functional site analysis, legend | 193 | 82 | Subs at UniProt site/binding/active positions | `function`: site 114, binding 71, active 8 |
| 12 | recurrent substitutions, legend | 223 | n/a (no alt_peptide column) | Subs recurring across tissues/individuals | `n_tissues` 4 to 18; per-tissue ratios in comma lists |
| 13 | bioplex substitutions, legend | 3,939 | 2,748 | 121 BioPlex HEK293 AP-MS datasets | no positions or intensities |
| 14 | purified proteins, overlaps, legend | 215 | Hb 60, R1 45, GAPDH 38, PRDX6 27, PARK7 27 | Final subs in in-house purified GAPDH, Hb, PARK7, PRDX6 and recombinant R1 antibody (PXD073135) | Published final list for our four QC proteins; Slava's run directories hold only Step 7 `subs.ipc`, so this is the localized reference. Bug: PRDX6 `uniprot` autofills P30041 to P30069 (only P30041 is PRDX6). GAPDH has 38 unique peptides vs 31 in the text |
| 15 | hemoglobin exact matches, legend | 27 | n/a | Hb subs matching IthaNET clinical variants | `O2_affinity` increase/decrease |
| 16 | hemoglobin overlapped matches, legend | 72 | n/a | Hb subs at clinically relevant residues with different exchanges | inferential `predicted_O2_direction`; text says 73 |
| 17 | Karayel et al, legend | 840 | 538 | In-vitro differentiated RBC precursors | `sample` P3, P4, P5, P12; some `uniprot` = "not UniProt ID" |
| 18 | synthetic peptides | 7 pairs (+ legend rows) | 7 | Synthetic peptide pairs (GenScript >= 98%) for ED Fig. 4 | includes F>M (KPLIIFTPK), W>D x2, T>V, T>C, L>A x2 |

## Comparing our outputs against ST14

```bash
uv run python scripts/compare_with_paper_st14.py --qc-step7          # recovered D-072 panel, Step 7
uv run python scripts/compare_with_paper_st14.py --table GAPDH=Barc11:<run>/11_localized/subs_localized.ipc
```

Unit: unique substituted peptide, Leu normalised to Ile. Baseline 2026-11-05, Step 7 candidates (ceiling for Step 11):

| Protein | ST14 unique | Slava Step 7 contains | Barc Step 7 contains | Barc misses |
|---|---|---|---|---|
| GAPDH | 38 | 38 (100%) | 32 (84.2%) | 6, all in allowed classes (sensitivity/FDR) |
| Hb | 60 | 60 (100%) | 58 (96.7%) | 2, both D>N, which our library blocks |
| PARK7 | 27 | 27 (100%) | 27 (100%) | 0 |
| PRDX6 | 27 | 27 (100%) | 26 (96.3%) | 1, C>Y (allowed) |

Slava's 100% confirms ST14 was built from these runs. The Barc tables predate D-073; rerun the four proteins and compare their `subs_localized.ipc` for the like-for-like result.

## ST4 = ST1 filtered: reconstructed rule

The text gives the rule loosely (no K/R, <=1 missed cleavage, ">=3 positions" in Results vs "within 4 residues" in Methods). Fitted against the data, this predicate reproduces ST4 with **0 false negatives and 157 false positives** (10,278 predicted, 10,121 actual):

```python
p = mistranslated_position_peptide            # 0-based
L = len(ref_peptide)
missed = sum(1 for j in range(L - 1) if ref_peptide[j] in "KR" and ref_peptide[j + 1] != "P")
keep = (origin not in "KR" and destination not in "KR"
        and p >= 3 and (L - 1 - p) >= 2 and missed <= 1)
```

The 157 extra rows are not explained by any positional variant tried; treat the rule as approximate.
