# Specification: Restore Missing `SpectralSim` and `RTScore` Columns in Step 11 Output

**Document ID:** SPEC-2026-07-23-SPECTRAL-SIM  
**Status:** DRAFT - awaiting implementation  
**Date:** 2026-07-23  
**Author:** Analysis of reference vs TARSUS_BC output  
**Ticket:** Slava reported missing columns in subs_localized.csv  

---

## Problem Statement

The TARSUS_BC Step 11 output (`subs_localized.csv` / `subs_localized.ipc`) is missing 2 metadata columns that are present in the reference pipeline's output:

1. **Column 18: `SpectralSim`** — Spectral similarity score from PepQuery
2. **Column 19: `RTScore`** — Retention time score (from IonQuant or PepQuery RT prediction)

**Evidence:**
- Reference output: 69 columns (includes SpectralSim, RTScore)
- TARSUS_BC output: 67 columns (missing SpectralSim, RTScore)
- Column positions shift: our column 18 is their column 20 (Expectation), etc.

**Data location:**
- Reference: `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs_localized.csv` (line 1, columns 18-19)
- Ours: `/home/labs/pilpel/barc/TARSUS_BC/output/trial/11_localized/subs_localized.csv` (missing these)

---

## Root Cause Analysis

### Data Flow Trace

```
Step 5 (PepQuery):
  pepquery_result/*/psm_rank.txt
  └─ Contains columns: peptide, modification, n, spectrum_title, charge, ..., score, ..., confident
  └─ (22 columns total from PepQuery)

Step 6 (Aggregation):
  psmrankall.txt (concatenated from all chunks)
  └─ Headers added by sed in aggregate_query.sh
  └─ Contains all 22 columns from PepQuery, PLUS headers

Step 6b (PDV Export):
  pdv_spectra/PDVExportResult.txt
  └─ Contains: Spectrum_Title, peptide, charge, #b_ions, #y_ions, #by_pairs, Ratio, ions, ions_mz, ions_int
  └─ (10 columns from PDV — does NOT include SpectralSim, RTScore)

Step 7 (Filtering):
  subs.ipc (from Step 7)
  ├─ Reads: psmrankall.txt
  ├─ Joins with: PDVExportResult.txt (ion data only)
  ├─ Problem: join operation drops columns from psmrankall.txt that don't have a match in PDVExportResult
  └─ Result: SpectralSim, RTScore are lost (they exist in psmrankall but not in PDV export)

Step 11 (Localization):
  subs_localized.ipc
  └─ Reads: subs.ipc (already missing SpectralSim, RTScore)
  └─ Result: Final output has columns already stripped from Step 7
```

### Where Do SpectralSim and RTScore Come From?

**Hypothesis 1: PepQuery Output**
- PepQuery generates `psm_rank.txt` with base scores
- These may not include SpectralSim/RTScore in the standard output
- Possibility: PepQuery has alternative output modes that include these

**Hypothesis 2: PDV Text Report Mode**
- Slava's code has commented-out `-ft report` flag for PDV
- Text report mode might output additional metrics alongside ion data
- Currently only using `-ft pdf` (PDF output only)

**Hypothesis 3: IonQuant Integration**
- FragPipe's IonQuant module generates RT scores
- These should be in the Step 6 pipeline somewhere
- May need to be explicitly extracted/merged

**Verification needed:** Check what columns PDV's text report mode actually produces.

---

## Solution Design

### Approach: PDV Text Report Mode + Preserved Join

**Rationale:**
1. Slava's reference uses PDV (implied by commented-out code)
2. Text report mode likely contains these columns
3. Preserve join semantics to keep all PepQuery columns

### Components to Modify

#### Component 1: Step 6 — PDV Invocation

**File:** `src/tarsus/steps/step06_aggregate_query.py`

**Current:**
```python
cmd = [
    str(pdv_exe),
    "-Djava.awt.headless=true",
    f"-Xmx{pdv_heap_mb}m",
    "-jar", str(pdv_exe),
    "-i", str(shard_file),
    "-o", str(output_dir / f"pdv_shard_{shard_id}"),
    "-e", "tsv",        # ← outputs TSV but where?
]
```

**Proposed Change:**

- Add `-ft report` flag to generate text report output (in addition to existing TSV/PDF)
- Parse text report to extract SpectralSim, RTScore per spectrum
- Create a lookup table: `{spectrum_title: (SpectralSim, RTScore)}`
- Store as a CSV or pickle for Step 7 to read

