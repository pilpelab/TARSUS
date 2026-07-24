# Progress: SpectralSim/RTScore nulls + GAPDH 72-col parity

**Last Updated:** 2026-07-24
**Status:** DONE. Clean rerun completed and QC'd against Slava GAPDH — recapitulated.

## Rerun result (job 300453, commit d3d43ff)

All 12 steps clean in ~2h23m. `output/homs_24814/`. Full QC in
`docs/qc-history/QC-HOMS-SLAVA-COMPARISON-2026-07-24.md`. Headlines:

- **262 rows / 233 unique spectra** vs Slava's 259 / **233** (was 191 / 167).
- **73 cols, 0 nulls** in SpectralSim/RTScore/ions/ion_mz/ion_int/sample.
- **100% substitution + position agreement** on all 166 shared spectra.
- 67/67 complementary spectra each way (genuine FDR-membership difference, the
  legitimate place for the FragPipe version change to show — not I/L, not values).
- Cys/Met-origin rows 0 → 34 (13%, vs Slava 17%); D-070 bias gone.

## Resolved

Root cause of the null `SpectralSim`/`RTScore` is **MSBooster being disabled**
(`cfd4886`), not a Step 7 column-selection bug. Full reasoning in **D-069**
(which supersedes the incorrect D-2026-07-23). Verified by reading the reference
generator `elizabev/TARSUS/analyze_outputs.py` and both canonical `second/psm.tsv`
files, and by falsifying the "scores come from the `.pin`" hypothesis empirically.

### Code changes landed (310 tests pass)
- `step03a_first_pass.py` / `step03c_second_pass.py` — stopped patching MSBooster
  off. Template already carries the reference settings; the patch chain now leaves
  that block alone. `find-best-rt-model=false` stays pinned (reference sets it false).
- `step07_analyze_outputs.py` — null placeholders replaced by a **loud failure**
  when the score columns are absent; PDV `ions`/`ion_mz`/`ion_int` joined on
  `(spectrum_title, dependent)` and positioned after `Traced Scans`.
- Fixtures updated to MSBooster-on reality; new tests assert score pass-through,
  ion columns, column positions, and the fail-loud path.

### Project cleanup
Root cleared (7 stale docs → `docs/archive/`, ~924 MB of pathological `rev_rev_`
double-decoy FASTAs deleted). `output/` emptied of all ~2.1 TB of prior runs; QC
report and `hoMS_24814/RESULTS.md` preserved under `docs/qc-history/`.

### Second bug found and fixed (D-070)
`_parse_modification` used `re.match` (anchored) where the reference uses polars
`str.extract` (unanchored), silently dropping every substitution listed *after*
another modification — i.e. essentially all Cys- and Met-containing PSMs, a
chemically biased loss. Dry run against reference inputs went **3521 → 3922 rows,
exactly matching the reference**, `in REF not ours: 0`, `in OURS not ref: 0`.

### Schema is now 1:1 (+ documented)
Renamed to the reference's exact spelling (`first Intensity`, `second Intensity`,
`mistranslatedPos`, `_right` suffix) and added the missing `sample` column. Output
is a strict superset of the reference: 73 = reference's 69 + `ions`/`ion_mz`/
`ion_int` + our `spectrum_title` key. Every column is documented in
**`docs/SUBS-SCHEMA.md`** — written so the table stays interpretable without Slava.

### Test status
305 unit + 7 Step 7 validation tests pass. The three heavyweight validation tests
(`step01_convert`, `step02_index`, `step03a_first_pass`) are LSF/tool integration
tests rooted at `output/trial/`, which the cleanup deleted — they now block on
real tool invocation. Not a code regression; the rerun exercises those paths.

### Rerun LAUNCHED 2026-07-24 13:32
LSF master job **300453**, output `output/homs_24814/`, provenance pinned to
commit `d3d43ff`. Full human proteome (`slavat/tehilapaper/fasta/protein.fasta`,
123,495 seqs) over the 15 `EX1_24814_Fraction-*_03092025.raw` fractions —
the same configuration Slava's GAPDH `fragpipe_fullpipeline` used for its first
pass. "GAPDH" in his directory name is the *experiment*, not a restricted
database, so a separate `_gapdh` run is redundant (the old one used the full
FASTA too, which is why both gave an identical 191 rows).

Monitor: `bjobs 300453`, `tail -f output/homs_24814/master.log`.

**Do not run `pytest tests/validation` while a run is live.** Those tests submit
their own LSF jobs (ThermoRawFileParser conversions, PepQuery index) into
`output/`, which both interferes with the run and recreates directories. This is
already documented at the top of `docs/rerun_qc_20260723.sh`; it was hit anyway
on 2026-07-24 and blocked the output purge for ~40 min. Unit tests are local and
safe: `pytest tests/unit`.

## Next

1. **Clean rerun** of `hoMS_24814_gapdh` end-to-end (single run, sequential).
2. **QC compare** vs `slavat/.../GAPDH/2d/fragpipe_fullpipeline/subs.ipc`:
   - 72 columns, `SpectralSim`/`RTScore` non-null
   - `ions`/`ion_mz`/`ion_int` populated
   - substitution + position agreement (was 100% / 98.5% on shared rows)
   - detection count vs Slava's 259 — expect a rise from 191 now that MSBooster
     rescoring feeds percolator.

## Watch for

- Do **not** source the scores from `_edited.pin` — empirically falsified (D-069).
- Do **not** delete real detections to make a count match the reference.
- MSBooster uses local DIA-NN models, so the rerun needs no internet. If it stalls
  on Koina, check `msbooster.rt-model`/`spectra-model` are still `DIA-NN`.
- Confirm no `*-decoys-*.fas` reappears at the repo root during the rerun.
