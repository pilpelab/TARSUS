# Progress: SpectralSim/RTScore nulls + GAPDH 72-col parity

**Last Updated:** 2026-07-24
**Status:** Root cause found and fixed in code; clean rerun pending.

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