```python
# Pseudocode
cmd = [
    ...,
    "-ft", "report",  # ADD: Text report mode
]

# After running PDV:
# Read pdv_report.txt (or whatever the output is called)
pdv_report = read_pdv_text_report(output_dir / "report.txt")

# Extract columns of interest
report_metrics = pdv_report[['Spectrum_Title', 'SpectralSim', 'RTScore']].to_dict('list')

# Store for Step 7
output_dir.joinpath('pdv_report_metrics.csv').write_csv(
    report_metrics,
    separator='\t'
)
```

#### Component 2: Step 7 — Column Preservation in Join

**File:** `src/tarsus/steps/step07_analyze_outputs.py`

**Current Logic (Problematic):**
```python
merged = psm_df.join(
    pdv_df[['Spectrum_Title', 'spectrum_title']],
    on='spectrum_title',
    how='inner'
)
# Problem: psm_df columns are implicitly dropped if not in pdv_df
```

**Proposed Change:**

- Read PDV metrics CSV (from Step 6)
- Perform a LEFT or INNER join that preserves ALL columns from `psm_df`
- Only add PDV ion columns from `pdv_df`

```python
# Pseudocode
subs = pl.read_ipc(subs_ipc)
psm_df = read_psmrankall(psmrankall_file)  # All 22 PepQuery columns

# Read PDV report metrics
pdv_metrics = pl.read_csv(pdv_report_metrics_file, separator='\t')

# Join: preserve all psm columns
psm_with_metrics = psm_df.join(
    pdv_metrics[['spectrum_title', 'SpectralSim', 'RTScore']],
    on='spectrum_title',
    how='left',  # LEFT: keep all psm rows even if no PDV metrics
)

# pdv_export still has ion data
pdv_export = read_pdv_export(pdv_export_file)

# Add ions to the enriched PSM table
full = psm_with_metrics.join(
    pdv_export[['Spectrum_Title', 'ions', 'ions_mz', 'ions_int']],
    left_on='spectrum_title',
    right_on='Spectrum_Title',
    how='left',
)

# Now full has:
# - All 22 original PepQuery columns (including SpectralSim, RTScore)
# - Ion data from PDV
```

#### Component 3: Step 7 → Step 11 Data Flow

**File:** `src/tarsus/steps/step07_analyze_outputs.py` and `src/tarsus/steps/step11_localize.py`

**Requirement:** Ensure that subs.ipc contains SpectralSim and RTScore columns

**Implementation:**
```python
# In step07_analyze_outputs.py, when writing subs.ipc:
result = full.filter(...)  # Apply filtering logic

# Ensure these columns are present before write
required_cols = [
    'spectrum_title', 'peptide', 'Charge', 'Retention', ...,
    'SpectralSim', 'RTScore',  # ADD: ensure present
    ...
]

missing = [c for c in required_cols if c not in result.columns]
if missing:
    raise ValueError(f"Missing columns in subs.ipc: {missing}")

result.write_ipc(subs_ipc)

# In step11_localize.py, when reading subs.ipc:
subs = pl.read_ipc(subs_ipc)

# Verify columns survived the journey
if 'SpectralSim' not in subs.columns:
    raise ValueError("SpectralSim not in Step 7 output — fix Step 7 join")
if 'RTScore' not in subs.columns:
    raise ValueError("RTScore not in Step 7 output — fix Step 7 join")

# Write to final output, preserving these columns
localized = subs.filter(...)
localized.write_ipc(output_ipc)
localized.write_csv(output_csv)
```

---

## Detailed Requirements

### Functional Requirements

| ID | Requirement | Acceptance Criterion |
|---|---|---|
| FR-1 | Extract SpectralSim from PDV output | PDV text report contains `SpectralSim` column |
| FR-2 | Extract RTScore from PDV output | PDV text report contains `RTScore` column |
| FR-3 | Preserve PepQuery columns in Step 7 join | All 22 PepQuery columns in subs.ipc |
| FR-4 | Include columns in final output | subs_localized.csv has 69 columns (not 67) |
| FR-5 | Column order matches reference | Columns 18-19 are SpectralSim, RTScore |
| FR-6 | No data loss on join | All spectra/rows preserved across joins |

### Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-1 | No changes to Step 1-5 (data already computed) |
| NFR-2 | Minimal performance impact (joins should be O(n) ) |
| NFR-3 | Backward compatible (old subs.ipc not reused) |
| NFR-4 | Clear error messages if columns missing |

---

## Implementation Plan

