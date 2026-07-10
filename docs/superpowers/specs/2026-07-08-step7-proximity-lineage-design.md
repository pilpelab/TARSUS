# Step 7 Proximity-Based Lineage Acceptance (Option C)

**Date:** 2026-07-08
**Status:** ⛔ **CANCELLED — superseded by D-047.** Never implemented. Its premise (that exact
targeted lineage was unachievable) was false: Step 2 was simply indexing the wrong mzML.
Retained for history only.
**Supersedes:** Nothing — this is the chosen repair for the D-044/D-045/D-046 Step 7 lineage blocker.

## Context

Step 7 currently produces `subs.ipc` with 0 rows on the trial dataset. Forensic investigation (D-044 through D-046) established:

- Step 4/5 currently run PepQuery in peptide-only open search (`-aa`, no spectrum title given). This means PepQuery may validate a Step 3c candidate peptide against a *different* spectrum than the one Step 3c originally found it on.
- Step 7 requires an *exact* `(spectrum_title, peptide)` match between Step 3c's candidate and PepQuery/PDV's validated evidence — so when PepQuery picks a different spectrum, Step 7 silently drops the candidate.
- Restoring exact targeted lineage (Option A) is blocked by a structural issue: PepQuery's own index-building step (`step02_make_index.py`, `pepquery.jar index`) computes its own precursor monoisotopic mass/charge per spectrum, independently of FragPipe/MSFragger's mass assignment for the same PSM. Measured directly: these disagree by up to ~900 Da for many Step 3c candidates on this Orbitrap Astral DDA dataset. This is inherited from the reference pipeline's method (same `pepquery.jar index` invocation), not a TARSUS_BC porting bug, and is not fixable by flag-tuning (four independent flag-level fixes were tried and ruled out: title-format, `-varMod`, `-indexType`, `-s` task type).
- Decision: implement Option C (hybrid proximity acceptance) now, using the peptide-only open-search results that already exist and already work (`05_pepquery/`, `06_aggregated/` — no rerun needed), rather than continuing to chase Option A's PepQuery-internal blocker.

## Goal

Change Step 7's evidence-acceptance rule from "exact spectrum-title match" to "exact spectrum-title match, OR a PepQuery/PDV-validated spectrum for the same peptide that is *proximate* to the Step 3c candidate's own spectrum." This unblocks Step 7 without touching Steps 1–6 or rerunning any LSF jobs.

## Matching rule (all parameters user-approved)

For a Step 3c candidate row (peptide `dep`, spectrum `A` with known file, charge, retention time, and precursor mass from `psm.tsv`), and each spectrum `B` that PepQuery/PDV validated for peptide `dep` (i.e. `B in pdv_export[dep]`):

- **File name (exact required):** the file-basename portion of `A` and `B`'s titles must match exactly (both use `file_sub:scan:charge` format).
- **Charge (exact required):** charge of `A` and `B` must match exactly.
- **Retention time (tolerance):** `|RT_B - RT_A| <= 24 seconds`. (No precedent in the original reference pipeline, which only ever did exact matching — 24s is anchored on FragPipe's own `freequant.rt-tol=0.4` min, the tolerance FragPipe itself already uses elsewhere in this same workflow to decide "is this the same physical eluting feature.")
- **Precursor mass (tolerance):** `|mass_B - mass_A| / mass_A <= 20 ppm`. (Anchored on the existing `precursor_true_tolerance=20` in the FragPipe second-pass workflow and the existing `-tol 20` in the current Step 5 PepQuery invocation — the same value already trusted twice elsewhere in this pipeline.)

A Step 3c candidate is accepted if **any** in-tolerance `B` also passes the existing two-fragment ion-coverage filter (`step07_analyze_outputs.py`'s existing logic, unchanged) — no additional distance-based tie-breaking; the two-fragment filter remains the sole arbiter among in-tolerance candidates, per explicit user choice.

## New data dependency: RT/mass lookup for PepQuery/PDV spectra

PepQuery's own output (`psmrankall.txt`/`ptmall.txt`) has `exp_mass` and `charge` per spectrum_title, but **no retention time column**. RT for a candidate `B` must come from the PepQuery index MGF files (`02_index/pepquery_index/*.mgf`), which carry `RTINSECONDS=` per `TITLE=`.

**New helper:** a one-time scan of `02_index/pepquery_index/*.mgf` (~24,944 files on the trial dataset) building `spectrum_title -> (rt_seconds, mass, charge)`, cached to `02_index/pepquery_index/_rt_mass_cache.parquet`. Subsequent Step 7 runs reuse the cache if present and not stale (staleness = index directory mtime newer than cache mtime). This is a pure derived artifact of Step 2's output directory — it does not modify or depend on Step 6, and does not require rerunning Steps 1–6.

## Output schema change

`subs.ipc` gains one new column: **`match_type`** — `"exact"` if the accepted evidence spectrum's title equals the Step 3c candidate's own title, `"proximity"` otherwise. This lets any downstream/manual analysis filter to exact-only for a stricter cut, or report the exact/proximity split for methods transparency.

## Scope / what does NOT change

- Steps 1–6: untouched. No rerun, no sentinel invalidation.
- Step 4/5 PepQuery invocation: untouched (still peptide-only open search).
- Existing two-fragment ion-coverage filter logic: untouched, reused as-is as the final arbiter.
- Sentinels to invalidate before rerun: `07_analyze/` onward only (`07_analyze`, `08_base_input`, `09_pepquery_base`, `10_aggregated_base`, `11_localized`).

## Error handling

- Malformed/unparseable spectrum titles (either Step 3c side or PepQuery/PDV side) are excluded from proximity consideration and logged — never crash the run.
- If the RT/mass cache build encounters a malformed MGF entry (missing `RTINSECONDS`/`PEPMASS`/`CHARGE`), that spectrum is skipped from the cache (absence from the cache = never considered a proximity candidate, which is safe/conservative).
- Cache staleness is detected, not silently trusted — a changed index directory triggers a rebuild rather than serving stale RT/mass data.

## Testing plan

- Unit tests for the new proximity-predicate function in isolation: same-file/diff-charge → reject; same file+charge, RT 25s away → reject; RT 20s away → accept; mass 21ppm away → reject; mass 19ppm away → accept.
- Unit test for the MGF-scan cache builder against a small synthetic MGF fixture (few files, known TITLE/RTINSECONDS/PEPMASS/CHARGE values).
- Extend `tests/validation/expected/step07_fixtures/` with a proximity-match scenario (current fixtures only cover exact-match) and a `match_type` assertion.
- Real-data validation: rerun Step 7 only against `output/trial` (Steps 1–6 outputs untouched) and confirm non-zero `subs.ipc` rows, reporting the exact/proximity split.

## Next step

Hand off to `superpowers:writing-plans` to produce the concrete implementation plan (function-level changes to `step07_analyze_outputs.py`, new cache-builder module/function, test additions, orchestration sentinel-invalidation notes).
