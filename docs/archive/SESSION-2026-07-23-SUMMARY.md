# Session 2026-07-23 — Deliverables Summary

**Duration:** Full investigation session  
**Status:** Complete (ready for handoff)  
**Outcome:** Specification ready for implementation by next agent  

---

## Deliverables Created

### 1. **docs/SLAVA-REFERENCE.md** (11 KB)
**Purpose:** Understand who Slava is and what reference materials exist

**Contents:**
- Who is Slava (Vyacheslav Tretyachenko, original TARSUS author)
- What reference code exists (13 scripts in TARSUS_elizabev/)
- Reference runs (EVpar ground truth, hoMS/GAPDH validation, AlaGGC test data)
- Reference experimental data (9-tRNA panel in slavat/coli_trna/)
- How to use the reference in practice
- Where code quality diverges (bugs found in reference)

**Use case:** New developer needs to understand the origin and purpose of Slava's code.

---

### 2. **docs/CODE-LEVEL-COMPARISON.md** (30 KB)
**Purpose:** Deep dive into code differences between reference and TARSUS_BC

**Contents:**
- High-level architecture (reference vs ours)
- Step-by-step code comparison (all 11 steps)
- Critical data transformations (title namespace, matrix transposition)
- Data flow examples with real numbers
- Output schema comparison
- Summarized differences table
- Code quality divergences
- Cross-run consistency checks
- Recommended next steps

**Use case:** Understanding why our pipeline produces different results (versions, design choices, bugs fixed).

---

### 3. **docs/BUG-MISSING-SPECTRAL-SIM.md** (6 KB)
**Purpose:** Bug report documenting the missing columns issue

**Contents:**
- Summary (2 missing columns, 69 vs 67)
- Evidence (column-by-column comparison)
- Root cause analysis with data flow trace
- Where columns come from (PepQuery vs PDV)
- Why they're lost (join operation drops them)
- Quick fix options (3 approaches)
- Verification steps

**Use case:** Quick reference for the bug; diagnostic starting point.

---

### 4. **docs/SPEC-MISSING-SPECTRAL-SIM.md** (20 KB) ⭐ **PRIMARY HANDOFF**
**Purpose:** Complete implementation specification (ready for developer)

**Contents:**
- Problem statement (with evidence)
- Root cause analysis (detailed)
- Solution design (2-component architecture)
- Detailed functional + non-functional requirements
- Implementation plan (4 phases: investigation, design, implementation, validation)
- Files to modify (3 files, impact analysis)
- Pseudocode (ready to implement, all 3 files)
- Detailed requirements table
- Data files affected (Steps 6-11 only; 1-5 untouched)
- Acceptance criteria (before/after checklists)
- Risk assessment (likelihood, impact, mitigation)
- Rollback plan
- Success metrics
- Full column reference (all 69 expected columns)
- PDV investigation commands (Appendix A)

**Use case:** This is the developer's roadmap for implementing the fix.

---

### 5. **HANDOFF-SPECTRAL-SIM.md** (5 KB) ⭐ **QUICK START**
**Purpose:** 5-minute read for next agent; quick actionable summary

**Contents:**
- Issue (1 min read)
- Root cause (1 min read)
- What to do (5 min implementation)
- Complete guide pointer
- Commands to run after
- Verification checklist
- Rollback instructions
- Context files reference
- Expected outcome
- Time estimate (~90 min)

**Use case:** Agent picks this up tomorrow, reads 5 min, knows exactly what to do.

---

## Work Completed

### Investigative Work
- ✅ Located Slava's reference code and runs
- ✅ Identified exact columns missing (SpectralSim, RTScore)
- ✅ Traced data flow to find where columns are lost
- ✅ Diagnosed root cause (join operation)
- ✅ Verified columns exist in reference output
- ✅ Verified columns missing in our output

### Diagnostic Work
- ✅ Column-by-column comparison (reference vs ours)
- ✅ Data file inspection (psmrankall.txt, PDVExportResult.txt, subs_localized.csv)
- ✅ Determined columns are in PepQuery output but not PDV export
- ✅ Identified probable solution (PDV text report mode)

### Documentation Work
- ✅ Created 5 comprehensive documents
- ✅ 71 KB total documentation
- ✅ Pseudocode ready to implement
- ✅ Acceptance criteria defined
- ✅ Rollback plan documented
- ✅ Risk assessment completed

### No Code Changes
- ❌ Did NOT implement the fix (per user request)
- ❌ Did NOT modify any source files
- ❌ Did NOT run the pipeline (preserve existing outputs)

---

## Key Findings