### Phase 1: Investigation & Validation

**Tasks:**
1. Verify PDV has `-ft report` mode
   ```bash
   java -jar tools/PDV-2.1.2/PDV-2.1.2.jar -h | grep -A 2 "\-ft"
   ```
   
2. Check what columns are in PDV text report
   ```bash
   # Run PDV with -ft report on a small sample
   java -jar PDV-2.1.2.jar \
     -r /path/to/psmrankall.txt \
     -ft report \
     -o /tmp/pdv_test/
   
   # List output files and their contents
   ls -la /tmp/pdv_test/
   head -1 /tmp/pdv_test/report.txt | tr '\t' '\n' | nl
   ```

3. Confirm these columns are in Slava's psmrankall.txt
   ```bash
   head -1 /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/psmrankall.txt | tr '\t' '\n' | nl
   ```

### Phase 2: Design Validation

**Tasks:**
1. Map where SpectralSim, RTScore should come from (PDV vs PepQuery vs IonQuant)
2. Document the exact data flow with column tracking
3. Get sign-off on design before code changes

### Phase 3: Implementation

**Tasks:**
1. Modify `step06_aggregate_query.py` to call PDV with `-ft report` and parse output
2. Modify `step07_analyze_outputs.py` to use LEFT join (preserve all PSM columns)
3. Add unit tests for column preservation
4. Add integration test: compare output schema with reference

### Phase 4: Validation & Verification

**Tasks:**
1. Re-run Steps 6-11 on trial data
2. Verify subs_localized.csv has 69 columns
3. Compare columns 1-69 with reference file (row-by-row)
4. Check that SpectralSim and RTScore values are reasonable (not NaN)
5. Re-run on hoMS/GAPDH data and compare

---

## Files to Be Modified

| File | Change Type | Impact | Reason |
|---|---|---|---|
| `src/tarsus/steps/step06_aggregate_query.py` | Add PDV text report parsing | Medium | Extract SpectralSim, RTScore from PDV |
| `src/tarsus/steps/step07_analyze_outputs.py` | Change join logic | Low | Preserve PepQuery columns |
| `src/tarsus/steps/step11_localize.py` | Add column validation | Low | Verify columns present before output |
| `tests/unit/test_step06.py` | Add test | Low | Verify PDV metrics extraction |
| `tests/unit/test_step07.py` | Add test | Low | Verify column preservation on join |
| `.memory/decisions.md` | Document decision | - | Record D-0XX decision |

---

## Data Files Affected

**No regeneration of Steps 1-5 required.** Only Steps 6-11 need re-execution.

| Step | Re-run? | Reason |
|---|---|---|
| 1-5 | NO | Data already computed |
| 6 | YES | Need PDV text report output |
| 7 | YES | Need to preserve PepQuery columns |
| 8 | YES | Depends on Step 7 output |
| 9-10 | Possibly | Depends on Step 8 |
| 11 | YES | Final output, needs all columns |

---

## Acceptance Criteria

### Before Implementation

- [ ] Investigation phase complete (PDV `-ft report` confirmed available)
- [ ] Design reviewed and approved
- [ ] All files to modify identified and listed
- [ ] Test plan written

### After Implementation

- [ ] `subs_localized.csv` has exactly 69 columns (not 67)
- [ ] Columns 18-19 are `SpectralSim`, `RTScore`
- [ ] Column order matches reference file exactly
- [ ] All SpectralSim values are numeric (not NaN/null)
- [ ] All RTScore values are numeric (not NaN/null)
- [ ] Unit tests pass (step06, step07 column logic)
- [ ] Integration test passes (full Steps 6-11 re-run)
- [ ] Head-to-head comparison with reference on hoMS/GAPDH:
  - [ ] Column counts match (69 vs 69)
  - [ ] Column names match (exact order)
  - [ ] Data types match
  - [ ] No NaN where reference has data

### For Validation

- [ ] Compare `subs_localized.csv` row-by-row with reference:
  - [ ] Spectrum titles match
  - [ ] Substitutions match (100% agreement on shared spectra)
  - [ ] SpectralSim values are sensible (e.g., 0-1 range or raw score)
  - [ ] RTScore values are sensible

---

## Pseudocode / Implementation Sketch

### Step 6: PDV Text Report Extraction

