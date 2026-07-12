# Decisions Log

## D-053: The `AlaGGC` Biology Does Not Validate. The Predicted Signal Is 8x DEPLETED, Not Enriched.
**Date:** 2026-07-12
**Status:** 🔴 **OPEN — blocked on the scientists. This is not a code question.**
**Context:** The pipeline is now mechanically faithful to the reference (D-047 → D-051) and completes
end-to-end. This entry records the biological validation, which **fails**.

**`AlaGGC` is documented NOWHERE.** Searched the repo, `TARSUS_elizabev/`, and the reference's own
`sdrf.tsv` / `experiment_annotation.tsv`. It appears only as a filename. The reference SDRF has every
biological field as *"not available"*; its `condition` column just repeats the LS/HS solubility
fractions. **No one wrote down what this experiment is.**

**Expected.** E. coli, tRNA lab. `GGC` is a **glycine codon**; `Ala` is alanine → an engineered tRNA
charged with Ala but decoding GGC ⇒ **Gly→Ala (G→A)** substitutions. Verified this matches the
pipeline's convention (Step 3b writes `>{pep}_{origin}{pos}{dest}` where the *reference* peptide
carries `origin` and the *variant* carries `dest`; so `origin→destination` = reference→observed).

**Observed — the opposite.**

| | AlaGGC (ours) | EVpar (reference) | ratio |
|---|---|---|---|
| **G→A** | 8 / 2,556 (**0.31%**) | 101 / 3,922 (**2.58%**) | **0.12x — 8-fold DEPLETED** |
| A→G (reverse) | 0.31% | 0.38% | 0.82x (flat) |

G→A is not merely absent; it is **8x rarer than in the control dataset.** A failed experiment would
show background levels — *below* background is stranger.

**What IS enriched looks like mass artifacts, not biology.** The top AlaGGC substitutions cluster at
±1, ±2 and ±16 Da — the classic isotope-peak / oxidation misassignment signature — and the reference
dataset (same pipeline, same instrument) has **literally zero** of several:

| Sub | Δmass | AlaGGC | EVpar | Likely cause |
|---|---|---|---|---|
| F→M | −16.03 Da | 109 | **0** | oxidation-related (M+O ≈ F) |
| L→N | +0.96 Da | 84 | **0** | ≈ +1 Da — C13 isotope / deamidation |
| I→N | +0.96 Da | 70 | **0** | same |
| L→D | +1.94 Da | 53 | **0** | ≈ +2 Da — double C13 |
| Q→K | +0.036 Da | 99 | 107 | **near-isobaric** — barely separable at 20 ppm |

**Three possibilities, indistinguishable from code:**
1. The reading of `AlaGGC` is wrong and a different substitution is expected.
2. The experiment did not produce the intended mistranslation (strain/induction/sample).
3. Something upstream is still wrong — the F→M / L→N asymmetry vs EVpar is unexplained.

**Decision: do not tune the pipeline to chase this.** We have no stated target. Tuning parameters
until G→A appears would be fitting to a number nobody supplied. **Ask the scientists first:**
1. What substitution should `AlaGGC` produce? Is it Gly→Ala, or is the reading backwards?
2. What is `EVpar` — the control (empty-vector parental)? If so, why does it show *more* G→A?
3. Was the mistranslation validated independently (western/reporter/targeted MS)? If the strain was
   never confirmed to mistranslate, absence of signal is a **biology result, not a pipeline bug**.
4. Are F→M and L→N expected? They dominate our data and are absent from theirs.
5. What G→A rate did the paper report? **That is the number to validate against.**

With answers to (1) and (5) the pipeline can be validated or falsified in minutes. Without them we
are validating against an unstated target.

## D-052: PepQuery Memory Derived from the FASTA — and a Latent `-Xmx > reservation` Bug
**Date:** 2026-07-12
**Status:** Implemented, 237 tests pass, mypy + ruff clean. New module `src/tarsus/resources.py`.
**Context:** A note in progress.md asked for dynamic PepQuery memory (E. coli works at the hardcoded
default; a human proteome, ~60x the FASTA, would not). Investigating it exposed something worse.

**The latent bug.** Step 5 shipped `memory_mb=1500` with `java_heap_mb=4096` — a JVM heap ceiling
**2.7x the entire LSF cgroup**. This is D-049 defect 1 verbatim (PDV ran a 4096 MB heap inside a
4000 MB reservation; every shard died with `TERM_MEMLIMIT` the moment targeted mode gave it real
data). It has not bitten Step 5 yet **only because E. coli's 1.8 MB FASTA never grows the heap near
its ceiling.** `-Xmx` is a *limit*, not a reservation: an oversized heap is invisible on small inputs
and fatal on large ones. Step 9 was the mirror image — a 5,000 MB reservation for jobs that peak at
279 MB.

**Model, fitted to two real data points and validated against both:**
- **Measured:** LSF `Max Memory` across 3,869 Step 9 jobs (E. coli, 1.8 MB FASTA): peak **279 MB**,
  median 249, p95 262.
- **Reported:** human proteome (106 MB FASTA) needs ~4 GB.
- `peak_mb ≈ 220 + 36 * fasta_mb` → predicts 285 MB and 4,036 MB respectively. Both hold.
- JVM heap = 1.5x predicted peak (floor 1024 MB); reservation = heap + 768 MB non-heap headroom.

| FASTA | reservation | heap | previously |
|---|---|---|---|
| E. coli 1.8 MB | 1,792 MB | 1,024 MB | step5 1500/4096 (**heap > reservation**); step9 5000/4096 |
| Human 106 MB | 6,822 MB | 6,054 MB | 1500 MB → OOM |

**Decision:** `estimate_pepquery_memory(fasta)` + `check_heap_fits(heap, memory)` in a shared
`resources.py`. Steps 5 and 9 take `memory_mb`/`java_heap_mb` as `None` by default and derive them.
An explicitly-supplied pair is **validated**, so an impossible config raises at submit time rather
than dying with `TERM_MEMLIMIT` on the first large run. Overridable per-lab via
`TARSUS_PEPQUERY_MEM_MB` / `TARSUS_PEPQUERY_HEAP_MB` — no code change (`.agents/project.md` requires
per-lab overridability).
**Note:** Step 6 keeps its own `_check_shard_memory` (headroom 1024, raising `ValueError`). Not
unified, to avoid churning a working, tested config; `ResourceConfigError` subclasses `ValueError`
so a future unification is safe.

## D-051: Step 3c Inherits Step 3a's Calibration via FragPipe's Own Second-Pass Workflow
**Date:** 2026-07-12 (revised same day)
**Status:** Implemented and unit-tested (223 tests pass, mypy clean). Awaiting live rerun.
**Context:** Slava reported that both Step 3a and Step 3c run "MASS CALIBRATION AND PARAMETER
OPTIMIZATION" (~5-6 min each). Calibration describes the instrument's mass drift on the raw files,
not the database, so re-running it in Step 3c is redundant.

**First implementation (pi agent) — replaced.** The pi agent had Step 3a regex-parse its own log for
`New <param> = <value>` lines, write them to `03a_first_pass/.calibration_params`, and Step 3c read
that file back and patch 5 values into `generic.workflow`. It validated clean and reproduced the
reference values exactly — but it hand-reconstructs a file FragPipe already writes, and it had two
traps: (a) `.calibration_params` was only written at the *end* of Step 3a's body, so on any rerun
that skips Step 3a via its `.done` sentinel, the file is absent and Step 3c silently falls back to
`calibrate_mass=2` — the fix does nothing, no error; (b) `remove_precursor_peak=0` (reference-mandated
for the second pass) was made conditional on the calibration log containing that key.

**Final implementation.** Step 3c now bases its search on
`03a_first_pass/fragpipe-second-pass.workflow` — the workflow **FragPipe itself generates during the
first pass**, with calibration already baked in (`calibrate_mass=0` + optimized tolerance/topN/
transform/ratio). This is exactly what the reference `search_pipeline_script.sh` seds. If that file
is absent, Step 3c falls back to the bundled `generic.workflow` (`calibrate_mass=2`, self-calibrates).
`remove_precursor_peak=0` is now patched **unconditionally**, matching the reference.
- `src/tarsus/steps/step03c_second_pass.py`: new `_second_pass_template()` and `_patch_workflow()`;
  removed `_read_calibration_params` / `_CALIB_WORKFLOW_MAP`.
- `src/tarsus/steps/step03a_first_pass.py`: reverted to HEAD — no log parsing, no `.calibration_params`.
- Tests: `TestSecondPassTemplate`, `TestPatchWorkflow`, `TestBundledTemplateHasEveryPatchedKey`.
  (The old `TestWorkflowPatching` re-implemented the patch logic inline and tested nothing; removed.)

**No hardcoded calibration values.** `calibrate_mass=0` is a *mode flag* ("values already present"),
not a value. Every numeric calibration parameter (10.0 PPM, topN 300, …) is read at runtime from
FragPipe's generated workflow, which was computed from the actual raw files. Verified end-to-end
against the reference's `second.workflow`: all 7 calibration params identical.

**⚠️ This CHANGES search results.** The prior 2,888-SAAV / 293-localized run used `generic.workflow`
(`calibrate_mass=2` → self-calibrated to 5.0 PPM, topN 150, transform 0). This moves Step 3c onto the
reference's parameters (10.0 PPM, topN 300, transform 1), so the SAAV counts will differ on the next
run. This is a correction toward the reference, not a regression — but the numbers in progress.md are
now stale until a rerun.

**Sentinel invalidation IS needed to see the effect.** To rerun with the new workflow, delete
`03c_second_pass/.done` **and everything downstream** (`04`–`11`). `03a`/`03b` are preserved, so
`fragpipe-second-pass.workflow` is already on disk and Step 3c picks it up. Rerunning only from a
later step has no effect — the change is in Step 3c's search itself.

## D-049: Three Independent Bugs Between Step 6 and Step 9, All Found by Actually Running the Pipeline
**Date:** 2026-07-09
**Status:** All three fixed and tested. Step 7 now yields **2,888 SAAV rows** (was 0).
**Context:** D-047 unblocked Step 7. Running the pipeline end-to-end then exposed three defects that no test and no prior run had ever reached.

