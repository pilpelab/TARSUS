# Discovery Flowchart: Where Do SpectralSim & RTScore Come From?

## Investigation Trail 🔍

### Initial Question
"Where do `SpectralSim` and `RTScore` come from?"

```
Step 11 Output (subs_localized.csv)
  └─ Missing columns at pos 18-19
     └─ Check Step 11 code
        └─ Just passes through from Step 7
           └─ CHECK STEP 7 ✓
```

### Step 7 Investigation

```
Step 7 reads from:
  ├─ first_psm_path (FragPipe first-pass)
  ├─ second_psm_path (FragPipe second-pass)
  ├─ ptmall_path (PepQuery PTM results)
  ├─ psmrankall_path (Aggregated PepQuery PSMs)
  └─ pdv_path (PDV ion evidence)

WHERE ARE SpectralSim & RTScore?
  Check each source:
  ├─ PepQuery results? NO (only 22 columns)
  ├─ PDV data? NO (only 10 columns)
  ├─ psmrankall? NO (same as PepQuery)
  ├─ FragPipe first-pass? LET'S CHECK! ✓
```

### Breakthrough Discovery

```
FragPipe first-pass PSM output (psm.tsv)
  Column 1: Spectrum
  Column 2: Spectrum File
  ...
  Column 17: Delta Mass
  Column 18: SpectralSim                    ← FOUND IT! ✅
  Column 19: RTScore                        ← FOUND IT! ✅
  Column 20: Expectation
  ...
  Column 49: (total columns)
```

### Data Verification

```
Our FragPipe output file:
  /output/trial/03a_first_pass/psm.tsv

Check column headers:
  head -1 psm.tsv | tr '\t' '\n' | nl | grep -E "Spectral|RTScore"
  
Output:
    18	SpectralSim                           ✅
    19	RTScore                               ✅
```

### Sample Data

```
Row 1: SpectralSim=0.8675, RTScore=0.0591
Row 2: SpectralSim=0.9588, RTScore=1.4539
Row 3: SpectralSim=0.6045, RTScore=1.1296
...
(All rows have numeric values - no nulls)
```

---

## The Bug Discovery 🐛

### Question: "Why don't these columns appear in Step 7 output?"

```
Step 7 reads: first_psms = pl.read_csv(first_psm_path)
  └─ first_psms has all 49 columns (including SpectralSim & RTScore)
     ├─ first_psms shape: (6820 rows, 49 columns) ✅
     └─ Columns visible when inspected directly ✅

Then Step 7 does: first_sub = first_psms.select([...])
  └─ Selects only 15 specific columns
  └─ "SpectralSim" NOT in the list ❌
  └─ "RTScore" NOT in the list ❌
  └─ Result: first_sub has only 15 columns ❌

When joined with second_psms:
  └─ Missing columns never reappear downstream ❌
  └─ subs.ipc has 67 columns instead of 69 ❌
```

### Root Cause Diagram

```
┌─────────────────────────────────────────────────┐
│ FragPipe PSM Output (49 columns)                │
│ Includes: SpectralSim ✓, RTScore ✓            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ first_psms = pl.read_csv(first_psm_path)       │
│ (49 columns, all present)                       │
│ Includes: SpectralSim ✓, RTScore ✓            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ first_sub = first_psms.select([                │
│   "Spectrum", "base", ..., "Is Unique"         │
│   ← SpectralSim NOT in this list!              │
│   ← RTScore NOT in this list!                  │
│ ])                                              │
│ (15 columns, MISSING CRITICAL ONES)            │
└──────────────────┬──────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────┐
│ joined = second_psms.join(first_sub)           │
│ (columns from first_sub are appended)          │
│ Result: 67 columns (missing 2)                 │
│ ← No SpectralSim, RTScore in final output      │
└─────────────────────────────────────────────────┘
```

---

## The Fix Applied ✅

### Change 1: Include the Missing Columns

```
┌─────────────────────────────────────────────────┐
│ first_sub = first_psms.select([                │
│   "Spectrum", "base", ..., "Is Unique",        │
│   "SpectralSim", "RTScore"  ← ADDED!           │
│ ])                                              │
│ (17 columns, all critical ones included)       │
└──────────────────┬──────────────────────────────┘
```

### Change 2: Reorder to Match Schema

```
After join, columns are appended:
  [..., Expectation, ..., [other 50 cols], SpectralSim, RTScore]

After reordering:
  [..., Delta Mass, SpectralSim, RTScore, Expectation, ...]
  (positions adjusted to match reference)
```

### Result

```
┌─────────────────────────────────────────────────┐
│ subs.ipc Output                                 │
│ - Total columns: 69 (vs 67 before) ✅          │
│ - Position 18: SpectralSim ✅                  │
│ - Position 19: RTScore ✅                       │
│ - Schema matches reference exactly ✅           │
└─────────────────────────────────────────────────┘
```

---

## Data Source Summary 📊

```
╔════════════════════════════════════════════════════╗
║ SPECTRAL SIMILARITY & RT SCORE: DATA SOURCES      ║
╠════════════════════════════════════════════════════╣
║                                                    ║
║ SpectralSim (Column 18)                           ║
║   Source: Philosopher (FragPipe component)        ║
║   Purpose: Spectral similarity score              ║
║   Range: ~0-1                                     ║
║   Generated: During first-pass search             ║
║   Available in: psm.tsv                           ║
║   Sample values: 0.86, 0.95, 0.60, 0.76, 0.87    ║
║                                                    ║
║ RTScore (Column 19)                               ║
║   Source: MSBooster (FragPipe component)          ║
║   Purpose: RT prediction accuracy score           ║
║   Generated: Post-search via ML model             ║
║   Available in: psm.tsv                           ║
║   Sample values: 0.06, 1.45, 1.13, 0.05, 1.97    ║
║                                                    ║
╚════════════════════════════════════════════════════╝
```

---

## Timeline of Investigation ⏰

```
14:00 - Start investigation
  └─ Check if PDV has text report mode
  └─ Check MSBooster output
  └─ Check IonQuant output
  
15:00 - Dead end on PDV/external tools
  └─ Check if columns computed somewhere
  └─ Check reference analyze_outputs.py
  
15:15 - BREAKTHROUGH! ✨
  └─ Check reference psm.tsv header
  └─ FOUND: SpectralSim at column 18
  └─ FOUND: RTScore at column 19
  
15:20 - Check our FragPipe output
  └─ Verify our psm.tsv has them too
  └─ Confirm data is present
  
15:25 - Find the bug
  └─ Trace Step 7 column selection
  └─ See they're excluded from first_sub
  
15:30 - Implement fix
  └─ Add columns to selection
  └─ Add reordering logic
  └─ Add validation
  
16:00 - Test fix
  └─ Full pipeline run
  └─ Verify 69 columns
  └─ Check data quality
  
16:20 - SUCCESS! ✅
  └─ All verification tests pass
  └─ Schema matches reference exactly
```

---

**Key Insight:** The data was there all along - it just needed to be preserved through Step 7's join operation instead of being filtered out during column selection.