```python
# src/tarsus/steps/step06_aggregate_query.py

def run_pdv_with_report(
    psmrankall_file: Path,
    mgf_file: Path,
    peptides_file: Path,
    output_dir: Path,
    pdv_exe: Path,
    ...
) -> tuple[Path, Path]:
    """Run PDV and extract text report metrics.
    
    Returns: (pdv_metrics_csv, ion_export_file)
    """
    
    # 1. Run PDV with -ft report
    cmd = [
        str(pdv_exe),
        "-r", str(psmrankall_file),
        "-s", str(mgf_file),
        "-i", str(peptides_file),
        "-o", str(output_dir / "pdv_report"),
        "-ft", "report",  # ADD: text report mode
    ]
    
    result = subprocess.run(cmd, check=True, capture_output=True)
    
    # 2. Locate and parse PDV text report output
    # (Note: PDV's actual output filename needs to be discovered)
    pdv_report_file = output_dir / "pdv_report" / "report.txt"  # or similar
    
    if not pdv_report_file.exists():
        raise FileNotFoundError(f"PDV report not found: {pdv_report_file}")
    
    # 3. Read report and extract columns
    report = pl.read_csv(pdv_report_file, separator='\t')
    
    # 4. Check for expected columns
    required = ['Spectrum_Title', 'SpectralSim', 'RTScore']
    missing = [c for c in required if c not in report.columns]
    if missing:
        raise ValueError(f"PDV report missing: {missing}")
    
    # 5. Extract and save metrics
    metrics = report.select(['Spectrum_Title', 'SpectralSim', 'RTScore'])
    metrics = metrics.rename({'Spectrum_Title': 'spectrum_title'})
    
    metrics_file = output_dir / "pdv_metrics.csv"
    metrics.write_csv(metrics_file, separator='\t')
    
    # 6. Also run for ion data (existing PDV call)
    # ... (existing ion extraction code)
    
    return metrics_file, ion_export_file
```

### Step 7: Preserved Join

```python
# src/tarsus/steps/step07_analyze_outputs.py

def analyze_outputs(
    psmrankall_file: Path,
    pdv_metrics_file: Path,  # NEW parameter
    pdv_export_file: Path,
    ...
) -> Path:
    """Analyze and filter with preserved column set."""
    
    # 1. Read PepQuery PSM results (all 22 columns)
    psm_df = pl.read_csv(psmrankall_file, separator='\t')
    
    # 2. Read PDV metrics (SpectralSim, RTScore)
    pdv_metrics = pl.read_csv(pdv_metrics_file, separator='\t')
    
    # 3. Merge metrics into PSM table
    psm_enriched = psm_df.join(
        pdv_metrics,
        on='spectrum_title',
        how='left',  # LEFT: keep all PSM rows
        suffix='_pdv_metrics',
    )
    
    # 4. Read PDV ion data
    pdv_export = pl.read_csv(pdv_export_file, separator='\t')
    
    # 5. Add ion data (but only ion columns, not other stuff)
    full = psm_enriched.join(
        pdv_export.select(['Spectrum_Title', 'ions', 'ions_mz', 'ions_int']),
        left_on='spectrum_title',
        right_on='Spectrum_Title',
        how='left',
        suffix='_pdv_ions',
    )
    
    # 6. Apply filtering logic (existing)
    result = full.filter(
        (pl.col('confident') == 'Yes') | (pl.col('singleSubstitution') == True)
    )
    
    # 7. Verify columns are present
    expected = [
        'peptide', 'spectrum_title', 'Charge', 'Retention',
        'SpectralSim', 'RTScore',  # Ensure these are here
        'ions', 'ions_mz', 'ions_int',
        ...
    ]
    missing = [c for c in expected if c not in result.columns]
    if missing:
        raise ValueError(f"Missing expected columns: {missing}")
    
    # 8. Write output (columns are preserved)
    result.write_ipc(subs_ipc)
    
    return subs_ipc
```

### Step 11: Column Validation