**1. PDV shard JVM heap exceeded its LSF reservation.** Step 6 shipped `java_heap_mb=4096` inside `memory_mb=4000` — the heap alone exceeded the whole cgroup. Every shard died with `TERM_MEMLIMIT`, killing the master. It lay dormant because open-search `psmrankall.txt` carried ~4 rows per spectrum (617,573 rows / 158,476 unique pairs), so a 20,000-row shard rendered only a few thousand *distinct* spectra. Targeted mode gives ~1 row per spectrum (19,914 rows), so the same shard now renders ~20,000 distinct spectra. Fixed: `memory_mb` 4000→8000 with `_check_shard_memory()` refusing any config lacking 1024 MB of headroom; `chunk_size` 20000→2500 (at 19,914 rows the old value produced exactly **one** shard — no parallelism at all).

**2. Xvfb display race destroyed PDV shards co-scheduled on one host.** `XvfbDisplay` scanned `:99, :98, …` and accepted a display as soon as `/tmp/.X11-unix/X<n>` appeared. A second worker on the same node saw the socket the *first* had just created, declared itself ready, and adopted a display it did not own — its own Xvfb had died on the lock file. When the owner exited it tore that X server down and the squatter lost its connection mid-render: PDV wrote a partial `PDVExportResult.txt` and exited 1 with **no Java exception**, surfacing only as `java rc=1, export_exists=True`.
  - **Live evidence:** of four shards co-scheduled on `cn810`, exactly one survived; all four shards that had a host to themselves succeeded.
  - Fixed by using Xvfb's own `-displayfd`, which claims a free display atomically and writes the number back. Verified: 8 concurrent instances get `:0`–`:7`, all alive. Re-ran with three shards again landing on `cn810` — **all three passed**. The scanning path is kept as a fallback for older Xvfb, but now skips already-claimed displays and only accepts one whose server process is still ours.
  - Step 6 now completes in **77 seconds** (it previously ran six days and was OOM-killed).

**3. Step 8 keyed on the wrong column — same class of bug as D-047.** `expand_mgf_with_mod_states()` and `write_dep_spectrum_chunks()` read `row["Spectrum"]`, FragPipe's raw `file_sub.101063.101063.2`. The MGF titles are `file:101063:2`. **0 of 1,113 titles matched**, producing a 0-byte `mgfall_fakes.mgf`.
  - Root cause is the port's renaming: the reference `analyze_outputs.py` *overwrites* its `Spectrum` column with the converted title, so its `ref_validation_prep.py` reading `Spectrum` gets a title. Our Step 7 keeps `Spectrum` raw and adds `spectrum_title` alongside. Fixed via an explicit `title_col=TITLE_COL` parameter. Verified on real data: **1,113/1,113 matched**, `mgfall_fakes.mgf` = 157 MB.
  - **Guardrail added:** `prepare_base_rescoring()` now raises when zero titles match. Step 8's existing guardrail only counted files in `pepquery_input_base/` — which was non-empty (4,287 chunks) because chunk-writing does not touch the MGF. An empty MGF sailed straight through into Step 9.

**Systemic note.** Every one of these — plus D-047 and D-048 — is the same failure mode: **silent defaults over missing data.** `.get(col, 0)`, `fill_null(0)`, `except: pass`, `.done` stamped over empty output, a guardrail that checks the wrong artifact. The pipeline now fails loudly at Steps 7 and 8. Steps 9 and 10 still do not validate that their inputs are non-empty; that is the remaining gap.

## D-048: Step 11 Was Guaranteed to Return Zero Rows. Four Defects Fixed; One Is a Deliberate Deviation from the Reference.
**Date:** 2026-07-09
**Status:** Fixed and unit-tested. Found by auditing Steps 9-11 while Step 5 ran — these steps had **never executed successfully**, so none of this was covered by any prior run.
**Context:** After D-047 unblocked Step 7, Steps 8-11 will execute for the first time. Audited them against the reference `query_psm_base.sh`, `aggregate_query_base.sh`, and `localize.py`.

**Clean:** Step 9's PepQuery flags match `query_psm_base.sh` exactly (`-ti 0,1,2,3 -maxLength 50 -tol 20 -fast -itol 0.01 -fixMod 0 -varMod 1,2 -maxVar 4 -hc -m 1 -s 2 -indexType 2 -e 2 -c 2 -plot`). Step 10 differs cosmetically (keeps the first file's header rather than inserting a canonical one) but is functionally equivalent.

**Defect 1 — fatal, silent.** `localize_shift()` read `row.get("mistranslatedPos", 0)`, but Step 7 emits the column as **`mistranslated_pos`** (snake_case; the reference uses camelCase). The `.get()` default made `expected_pos` **always 1**. Step 7 guarantees `mistranslated_pos > 0`, and the position is 0-based (verified: `AAAAPVTGPLADDPIQETITFDDFAK_F20A` — index 20 is `F`), so the true 1-based position is always ≥ 2. **`expected_pos == 1` could never match, so Step 11 returned zero rows on every possible input.** Confirmed against the reference's own `subs.ipc`: `mistranslatedPos` ranges 1-27, so expected positions are 2-28 — never 1. This explains the header-only `subs_localized.csv` in `output/trial/invalid_empty_downstream_20260707132848/`. Fixed via `_expected_position()`, which raises `KeyError` rather than defaulting.

**Defect 2 — silently inflated results.** `nonbase_hits` used `deps.join(base_max, how="left")` + `fill_null(0)`, so a variant PSM with **no base rescoring at all** got `delta_score = score - 0 > 0` and was admitted. The reference uses an inner join: no base comparison means no evidence, so the row is dropped. Fixed.

**Defect 3 — mislocalization.** `localize_shift()` passed empty `aux_mod_pos`/`aux_mod_mass` to PyAscore. The reference parses them from psmrankall's `modification` column (`@(\d+)` / `\[([\d.]+)\]`). Without them PyAscore cannot subtract co-occurring Ox/CAM mass contributions, shifting fragment masses and mislocalizing the substitution. Fixed via `_parse_aux_mods()`.

**Defect 4 — a bug in the reference itself; fixed here, deviating deliberately.** Step 8 patches each fake spectrum's TITLE with a Met/Cys modification-state suffix whose grammar is `_M<pos>[_<pos>...]C<pos>[_<pos>...]` (e.g. `_M0C0`, `_M0C1`, `_M6_14C0`). The reference strips it with `_[^_]*$`, which removes only the final `_<chunk>` and so mangles every multi-position suffix: `..._M6_14C0` -> `..._M6`, a title that joins to nothing. **Measured on the reference's own `psmrankall_base.txt`: 1,638 of 25,615 rows (6.39%) are mangled and silently lose their base comparison.** Combined with the reference's inner join, those variant PSMs are discarded entirely. Replaced with `_strip_mod_suffix()`, anchored on the exact suffix grammar Step 8 writes; validated against the reference file: **0% malformed, down from 6.39%.**
  - **This is a deliberate divergence from the reference and it changes results.** It can only *add* rows relative to the reference, by restoring the base comparison for those 6.4% (some will then lose to base and be dropped — a false-positive removal; others legitimately beat base and are kept). It is a strictly better-founded comparison, but it means our SAAV counts will not match the reference exactly on the same input. Revert `_strip_mod_suffix()` to `r"_[^_]*$"` for bit-exact reference parity.

**Also:** `localize()` returned the widened `subs ⋈ psmrankall` join; it now returns `subs.ipc`'s own schema, matching the reference (whose `subs_localized.ipc` has the same 69 columns as its `subs.ipc`). The join key remains `spectrum_title` rather than the reference's `dependent` peptide — this is stricter and preserves the exact lineage D-047 restored, instead of borrowing another spectrum's evidence for the same peptide.
**Dead code retained:** `get_var_mod_positions()` is unused by the pipeline but has unit tests; left in place.

## D-047: Ground Truth Found — Option C Is Unnecessary. The Root Cause Is Step 2 Indexing `_sub.mzML`; D-044/D-045/D-046 Are All Downstream of It.
**Date:** 2026-07-09
**Status:** Closes D-044, D-045, D-046. Supersedes the Option C design/plan (`docs/superpowers/specs|plans/2026-07-08-step7-proximity-lineage*.md`) — **do not implement them.**
**Context:** Located the colleagues' real, completed reference run at
`/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` (the `TARSUS_elizabev/` symlink points only
at their *scripts* repo, whose `pepquery_inputs/` is empty and whose `pepquery_result/*/` is a
literal `*` directory from an aborted invocation — which is why no ground truth was found before).

**The reference run succeeds, on the same instrument family (Orbitrap Astral DDA, `HouYM-25-G140-AstralDDA-EVpar-{LS,HS}-3`), using exact targeted PepQuery validation.** Its funnel:

| Artifact | Reference | TARSUS_BC trial |
|---|---|---|
| Step 4 `psm_input4pepquery.tsv` | 37,729 rows × **2 cols** (`peptide\tspectrum_title`) | 45,678 rows × **1 col** (peptide only) |
| Step 6 `psmrankall.txt` | 15,232 rows | 617,573 rows |
| Step 7 `subs.ipc` | **3,922 rows** × 69 cols | **0 rows** × 69 cols |
| Step 11 `subs_localized.ipc` | **697 rows** | (never ran) |

**Root cause, proven.** The reference builds its PepQuery index from the **original** mzML files, per
`make_index.sh` and README step 2 (which runs *before* the FragPipe search that creates `_sub.mzML`).
Verified directly — reference index `TITLE=` lines carry **no `_sub`**:
`TITLE=HouYM-25-G140-AstralDDA-EVpar-LS-3:121018:2`, and its `psmrankall.txt` `spectrum_title`s match
(`...-LS-3:204674:2`). Consistently, `extract_psm.py` and `analyze_outputs.py` both **strip** `_sub`
from FragPipe's second-pass `Spectrum` column (`..._sub.02863.02863.2` → `...:2863:2`), landing
exactly in that namespace. `_sub.mzML` preserves the original scan numbering, so the lookup resolves.
The chain is coherent end-to-end and demonstrably yields 3,922 SAAVs.