### The Bug
```
Our Step 11 output:     67 columns (missing SpectralSim, RTScore)
Reference Step 11 output: 69 columns
```

### Root Cause
Step 7 join operation in `step07_analyze_outputs.py`:
```python
# Current (loses columns)
merged = psm_df.join(pdv_df, on='spectrum_title', how='inner')
# psm_df has SpectralSim, RTScore (from PepQuery)
# pdv_df does NOT have these (only has ion data)
# → columns get dropped on join
```

### Solution Approach
1. Extract SpectralSim, RTScore from PDV text report mode (Step 6)
2. Use LEFT join instead of INNER join to preserve all columns (Step 7)
3. Validate columns present before output (Step 11)

### Implementation Scope
- 3 files to modify (~200 lines total)
- No changes to Steps 1-5 (data already computed)
- Steps 6-11 need re-execution
- Expected runtime: ~90 min (45 min code, 30 min re-run, 15 min verify)

---

## Files to Read in Order

**For quick start (5 min):**
1. `HANDOFF-SPECTRAL-SIM.md` ← **START HERE**

**For implementation (45 min):**
2. `docs/SPEC-MISSING-SPECTRAL-SIM.md` → Section "Pseudocode" → copy and adapt

**For understanding the full context:**
3. `docs/BUG-MISSING-SPECTRAL-SIM.md` (understand the bug)
4. `docs/CODE-LEVEL-COMPARISON.md` (understand the pipeline)
5. `docs/SLAVA-REFERENCE.md` (understand the reference)

---

## Next Agent's Checklist

### Before Starting
- [ ] Read `HANDOFF-SPECTRAL-SIM.md` (5 min)
- [ ] Skim `docs/SPEC-MISSING-SPECTRAL-SIM.md` → "Solution Design" section
- [ ] Verify PDV has `-ft report` mode (Appendix A in spec)

### Implementation
- [ ] Modify `src/tarsus/steps/step06_aggregate_query.py`
- [ ] Modify `src/tarsus/steps/step07_analyze_outputs.py`
- [ ] Modify `src/tarsus/steps/step11_localize.py`
- [ ] Add unit tests (step06, step07)
- [ ] Update `.memory/decisions.md` with new decision (D-0XX)

### Validation
- [ ] Delete Step 6-11 sentinels
- [ ] Re-run pipeline (Steps 6-11)
- [ ] Verify output has 69 columns
- [ ] Compare with reference file
- [ ] Check SpectralSim, RTScore have values

### Completion
- [ ] All acceptance criteria met
- [ ] Tests pass
- [ ] Commit changes with decision reference

---

## Where Everything Is

```
/home/labs/pilpel/barc/TARSUS_BC/

├── HANDOFF-SPECTRAL-SIM.md          ← QUICK START (5 min)
│
├── docs/
│   ├── SLAVA-REFERENCE.md           ← Who/what is the reference
│   ├── CODE-LEVEL-COMPARISON.md     ← Full code comparison
│   ├── BUG-MISSING-SPECTRAL-SIM.md  ← Bug details
│   └── SPEC-MISSING-SPECTRAL-SIM.md ← IMPLEMENTATION SPEC ⭐
│
├── .memory/
│   ├── progress.md                  ← Updated with this session
│   └── decisions.md                 ← (For next decision: D-0XX)
│
└── src/tarsus/steps/
    ├── step06_aggregate_query.py    ← Modify
    ├── step07_analyze_outputs.py    ← Modify
    └── step11_localize.py           ← Modify
```

---

## Success Definition

When the next agent is done:
- ✅ `subs_localized.csv` has 69 columns (not 67)
- ✅ Columns 18-19 are SpectralSim, RTScore
- ✅ All values are numeric (not NaN)
- ✅ Row count unchanged
- ✅ Schema matches reference exactly
- ✅ Tests pass
- ✅ Git commit includes reference to this analysis

---

## Context for Maintenance

**Why this matters:**
- Slava reported the missing columns (they're important)
- Output schema must match reference for validation
- These columns are quality metrics (could be used for filtering/ranking)

**Why it wasn't implemented:**
- Per user request: "build spec, don't perform fix"
- Better to hand off complete spec than partial implementation

**Why it's low-risk:**
- Only affects Steps 6-11 output
- Steps 1-5 data already computed (no re-acquisition needed)
- Clear rollback path if something goes wrong

---

**READY FOR HANDOFF**

Next agent can start immediately with `HANDOFF-SPECTRAL-SIM.md`.

All investigation complete. All decisions documented.

Estimated implementation time: 90 minutes.