```python
# src/tarsus/steps/step11_localize.py

def localize(...) -> pl.DataFrame:
    """Localize with column validation."""
    
    subs = pl.read_ipc(subs_ipc)
    
    # Verify SpectralSim and RTScore survived Step 7
    if 'SpectralSim' not in subs.columns:
        raise ValueError(
            "SpectralSim not in Step 7 output. "
            "Check step07_analyze_outputs join logic."
        )
    if 'RTScore' not in subs.columns:
        raise ValueError(
            "RTScore not in Step 7 output. "
            "Check step07_analyze_outputs join logic."
        )
    
    # ... rest of localization logic
    
    localized = subs.filter(pl.col('spectrum_title').is_in(sure_titles))
    
    # Output preserves all columns including SpectralSim, RTScore
    localized.write_ipc(output_ipc)
    localized.write_csv(output_csv)
    
    return localized
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PDV `-ft report` not available or different name | Low | Blocks implementation | Investigate during Phase 1 |
| Column names different from expected | Low | Requires mapping | Document actual PDV output |
| Data loss on join (misaligned keys) | Very Low | Missing rows | Unit tests + row count checks |
| Performance regression | Very Low | Slower Steps 6-7 | Profile before/after |
| Schema mismatch with reference | Low | Validation fails | Compare column-by-column |

---

## Rollback Plan

If the implementation causes issues:

1. Revert changes to `step06_aggregate_query.py`, `step07_analyze_outputs.py`, `step11_localize.py`
2. Restore from git: `git checkout HEAD -- src/tarsus/steps/`
3. Re-run Steps 6-11 using checkpoint sentinels (Steps 1-5 untouched)
4. Verify old output is restored

---

## Success Metrics

| Metric | Target | Method |
|---|---|---|
| Column count | 69 | `wc -F, subs_localized.csv` |
| Column names | Match reference exactly | `diff <(headers reference) <(headers ours)` |
| SpectralSim NaN rate | < 1% | `grep -c ",,," subs_localized.csv` |
| RTScore NaN rate | < 1% | `grep -c ",,," subs_localized.csv` |
| Agreement on shared spectra | 100% | Manual spot check on 10 rows |

---

## References

- **Reference output:** `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs_localized.csv`
- **Our output:** `/home/labs/pilpel/barc/TARSUS_BC/output/trial/11_localized/subs_localized.csv`
- **Comparison report:** `docs/PIPELINE-COMPARISON.md`
- **Bug report:** `docs/BUG-MISSING-SPECTRAL-SIM.md`

---

## Appendix A: PDV Investigation Commands

```bash
# Check PDV help for available output formats
java -jar tools/PDV-2.1.2/PDV-2.1.2.jar -h | grep -E "(^-|ft)"

# Test PDV text report on small sample
mkdir -p /tmp/pdv_test_report
java -jar tools/PDV-2.1.2/PDV-2.1.2.jar \
  -r output/trial/06_aggregated/psmrankall.txt \
  -s output/trial/06_aggregated/mgfall.mgf \
  -i output/trial/06_aggregated/peptides.txt \
  -o /tmp/pdv_test_report \
  -ft report

# Inspect output
ls -la /tmp/pdv_test_report/
head -5 /tmp/pdv_test_report/*.txt 2>/dev/null | head -20
```

---

## Appendix B: Column Order Reference

### Expected Final Output (69 columns)

```
1.  Spectrum
2.  Spectrum File
3.  dependent
4.  Modified Peptide
5.  Extended Peptide
6.  Prev AA
7.  Next AA
8.  Peptide Length
9.  Charge
10. Retention
11. Observed Mass
12. Calibrated Observed Mass
13. Observed M/Z
14. Calibrated Observed M/Z
15. Calculated Peptide Mass
16. Calculated M/Z
17. Delta Mass
18. SpectralSim              ← CRITICAL (currently missing)
19. RTScore                  ← CRITICAL (currently missing)
20. Expectation
21. Hyperscore
22. Nextscore
23. Probability
24. Qvalue
25. Number of Enzymatic Termini
26. Number of Missed Cleavages
27. Protein Start
28. Protein End
29. second_intensity
30. Assigned Modifications
31. Observed Modifications
32. Purity
33. Is Decoy
34. Is Contaminant
35. Is Unique
36. Protein
37. Protein ID
38. Entry Name
39. Gene
40. Protein Description
41. Mapped Genes
42. Mapped Proteins
43. Parent Scan Number
44. Apex Retention Time
45. Apex Scan Number
46. Retention Time Start
47. Retention Time End
48. Retention Time FWHM
49. Traced Scans
50. base
51. spectrum_title
52. Spectrum_first
53. Prev AA_first
54. Next AA_first
55. Protein_first
56. first_intensity
57. Retention_first
58. Protein Start_first
59. Protein End_first
60. Mapped Proteins_first
61. Hyperscore_first
62. Extended Peptide_first
63. Number of Missed Cleavages_first
64. Is Unique_first
65. mistranslated_pos
66. origin
67. destination
68. misProt
69. dpbp
```

---

**END OF SPECIFICATION**

**Next steps:** 
1. Review this spec
2. Approve for implementation (or request changes)
3. Move to Phase 1 Investigation
