# `subs.ipc` column reference

The substitution table written by **Step 7** (`step07_analyze_outputs.py`) and
carried through Step 11 (`subs_localized.ipc`). One row = one PSM supporting a
single amino-acid substitution.

This file exists so the table stays interpretable independently of Slava. Every
column below is either produced by an external tool (and named by that tool) or
derived by us — the "Source" column says which, so you can always trace a value
back to the program that computed it.

**73 columns.** That is the reference's 69, plus 3 PDV annotation columns
(`ions`/`ion_mz`/`ion_int`, present in Slava's GAPDH file) and our
`spectrum_title` join key. It is a strict superset of both reference schemas —
nothing the reference emits is dropped.

## Reading the layout

Columns arrive in three blocks, in this order:

1. **0-51** — the second-pass (variant) FragPipe `psm.tsv`, verbatim, with
   MSBooster scores at 17-18 and PDV annotation appended at 49-51.
2. **52-54** — identity columns we add.
3. **55-67** — the *first-pass* (reference peptide) search, joined on
   `(base, Charge)`. These all carry the **`_right`** suffix.
4. **68-72** — the substitution call itself, derived last.

The `_right` suffix is the single most important thing to understand: **a column
without it describes the substituted (variant) peptide; the same column with it
describes the original reference peptide.** `Hyperscore` is the variant's score,
`Hyperscore_right` is the reference peptide's.

## Source legend

| Source | Meaning |
|---|---|
| `FragPipe/2nd` | second-pass `psm.tsv`, variant search — copied verbatim |
| `MSBooster` | written into `psm.tsv` by MSBooster; **null if MSBooster is off** |
| `PDV` | `PDVExportResult.txt` fragment annotation, raw bracketed strings |
| `FragPipe/1st` | first-pass `psm.tsv`, reference-peptide search (`_right`) |
| `TARSUS` | derived by Step 7 |

## Columns

| # | Column | Type | Source | Meaning |
|---:|---|---|---|---|
| 0 | `Spectrum` | str | FragPipe/2nd | FragPipe spectrum id, `file.scan.scan.charge` |
| 1 | `Spectrum File` | str | FragPipe/2nd | source mzML |
| 2 | `dependent` | str | FragPipe/2nd | **the substituted peptide sequence** (renamed from `Peptide`) |
| 3 | `Modified Peptide` | str | FragPipe/2nd | sequence with modification masses inline |
| 4 | `Extended Peptide` | str | FragPipe/2nd | peptide with flanking residues |
| 5-6 | `Prev AA`, `Next AA` | str | FragPipe/2nd | flanking residues in the protein |
| 7 | `Peptide Length` | int | FragPipe/2nd | residue count |
| 8 | `Charge` | int | FragPipe/2nd | precursor charge; part of the first/second join key |
| 9 | `Retention` | float | FragPipe/2nd | observed retention time (s) |
| 10-15 | `Observed/Calibrated/Calculated Mass`, `M/Z` | float | FragPipe/2nd | precursor mass and m/z, measured vs theoretical |
| 16 | `Delta Mass` | float | FragPipe/2nd | observed − calculated mass; ~the substitution's mass shift |
| **17** | **`SpectralSim`** | float | **MSBooster** | similarity of the observed MS2 to the predicted spectrum (higher = better). **Requires MSBooster; see D-069** |
| **18** | **`RTScore`** | float | **MSBooster** | retention-time agreement vs prediction (lower = better) |
| 19 | `Expectation` | float | FragPipe/2nd | MSFragger e-value |
| 20-21 | `Hyperscore`, `Nextscore` | float | FragPipe/2nd | best and runner-up match scores |
| 22-23 | `Probability`, `Qvalue` | float | FragPipe/2nd | posterior probability and FDR q-value |
| 24-25 | `Number of Enzymatic Termini`, `...Missed Cleavages` | int | FragPipe/2nd | digestion properties |
| 26-27 | `Protein Start`, `Protein End` | int | FragPipe/2nd | peptide coordinates in the protein |
| 28 | `second Intensity` | float | FragPipe/2nd | **variant peptide abundance** (renamed from `Intensity`) |
| 29-30 | `Assigned/Observed Modifications` | str | FragPipe/2nd | PTMs on this PSM |
| 31 | `Purity` | float | FragPipe/2nd | precursor isolation purity |
| 32-34 | `Is Decoy`, `Is Contaminant`, `Is Unique` | bool | FragPipe/2nd | flags |
| 35-41 | `Protein`, `Protein ID`, `Entry Name`, `Gene`, `Protein Description`, `Mapped Genes`, `Mapped Proteins` | str | FragPipe/2nd | protein identification. `Protein` holds the **candidate header** `<base>_<origin><pos><dest>` that Step 3b generated |
| 42-48 | `Parent Scan Number`, `Apex Retention Time`, `Apex Scan Number`, `Retention Time Start/End/FWHM`, `Traced Scans` | mixed | FragPipe/2nd | IonQuant chromatographic tracing |
| **49** | **`ions`** | str | **PDV** | matched fragment ion labels, e.g. `[b4, y7++]` |
| **50** | **`ion_mz`** | str | **PDV** | m/z of those fragments, same order |
| **51** | **`ion_int`** | str | **PDV** | intensity of those fragments, same order |
| 52 | `base` | str | TARSUS | **the reference (unsubstituted) peptide**, from `Protein.split('_')[0]` |
| 53 | `sample` | str | TARSUS | run/sample name, so concatenated runs stay separable |
| 54 | `spectrum_title` | str | TARSUS | `file:scan:charge` — the PepQuery/PDV key namespace (see D-047) |
| 55-67 | `*_right` | mixed | FragPipe/1st | the **reference peptide's** first-pass values: `Spectrum_right`, `Prev AA_right`, `Next AA_right`, `Protein_right`, `Retention_right`, `Protein Start/End_right`, `Mapped Proteins_right`, `Hyperscore_right`, `Extended Peptide_right`, `Number of Missed Cleavages_right`, `Is Unique_right` |
| 59 | `first Intensity` | float | FragPipe/1st | **reference peptide abundance** (denominator of `dpbp`) |
| 68 | `mistranslatedPos` | int | TARSUS | **0-based** position of the substitution within `dependent`. Step 11 converts to 1-based for PyAscore |
| 69 | `origin` | str | TARSUS | the encoded residue. Read from `base[mistranslatedPos]`, **not** the header — the header collapses I/L to `I` (D-065) |
| 70 | `destination` | str | TARSUS | the misincorporated residue. Seen only by mass, so I/L is genuinely ambiguous; Step 11 relabels it `I/L` as its last act |
| 71 | `misProt` | int | TARSUS | substitution position in **protein** coordinates (`Protein Start_right + mistranslatedPos − 1`) |
| 72 | `dpbp` | float | TARSUS | `log10(second Intensity / first Intensity)` — **substitution rate**: variant abundance relative to its reference peptide |

## The two columns that break silently

`SpectralSim` and `RTScore` are the only columns produced by a tool that the
pipeline can run *without*. FragPipe writes them into `psm.tsv` only when
MSBooster runs; disable MSBooster and they vanish, and any code that fills them
with nulls will produce a table that looks structurally perfect and is
scientifically empty. Step 7 now raises instead. Do not "fix" a failure there by
re-adding placeholders, and do not source them from `_edited.pin` — the pin's
`unweighted_spectral_entropy`/`delta_RT_loess` are different quantities
(r=0.16 / r=−0.08 against these). See **D-069**.

## Naming

Column names match the reference generator (`elizabev/TARSUS/analyze_outputs.py`)
exactly, including its quirks — the space in `first Intensity`/`second Intensity`,
the camelCase `mistranslatedPos`, and the `_right` join suffix. They are
deliberately *not* tidied into snake_case: keeping them byte-identical is what
lets our output be diffed directly against Slava's existing `subs.ipc` files.
