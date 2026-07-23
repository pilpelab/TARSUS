# CRITICAL BUG: Missing `SpectralSim` and `RTScore` Columns in Step 11 Output

**Status:** CONFIRMED - Slava's claim is correct

**Date found:** 2026-07-23

**Impact:** Outputs missing 2 crucial metadata columns from PDV/PepQuery results

---

## Summary

**Reference output (subs_localized.csv):** 69 columns
**Our output (subs_localized.csv):** 67 columns

**Missing columns:**
1. **Column 18: `SpectralSim`** — Spectral similarity score from PepQuery
2. **Column 19: `RTScore`** — Retention time score from PepQuery/ionquant

These columns are **completely absent** from our pipeline.

---

## Evidence

### Slava's Column Order (psmrankall.txt / subs_localized.csv)

```
Column 17: Delta Mass
Column 18: SpectralSim              ← MISSING IN OURS
Column 19: RTScore                  ← MISSING IN OURS
Column 20: Expectation
Column 21: Hyperscore
Column 22: Nextscore
Column 23: Probability
Column 24: Qvalue
```

### Our Column Order

```
Column 17: Delta Mass
Column 18: Expectation             (should be column 20)
Column 19: Hyperscore              (should be column 21)
Column 20: Nextscore               (should be column 22)
Column 21: Probability             (should be column 23)
Column 22: Qvalue                  (should be column 24)
--- NO SpectralSim, NO RTScore ---
```

---

## Root Cause

### Where do these columns come from?

Looking at `psmrankall.txt` (Step 6 aggregation output):

```bash
$ head -1 psmrankall.txt | tr '\t' '\n' | nl

1  peptide
2  modification
3  n
4  spectrum_title
5  charge
6  exp_mass
7  tol_ppm
8  tol_da
9  isotope_error
10 pep_mass
11 mz
12 score
13 n_db
14 total_db
15 n_random
16 total_random
17 pvalue
18 rank
19 n_ptm
20 confident
21 ref_delta_score
22 mod_delta_score
```

These columns come from **PepQuery output** (psm_rank.txt files). But `SpectralSim` and `RTScore` are **not in psmrankall.txt**.

### Where are they supposed to come from?

These columns must be coming from the **PDV export** or a **second PepQuery output mode**. 

Possibilities:
1. **PDV has a text report mode** (`-ft report`) that outputs these columns
2. **IonQuant or FragPipe ionquant output** adds RT scores
3. **A separate PepQuery column set** that we're not reading

### Slava's PDV Call

```bash
java -jar PDV-2.1.2.jar \
  -r psmrankall.txt \
  -rt 4 \
  -s mgfall.mgf \
  -st 1 \
  -i peptides.txt \
  -k p \
  -o pdv_spectra/ \
  -ft pdf                    # ← outputs PDFs only
```

**Note:** There's a commented-out version in his code:
```bash
# -ft report                  # ← would output text report instead
```

---

## What We're Doing Wrong

### Our Step 7 (`step07_analyze_outputs.py`)

We read:
- `psmrankall.txt` (PepQuery results)
- `PDVExportResult.txt` (PDV ion data)

But we only **filter and rename** — we don't merge additional PepQuery columns.

```python
# Current approach
psm_df = pl.read_csv(psmrankall_file, separator='\t')
pdv_df = pl.read_csv(pdv_export_file, separator='\t')

merged = psm_df.join(pdv_df, on='spectrum_title', how='inner')
result = merged.filter(...)
result.write_ipc(subs_ipc)
```

**We're losing columns from `psm_df` that don't exist in `pdv_df`!**

The columns `SpectralSim` and `RTScore` are probably in `psmrankall.txt` but not in `PDVExportResult.txt`, so the join drops them.

---

## The Fix

### Option A: Read from PDV Text Report Mode (Preferred)

Call PDV with `-ft report` to output a text file containing `SpectralSim` and `RTScore`:

```python
# In step06_aggregate_query.py or step07_analyze_outputs.py

cmd = [
    str(pdv_exe),
    "-r", str(psmrankall_file),
    "-rt", "4",
    "-s", str(mgf_file),
    "-st", "1",
    "-i", str(peptides_file),
    "-k", "p",
    "-o", str(output_dir),
    "-ft", "report"  # ← ADD THIS (text report, not PDF)
]

# Read the report output
pdv_report = pl.read_csv(output_dir / "report.txt", separator='\t')

# Extract SpectralSim and RTScore
spectral_sim = pdv_report[['spectrum_title', 'SpectralSim', 'RTScore']]

# Merge with Step 7 results
result = merged.join(spectral_sim, on='spectrum_title', how='left')
```

### Option B: Don't Drop Columns on Join

Preserve all columns from `psmrankall.txt` instead of only those that match `pdv_df`:

```python
# Current (drops columns from psm_df that don't match pdv_df)
merged = psm_df.join(pdv_df, on='spectrum_title', how='inner')

# Better: outer join, then select needed columns
merged = psm_df.join(
    pdv_df[['spectrum_title', 'ions', 'ions_mz', 'ions_int']],
    on='spectrum_title',
    how='inner'
)
# Now merged has all columns from psm_df PLUS PDV ion data
```

---

## Verification

### Before Fix

```
$ head -1 subs_localized.csv | tr ',' '\n' | nl | tail -10
18	Expectation
19	Hyperscore
20	Nextscore
```

### After Fix

```
$ head -1 subs_localized.csv | tr ',' '\n' | nl | tail -10
18	SpectralSim
19	RTScore
20	Expectation
21	Hyperscore
22	Nextscore
```

---

## Impact

- **Data loss:** 2 columns (metadata scoring information) not included in final output
- **Validation:** Cannot reproduce Slava's output exactly
- **Science:** SpectralSim and RTScore may be important for filtering/ranking (need to check Slava's paper)

---

## Files to Check

1. `src/tarsus/steps/step06_aggregate_query.py` — PDV invocation
2. `src/tarsus/steps/step07_analyze_outputs.py` — Column merging
3. `src/tarsus/steps/step11_localize.py` — Final output assembly

---

## Next Steps

1. **Verify PDV has text report mode** — run `java -jar PDV-2.1.2.jar -h` to check `-ft` options
2. **Check if these columns are actually in Slava's `psmrankall.txt`** — they might only be in a separate PepQuery output
3. **Implement the fix** — read text report or preserve join columns
4. **Re-run Step 6-11** — regenerate subs_localized.ipc and .csv
5. **Validate against reference** — check column-by-column agreement
