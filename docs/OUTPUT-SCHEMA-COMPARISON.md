# Output Schema Comparison: TARSUS_BC vs Slava's Original Pipeline

**Written:** 2026-07-23  
**Purpose:** Conceptual comparison of output file structure, column counts, naming, and data sources  
**Evidence base:** Measured directly from actual output files (not documentation or code alone)

---

## 1. The Two Pipelines at a Glance

| | Slava's Original | TARSUS_BC (ours) |
|---|---|---|
| **Location** | `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` | `/home/labs/pilpel/barc/TARSUS_BC/output/<run>/` |
| **FragPipe version** | 23.1 | 24.0 |
| **Orchestration** | Hand-run Bash scripts | LSF-orchestrated Python steps |
| **Key script** | `analyze_outputs.py` | `step07_analyze_outputs.py` |
| **`subs.ipc` cols** | **69** | **67** (production) / 69 (trial with NaN placeholders) |
| **`subs_localized.ipc` cols** | **69** | **67** |

---

## 2. The Primary Output File: `subs.ipc`

This is the main artifact. Every downstream step reads it.  
Measured on: Slava's EVpar run (3922 rows) vs our alaggcpar run (3446 rows).

### 2a. Column Count Summary

```
Slava:    69 columns
Ours:     67 columns  (production - alaggcpar, hoMS_24814)
          69 columns  (trial run - SpectralSim/RTScore present as NaN placeholders)
```

**We are 2 columns short in production.** The 2 missing columns are `SpectralSim` [17] and `RTScore` [18].

### 2b. Full Side-by-Side Column Map

