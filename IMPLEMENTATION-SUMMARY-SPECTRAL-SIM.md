# Implementation Summary: Missing SpectralSim and RTScore Columns

**Date:** 2026-07-23  
**Task:** Add missing `SpectralSim` and `RTScore` columns to Step 11 output  
**Status:** Implementation Complete (Placeholder Columns Added)  

---

## What Was Done

### 1. Step 7 (`step07_analyze_outputs.py`) - MODIFIED

**Change:** Added placeholder columns for SpectralSim and RTScore in the correct position

```python
# After line 346 (after join operations), added:
joined = joined.with_columns([
    pl.lit(None).cast(pl.Float64).alias("SpectralSim"),
    pl.lit(None).cast(pl.Float64).alias("RTScore"),
])

# Then reordered columns to place them after "Delta Mass" and before "Expectation"
# to match the reference schema (columns 18-19)
```

**Why:** The reference pipeline's subs.ipc output has 69 columns (ours had 67). These two columns must be inserted at positions 18-19 to match the reference schema.

**Impact:**
- subs.ipc now includes SpectralSim and RTScore columns
- Columns are positioned correctly after Delta Mass
- Currently populated with NaN values (placeholder)

### 2. Step 11 (`step11_localize.py`) - MODIFIED

**Change:** Added validation to check that required columns exist

```python
# After reading subs.ipc, added:
required_cols = ["SpectralSim", "RTScore"]
missing_cols = [c for c in required_cols if c not in subs.columns]
if missing_cols:
    raise ValueError(
        f"Step 7 output is missing required columns: {missing_cols}..."
    )
```

**Why:** Early detection of missing columns prevents silent failures downstream.

**Impact:**
- Step 11 will fail explicitly if columns are missing
- Error message clearly indicates the problem

---

## Current State

### What Works
- ✅ Column schema matches reference (69 columns for subs.ipc)
- ✅ Columns positioned correctly (SpectralSim at 18, RTScore at 19)
- ✅ Validation in place to detect issues

### What Still Needs Doing
- ⚠️ **CRITICAL:** Populate SpectralSim and RTScore with actual data
  - Currently: NaN/null values
  - Need: Real numeric scores from PDV text report mode
  
---

## Investigation Notes

### Where Do These Columns Come From?

After extensive investigation:

1. **Not in PepQuery output** - psmrankall.txt has only 22 columns
2. **Not in PDV basic export** - PDVExportResult.txt has only 10 columns
3. **Not computed in analyze_outputs.py** - Reference code doesn't show computation

### Likely Source: PDV Text Report Mode

**Evidence:**
- Step 6 already calls PDV with `-ft report` flag
- PDV's report mode is configured but not being parsed
- These columns likely come from PDV's text report output

**Next Steps to Populate Values:**

1. **Check if PDV generates additional files in report mode**
   - Run PDV manually to see what `-ft report` produces
   - Files might be named `report.txt`, `*_metrics.txt`, etc.

2. **Parse the report output**
   - In Step 6, after PDV runs, look for the report file
   - Extract SpectralSim and RTScore by spectrum_title
   - Save to CSV for Step 7 to read

3. **Merge in Step 7**
   - Read the metrics CSV from Step 6
   - Join with psmrankall on spectrum_title
   - This will populate the columns with actual values

### Alternative Possibility

These columns might come from MSBooster or another tool in the FragPipe pipeline. If PDV doesn't generate them, check:
- MSBooster output (spectral similarity scores)
- IonQuant output (retention time predictions)
- FragPipe's built-in scoring

---

## Files Modified

1. `/home/labs/pilpel/barc/TARSUS_BC/src/tarsus/steps/step07_analyze_outputs.py`
   - Added lines: ~12-20 (column addition and reordering)
   - Inserted placeholder columns with proper positioning

2. `/home/labs/pilpel/barc/TARSUS_BC/src/tarsus/steps/step11_localize.py`
   - Added lines: ~11-19 (validation check)
   - Validates required columns exist before processing

---

## Testing

### Syntax Validation
- ✅ `python -m py_compile step07_analyze_outputs.py` - OK
- ✅ `python -m py_compile step11_localize.py` - OK

### Logic Validation
- ✅ Column addition logic verified in test (Polars `with_columns` works)
- ✅ Column reordering logic verified in test (proper insertion after Delta Mass)

### Integration Testing
- ⚠️ Full pipeline run needs all input data (Steps 1-6 must complete)
- Current environment lacks full input data for end-to-end test
- Next implementer should verify with actual pipeline run

---

## How to Complete This Task

### Option A: Discover PDV Text Report Format (Recommended)

1. Run a small PDV job manually with `-ft report` flag
2. Check what files PDV generates
3. Parse the report file in Step 6
4. Merge the metrics into Step 7
5. Re-run pipeline to verify

### Option B: Use Reference Data Directly

1. Compare reference's subs.ipc with reference's psmrankall.txt
2. Try to reverse-engineer which scores come from which rows
3. If a pattern emerges, hardcode logic in Step 7

### Option C: Check FragPipe Tools

1. Look at MSBooster or IonQuant output for these metrics
2. If found, add a merge in Step 7 to include them
3. Test with reference data to validate

---

## Success Criteria

After completing the population of actual values:

```bash
# Should match the reference
python << 'EOF'
import polars as pl

# Your output
our = pl.read_ipc('output/trial/07_analyze/subs.ipc')
print(f"Column count: {len(our.columns)} (expected: 69)")
print(f"SpectralSim values (first 3): {our['SpectralSim'].head(3).to_list()}")
print(f"RTScore values (first 3): {our['RTScore'].head(3).to_list()}")

# Verify not all NaN
print(f"SpectralSim null count: {our['SpectralSim'].null_count()} (should be < {len(our)})")
print(f"RTScore null count: {our['RTScore'].null_count()} (should be < {len(our)})")
EOF
```

---

## Related Documents

- `HANDOFF-SPECTRAL-SIM.md` - Overview and next steps
- `docs/SPEC-MISSING-SPECTRAL-SIM.md` - Detailed technical specification
- `.memory/progress.md` - Progress tracking
- `.memory/decisions.md` - Decision log

---

## Questions for Next Implementer

1. What does PDV's `-ft report` mode actually output?
2. Are these columns always populated or sometimes null?
3. Should placeholder NaN values be replaced, or could there be spectra without scores?
4. How should the join handle spectra that appear in PSM but not in PDV metrics?

---

**End of Implementation Summary**
