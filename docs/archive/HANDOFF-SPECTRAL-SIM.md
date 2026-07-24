# Handoff: Missing SpectralSim & RTScore Columns in Step 11

**For:** Next developer/agent working on TARSUS_BC  
**Date:** 2026-07-23  
**Status:** Ready for implementation  
**Complexity:** Medium (3 files to modify, ~200 lines of code)  

---

## The Issue (1 min read)

Our Step 11 output is missing 2 columns that Slava's reference has:
- **Column 18: `SpectralSim`** — spectral quality score from PepQuery
- **Column 19: `RTScore`** — retention time score

**Evidence:**
```
Reference: subs_localized.csv has 69 columns
Ours:      subs_localized.csv has 67 columns
```

See `/home/labs/pilpel/barc/TARSUS_BC/docs/BUG-MISSING-SPECTRAL-SIM.md` for details.

---

## Root Cause (1 min read)

In Step 7, when we join PepQuery results with PDV ion data:
```python
# Current (wrong)
merged = psm_df.join(pdv_df, on='spectrum_title', how='inner')
# This drops psm_df columns that don't exist in pdv_df
# → SpectralSim, RTScore are lost
```

They're in `psmrankall.txt` but not in `PDVExportResult.txt`, so they get silently dropped.

---

## What To Do (5 min implementation)

### Step 1: Check PDV Has Text Report Mode

```bash
# In /home/labs/pilpel/barc/TARSUS_BC/:
java -jar tools/PDV-2.1.2/PDV-2.1.2.jar -h | grep -A 2 "\-ft"

# Should show: -ft report  (or similar)
```

If it works, continue. If not, see the spec (next section).

### Step 2: Modify 3 Files

**File 1: `src/tarsus/steps/step06_aggregate_query.py`**
- Add `-ft report` flag when calling PDV
- Parse the text report output
- Extract `SpectralSim`, `RTScore` columns
- Save to CSV for Step 7 to read

**File 2: `src/tarsus/steps/step07_analyze_outputs.py`**
- Read the CSV from Step 6
- Use LEFT join instead of INNER join (preserves all PSM columns)
- Verify `SpectralSim`, `RTScore` are in the output before writing subs.ipc

**File 3: `src/tarsus/steps/step11_localize.py`**
- Add validation: check that `SpectralSim`, `RTScore` exist in subs.ipc
- Raise error if missing (early detection instead of silent failure)

---

## Complete Implementation Guide

**Read this first:**
```
docs/SPEC-MISSING-SPECTRAL-SIM.md
```

It has:
- Pseudocode for all 3 changes
- Acceptance criteria (before/after)
- Detailed requirements
- Risk assessment
- Rollback plan

**Key sections:**
- "Implementation Plan" → Step-by-step
- "Pseudocode / Implementation Sketch" → Copy-paste friendly code
- "Files to Be Modified" → Exact list
- "Acceptance Criteria" → How to verify it works

---

## Commands To Run After Implementation

```bash
cd /home/labs/pilpel/barc/TARSUS_BC

# Delete old Step 6+ outputs (preserve Steps 1-5)
rm -rf output/trial/06_aggregated/.done
rm -rf output/trial/07_analyze/.done
rm -rf output/trial/08_ref_validation_prep/.done
rm -rf output/trial/09_pepquery_base/.done
rm -rf output/trial/10_aggregated_base/.done
rm -rf output/trial/11_localized/.done

# Re-run Steps 6-11 (will resume from 06 using .done sentinels)
bsub -q gsla-cpu -oo output/trial/master_rerun_spectral_sim.log \
  python -m tarsus.orchestration output/trial

# Monitor progress
tail -f output/trial/master.log
```

---

## Verification Checklist

After re-running Steps 6-11:

- [ ] `output/trial/11_localized/subs_localized.csv` exists
- [ ] `head -1 subs_localized.csv | tr ',' '\n' | wc -l` = **69** (not 67)
- [ ] Column 18 is `SpectralSim`
- [ ] Column 19 is `RTScore`
- [ ] Both columns have numeric values (not NaN)

```bash
# Quick check
head -1 output/trial/11_localized/subs_localized.csv | tr ',' '\n' | nl | sed -n '17,20p'

# Expected output:
#    17	Delta Mass
#    18	SpectralSim
#    19	RTScore
#    20	Expectation
```

---

## If Something Breaks

**Option 1: Check the spec for details**
```
docs/SPEC-MISSING-SPECTRAL-SIM.md → Section: "Risk Assessment"
```

**Option 2: Revert quickly**
```bash
git checkout HEAD -- src/tarsus/steps/step06_aggregate_query.py \
                      src/tarsus/steps/step07_analyze_outputs.py \
                      src/tarsus/steps/step11_localize.py

# Delete Steps 6-11 sentinels and re-run
rm -rf output/trial/{06,07,08,09,10,11}_*/.done
```

---

## Context Files

**All docs in:** `/home/labs/pilpel/barc/TARSUS_BC/docs/`

| File | Read if... |
|---|---|
| `SPEC-MISSING-SPECTRAL-SIM.md` | You're implementing (detailed spec) |
| `BUG-MISSING-SPECTRAL-SIM.md` | You want to understand the bug |
| `CODE-LEVEL-COMPARISON.md` | You need to understand the full pipeline |
| `SLAVA-REFERENCE.md` | You need to understand the reference |

---

## Expected Outcome

After implementation:
- ✅ 69 columns in subs_localized.csv (currently 67)
- ✅ SpectralSim, RTScore columns present with values
- ✅ Row count unchanged (no data loss)
- ✅ Schema matches reference exactly
- ✅ All tests pass

---

## Time Estimate

- Investigation: 15 min (verify PDV has `-ft report`)
- Implementation: 45 min (modify 3 files, ~200 lines total)
- Testing: 30 min (re-run Steps 6-11, verify output)
- **Total: ~90 min**

---

## Questions Before Starting?

Check:
1. `docs/SPEC-MISSING-SPECTRAL-SIM.md` → all answers there
2. `.memory/decisions.md` → any prior context
3. `.memory/progress.md` → current state of work

---

**Good luck! Ping if blocked.**