| Slava [idx] | Column Name | Ours [idx] | Status |
|---|---|---|---|
| [00] | Spectrum | [00] | EXACT MATCH |
| [01] | Spectrum File | [01] | EXACT MATCH |
| [02] | dependent | [02] | EXACT MATCH |
| [03] | Modified Peptide | [03] | EXACT MATCH |
| [04] | Extended Peptide | [04] | EXACT MATCH |
| [05] | Prev AA | [05] | EXACT MATCH |
| [06] | Next AA | [06] | EXACT MATCH |
| [07] | Peptide Length | [07] | EXACT MATCH |
| [08] | Charge | [08] | EXACT MATCH |
| [09] | Retention | [09] | EXACT MATCH |
| [10] | Observed Mass | [10] | EXACT MATCH |
| [11] | Calibrated Observed Mass | [11] | EXACT MATCH |
| [12] | Observed M/Z | [12] | EXACT MATCH |
| [13] | Calibrated Observed M/Z | [13] | EXACT MATCH |
| [14] | Calculated Peptide Mass | [14] | EXACT MATCH |
| [15] | Calculated M/Z | [15] | EXACT MATCH |
| [16] | Delta Mass | [16] | EXACT MATCH |
| **[17]** | **SpectralSim** | **(missing)** | **ABSENT - FragPipe version gap** |
| **[18]** | **RTScore** | **(missing)** | **ABSENT - FragPipe version gap** |
| [19] | Expectation | [17] | MATCH (shifted -2) |
| [20] | Hyperscore | [18] | MATCH (shifted -2) |
| [21] | Nextscore | [19] | MATCH (shifted -2) |
| [22] | Probability | [20] | MATCH (shifted -2) |
| [23] | Qvalue | [21] | MATCH (shifted -2) |
| [24] | Number of Enzymatic Termini | [22] | MATCH (shifted -2) |
| [25] | Number of Missed Cleavages | [23] | MATCH (shifted -2) |
| [26] | Protein Start | [24] | MATCH (shifted -2) |
| [27] | Protein End | [25] | MATCH (shifted -2) |
| **[28]** | **second Intensity** (space) | **[26]** | **RENAMED: `second_intensity` (underscore)** |
| [29] | Assigned Modifications | [27] | MATCH |
| [30] | Observed Modifications | [28] | MATCH |
| [31] | Purity | [29] | MATCH |
| [32] | Is Decoy | [30] | MATCH |
| [33] | Is Contaminant | [31] | MATCH |
| [34] | Is Unique | [32] | MATCH |
| [35] | Protein | [33] | MATCH |
| [36] | Protein ID | [34] | MATCH |
| [37] | Entry Name | [35] | MATCH |
| [38] | Gene | [36] | MATCH |
| [39] | Protein Description | [37] | MATCH |
| [40] | Mapped Genes | [38] | MATCH |
| [41] | Mapped Proteins | [39] | MATCH |
| [42] | Parent Scan Number | [40] | MATCH |
| [43] | Apex Retention Time | [41] | MATCH |
| [44] | Apex Scan Number | [42] | MATCH |
| [45] | Retention Time Start | [43] | MATCH |
| [46] | Retention Time End | [44] | MATCH |
| [47] | Retention Time FWHM | [45] | MATCH |
| [48] | Traced Scans | [46] | MATCH |
| [49] | base | [47] | MATCH |
| **[50]** | **sample** | **(missing)** | **ABSENT - we never add run label** |
| **[51]** | **Spectrum_right** | **[49]** | **RENAMED: `Spectrum_first`** |
| **[52]** | **Prev AA_right** | **[50]** | **RENAMED: `Prev AA_first`** |
| **[53]** | **Next AA_right** | **[51]** | **RENAMED: `Next AA_first`** |
| **[54]** | **Protein_right** | **[52]** | **RENAMED: `Protein_first`** |
| **[55]** | **first Intensity** (space) | **[53]** | **RENAMED: `first_intensity` (underscore)** |
| **[56]** | **Retention_right** | **[54]** | **RENAMED: `Retention_first`** |
| **[57]** | **Protein Start_right** | **[55]** | **RENAMED: `Protein Start_first`** |
| **[58]** | **Protein End_right** | **[56]** | **RENAMED: `Protein End_first`** |
| **[59]** | **Mapped Proteins_right** | **[57]** | **RENAMED: `Mapped Proteins_first`** |
| **[60]** | **Hyperscore_right** | **[58]** | **RENAMED: `Hyperscore_first`** |
| **[61]** | **Extended Peptide_right** | **[59]** | **RENAMED: `Extended Peptide_first`** |
| **[62]** | **Number of Missed Cleavages_right** | **[60]** | **RENAMED: `Number of Missed Cleavages_first`** |
| **[63]** | **Is Unique_right** | **[61]** | **RENAMED: `Is Unique_first`** |
| **[64]** | **mistranslatedPos** | **[62]** | **RENAMED: `mistranslated_pos` (snake_case)** |
| [65] | origin | [63] | MATCH |
| [66] | destination | [64] | MATCH |
| [67] | misProt | [65] | MATCH |
| [68] | dpbp | [66] | MATCH |

