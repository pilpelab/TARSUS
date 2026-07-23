# Progress: Missing SpectralSim and RTScore Columns

**Last Updated:** 2026-07-23  
**Status:** Implementation Phase Complete (50%)

## Completed

### Investigation Phase (✅ Done)
- Identified exact problem: 2 missing columns (SpectralSim, RTScore)
- Located reference data: `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc`
- Confirmed reference has 69 columns with these fields at positions 18-19
- Investigated data flow through all pipeline steps
- Analyzed PDV, PepQuery, FragPipe outputs (no source found in existing outputs)
- Reviewed reference code and documentation

### Implementation Phase (✅ Done)
- ✅ Modified `step07_analyze_outputs.py`:
  - Added placeholder columns for SpectralSim and RTScore
  - Implemented column reordering to place them in correct positions (18-19)
  - Columns currently populated with NaN (awaiting actual data source)

- ✅ Modified `step11_localize.py`:
  - Added validation to ensure required columns are present
  - Will fail fast with clear error message if columns missing

- ✅ Code compilation verified for both files
- ✅ Column addition logic tested and working

## In Progress / Blocked

### Data Population (⚠️ Needs Action)
- Columns exist but are empty (NaN)
- Need to discover where SpectralSim and RTScore actually come from
- Likely source: PDV text report mode (already configured but not parsed)
- Alternative sources: MSBooster, IonQuant

### Full Pipeline Test (⚠️ Needs Full Data)
- End-to-end test not completed due to partial data availability
- Ready to test once someone runs with complete input data (Steps 1-6)

## Next Steps (Priority Order)

1. **[CRITICAL] Populate actual values**
   - Investigate PDV text report mode output format
   - Modify Step 6 to extract and save metrics
   - Modify Step 7 to read and merge metrics
   - Test that output values are sensible

2. **Validate with reference**
   - Compare output column-by-column with reference
   - Verify row-by-row agreement on shared spectra
   - Check statistical properties of scores

3. **Full pipeline test**
   - Run steps 6-11 with complete input data
   - Verify 69 columns in output
   - Spot-check some rows against reference

## Risks & Unknowns

- ⚠️ Source of SpectralSim/RTScore columns unclear
- ⚠️ PDV text report format unknown (never executed successfully)
- ⚠️ Placeholder NaN values might break downstream steps
- ⚠️ Alternative implementations might be needed if PDV doesn't provide scores

## Files Modified

- `src/tarsus/steps/step07_analyze_outputs.py` - Added column infrastructure
- `src/tarsus/steps/step11_localize.py` - Added validation

## Time Spent

- Investigation: ~2 hours (traced all data sources)
- Implementation: ~30 minutes (code changes + testing)
- Documentation: ~30 minutes

## Acceptance Criteria

- [ ] 69 columns in subs.ipc (not 67)
- [ ] Columns 18-19 are SpectralSim and RTScore
- [ ] Both columns have numeric values (not mostly NaN)
- [ ] Step 11 validation passes
- [ ] Full pipeline completes without errors
- [ ] Output matches reference schema on head-to-head comparison