TARSUS_BC broke this in commit `e143a46` ("reorder Step 2 after Step 3a — index `*_sub.mzML` not
original mzML"), a compute optimization that moved the index into a **`_sub`-bearing title
namespace**. Every subsequent finding is a downstream artifact of that one change:
- `extract_psm.py`'s `_sub` stripping then produced titles absent from the index → misdiagnosed as
  "FragPipe 24.0 scan numbers don't match mzML" (**D-032 — false**, later disproved by D-045 Finding 1).
- That false diagnosis motivated commit `68957c2`, dropping Step 4 to peptide-only input, which is
  the actual **D-044 lineage break** that zeroes Step 7.
- D-045 Finding 3's "missing precursor-mass bins" and Finding 4's `NullPointerException` were both
  **self-inflicted**: the NPE only appears once `-varMod 2,33` is added, and `-varMod` was added to
  work around the bin mismatch caused by the wrong index. **The reference passes no `-varMod` at all**
  and hits neither problem. Step 5's flags are otherwise byte-identical to `query_psm.sh`.
- D-046's "PepQuery index mass disagrees with FragPipe by −162…+943 Da" cannot be a PepQuery
  pathology: FragPipe's own `Delta Mass` across all 45,678 second-pass candidates spans only
  −0.078…+3.082 Da (100% within ±60 Da), and both tools read the same file. The measurement almost
  certainly keyed on scan number without pinning charge (PepQuery indexes a scan under multiple
  charge titles, whose neutral masses differ by ~1.5×) — which reproduces that exact spread.

**Decision:** Abandon Option C. Restore the reference contract, which is now known to work:
1. **Step 2** — index `01_mzml/` (original mzML), not `03a_first_pass/*_sub.mzML`. Reverts `e143a46`;
   Step 2 no longer depends on Step 3a and may run in parallel with it, as in the reference.
2. **Step 4** — emit two columns (`peptide\tspectrum_title`), stripping `_sub`, per reference
   `extract_psm.py`. Reverts `68957c2`.
3. **Step 7** — revert `_spectrum_to_title()`/`_normalize_spectrum_title()` to **strip** `_sub`
   (undoes the `_sub`-preserving half of `c70f35e`, which was only correct for the `_sub` index).
4. **Step 5** — no change. Do **not** add `-varMod`, `-indexType`, or `-s`.
**Rationale:** This is not a scientific-method change — it restores the published method exactly, and
Option C's proximity acceptance (which validates a SAAV against a *different* spectrum than the one
it was identified on, weakening the evidence and the `dpbp` intensity ratio) becomes unnecessary.
**Sentinels to invalidate:** `02_index/`, `04_psm_input/`, `05_pepquery/`, `06_aggregated/`,
`07_analyze/`, `08_base_input/`. Steps 01/03a/03b/03c are unaffected and must be preserved.
**Cost:** re-index (~6 GB) + re-run PepQuery (~21 GB) + re-aggregate (~29 GB). Steps 5/6 are the
expensive ones. Note the reference targeted only 37,729 PSMs and produced a 3.8 MB `psmrankall.txt`,
versus our peptide-only run's 167 MB — targeted mode should be substantially *cheaper*, not dearer.
**Acceptance test:** Step 7 `subs.ipc` must have > 0 rows. Order-of-magnitude sanity: the reference
got 3,922 SAAVs → 697 localized from 2 Astral DDA files; our trial is also 2 Astral DDA files.
**Ground truth for regression testing:** `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/`
(`subs.ipc`, `subs_localized.ipc`, `psmrankall.txt`, `second/psm_input4pepquery.tsv`). Column *sets*
already match ours 69/69, modulo naming (`_right`→`_first`, `first Intensity`→`first_intensity`,
`mistranslatedPos`→`mistranslated_pos`; reference has `sample`, we have `spectrum_title`).
**Note:** the reference's original EVpar `.mzML` inputs are no longer on disk (only `_sub.mzML`), so
we cannot bit-for-bit reproduce their run — but their outputs remain valid as a magnitude/schema oracle.
**Read-only:** nothing under `/home/labs/pilpel/elizabev/` was modified.

## D-046: Option A (Targeted PepQuery) Blocked by a Deeper Issue — PepQuery's Own Index Precursor Mass Disagrees with FragPipe's Assigned Mass
**Date:** 2026-07-07
**Status:** Open. User chose Option A; this entry records why it is not yet implementable and is a pre-existing characteristic of the reference method, not a TARSUS_BC porting bug.
**Context:** Following D-045's NPE discovery, continued live experimentation (scratch-only, no production files touched) to see if Option A could actually be made to work.

**Fix found and confirmed:** The `NullPointerException` in D-045 Finding 4 is caused specifically by requesting PepQuery modification ID 33 ("Acetylation of *protein* N-term") in `-varMod`, which requires protein-mapping context that novel/candidate peptides don't have (`PeptideUtils.isNterm` → `Peptide.getProteinMapping()` is null for a peptide absent from `-db`). Substituting modification ID 5 ("Acetylation of *peptide* N-term", same +42.0106 Da mass, but "Peptide N-term" context — no protein mapping needed) eliminates the crash entirely (`-varMod 2,5` instead of `-varMod 2,33`). This is a real, usable fix.