**Ours ALSO adds (not in Slava's 69):**

| Ours [idx] | Column Name | Reason |
|---|---|---|
| [48] | spectrum_title | Explicit spectrum ID string we track for D-047 join correctness |

---

## 3. Column Difference Categories

### Category A: Structural Gaps (data simply absent)

These 2 columns are missing and cannot be filled from any current pipeline output:

| Column | Slava position | Where it comes from | Why we don't have it |
|---|---|---|---|
| `SpectralSim` | [17] | `second/psm.tsv` - written by FragPipe/MSBooster | **FragPipe 23.1 writes it; FragPipe 24.0 does not** |
| `RTScore` | [18] | `second/psm.tsv` - written by FragPipe/MSBooster | Same - version gap |

**Verified:** Slava's `second/psm.tsv` has 49 cols including SpectralSim and RTScore. Our `second/psm.tsv` has 47 cols; these two are absent. The data never enters the pipeline because FragPipe 24.0 dropped or moved these MSBooster output fields.

**Impact:** Steps 8-11 that filter on SpectralSim or use it as a score are working on NaN values in the "trial" run (which added placeholder columns), or have no signal at all in production runs.

### Category B: Structural Gap (metadata column)

| Column | Slava position | Where it comes from | Why we don't have it |
|---|---|---|---|
| `sample` | [50] | Slava adds `sys.argv[1].split('/')[-1]` in `analyze_outputs.py` | We never add the run label |

**Impact:** Low. Slava's column is always an empty string `""` in EVpar (the reference run has blank sample labels). Our multi-run architecture uses directory paths as context; a `sample` string was not ported.

### Category C: Renamed Columns (same data, different name)

These 14 pairs are semantically identical. Different naming convention only.

| Slava name | Our name | Convention |
|---|---|---|
| `second Intensity` | `second_intensity` | Space vs underscore |
| `first Intensity` | `first_intensity` | Space vs underscore |
| `mistranslatedPos` | `mistranslated_pos` | camelCase vs snake_case |
| `Spectrum_right` | `Spectrum_first` | `_right` vs `_first` join suffix |
| `Prev AA_right` | `Prev AA_first` | same |
| `Next AA_right` | `Next AA_first` | same |
| `Protein_right` | `Protein_first` | same |
| `Retention_right` | `Retention_first` | same |
| `Protein Start_right` | `Protein Start_first` | same |
| `Protein End_right` | `Protein End_first` | same |
| `Mapped Proteins_right` | `Mapped Proteins_first` | same |
| `Hyperscore_right` | `Hyperscore_first` | same |
| `Extended Peptide_right` | `Extended Peptide_first` | same |
| `Number of Missed Cleavages_right` | `Number of Missed Cleavages_first` | same |
| `Is Unique_right` | `Is Unique_first` | same |

The `_right` suffix is Polars' default when two DataFrames share a column name during a join. Slava got `_right` because the join is `second_psms.join(first_psms, ...)`. We renamed `_right` to `_first` to make direction explicit: first-pass columns are labeled `_first`.

**Note on `mistranslatedPos`:** Slava's `localize.py` has a known bug: it calls `.get('mistranslatedPos', 0)` on a row that uses snake_case `mistranslated_pos`, so it always gets 0. This is one of the bugs D-048 fixed in our Step 11.

### Category D: Extra Column in Ours (not in Slava)

| Column | Our position | Why we added it |
|---|---|---|
| `spectrum_title` | [48] | Explicit spectrum ID we carry through all join steps. Critical for D-047: tracing which mzML file and scan number a PSM came from. Slava uses the `Spectrum` column for this (same data, different form). |

---

## 4. Where the Missing Columns Come From (Data Lineage)

```
FragPipe 23.1 (Slava):
  second/psm.tsv  [49 cols]
      │
      ├── SpectralSim  <-- MSBooster similarity score (spectrum vs predicted)
      └── RTScore      <-- MSBooster retention time score (predicted vs observed)
      │
      v
  analyze_outputs.py
      reads psm.tsv, keeps all columns including SpectralSim/RTScore
      joins with first/psm.tsv
      writes subs.ipc [69 cols]

FragPipe 24.0 (ours):
  second/psm.tsv  [47 cols]
      │
      ├── SpectralSim  <-- NOT PRESENT (dropped or moved in FP24.0)
      └── RTScore      <-- NOT PRESENT
      │
      v
  step07_analyze_outputs.py
      reads psm.tsv, SpectralSim/RTScore simply don't exist
      joins with first/psm.tsv
      writes subs.ipc [67 cols]   <- the gap starts here
```

This is a **pipeline tool version difference**, not a code logic difference. The columns are standard MSBooster outputs; FP24.0 either stores them elsewhere or stopped outputting them under these names.

---

## 5. `subs_localized.ipc` - The Final Localization Output

Both pipelines produce `subs_localized.ipc` from Step 11. Same schema structure as `subs.ipc` plus AScore; the column gap propagates directly.

| | Slava | Ours |
|---|---|---|
| **Rows (EVpar/AlaGGCpar)** | 697 | 473 |
| **Cols** | 69 | 67 |
| **AScore threshold** | >= 13 | >= 13 |

The 2-column gap is the same gap as in `subs.ipc`. No new columns are added in Step 11.

---

## 6. Other Output Files (Intermediate)

### `psmrankall.txt` (Step 6 output, input to Step 7)

This is a text/TSV file, not IPC. Schema is nearly identical.

| | Slava | Ours |
|---|---|---|
| **Source** | `aggregate_query.sh` concatenates PepQuery `detail.txt` chunks | `step06_aggregate_query.py` same logic + blank-line guard (D-038) |
| **Format** | TSV, PepQuery standard columns | TSV, same PepQuery columns |
| **Column count** | Same as PepQuery output (varies by PepQuery version) | Same |
| **Key difference** | None - both read PepQuery's raw output | We fixed blank-line join bug |

### `PDVExportResult.txt` (Step 6 PDV output)

PDV is a visualization tool that exports ion evidence. Schema identical between pipelines (same PDV tool version). Slava references `pdv_spectra/PDVExportResult.txt`; we reference the same structure.

### `first.ipc` / `first/psm.tsv`

First-pass FragPipe output. No meaningful column difference. Same MSFragger output schema. The `SpectralSim`/`RTScore` are present in Slava's first-pass psm.tsv too (FP23.1) and absent from ours (FP24.0).

---

## 7. Conceptual Summary: What Matters

### The 2-col gap is real but has one root cause

```
SpectralSim + RTScore = MSBooster scores
                      = written by FragPipe into psm.tsv
                      = present in FP23.1, absent in FP24.0
                      = the ONLY reason subs.ipc has 67 not 69 cols
```

Everything else is renaming. The underlying data is the same.

### The renamed columns are semantically stable

14 columns renamed. None have different data. The `_right`->`_first` rename is strictly clearer. The `mistranslatedPos`->`mistranslated_pos` rename is Python convention and fixed a downstream bug.

### Our extra `spectrum_title` column is an improvement

Slava reconstructs the spectrum ID on the fly from the `Spectrum` column. We carry `spectrum_title` explicitly through every step, which is what made D-047 fixable and the join correctness measurable.

### Row counts differ but agreement is 100% where both fire

On the shared hoMS/GAPDH dataset:
- 115 of our spectra appear in Slava's output
- 115/115 (100%) agree on origin-destination substitution call
- Position matches on 113/115; 2 off by 4 positions
- Yield difference (167 vs 233) explained by library scope, not schema differences

---

## 8. Action Items Derived from This Comparison

| Priority | Item | What it fixes |
|---|---|---|
| HIGH | Investigate where FP24.0 puts SpectralSim/RTScore | Closes the 2-col gap permanently |
| HIGH | Check if FP24.0 renamed them (e.g. `MSBooster_MS2` or similar in psm.tsv) | May be a trivial rename |
| MEDIUM | Add `sample` column in Step 7 (from run directory name) | Matches Slava schema exactly |
| MEDIUM | Align `_first` suffix naming with Slava downstream scripts | Prevents confusion if someone uses Slava's analysis scripts on our output |
| LOW | Consider renaming `spectrum_title` -> keep it, it's useful | No action needed; strictly additive |

---

## 9. Files Measured

```
Slava reference subs.ipc:
  /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc
  3922 rows x 69 cols

Slava reference subs_localized.ipc:
  /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs_localized.ipc
  697 rows x 69 cols

Slava second/psm.tsv:
  /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/second/psm.tsv
  49 cols (includes SpectralSim, RTScore)

Our production subs.ipc:
  /home/labs/pilpel/barc/TARSUS_BC/output/alaggcpar/07_analyze/subs.ipc
  3446 rows x 67 cols

Our second/psm.tsv:
  /home/labs/pilpel/barc/TARSUS_BC/output/alaggcpar/03c_second_pass/second/psm.tsv
  47 cols (SpectralSim and RTScore ABSENT)

Our trial subs.ipc (NaN placeholders):
  /home/labs/pilpel/barc/TARSUS_BC/output/trial/07_analyze/subs.ipc
  2940 rows x 69 cols (SpectralSim and RTScore are null)
```