**New, more serious finding:** Even with the NPE fixed, live targeted-mode runs still returned "Matched spectra: 0". Root cause: Step 2's PepQuery index is built via **PepQuery's own `index -r -i <mzml> -o <dir>` command** (`step02_make_index.py:127-134` — this exactly matches the reference `make_index.sh`, so it is not a TARSUS_BC-introduced difference). PepQuery computes its own precursor monoisotopic mass/charge for every spectrum from the mzML during indexing, entirely independently of FragPipe/MSFragger's own mass assignment for the PSM it reports in `psm.tsv`. Measured directly on 28 of 30 Step 3c candidates (2 titles not found in the sampled index subset): the PepQuery-index-recorded neutral mass vs. FragPipe's `Calculated Peptide Mass` for the *same native scan* disagree by anywhere from **-162 Da to +943 Da**, with only 2/28 candidates agreeing to within ~1 Da. This is far outside any plausible modification-adjusted tolerance (the workflow's own enabled variable mods only span +15.99/+42.01 Da) — it reflects PepQuery's monoisotopic-peak-picking/deisotoping algorithm disagreeing with MSFragger's, likely because this is complex Orbitrap Astral DDA data with dense isotope envelopes. PepQuery's targeted search still filters candidate spectra by *its own* recorded precursor mass against the query peptide's theoretical mass (`-tol`/`-itol`), so even a perfectly-titled, perfectly-mapped target spectrum is invisible to it whenever this disagreement exceeds tolerance — which is most of the time in this dataset.

**This is not a new bug we introduced.** The reference pipeline built its PepQuery index the identical way (`pepquery-2.0.2.jar index -r -i <mzml_dir> -o <output>` in `make_index.sh`) and its `query_psm.sh` also relies on PepQuery's own precursor-mass filtering during targeted search. Whether the reference pipeline's targeted validation ever actually worked well is now an open question — this mass-disagreement issue may have always existed but gone unnoticed, or the reference's original FragPipe 23.1 + non-Astral(?) data may have had much better PepQuery/FragPipe mass agreement than FragPipe 24.0 + this Orbitrap Astral DDA trial dataset.

**Decision:** Per `superpowers:systematic-debugging`'s "3+ failed fixes → question the architecture" rule — title format, `-varMod`, `-indexType`, and `-s` task type have all been tried and tuned, and the blocker persists for a structural reason unrelated to any of them. Do not attempt further ad hoc PepQuery flag tuning. Before any further Option A implementation work, this needs an explicit decision from the user on how to proceed, e.g.:
  (a) widen `-tol`/`-itol` drastically for the targeted call (scientifically weaker, converges toward Option C anyway),
  (b) investigate replacing PepQuery's self-computed index masses with FragPipe's own assigned masses (would require a custom MGF/index-writer instead of PepQuery's `index` subcommand — nontrivial engineering, diverges from both reference and current implementation),
  (c) accept Option C (hybrid proximity) as the practical near-term path, since it does not depend on PepQuery's internal precursor-mass agreement at all — it only needs peptide-level open-search hits (already working) plus RT/mass/charge/file proximity computed directly from FragPipe's own numbers.
**No code changed.** All testing was against scratch copies/single MGF files; `output/trial/` and `src/tarsus/` are untouched.

## D-045: Step 4/5→7 Lineage Forensics — D-032's Stated Cause Is Wrong; Targeted PepQuery Hits a New PepQuery Bug
**Date:** 2026-07-07
**Status:** Open — forensics complete, repair strategy not yet implemented. Supersedes D-044's open question with concrete findings.
**Context:** D-044 identified the Step 7 zero-row blocker as a Step 4/5→7 lineage contract break and required a forensic session (per `.planning/step07-lineage-repair.md`) before choosing a repair. This entry records that session's findings.

**Finding 1 — D-032's root cause claim is false.** Directly verified (5 sampled scans: 2213, 2702, 3091, 3193, 3482) that FragPipe 24.0's `Spectrum` column scan number in `03c_second_pass/second/psm.tsv` **exactly matches** the native `scan=` number in the corresponding `_sub.mzML` file (cross-checked via retention time and charge). There is no FragPipe/mzML scan-number mismatch. D-032's stated justification for switching Step 4/5 to peptide-only open search was incorrect (or at least never verified).

**Finding 2 — the real title-format bug was `_sub` stripping, and it's already fixed in Step 7.** PepQuery's own index MGF `TITLE=` lines (`output/trial/02_index/pepquery_index/*.mgf`) and Step 5's `psm_rank.txt` `spectrum_title` column both use the format `<file>_sub:<scan>:<charge>` — `_sub` **preserved**. The reference `extract_psm.py` strips `_sub` (`file_name = d[0].split('_sub')[0]`), which would have produced titles that never match this index. Step 7's current `_spectrum_to_title()`/`_normalize_spectrum_title()` (fixed same day, see progress.md 2026-07-07 session) already compute the correct `file_sub:scan:charge` form. This means a deterministic mapping from Step 3c's `Spectrum` column to PepQuery's indexed titles **does exist** and is already implemented correctly in Step 7 — it was just never wired into Step 4/5's PepQuery input.

**Finding 3 — most Step 3c candidates carry unaccounted-for modifications.** Sampled 5,000 Step 3c positive-intensity rows: **4,330 (86.6%)** have `Modified Peptide` != `Peptide` (mainly `n[43]` protein N-term acetylation, +42.0106 Da, and M oxidation, +15.9949 Da — both enabled in `fragpipe-second-pass.workflow`'s `var-mods` table). A naive targeted PepQuery call using bare `Peptide` text and PepQuery's defaults (`-varMod 2` oxidation only) computes precursor-mass bins from the *unmodified* mass and misses the real spectrum's bin entirely (confirmed: candidate GVAEQAR/scan 3193 computed bins ~7274–7324, none of which exist in the 24,944-bin index; the real spectrum lives in bin 9344, matching its *actual* recorded mass). Fixed by passing `-varMod 2,33` (Oxidation of M; Acetylation of protein N-term, per `pepquery -printPTM`) — this eliminated the "file doesn't exist" bin warnings entirely.

**Finding 4 — new blocker: PepQuery 2.0.2 throws in its targeted-PSM-input code path for novel peptides.** Live experiment (`java -jar pepquery-2.0.2.jar ... -i <peptide>\t<spectrum_title> ...`, format (4) as documented by `pepquery -h`, matching what the reference `query_psm.sh` also does): even with correct `_sub`-preserving titles, correct `-varMod`, and `-indexType 2` (spectrum title, not 1-based index) set explicitly, PepQuery's `generatePeptideInputs` step threw `NullPointerException: Cannot invoke "TreeMap.keySet()" because ... "Peptide.getProteinMapping()" is null` for the tested candidate peptides, and every run terminated with `Matched spectra: 0` / `Peptides with matched spectra: 0`. This reproduced across a 30-candidate batch and a single hand-picked candidate/spectrum pair (GVAEQAR / scan 3193, confirmed physically present in the index). **This NPE does not occur** in the current production peptide-only open-search invocation (verified against real `output/trial/05_pepquery/pepquery_logs/chunk_1104.tsv.log`, which completes cleanly: "Matched spectra: 57", "Peptides with matched spectra: 8"). The NPE is specific to giving PepQuery the two-column peptide+spectrum-title `-i` input for peptides absent from the reference FASTA (i.e., exactly the novel/substituted peptides this pipeline needs to validate) — an apparent bug or unsupported combination in PepQuery 2.0.2's targeted-validation code path, not a data or config error on our side.

**Decision:** Do not implement Option A (restore targeted lineage) yet — it is blocked by Finding 4, a PepQuery-internal issue requiring its own investigation (candidates: decompile `PeptideSearchMT.generatePeptideInputs`/`Peptide.getProteinMapping()` to find the exact null condition; try `-s 2` known-peptide mode; check for a newer PepQuery patch release; or pad `-db` with `03b_candidates/pep_candidates.fa` to see if giving novel peptides a "protein mapping" avoids the null). Do not implement Option B/D-032-as-is silently either — Findings 1-2 show its premise was wrong, so keeping pure peptide-only open search means Step 7 is validating "some spectrum somewhere," not the Step 3c-identified spectrum, and this was never an explicit, reviewed scientific choice.
**Recommended near-term path:** Option C (hybrid proximity acceptance) using the **existing, already-working** peptide-only open-search results (`05_pepquery`/`06_aggregated` as they exist today — no rerun needed) filtered by file/charge/retention-time/precursor-mass proximity to each Step 3c candidate's own spectrum, since ~23,171 of 45,678 candidate peptides already have *some* open-search hit in Step 6 (peptide-only overlap per D-044). This unblocks Step 7 without waiting on the PepQuery bug, and is honestly weaker evidence than exact-spectrum validation — it should be presented to the user as an explicit scientific-method choice before implementing, per D-044's Phase 2 instruction not to silently redesign Step 7.
**Rationale:** Systematic debugging (per `superpowers:systematic-debugging`) requires root-causing before fixing. The forensic session fully confirmed the reference lineage contract (targeted validation, `_sub`-preserving titles) and proved it is technically implementable end-to-end *except* for a newly discovered PepQuery library bug that blocks the exact-spectrum path for novel peptides — a materially different and more specific blocker than D-032/D-044 had assumed.
**Next steps if Option A is pursued later:** modify `src/tarsus/steps/step04_extract_psm.py` to write `peptide\tspectrum_title` (title format = current `_spectrum_to_title()` logic, i.e. preserve `_sub`); modify `src/tarsus/steps/step05_query_psm.py` to pass `-indexType 2 -varMod 2,33 -maxVar 4` and the two-column chunk file; but only after resolving Finding 4's NPE. **Sentinels to invalidate:** `04_psm_input/`, `05_pepquery/`, `06_aggregated/`, `07_analyze/`, `08_base_input/` (Steps 1-3c are unaffected and must be preserved).
**Next steps if Option C is pursued instead:** modify `src/tarsus/steps/step07_analyze_outputs.py`'s join logic to add proximity-based acceptance (file name + charge equality, RT/precursor-mass tolerance windows) alongside (or instead of) the exact spectrum-title join; no Step 4/5/6 changes or reruns needed, only Step 7 onward. **Sentinels to invalidate:** `07_analyze/` through `11_localized/` only.

## D-044: Step 7 Blocker Is a Step 4/5→7 Lineage Contract Break, Not Step 6 Corruption
**Date:** 2026-07-07
**Status:** Open design blocker; do not work around silently.
**Context:** The trial run now completes Steps 1-6 and produces a complete Step 6 PDV report, but Step 7 outputs `subs.ipc` with 0 rows. Step 8 then creates no base-rescoring input files and orchestration correctly stops before Steps 9-11 (D-043). The user suspected Step 6/PDV sharding was corrupting or losing evidence.
**Investigation:** Audited the current `output/trial/06_aggregated/` artifacts:
- `psmrankall.txt`: 617,573 data rows; 158,476 unique `(spectrum_title, peptide)` pairs.
- `pdv_spectra/PDVExportResult.txt`: 617,573 data rows; 158,476 unique `(Spectrum_Title, peptide)` pairs.
- Pair-set difference between `psmrankall.txt` and PDV export is zero in both directions.
- Full `(spectrum_title, peptide)` multiplicity counters are exactly equal between `psmrankall.txt` and PDV export.
- Step 3c second-pass positive rows / unique pairs: 45,678.
- Exact Step 3c `(spectrum_title, dependent peptide)` overlap with Step 6 `psmrankall.txt`: 0.
- Exact Step 3c overlap with Step 6 PDV export: 0.
- Spectrum-only Step 3c overlap with Step 6 PDV: 2,069.
- Peptide-only Step 3c overlap with Step 6 PDV: 23,171.
**Decision:** Treat the blocker as a lineage contract break introduced by D-032's peptide-only/open-search workaround, not as Step 6 data corruption. Step 4 currently writes only peptide sequences for PepQuery; Step 5 validates those peptides in open-search mode (`-aa`) against any indexed spectrum; Step 7 still assumes the original FragPipe second-pass spectrum title can be joined exactly to PepQuery/PDV spectrum titles. That assumption is invalid under the current Step 4/5 contract.
**Rationale:** Step 6 faithfully transforms Step 5 output into PDV ion evidence. The exact pairs Step 7 wants are already absent from Step 5/6 input, so rerunning Steps 1-6 cannot fix the issue. The pipeline must either restore targeted spectrum lineage or explicitly redesign Step 7 around open-search evidence with scientific approval.
**Required next step:** Run a focused design/forensics session before changing pipeline behavior. Priority order:
1. Re-read original reference `extract_psm.py`, `query_psm.sh`, and `analyze_outputs.py` to confirm the intended lineage contract.
2. Audit title namespaces from FragPipe Step 3c, PepQuery index MGF titles, Step 5 `psm_rank.txt`, and PDV export.
3. Test whether a deterministic mapping can restore targeted PepQuery from Step 3c spectra to PepQuery indexed spectra.
4. If mapping is possible, restore targeted lineage in Steps 4/5 and keep Step 7's exact-pair evidence model.
5. If mapping is impossible, choose between an explicit open-search Step 7 redesign or a hybrid acceptance rule using file/charge/retention-time/precursor-mass proximity. Do not silently implement either as a bugfix because both change the scientific method.

## D-043: Do Not Mark Downstream Done When Step 8 Has No Base-Rescoring Inputs
**Date:** 2026-07-07
**Status:** Corrects/supersedes the earlier same-day empty-result fast path.
**Context:** After Step 6 produced a complete PDV report, Step 7 initially
produced `subs.ipc` with 0 rows, Step 8 created no base-rescoring input chunks,
and the first implementation marked Steps 9-11 `.done` with empty placeholder
outputs. The user correctly flagged this as unsafe: it can hide upstream
spectrum-title/peptide-lineage bugs and gives the appearance of a valid full run
when expected downstream files are absent.
**Decision:** Remove the empty-result fast path. Orchestration now raises a
`RuntimeError` if Step 8 produces no files in `08_base_input/pepquery_input_base/`,
stopping before Steps 9-11 and instructing the operator to inspect Step 7 lineage
and candidate counts. The invalid prior outputs (`07_analyze` through
`11_localized`) were moved to `output/trial/invalid_empty_downstream_*/`; Steps
1-6 were left intact.
**Rationale:** A true empty scientific result may eventually need an explicit,
well-designed final-output contract, but it must not be inferred silently from
missing intermediate inputs. Failing loudly is safer until Step 7 candidate
lineage is proven correct.
**Verification:** Real LSF rerun job 30275 (2026-07-07) resumed at Step 7,
produced `07_analyze/.done` and `08_base_input/.done`, then stopped with the
intended RuntimeError after Step 8 produced no `pepquery_input_base` chunks. No
`.done` files were created for Steps 9, 10, or 11.

## D-042: Step 7 Memory Optimization + Master Memory Default
**Date:** 2026-07-07
**Context:** Step 7 initially exceeded 4GB and then 32GB LSF memory while loading
large Step 6 tables (`ptmall.txt` ~9.4GB, `psmrankall.txt`, PDV report). The
eager `pl.read_csv()` calls materialized many unused columns.
**Decision:** Step 7 now reads only columns it actually uses:
- `ptmall.txt`: `peptide`, `spectrum_title`, `ptm_peptide`, `ptm_modification`,
  `ptm_score`.
- `psmrankall.txt`: `spectrum_title`, `confident`.
- `PDVExportResult.txt`: `Spectrum_Title`, `peptide`, `ions`.
Also added `--memory` to `tarsus run`, defaulting the master orchestration job
to 32GB because Steps 7-11 are not lightweight for full datasets.
**Rationale:** This preserves scientific behavior while reducing memory pressure
substantially. On the trial data, Step 7 max memory fell to ~9GB and completed.
The CLI memory option allows future runs to tune the master job without code
edits.

## D-041: PDV Report Mode + Shard Failure Safety
**Date:** 2026-07-07
**Context:** The initial sharded Step 6 implementation used `-ft pdf`, matching
the active line in the reference `aggregate_query.sh`, but PDV source shows
`PDVExportResult.txt` is only written when `-ft report`. Step 7 consumes
`PDVExportResult.txt`; PDFs are not used downstream. Sharded runs also revealed
that failed PDV shards may leave partial report files behind, and the old LSF
polling helper treated `EXIT` as merely terminal.
**Decision:** Step 6 production PDV runs now use `-ft report`, not `-ft pdf`.
Shard resume/merge treats an export as reusable only if the shard log has no
failure markers (`Traceback`, `Exited with exit code`, etc.). `wait_for_jobs()`
now raises immediately on `EXIT`, preventing partial child-job output from being
merged silently. `XvfbDisplay` now tries a broad display-number range so dozens
of shard jobs can coexist on one compute node without `:99..:96` exhaustion.
**Rationale:** The pipeline's required PDV artifact is the ion report, not image
figures. Failing fast on child-job failures and refusing partial shard reports
prevents incomplete PDV ion annotations from contaminating Step 7 confidence
filtering.

## D-040: Inherited Duplicate `(peptide, spectrum_title)` Ion-Annotation Overwrite Caveat
**Date:** 2026-07-07
**Context:** Step 7 builds a nested dict from PDV's `PDVExportResult.txt` using
`pdv_export[peptide][spectrum_title] = ions`. This silently overwrites earlier
rows when multiple PDV export rows share the same `(peptide, spectrum_title)`
key. The current real dataset has substantial duplication at this level:
617,573 PSM rows, 158,476 unique `(peptide, spectrum_title)` pairs, and 71,843
pairs occurring more than once. This matters scientifically because Step 7's
final two-fragment coverage filter uses the surviving ion string for that key;
a different surviving duplicate could theoretically flip pass/fail for a
candidate.
**Investigation:** Confirmed this is not a new porting/sharding artifact. The
original reference pipeline has the same silent overwrite behavior at
`/home/labs/pilpel/elizabev/TARSUS/analyze_outputs.py:120`:
`psmdict[psm['peptide']][psm['Spectrum_Title']] = ionseries`.
PDV itself also writes PDFs with filenames based only on
`spectrumTitle + "_" + peptide + ".pdf"`, so duplicate PDFs collide in the
same last-write-wins style. PDV internally disambiguates repeated spectrum
rows as `spectrum_title + "_rank_" + N`, but that rank suffix is only a
HashMap key and is not written to `PDVExportResult.txt`.
**Decision:** Do not silently change this scientific behavior in the port. Keep
compatibility with the reference pipeline and document/report the caveat. Any
future fix (e.g. carrying rank/modification through PDV export or aggregating
all duplicate ion strings instead of overwriting) would change downstream
confidence calls and needs explicit scientific review.
**Rationale:** Scope discipline and scientific reproducibility: the current
pipeline should first reproduce/reference-match the inherited method. Fixing
this may be worthwhile, but it is a methodological change, not a safe bugfix.

## D-039: PDV Parallelization by LSF Sharding, Grouped by `spectrum_title`
**Date:** 2026-07-07
**Context:** PDV has no usable thread/parallelism flag. Decompilation of
`PDVCLIMainClass` and CLI experiments confirmed the CLI accepts no worker-count
option; `-Djava.awt.headless=true` also cannot avoid GUI construction. A single
PDV process processes the real Step 6 dataset too slowly (~4 PDFs/sec observed)
and, when run inside the 4GB master job, can exceed LSF's memory limit because
Python + a 4GB PDV JVM share the same LSF cgroup.
**Decision:** Parallelize PDV externally in Step 6 by splitting `psmrankall.txt`
rows into shards and submitting one `_pdv_worker.py` LSF child job per shard.
Each shard gets its own rank file, peptide list, output directory, LSF memory
reservation, and JVM heap. After all shard jobs finish, Step 6 merges
`PDVExportResult.txt` with a single header and moves PDFs into the final
`pdv_spectra/` directory.
**Important refinement:** Shards are grouped by `spectrum_title`, not by raw row
number alone. All rows for one spectrum stay in the same PDV process. This does
not fix D-040's inherited duplicate overwrite behavior, but it avoids adding a
new source of cross-shard nondeterminism to it.
**Rationale:** This is the only practical speedup path without modifying PDV
source. It also fixes the observed master-job memory-limit failure because the
heavy JVMs now run as child LSF jobs with independent reservations instead of
inside the master's 4GB envelope. Tests now monkeypatch `submit_bsub` and
`wait_for_jobs` to guarantee unit tests never submit real LSF jobs.

## D-037: Self-Contained Xvfb Bundle (supersedes D-036's module-load approach)
**Date:** 2026-07-06
**Context:** D-036 (same day, superseded within hours) fixed Xvfb startup by
shelling out to `module load Xvfb/<ver>` before launching the binary. This
worked, but ties the pipeline to this cluster's EasyBuild/Lmod module system
— violating D-004 (self-contained tool distribution, no cluster-specific
dependencies). The user flagged this immediately.
**Investigation (in order):**
1. **Checked if PDV has a real headless mode.** No: `-Djava.awt.headless=true`
   still throws `HeadlessException`. `PDVCLIMainClass`'s constructor
   unconditionally does `new JFrame(...)`, and Java's headless mode
   categorically forbids `Window`/`Frame` construction — there is no flag or
   property that bypasses this. Confirmed on both PDV 2.1.2 and 2.2.3.
2. **Checked if Xvfb is part of the original reference pipeline.** No:
   `TARSUS_elizabev/aggregate_query.sh` calls `java -jar PDV....jar` directly
   with zero display handling. The original author must have run this
   interactively with a real/forwarded X11 session (e.g. `ssh -X`). Xvfb was
   entirely our own addition (D-020) to support unattended LSF batch
   execution, and was never actually load-bearing tested outside a shell
   that happened to have `module load` already active.
3. **Tried conda-forge's `xorg-x11-server-xvfb` packages** (both the plain
   `-conda-x86_64` variant and the portable `-cos7-x86_64` CDT baseline
   variant, via a throwaway `micromamba` env — used only as a build-time
   fetch tool, not a runtime dependency). Both are missing `libXfont2.so.2`,
   `libXdmcp.so.6`, and `libcrypto.so.10`. `libXfont2` is not published as a
   standalone package on conda-forge at all — a real, unfixable gap in that
   feedstock. Dead end.
4. **Vendored the working EasyBuild build ourselves.** The EasyBuild
   `Xvfb/21.1.9-GCCcore-13.2.0` binary resolves every dependency except
   `libbz2.so.1.0` (confirmed via `ldd`). Copied the binary + its full
   non-universal `.so` closure (`libX11`, `libXext`, `libXau`, `libXdmcp`,
   `libxcb`, `libXfont2`, `libfontenc`, `libfreetype`, `libpng16`,
   `libpixman-1`, `libxshmfence`) into `tools/xvfb/{bin,lib}/`. Sourced
   `libbz2.so.1.0` separately and safely from conda-forge's standalone
   `bzip2` package (public URL, pinned SHA256, only depends on `libc`).
   Discovered and fixed a second missing piece during testing: Xvfb forks a
   helper binary (`xkbcomp`) at startup to compile the keyboard map; that
   helper needed `libxkbfile.so.1`, also copied from the same EasyBuild X11
   tree (matching toolchain version, ABI-consistent with the rest).
**Decision:** `tools/xvfb/` is now a committed, self-contained bundle (7.1 MB,
14 files, checksums in `tools/xvfb/CHECKSUMS.sha256`). `XvfbDisplay` in
`src/tarsus/env.py` was rewritten to launch `tools/xvfb/bin/Xvfb` directly
with `LD_LIBRARY_PATH` pointed only at `tools/xvfb/lib/` — no `module load`,
no Lmod, no cluster-specific paths at runtime. `$DISPLAY`, if already set
(e.g. user's own X11/VNC session), is still honored and skips Xvfb entirely.
Added `make xvfb` / `make test-xvfb` targets (Makefile) matching the existing
JDK/.NET bundling pattern; `.gitignore` updated to track `tools/xvfb/` despite
the blanket `tools/**` ignore (same exception pattern as the PDV JAR).
**Rationale:** Matches D-004's self-containment principle exactly — anyone
cloning the repo gets a working headless PDV without needing this specific
cluster's module system. The EasyBuild-sourced files are pinned by checksum
for reproducibility but were extracted from a live cluster install rather
than a public URL; this is documented as a known limitation in
`tools/README.md` (a lab on a different cluster without an equivalent Xvfb
build would need to redo the one-time extraction, or just set `$DISPLAY`).
**Verification:** `make test-xvfb` passes (display becomes ready standalone).
Ran the actual PDV command from the stalled pipeline run (125370) against it:
the `HeadlessException`/`AWTError` is completely gone. A *different*,
unrelated bug surfaced one layer deeper — see D-038.

## D-038 (RESOLVED 2026-07-06, same day): PDV `TextImport.parseTextFile` ArrayIndexOutOfBoundsException
**Date:** 2026-07-06
**Context:** With D-037's Xvfb fix in place, re-running the exact PDV command
that pipeline run 125370 hung on (Step 6, `output/trial/06_aggregated/`)
produces a new failure, one layer past the display problem:
```
Exception in thread "main" java.lang.ArrayIndexOutOfBoundsException: Index 3
out of bounds for length 1
    at PDVCLI.TextImport.parseTextFile(TextImport.java:119)
    at PDVCLI.TextImport.<init>(TextImport.java:80)
    at PDVCLI.PDVCLIMainClass.importFile(PDVCLIMainClass.java:676)
```
This strongly suggests PDV is trying to parse `psmrankall.txt` (or
`peptides.txt`) expecting more tab-separated columns than are present on at
least one line — likely a format mismatch between what our Step 6
aggregation logic (`step06_aggregate_query.py`) produces and what PDV's
`TextImport` parser expects for the `-i` (peptide list) or `-r` (rank
results) input.
**Also observed:** after throwing this exception, the JVM does not exit —
the process hangs indefinitely (observed via `subprocess.run(..., timeout=120)`
timeout, and a 300s timeout in an earlier test). This means in production,
Step 6 would not fail fast; it would hang until LSF's queue wall-time limit
kills it. Worth wrapping the Step 6 PDV subprocess call with an explicit
`timeout=` in `step06_aggregate_query.py` regardless of the root-cause fix
below.
**Root cause confirmed:** `grep -c "^$" psmrankall.txt` returned exactly
4568 — matching the PepQuery chunk count. Decompiled `TextImport.class`
with CFR to confirm the exact mechanism: `getParameters()` reads the header
row of the `-r` file (`psmrankall.txt`) and maps column names
(`spectrum_title`, `peptide`, `modification`, `charge`) to indices;
`parseTextFile()` then indexes into every subsequent line by those fixed
indices. `step06_aggregate_query.py`'s concatenation logic
(`content.split("\n")` on a newline-terminated file always yields a trailing
empty string; stripping the header via `lines[1:]` for `i > 0` files left
that trailing empty string as a lone blank line for every chunk with a
header-only, zero-match `psm_rank.txt`) produced exactly one stray blank
line per zero-match chunk. A blank line splits by `\t` into a length-1
array; PDV unconditionally indexes `values[3]`/`values[4]` →
`ArrayIndexOutOfBoundsException: Index 3 out of bounds for length 1`. Exact
match confirmed.
**Fix applied:** filter `if line.strip()` when building the `lines` list for
both the `psmrankall.txt` and `ptmall.txt` concatenation loops in
`step06_aggregate_query.py`. Verified: regenerated `psmrankall.txt` has 0
blank lines (previously 4568). 5/5 unit tests + mypy pass.
**Also fixed (robustness, same function):** added an explicit `timeout=`
to the PDV `subprocess.run()` call, since the JVM was observed not exiting
reliably after an uncaught exception (would otherwise hang until LSF's
wall-time limit). Initial value (1800s) was too conservative for
production-scale data and had to be raised to 28800s (8h) after a real run
was killed mid-flight at 7153/23171+ PDFs generated (~4/sec throughput
observed, real datasets have tens of thousands of unique peptides). Verified
`gsla-cpu` queue RUNLIMIT is 45000 min (750h) — no queue-level constraint
for an 8h step.
**Rerun via LSF:** used the existing sentinel-checkpoint resume mechanism
(no code changes needed) — `tarsus run` with the same inputs skips Steps
1–5 (`.done` present) and resumes at Step 6. Two resubmissions this session:
job 920703 (killed by the initial 1800s timeout, later raised) and job
928042 (running with the corrected 8h timeout as of session end). Backed up
`master.log` before each resubmission (LSF's `-oo` overwrites it) so run
history isn't lost.
**Existing data preserved throughout:** the original
`output/trial/05_pepquery/` PepQuery chunk results (the expensive,
hours-long compute) were never touched, deleted, or regenerated at any
point. The Step 6 aggregation files (`psmrankall.txt`, `mgfall.mgf`,
`peptides.txt`, `ptmall.txt`) were intentionally regenerated by Step 6
itself once fixed — expected, cheap (minutes), and correct behavior for a
step re-run, not data loss.

## D-036: XvfbDisplay Must Set Module LD_LIBRARY_PATH and Verify Process Liveness
**Status:** SUPERSEDED by D-037 same day — kept for history, do not re-implement.
**Date:** 2026-07-06
**Context:** Pipeline run 125370 (2026-07-01) stalled at Step 6 with PDV failing
`java.awt.AWTError: Can't connect to X11 window server using ':99'`. Root cause:
`XvfbDisplay` (D-020) launches the EasyBuild Xvfb binary via bare `subprocess.Popen`
without the toolchain's `LD_LIBRARY_PATH`. The binary dies immediately
(`error while loading shared libraries: libbz2.so.1.0`), but `XvfbDisplay.__enter__`
only catches `FileNotFoundError` and does not check whether the process is still
running after the startup grace period. It sets `DISPLAY` regardless, so PDV
fails downstream instead of failing fast with a clear error.
**Decision:** `XvfbDisplay` now derives `LD_LIBRARY_PATH` (and other required env)
from the selected Xvfb module's sibling directories (matching EasyBuild's module
convention: the toolchain's `lib`/`lib64` directories under the same GCCcore
version tree), and polls `Popen.poll()` after the startup sleep to confirm the
process is still alive before returning `DISPLAY`. If a display candidate's Xvfb
process dies, it tries the next display number; if all fail, it raises
`RuntimeError` with the captured stderr instead of silently returning a dead
display.
**Rationale:** Fail fast with a diagnosable error rather than have the bug surface
three steps and hours of compute later at PDV. This also matches D-013's principle
of validating pipeline preconditions early. No change to the D-020 architecture
(Xvfb-on-EasyBuild approach) — only to its robustness.

## D-035: LSF Purged-Job Handling + Step05 Resume Logic
**Date:** 2026-07-01
**Context:** `wait_for_jobs()` in `src/tarsus/lsf.py` polls `bjobs` to detect when child
jobs finish. LSF purges completed jobs from `bjobs` output after a short retention
window, which produces empty stdout with exit code 0. The polling loop treated this
as "job still active" (mistaking silence for pending state), causing indefinite
stalls waiting on jobs that had, in fact, already finished (commonly for the 4500+
chunked PepQuery step 5 jobs, which finish and get purged faster than slower steps
are polled).
**Decision:** `wait_for_jobs()` now treats empty stdout, or stderr containing "not
found", as a terminal (finished) state rather than "still running". Additionally,
`step05_query_psm()` gained resume logic: chunks with an existing `psm_rank.txt`
are skipped on restart, so a partially-completed Step 5 (e.g. after a stall or
manual restart) does not redo already-finished PepQuery chunk searches.
**Rationale:** Prevents indefinite hangs caused by a state-detection gap in LSF
polling. The resume logic makes Step 5 restart-safe and cheap to re-invoke after
any master-job interruption, in line with the sentinel-checkpointing philosophy
from D-017.

## D-034: IonQuant 1.11.20 Added as Required Tool Dependency
**Date:** 2026-06-30
**Context:** FragPipe 24.0's Linux ZIP distribution does not bundle IonQuant.jar (unlike the Windows distribution). The pipeline failed with missing IonQuant at Step 3a/3c when FragPipe internally calls IonQuant for quantification.
**Decision:** Add IonQuant 1.11.20 as a separate tool dependency in `tools/Makefile`. Copy the JAR from the reference installation at `/home/labs/pilpel/slavat/fragpipe-24.0/tools/IonQuant-1.11.20.jar`. Add `ionquant` target and `test-ionquant` check to `make setup`.
**Rationale:** IonQuant is a hard dependency of FragPipe's quantification module. Without it, FragPipe exits with an error before producing any results. Including it in `make setup` ensures it is always present.

## D-033: Target-Decoy FASTA Generated Inline for Both 3a and 3c Passes
**Date:** 2026-06-30
**Context:** FragPipe requires a target-decoy FASTA for FDR estimation (it reads the `rev_` tag to identify decoys). The reference pipeline assumed decoys were baked into the workflow configuration. Steps 3a and 3c both need decoys but the raw FASTA has none.
**Decision:** Add `_make_decoy_fasta()` to both `step03a_first_pass.py` and `step03c_second_pass.py`. This function reads the input FASTA, writes forward sequences plus reversed copies with `>rev_` prefix, outputting `protein_decoy.fasta`. The workflow `database.db-path` is set to the decoy FASTA, and `database.decoy-tag=rev_` is patched.
**Rationale:** Generates decoys inline without requiring pre-processed FASTA files. Both passes get independent decoy FASTA files in their own output directories. The reversed-sequence approach is the standard FragPipe convention.

## D-032: FragPipe 24.0 Scan Number Mismatch — Peptide-Only PepQuery Input
**Date:** 2026-06-30
**Context:** FragPipe 24.0 uses internal scan numbering that does not match the native mzML scan numbers. Step 4 originally extracted `peptide:scan:charge` spectrum titles for PepQuery's targeted search mode, but the scan numbers from FragPipe's `Spectrum` column did not correspond to PepQuery's indexed scan numbers. This caused "Matched spectra: 0" for every peptide.
**Decision:** Switch Step 4 output from two-column (peptide + spectrum_title) to one-column (peptide only). PepQuery runs in open-search mode (`-aa` flag), which searches all indexed spectra for each peptide without requiring a scan number match. Step 4's `extract_psm()` function now writes only peptide sequences.
**Rationale:** PepQuery's open-search mode finds matching spectra by peptide sequence alone — scan numbers are irrelevant. This bypasses the FragPipe/PepQuery scan numbering mismatch entirely. For the variant-peptide validation use case (confirming variant peptides exist in the data), open-search is correct: it returns all spectra matching the peptide sequence regardless of scan position.

## D-031: Header-Free PepQuery Input (Peptide-Only Format)
**Date:** 2026-06-30
**Context:** Step 4 output originally had a TSV header line (`peptide\tspectrum_title`). Step 5 (`step05_query_psm`) split this file into chunks and prepended the header to each chunk. PepQuery interpreted the header repetition as data, causing parse errors and zero matched spectra.
**Decision:** Remove the TSV header from Step 4 output entirely. Step 5 splits raw lines without header handling — each line is one peptide. PepQuery receives peptide-only input with no header, column names, or spectrum titles.
**Rationale:** PepQuery's open-search mode reads one peptide per line. Headers and spectrum titles are not expected and cause parse errors. Peptide-only input is simpler, faster, and correct for the use case.

## D-030: PepQuery `-db` Must Point to Raw FASTA, Not Index Directory
**Date:** 2026-06-30
**Context:** The `-db` flag in PepQuery validation (Steps 5 and 9) was set to `str(index_dir.resolve())` — the PepQuery index directory. PepQuery uses the `-db` path to resolve sequence annotations for matched spectra. Pointing it at the index caused PepQuery to fail silently (no error, no matches).
**Decision:** Pass the user's `--fasta` path through orchestration to both `step05_query_psm()` and `step09_query_psm_base()`. Use `str(fasta_path.resolve())` for the `-db` flag instead of the index directory. Add `fasta_path: Path | None = None` parameter to both functions.
**Rationale:** The FASTA file is required for PepQuery to annotate matched spectra with protein names and sequence context. The index directory path was a copy-paste error from the reference implementation.

## D-029: MSBooster Fully Disabled in Step 3c Second Pass
**Date:** 2026-06-30
**Context:** The FragPipe workflow template has `msbooster.run-msbooster=true`, `msbooster.predict-rt=true`, and `msbooster.predict-spectra=true` by default. Step 3c (variant-peptide second pass) was only disabling `find-best-rt-model=false`. MSBooster was still attempting to calibrate RT/spectra predictions on the nocleavage search results, causing silent hangs and excessive wall time (30+ minutes).
**Decision:** Add three additional MSBooster workflow patches to `step03c_second_pass.py`: `msbooster.run-msbooster=false`, `msbooster.predict-rt=false`, `msbooster.predict-spectra=false`.
**Rationale:** MSBooster calibration requires training data that does not exist for variant-peptide second-pass searches (different enzyme, different search space). Fully disabling all MSBooster features prevents wasted compute and potential hanging.

## D-028: Step 2 Reordered After Step 3a — Index `_sub.mzML`, Not Original mzML
**Date:** 2026-06-30
**Context:** Step 2 (PepQuery index) originally ran immediately after Step 1, indexing the full mzML files in `01_mzml/`. But PepQuery validation (Step 5) searches against `*_sub.mzML` — the unidentified spectra output by FragPipe's first pass. The index must contain only the spectra that Step 5 will actually search against. Indexing full mzML was also wasteful: 60 minutes to index spectra that would never be searched.
**Decision:** Reorder pipeline execution so Step 2 runs AFTER Step 3a. The index directory is built from `03a_first_pass/*_sub.mzML` instead of `01_mzml/*.mzML`. The `summary.txt` also strips `_sub` from `ms_file` paths (D-027) so PepQuery can match spectrum filenames. Data flow changes from `01_mzml → 02_index` to `03a_first_pass → 02_index`.
**Rationale:** Only the unidentified spectra from Step 3a's `_sub.mzML` files are searched by Step 5. Indexing the full mzML is a 2× waste (60 min indexing of already-identified spectra). The reorder also simplifies workflow: Step 3b (variant peptide generation) uses Step 3a's `peptide.tsv`, which is now produced before Step 2 runs. The `summary.txt` `_sub` stripping ensures PepQuery's internal filename matching works correctly.

## D-001: LSF Cluster as Deployment Target
**Date:** 2025-06-11
**Context:** The reference pipeline relies on LSF (bsub) for job submission. The institute operates an LSF cluster.
**Decision:** Keep LSF as the execution environment. Do not introduce Docker or other containerization at this stage.
**Rationale:** The target audience (academic labs within the institute) already uses the LSF cluster. Containerization adds complexity without immediate benefit. All tool paths and cluster parameters must be externalized for cross-lab portability.

## D-002: Python Package Structure
**Date:** 2025-06-11
**Context:** The reference implementation is a loose collection of scripts without a package structure.
**Decision:** Organize all Python code as a proper package under `src/tarsus/`.
**Rationale:** Enables import-based reuse, testing, type checking, and dependency management via uv.

## D-003: Configuration-Driven Design
**Date:** 2025-06-11
**Context:** Every script in the reference implementation contains hardcoded paths to tool installations and databases.
**Decision:** All tool paths, database paths, and cluster parameters must be externalized via environment variables or a config file.
**Rationale:** Different labs within the institute have different tool installation directories and data locations. No code changes should be required to adapt the pipeline.

## D-004: Self-Contained Tool Distribution (supersedes original D-004)
**Date:** 2025-06-16 (revised)
**Context:** Original D-004 assumed tools were pre-installed on cluster. We now want full control over versions and distribution, independent of the cluster.
**Decision:** All external tools are downloaded and pinned in `tools/` via a Makefile. Each tool version is explicit, checksum-verified. The pipeline discovers tools at a configurable path (default `tools/`).
**Rationale:** Removes dependency on cluster administrators for tool maintenance. Enables reproducible deployments. The Makefile pattern means anyone can run `make setup` and have a working environment. Dockerization in the future will bundle these tools.

## D-005: Python Orchestration
**Date:** 2025-06-11
**Context:** The reference pipeline uses bash for orchestration (job submission, file management, tool invocation).
**Decision:** Replace bash orchestration with Python where feasible, using subprocess for external tool calls. Keep minimal bash wrappers for LSF job submission where unavoidable.
**Rationale:** Python provides better error handling, logging, configuration management, and testability compared to bash.

## D-006: TARSUS_elizabev is Read-Only Reference
**Date:** 2025-06-11
**Context:** The `TARSUS_elizabev/` directory is a symlink to the colleagues' working directory.
**Decision:** Never modify files inside `TARSUS_elizabev/`. It is read-only reference material for understanding pipeline logic.
**Rationale:** It is someone else's code. Our job is to re-implement, not modify. Changes to the reference would cause confusion.

## D-007: No Embedded Reference Database
**Date:** 2025-06-16
**Context:** The reference implementation hardcodes a specific organism's FASTA path.
**Decision:** The pipeline does not ship with a default reference database. Users always supply `--fasta` explicitly.
**Rationale:** The project supports multiple organisms (E. coli, human, mouse, etc.). An embedded default would imply E. coli is special. The `data/` directory contains test fixtures only.

## D-008: User-Driven Pipeline Entry
**Date:** 2025-06-16
**Context:** The reference pipeline assumes specific file paths and a fixed batch.
**Decision:** The pipeline requires explicit `--fasta`, `--input` (one or more), and `--output-dir` flags. No auto-discovery of files.
**Rationale:** Users need full control over which files to process and in what batches. The same raw file can be analyzed against different references.

## D-009: Git Tracking Policy
**Date:** 2025-06-16
**Context:** Raw MS files are 7-11 GB each. Reference FASTA is user-supplied.
**Decision:** Only source code, documentation, and configuration are tracked. All of `data/` (except `data/README.md`) and `output/` are gitignored.
**Rationale:** Large binary files have no place in git. Every lab brings their own data and reference.
*Note: Small test fixtures in `data/test-pdv/` are tracked via `.gitignore` exception (`!data/test-pdv/**`).*

## D-010: Organism-Based Reference (Future)
**Date:** 2025-06-16
**Context:** The pipeline currently requires manual FASTA download for each organism.
**Decision:** Deferred. A future `--organism` flag will auto-fetch Uniprot proteomes on demand.
**Rationale:** The feature adds non-trivial download/caching logic. Not needed until the pipeline is used by multiple labs.

## D-011: Bundle Java 21 and .NET 8 Runtimes
**Date:** 2025-06-16
**Context:** The system lacks Java and .NET runtimes, making FragPipe, PepQuery, PDV, and ThermoRawFileParser unusable.
**Decision:** Download and pin JDK 21 (Eclipse Temurin, jdk-21.0.11+10) and .NET 8 runtime (8.0.28) into `tools/` via Makefile. The pipeline sets `JAVA_HOME`, `DOTNET_ROOT`, and `PATH` at runtime via `src/tarsus/env.py`.
**Rationale:** Full self-containment — a developer can clone the repo, run `make setup`, and have a complete working environment. No system package manager or cluster module dependencies. The Makefile pins exact versions with SHA256 verification.

## D-012: LSF-Only Pipeline Execution
**Date:** 2025-06-16
**Context:** Raw MS files are 7-11 GB each; conversion and search steps are computationally intensive.
**Decision:** Steps 1, 2, 3, 5, 6, 9, and 10 run exclusively via LSF cluster (bsub). The pipeline submits one job per file per step and waits for completion. Python analysis steps (3b, 4, 7, 8, 11) run locally.
**Rationale:** The reference pipeline was designed for cluster execution. Single-machine processing of multi-GB raw files is impractical. The `--local` flag exists for debugging, not production.

## D-013: Golden-File Validation Framework
**Date:** 2025-06-16
**Context:** Every pipeline step must be validated against the trial data to ensure correctness.
**Decision:** Validation uses a golden-file capture pattern. On first run, expected output properties (scan counts, file sizes, row counts) are captured to `tests/validation/expected/*.yaml`. Subsequent runs compare against these values. Captured values are tracked in git and reviewed manually.
**Rationale:** Scientific pipelines have stable, data-specific output characteristics. Golden-file capture automates the process while keeping human review in the loop.

## D-014: CLI and Configuration Stack
**Date:** 2025-06-16
**Context:** The pipeline needs a consistent CLI interface and configuration mechanism.
**Decision:** Use `click` for CLI, environment variables for configuration (with `--flag` overrides), and `pyproject.toml` console_scripts for entry point. No config file format — env vars are simpler for cluster environments and Docker.
**Rationale:** click is the standard Python CLI library. Env vars work naturally with LSF job submission and Docker. No config file parsing needed.

## D-015: Trial Data as Validation Reference
**Date:** 2025-06-16
**Context:** Test data exists in `data/` (protein.fasta + two .raw files from the same E. coli K12 sample).
**Decision:** The trial data is the canonical reference for all validation. Every validation test uses these exact files. Expected output schemas are derived from running on this data. Adding new trial data requires updating the validation expected files.
**Rationale:** Using real rather than synthetic data ensures the validation catches real pipeline issues. The trial data is small enough (relative to production) for iteration.

## D-016: LSF Verified Working
**Date:** 2025-06-29
**Context:** Before building pipeline orchestration, needed to confirm the cluster is accessible.
**Decision:** Verified: `bsub` available (IBM Spectrum LSF 10.1.0.0), `gsla-cpu` queue Open:Active. Test job (ID 854986) submitted and completed. Trial data files present (protein.fasta 1.9 MB, two .raw files 7.3+11 GB). No blockers for LSF-based execution.
**Rationale:** Confirms the target environment matches the original architecture decision D-001.

## D-017: Master-Job Architecture (All-LSF)
**Date:** 2025-06-29
**Context:** User requires all pipeline steps to execute on LSF — nothing on the login node beyond initial submission.
**Decision:** A single "master" LSF job orchestrates the entire pipeline. Heavy-tool steps (1, 2, 3a, 3c, 5, 9) submit child bsub jobs and wait. Python analysis steps (3b, 4, 6, 7, 8, 10, 11) run inline on the master job's compute node. The login node is only used for `bsub` submission.
**Rationale:** Keeps login nodes free for interactive use. Child jobs get appropriate resource allocations (memory, CPUs) per step. Python steps are lightweight and don't need separate LSF jobs.

## D-018: Bundled Reference Assets
**Date:** 2025-06-29
**Context:** Steps 3a/3c need `generic.workflow` (FragPipe workflow template). Step 3b needs `subs_exclude.csv` (AA substitution exclusion matrix). Both were referenced from `TARSUS_elizabev/`.
**Decision:** Bundle both files in `src/tarsus/assets/`. Import via module constant (`WORKFLOW_TEMPLATE`, `SUBS_EXCLUDE_CSV`). Remove all runtime dependencies on `TARSUS_elizabev/`.
**Rationale:** Makes the package fully self-contained — no external file references. Matches D-006 (TARSUS_elizabev is read-only reference). Users don't need the reference directory at all.

## D-019: Minimal CLI Interface
**Date:** 2025-06-29
**Context:** The pipeline has many internal paths (workflow templates, exclusion matrices, output subdirectories) but users should not need to know them.
**Decision:** `tarsus run` requires only 3 flags: `--fasta`, `--input` (repeatable), `--output-dir`. All other paths are auto-derived. Internal assets are bundled in the package. Advanced options (queue, memory, CPUs) have sensible defaults.
**Rationale:** Reduces cognitive load for new users. Follows the "convention over configuration" pattern. Advanced users can still override via environment variables.

## D-020: PDV 2.1.2 with Xvfb Display Manager
**Date:** 2025-06-29
**Context:** PDV requires an X11 display even in CLI mode (JFrame created in constructor). Both 2.1.2 and 2.2.3 crash with HeadlessException without a display. The cluster has Xvfb available via EasyBuild modules (no sudo).
**Decision:** Bundle PDV 2.1.2 JAR (matches reference), symlink lib/ from 2.2.3 for shared dependencies. Add `XvfbDisplay` context manager in env.py: automatically detects and starts Xvfb from the cluster module system when `$DISPLAY` is not set.
**Rationale:** No version-specific GUI workarounds needed. Xvfb is already on the cluster. The context manager pattern ensures clean startup/shutdown with zero GUI windows.

## D-021: Unbuffered Python Output for LSF Jobs
**Date:** 2025-06-29
**Context:** The master job's `print()` calls were fully buffered when stdout was redirected to a file by `bsub -oo`. Logs showed no progress until the buffer filled or the job exited.
**Decision:** Set `PYTHONUNBUFFERED=1` in `os.environ` before submitting the master bsub job. This propagates via `tool_env.env()` and ensures all Python output flushes immediately to the LSF log file.
**Rationale:** Real-time log visibility is critical for monitoring long-running pipeline jobs. No downside — all Python output, including from child subprocesses, becomes unbuffered.

## D-022: PDV Export Path Resolution
**Date:** 2025-06-29
**Context:** Step 7 (`analyze_outputs`) reads a TSV file with PDV ion annotations. The master.py orchestration script had the path hardcoded to `pdv_export.tsv`, but PDV actually writes `PDVExportResult.txt` inside the `pdv_spectra/` directory.
**Decision:** Corrected the path in the master.py template to `06_aggregated/pdv_spectra/PDVExportResult.txt`. Verified against the reference pipeline's actual file naming convention.
**Rationale:** The wrong path caused Step 7 to silently skip PDV ion data (the try/except caught the FileNotFoundError), which meant the two-fragment coverage filter was always bypassed. This fix restores the intended filtering behavior.

## D-023: Mock Dev Dataset for Fast Iteration
**Date:** 2025-06-30
**Context:** Pipeline debugging requires 60+ minute iterations because each step processes 6-8 GB mzML files. A 10 MB mock dataset with 50 spectra would reduce iteration time to seconds.
**Decision:** Create a small mock mzML file by extracting the first 50 spectra from the real mzML using a Python script (`scripts/make_mock_mzml.py`). Track it in `data/test-mock/` alongside a mock FASTA. Add validation tests (golden-file pattern) for Steps 2, 3a, 7 that run against the mock data without requiring LSF.
**Rationale:** Enables sub-minute feedback cycles for pipeline development. Uses the existing golden-file validation pattern (capture on first run, compare on subsequent). Does not require LSF — steps are called directly. The mock data is valid mzML (subset of real data), so pipeline behavior is representative.

## D-024: gsla-cpu as Universal Default Queue
**Date:** 2025-06-30
**Context:** Steps 5 and 9 originally used the "short" queue, which was intermittently unavailable. All other steps already used gsla-cpu.
**Decision:** All pipeline steps default to gsla-cpu queue. No step uses "short" by default.
**Rationale:** Simplifies configuration, avoids queue-availability problems, and ensures consistent scheduling behavior across all steps.

## D-025: Step 3c Must Use _sub.mzML (Unidentified Spectra)
**Date:** 2025-06-30
**Context:** Step 3c (FragPipe second pass, nocleavage) was pointed at the original mzML files from Step 1 (`01_mzml/`). It should search against `*_sub.mzML` files from Step 3a (`03a_first_pass/`) — the unidentified spectra that didn't match in the first pass.
**Decision:** Changed `orchestration.py` line 87 from `mzml_dir=outdir / "01_mzml"` to `mzml_dir=outdir / "03a_first_pass"`.
**Rationale:** Running the second pass on ALL spectra instead of only unidentified spectra defeats the purpose of the two-pass pipeline. It wastes compute on already-identified peptides and artificially inflates the search space. The `*_sub.mzML` files are the correct input — they contain only the spectra that need variant-peptide searching.

## D-027: PepQuery Index Must Be Flat .mgf at Root, Multi-File Bins Concatenated
**Date:** 2026-06-30
**Context:** Step 05 (PepQuery validation) ran successfully (LSF exit 0) but produced zero results — every `detail.txt` was header-only and no `psm_rank.txt` appeared. Root cause investigation via chunk logs showed three bugs in step02's merge logic:
1. MGF files were placed in `pepquery_index/tmp/<mzml_name>_<idx>/` subdirectories, but PepQuery search looks for files flat at the root of the index directory.
2. Files were left as `.mgf.gz`; PepQuery search expects uncompressed `.mgf`.
3. The native `summary.txt` generated by PepQuery's own `index` command was overwritten with a custom version that stripped `_sub` from `ms_file` paths, pointing to non-existent files.
Additionally: PepQuery organises spectra into mass-bin files (named by `floor(precursor_mass × ~20)`). Both HS-1 and LS-1 `_sub.mzML` files share overlapping mass-bin ranges, so a naive flat merge overwrites one file's spectra with the other's. Files must be **concatenated** (append mode).
**Decision:** Rewrite step02 merge logic to: (a) decompress `.mgf.gz` → `.mgf`, (b) place files flat at `pepquery_index/` root, (c) open each dest in append mode so same-mass-bin spectra from multiple mzML files are concatenated, (d) preserve the native PepQuery `summary.txt` (merge across files) instead of generating a custom one.
**Rationale:** PepQuery's `MsLibrarySearchWorker` constructs paths as `<index_dir>/<bin_id>.mgf` directly — no subdirectory traversal. Subdirectories and `.gz` extensions both cause silent "File doesn't exist" warnings and 0 matched spectra. The FASTA `.sqldb` warning seen in logs is benign — PepQuery re-indexes on the fly and continues.

## D-026: I/L Ambiguity in Mass Spectrometry
**Date:** 2025-06-30
**Context:** The substitution exclusion matrix (`subs_exclude.csv`) uses "I/L" notation for isoleucine/leucine positions. This string was leaking into peptide sequences, causing FragPipe/MSBooster to fail with "WARNING: Trying to compute mass of non-residue: /".
**Decision:** Normalize "I/L" → "I" in both the matrix column headers and the `_single_substitutions` function. FASTA headers retain "I/L" for informational clarity, but the actual peptide sequences use only canonical amino acid codes.
**Rationale:** Mass spectrometry cannot distinguish isoleucine from leucine — they have identical monoisotopic mass (113.08406 Da). Using "I" as the canonical representation is the standard convention in proteomics. The "/" character is not a valid amino acid and breaks downstream tools.
