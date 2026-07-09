# Progress Log

## Session 2026-07-09 (cont'd) — Ground truth located; root cause proven; Option C cancelled (D-047)

### What was done
Searched `TARSUS_elizabev/` for validation evidence. That symlink points only at the colleagues'
*scripts* repo — its `pepquery_inputs/` is empty and `pepquery_result/*/` is a literal `*` directory
left by an aborted run, which is why earlier sessions concluded no ground truth existed. The FragPipe
log `tarsus_analysis.txt` names their real working directory:
`/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/`. It holds a **complete, successful run**.

### The answer
The reference run **succeeds with exact targeted PepQuery validation** on the same instrument family
(Orbitrap Astral DDA): 37,729 two-column targeted PSMs → 15,232 `psmrankall.txt` rows → **3,922-row
`subs.ipc`** → **697-row `subs_localized.ipc`**. Ours: 45,678 one-column peptides → 617,573 rows → **0**.

Its PepQuery index is built from the **original** mzML, so index titles carry **no `_sub`**
(`TITLE=...-EVpar-LS-3:121018:2`), and both `extract_psm.py` and `analyze_outputs.py` strip `_sub`
from FragPipe's `Spectrum` column to land in that namespace. TARSUS_BC's commit `e143a46` moved
Step 2 to index `_sub.mzML` — a compute optimization that silently shifted the title namespace.
Everything since (D-032's false scan-number claim, D-044's lineage break, D-045's NPE, D-046's mass
disagreement) is downstream of that single change. The NPE and bin mismatch were self-inflicted by
`-varMod 2,33`, which the reference never passes.

### Decision: Option C is cancelled — see D-047
Do **not** implement `docs/superpowers/plans/2026-07-08-step7-proximity-lineage.md`. The fix is to
restore the reference contract: Step 2 indexes `01_mzml/`; Step 4 emits `peptide\tspectrum_title`
with `_sub` stripped; Step 7 strips `_sub` again; Step 5 unchanged. Invalidate sentinels
`02_index` → `08_base_input`; preserve Steps 01/03a/03b/03c.

### Ground truth now available for regression testing
`/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` — `subs.ipc`, `subs_localized.ipc`,
`psmrankall.txt`, `second/psm_input4pepquery.tsv`. Column sets already match ours 69/69 modulo
naming. Their original `.mzML` inputs are gone (only `_sub.mzML` survives), so exact reproduction
isn't possible; use them as a magnitude/schema oracle.

### No code changed; nothing under elizabev/ touched
`src/tarsus/` untouched. No step rerun. No sentinel deleted. All reads of
`/home/labs/pilpel/elizabev/` were read-only.

---

## Session 2026-07-09 — Migration status audit (no pipeline code changed)

### Question asked
"Is the migration done? Are Steps 3–6 mid-run? Why is Step 8 empty and Step 7 'done'?
How would I even know I succeeded?"

### Answer: the migration is NOT complete. Steps 1–6 are sound; Step 7 is the sole blocker.

**Steps 1–6: complete and internally consistent — not mid-run.** All sentinels stamped, all
artifacts substantial and non-truncated. No LSF jobs active. Sentinel times confirm the intended
DAG (`01 → 03a → {02 ‖ 03b → 03c} → 04 → 05 → 06`); Step 2 finishing *after* Step 3c is expected,
since both only depend on 03a and run in parallel (commit `e143a46`).

| Step | Sentinel | Key artifact | Size |
|------|----------|--------------|------|
| 01 | 06-29 16:49 | 2 × `.mzML` | 5.7 G |
| 03a | 06-30 13:14 | `psm.tsv` | 116 M |
| 03b | 06-30 13:14 | `pep_candidates.fa` | 299 M |
| 03c | 06-30 14:15 | `second/psm.tsv` | 39 M |
| 02 | 06-30 16:34 | 24,944 index MGFs | 6.4 G |
| 04 | 06-30 16:49 | `psm_input4pepquery.tsv` (45,678 peptides, **1 column**) | 864 K |
| 05 | 07-01 17:18 | 4,568 result files | 21 G |
| 06 | 07-07 09:42 | `psmrankall.txt` / `ptmall.txt` / PDV export | 29 G |

**Step 7 is stamped `.done` but `subs.ipc` is `(0, 69)` — zero rows.** Verified directly with
polars. Step 8 consumed 0 rows → wrote 0 base-input files → the guardrail in
`orchestration.py:176` raised, correctly halting before Steps 9–11. `master.log` confirms:
`Total DF titles: 0`. Steps 9/10/11 therefore do not exist in `output/trial/` at all.

### Root cause is *unchanged* since D-044/D-045 — the July 8 commit did not fix it
`c70f35e` ("correct Step 7 spectrum-title lineage bug") fixed a **real but insufficient** bug:
`_spectrum_to_title()` was stripping `_sub`. Correcting the title *format* does not help, because
the exact `(spectrum_title, peptide)` pairs Step 7 joins on were **never sent to PepQuery**. Step 4
emits peptide-only input (verified: `psm_input4pepquery.tsv` has exactly 1 column), so Step 5
open-searches each peptide against any indexed spectrum. Exact overlap with Step 3c pairs = 0
(D-044). No rerun of Steps 1–6 can fix this.

### The approved repair was never implemented
- Design spec: `docs/superpowers/specs/2026-07-08-step7-proximity-lineage-design.md` — "Approved by user".
- Implementation plan: `docs/superpowers/plans/2026-07-08-step7-proximity-lineage.md` — 959 lines,
  **every task checkbox still `- [ ]`**.
- Confirmed absent from the codebase: `src/tarsus/steps/_index_rt_cache.py` does not exist;
  `match_type` appears nowhere in `src/` or `tests/`; `step07_analyze_outputs.py:275` still does the
  exact-title `is_in(first_set | saved_set)` filter.

### ⚠️ Sentinel trap — read before the next rerun
`.done` is stamped unconditionally after a step runs, regardless of whether it produced rows.
`07_analyze/.done` and `08_base_input/.done` both exist over empty output. If Option C is
implemented and the pipeline rerun *without deleting those two sentinels*, `_skip_if_done()` will
skip Step 7 entirely and the fix will silently have no effect. Delete `07_analyze/.done` through
`11_localized/.done` before any Step-7 rerun (Steps 1–6 must be preserved — they cost ~65 GB and
several days of cluster time).

Related: an earlier run stamped Steps 7–11 `.done` over empty data and reported "Pipeline complete."
Those artifacts are quarantined in `output/trial/invalid_empty_downstream_20260707132848/`; its
`11_localized/subs_localized.csv` is **header-only (1 line)**. That vacuous success is exactly what
the Step 8 guardrail now prevents. There is still **no guardrail on Step 7 itself** — it will stamp
`.done` over a 0-row `subs.ipc` — so Step 8's check is currently the only thing standing between a
lineage bug and a false "complete".

### Acceptance criteria — how to know the migration actually succeeded
The pipeline is migrated when *all* of these hold, in order:
1. `uv run pytest -m "not lsf"` → all green (currently: 163 passed).
2. `07_analyze/subs.ipc` has **> 0 rows**, and (post-Option-C) reports its `exact` vs `proximity`
   `match_type` split.
3. `08_base_input/pepquery_input_base/` contains ≥ 1 chunk file, and `mgfall_fakes.mgf` is non-empty
   (it is currently **0 bytes**).
4. Steps 09/10/11 directories exist; `10_aggregated_base/psmrankall_base.txt` is non-empty
   (the quarantined copy is 0 bytes).
5. `11_localized/subs_localized.csv` has **> 1 line** (i.e. a header *and* data rows).
6. `master.log` ends with `[…] DONE: Pipeline complete.` and the LSF job exits 0.
Today only criterion 1 passes.

### Documentation corrected this session
`README.md` and `.context/architecture.md` both still asserted the D-032 rationale — "FragPipe 24.0
scan numbering does not match native mzML scan numbers" — which **D-045 Finding 1 tested and
disproved**. `architecture.md` further described the open-search workaround as "correct for the
variant-peptide validation use case", contradicting D-044's finding that it breaks Step 7's lineage
contract. Both replaced with the verified state and a pointer to the Option C spec/plan. Also fixed
the README's test instructions: it advertised `uv run pytest` / "151 tests", but a bare `pytest`
run **hangs** on 3 `@pytest.mark.lsf` real-tool tests; the counts are now 166 collected / 163 non-LSF.

### No pipeline code or outputs changed
`src/tarsus/` untouched. No step rerun. No sentinel deleted. No file under `output/trial/` modified.

---

## Session 2026-07-07 (cont'd) — Step 4/5→7 lineage forensics complete (D-045)

### What was done
Ran the full forensic/design session requested for the Step 4/5→7 lineage blocker (D-044), per `.planning/step07-lineage-repair.md`. Read reference `extract_psm.py`/`query_psm.sh`/`analyze_outputs.py` fully; audited FragPipe/mzML/PepQuery-index/PDV title namespaces; ran live tiny PepQuery experiments (not on production data/paths — scratch dir only, no pipeline outputs touched or reran).

### Key findings (full detail in D-045)
1. **D-032's stated root cause (FragPipe scan numbers don't match mzML) is factually wrong.** Verified directly: FragPipe `Spectrum` column scan numbers exactly match native mzML `scan=` numbers (checked via RT/charge cross-reference on 5 samples).
2. PepQuery's own index MGF titles and Step 5's `psm_rank.txt` titles both use `file_sub:scan:charge` (`_sub` preserved) — exactly what Step 7's current `_spectrum_to_title()` already computes. A deterministic Step-3c-to-PepQuery-index title mapping exists and is already correct in Step 7; it was just never given to Step 4/5's PepQuery input.
3. 86.6% of Step 3c positive-intensity PSMs carry unaccounted modifications (mainly protein N-term acetylation +42, M oxidation +15.99) not reflected in the bare `Peptide` string — naive targeted PepQuery calls miss the correct precursor-mass bin unless `-varMod 2,33` is passed.
4. **New blocker found:** even with all of the above fixed, PepQuery 2.0.2's targeted-PSM `-i peptide\tspectrum_title` code path throws a `NullPointerException` in `generatePeptideInputs`/`Peptide.getProteinMapping()` for novel (non-reference) peptides — reproduced on both a 30-candidate batch and a single hand-verified candidate/spectrum pair. This does NOT occur in the current production peptide-only open-search path (verified clean in real `pepquery_logs/chunk_1104.tsv.log`). This is an apparent PepQuery-internal bug/unsupported-combination blocking Option A (restore targeted lineage) until further investigated.

### Recommendation (not yet implemented — awaiting user decision)
Pursue **Option C (hybrid proximity acceptance)** as the near-term unblock: reuse the already-working peptide-only open-search results in `05_pepquery`/`06_aggregated` (no rerun needed), and change Step 7's join to accept a PepQuery/PDV hit for a Step 3c candidate based on file+charge+RT+mass proximity instead of requiring an exact spectrum-title match. Keep **Option A (restore targeted lineage)** as the scientifically-preferred long-term fix, gated on resolving the PepQuery NPE (decompile `Peptide.getProteinMapping()`, try `-s 2`, try padding `-db` with `03b_candidates/pep_candidates.fa`, or check for a newer PepQuery release).

### No production changes made
No files in `src/tarsus/` were modified. No pipeline steps were rerun. No output artifacts under `output/trial/` were touched, moved, or deleted. All experiments ran against copies/scratch files only, reading (never writing) the existing `02_index/`, `03c_second_pass/`, and `05_pepquery/` outputs.

---

## Handoff — Step 7 lineage blocker priority order

### Current blocker
- The pipeline is blocked at Step 7/8 because Step 7 produces `subs.ipc` with 0 rows, Step 8 creates no `pepquery_input_base` files, and orchestration correctly stops before Steps 9-11.
- This is now documented as **D-044** in `.memory/decisions.md`.
- Full repair plan for the next Claude/cloud session: `.planning/step07-lineage-repair.md`.

### Priority order
1. **P0: Fix/decide Step 4/5→7 lineage contract.** Step 4/5 currently do peptide-only PepQuery open search, while Step 7 requires exact original FragPipe `(spectrum_title, peptide)` evidence.
2. **P1: Forensically map title namespaces.** Re-read the original reference scripts and compare FragPipe Step 3c titles, PepQuery index MGF `TITLE=` lines, Step 5 `psm_rank.txt`, and PDV export titles.
3. **P2: Run tiny targeted PepQuery experiments.** Do not rerun the full pipeline until a small candidate subset proves a repair strategy.
4. **P3: Choose scientific contract explicitly.** Prefer restoring targeted lineage if possible; otherwise decide between open-search Step 7 redesign or hybrid file/charge/RT/mass proximity constraints.
5. **P4: Only then invalidate sentinels from the earliest affected step.** Current `output/trial` has `.done` through Step 8, but Step 7/8 outputs are known blocker artifacts; do not delete expensive Steps 1-6 unless the chosen fix requires it.

### Known not-the-problem
- Step 6/PDV sharding is internally faithful for the current run: `psmrankall.txt` and `PDVExportResult.txt` have identical `(spectrum_title, peptide)` pair sets and multiplicities.
- Rerunning Steps 1-6 without changing the lineage contract is expected to reproduce the same Step 7 zero-row result.

## Session 2026-07-07 — Step 7 validation fixtures unstaled

### Completed
- Updated `tests/validation/test_step07_analyze.py` to expect `_sub` preservation in `_spectrum_to_title()`.
- Replaced the stale `xfail` end-to-end Step 7 validation case with a passing coherent fixture that exercises the current Step 7 join/filter path.
- Updated Step 7 synthetic fixtures so PepQuery, PDV, and FragPipe spectrum/peptide lineage agree on `dev_sub:1:2` / `VARIANT` / `PEPTIDE_A3R`.

### Validation
- `uv run pytest tests/validation/test_step07_analyze.py -q` → 6 passed.
- `uv run pytest tests/unit/test_step07_analyze_outputs.py -q` → 19 passed.

### Step 6 / Step 7 lineage diagnostic
- Audited current `output/trial/06_aggregated/` artifacts after the user suspected Step 6 was corrupting Step 7 evidence.
- Step 6 is internally faithful for the current run:
  - `psmrankall.txt`: 617,573 data rows, 158,476 unique `(spectrum_title, peptide)` pairs.
  - `PDVExportResult.txt`: 617,573 data rows, 158,476 unique `(Spectrum_Title, peptide)` pairs.
  - Pair-set difference is zero in both directions.
  - Pair multiplicity counters are exactly equal between `psmrankall.txt` and PDV export.
- Against Step 3c candidates:
  - second-pass positive rows / unique pairs: 45,678.
  - exact overlap with Step 6 `psmrankall` pairs: 0.
  - exact overlap with Step 6 PDV pairs: 0.
  - spectrum-only overlap with PDV: 2,069.
  - peptide-only overlap with PDV: 23,171.
- Conclusion: Step 6 is not dropping the exact pairs; those exact second-pass `(spectrum_title, peptide)` pairs are already absent from Step 5/6 PepQuery output. The current blocker is the D-032 peptide-only/open-search lineage break: Step 4 sends only peptides to PepQuery, so Step 5 validates peptides against any indexed spectrum, while Step 7 still expects the original FragPipe second-pass spectrum title to match the PepQuery/PDV spectrum title.

### Note
- The stale tests/fixtures are fixed. The real trial-data Step 7 0-row issue remains an upstream lineage/design problem, not a rerun/resource problem.

## Session 2026-07-07 — Step 6 PDV sharding made safe/tested

### Status
- Pipeline master job `928042` is no longer running. LSF reports it was killed on
  2026-07-06 20:49:56 by `TERM_MEMLIMIT` after ~6h44m. It was still using the
  old single-process PDV path because it was submitted before the sharded code
  work. The 4GB master-job reservation was too small for Python + a 4GB PDV JVM
  in the same process group.
- No TARSUS Step 6/PDV/PepQuery jobs are currently active. Checked `bjobs -a` and
  no stray `pdv_`/PepQuery jobs were present after the test run.

### Completed
- Implemented spectrum-title-aware PDV sharding in
  `src/tarsus/steps/step06_aggregate_query.py`:
  - Added `_group_chunk_rows()`.
  - Shards are sized by PSM row count but never split rows with the same
    `spectrum_title` across different shards.
  - This avoids adding new cross-shard nondeterminism on top of PDV/reference
    duplicate-overwrite behavior.
- Made `_run_pdv_sharded()` self-contained by ensuring `pdv_spectra/` exists
  before merging shard outputs.
- Rewrote `tests/unit/test_step06_aggregate_query.py` so tests never call real
  LSF:
  - `submit_bsub` and `wait_for_jobs` are monkeypatched for sharded tests.
  - Local concat tests explicitly use `parallel=False` and fake `$DISPLAY`.
  - Added D-038 regression test for blank-line-free aggregation.
  - Added tests for grouped chunking, shard resume, export merge, PDF move, and
    missing-shard-output failure.

### Validation
- `uv run pytest tests/unit/test_step06_aggregate_query.py -v` → 14 passed.
- `uv run pytest tests/unit/ -q` → 156 passed in 74.24s.
- `uv run mypy src/tarsus/steps/step06_aggregate_query.py src/tarsus/steps/_pdv_worker.py`
  → success, no issues.
- Checked `bjobs -a | grep -i "pdv_\\|pq"` after tests → no stray jobs.

### Current corrected state (after user flagged false empty downstream completion)
- **Do not consider the earlier job 5315 a valid scientific end-to-end completion.**
  It only proved the code could reach the end, but it did so by incorrectly marking
  Steps 9-11 done after Step 8 produced no base-rescoring input files.
- Valid completed state is now **Steps 01-06 only**:
  - `06_aggregated/.done` present.
  - `06_aggregated/pdv_spectra/PDVExportResult.txt` present with **617,574 lines**
    (header + 617,573 PSM rows).
  - PDV ran in `-ft report` mode because Step 7 consumes the report; PDF mode does
    not produce `PDVExportResult.txt`.
- Invalid downstream outputs from the false-empty run were moved, not deleted, to:
  - `output/trial/invalid_empty_downstream_20260707132848/`
- Remaining `.done` sentinels now stop at Step 6 only.

### Step 7 lineage bug fixed
- `_spectrum_to_title()` and `_normalize_spectrum_title()` now preserve the `_sub`
  suffix. Previously Step 7 converted FragPipe second-pass spectra like
  `file_sub.100.100.2` to `file:100:2`, while PepQuery/PDV Step 6 titles are
  `file_sub:100:2`. This made the first Step 7 spectrum-title intersection zero.
- Regression test updated: `file_sub.100.100.2 -> file_sub:100:2`.
- Diagnostic after the fix:
  - `saved_singles`: 1293 rows.
  - PepQuery-confident unique spectra: 700.
  - union size: 1987.
  - second-pass rows in union: 62 (was 0 before preserving `_sub`).

### Remaining Step 7 hard issue (not fixed yet)
- Full Step 7 still produces 0 rows even after `_sub` preservation.
- Stage diagnosis:
  - 62 second-pass rows survive the `first_set | saved_set` spectrum-title filter.
  - PDV export has spectrum-only overlap and peptide-only overlap, but **0 exact
    `(spectrum_title, dependent peptide)` overlaps** for those 62 rows.
  - PDV annotations for those spectra are for different peptides than the
    second-pass variant peptide.
- This likely reflects the earlier FragPipe/PepQuery scan-number/title lineage
  problem (D-032): Step 5 PepQuery was intentionally switched to peptide-only open
  search because FragPipe spectrum titles cannot be trusted as native PepQuery
  titles. Step 7 still assumes those titles can be used to connect second-pass PSMs
  to PDV/PepQuery ion evidence. This needs careful scientific/design review before
  changing behavior.

### Guardrail added and verified by real rerun
- Removed the unsafe empty-result fast path. If Step 8 produces no
  `pepquery_input_base` chunks, orchestration now raises a `RuntimeError` and will
  not mark Steps 9-11 `.done`.
- Added regression test `tests/unit/test_orchestration.py` proving that an empty
  Step 8 input directory raises and does not create `.done` for Steps 9, 10, or
  11.
- Validation: `uv run pytest tests/unit/ -q` → 157 passed.
- Real guarded rerun: master job **30275** (2026-07-07 14:04–14:08) resumed from
  Step 7, ran Steps 7 and 8, then stopped with the intended guardrail error:
  `Step 8 produced no base-rescoring input files ... Downstream Steps 9-11 were
  not run.`
- Current sentinel state after job 30275:
  - `.done` present through **08_base_input**.
  - `.done` absent for **09_pepquery_base**, **10_aggregated_base**, and
    **11_localized**.
  - This confirms the original hard bug (fake downstream `.done` files) is fixed.

### Additional fixes after first sharded run
- Expanded `XvfbDisplay` from 4 fixed display candidates (`:99..:96`) to a broad
  range so many PDV shards can coexist on the same compute node.
- Changed `wait_for_jobs()` to raise on LSF `EXIT` instead of treating failed child
  jobs as successful terminal states.
- Switched PDV from `-ft pdf` to `-ft report`; PDV source confirms the export file
  is only written in report mode.
- Added shard resume safety: a prior `PDVExportResult.txt` is reusable only if the
  associated shard log does not contain failure markers. This prevents merging
  partial reports left by failed PDV runs.
- Added Step 7 memory optimization by reading only required columns from huge
  Step 6 outputs. This reduced Step 7 max memory from >32GB to ~9GB on trial data.
- Fixed Step 7 missing `base` column by deriving it from the second-pass `Protein`
  field via the existing `_extract_base_name()` helper.
- Added `--memory` to `tarsus run`, defaulting the master orchestration job to
  32GB (needed for Step 7+ large-table analysis).

### Validation
- `uv run pytest tests/unit/ -q` → 156 passed.
- `uv run mypy` on changed modules passed.
- Tiny local PDV report smoke test produced `PDVExportResult.txt` successfully.

### Notes for next session
- The trial dataset producing 0 final localized SAAVs is a scientific outcome of
  the current filters, not a pipeline crash. If unexpected, investigate Step 7's
  filtering thresholds and PDV two-fragment coverage logic scientifically rather
  than changing code silently.
- Several failed/intermediate master logs are preserved as `master.log.job*.bak`.
- Partial shard dirs from failed attempts were moved to `pdv_*job*.bak.*` backup
  directories, not deleted.

---

## Session 2026-07-06 — Memory Resync + Step 6 (PDV/Xvfb) Root-Cause

### Context
Memory files were stale (last updated 2026-07-01 morning, before that day's pipeline
run completed/failed). This session reconciles memory with actual repo/cluster state
and diagnoses a real, currently-blocking bug.

### What was missed by memory
- Commit `eb133dd` (2026-07-01 16:30): `wait_for_jobs()` no longer stalls on
  LSF-purged jobs (empty `bjobs` stdout + exit 0 was wrongly read as "still running");
  `step05_query_psm` gained resume logic (skips chunks with existing `psm_rank.txt`).
  Recorded as **D-035**.
- `.planning/resource-tuning.md` (draft, 2026-07-01): broader resource-tuning analysis
  (LSF `-M` flag missing, JVM heap vastly exceeds LSF reservation on steps 3a/3c/5,
  PepQuery job-storm of 4568 un-throttled bsub submissions). Explicitly marked
  "premature" — deferred until pipeline runs clean end-to-end. Not yet actioned.

### Pipeline run 125370 (submitted 2026-07-01 16:32, exited 17:19) — actual state
- Steps 1–5 completed successfully (`.done` present for 01–05, includes PepQuery
  validation with the new resume logic).
- **Step 6 (aggregate PepQuery results + PDV) failed.** Aggregation succeeded
  (`psmrankall.txt` 167M, `mgfall.mgf` 5.7G, `peptides.txt` 14M, `ptmall.txt` 9.4G
  all present and non-empty in `output/trial/06_aggregated/`), but the PDV subprocess
  call exited 1 and `pdv_spectra/` was left empty. No `.done` for step 6. Pipeline
  has been stalled here since 2026-07-01, unnoticed until this session.

### Root cause: `XvfbDisplay` silently produces a dead virtual display (D-036)
- `src/tarsus/env.py::XvfbDisplay` locates the Xvfb binary in the EasyBuild tree
  and starts it via bare `subprocess.Popen(...)` — no `LD_LIBRARY_PATH` or other
  module-environment variables are set.
- Direct reproduction: `Xvfb :97 ...` → `error while loading shared libraries:
  libbz2.so.1.0: cannot open shared object file` — the binary needs its GCCcore
  toolchain's shared libs, normally supplied by `module load Xvfb/<ver>`.
- `XvfbDisplay.__enter__` only catches `FileNotFoundError`; it does not check
  whether the spawned process is still alive after starting. It proceeds to set
  `DISPLAY=:99` regardless, so the caller (PDV) fails downstream with
  `java.awt.AWTError: Can't connect to X11 window server using ':99'`.
- This has been true since D-020 (2025-06-29) introduced `XvfbDisplay` — it was
  never actually exercised successfully in the cluster's non-interactive/module-free
  invocation path; earlier PDV smoke tests likely ran with `module load Xvfb`
  active in the shell, masking the missing-library issue.

### Fix landed: self-contained Xvfb bundle (D-037, supersedes D-036)
The first attempt (module-load based, D-036) worked but was rejected by the
user as violating self-containment (D-004) — it depended on the cluster's
EasyBuild/Lmod module system. Rebuilt properly:

1. **Confirmed PDV has no real headless mode** — `-Djava.awt.headless=true`
   still throws `HeadlessException`. `PDVCLIMainClass` unconditionally builds
   a `JFrame`; Java's headless mode forbids that categorically, no bypass.
2. **Confirmed Xvfb is not part of the original reference pipeline** —
   `TARSUS_elizabev/aggregate_query.sh` calls `java -jar PDV.jar` bare, no
   display handling. The original author ran this interactively with a real
   X11 session; Xvfb was our own addition (D-020) for unattended LSF batch use.
3. **Tried conda-forge's `xorg-x11-server-xvfb` packages** (plain + portable
   "cos7" variant) — both dead ends, missing `libXfont2.so.2` which
   conda-forge doesn't publish standalone at all.
4. **Vendored the working EasyBuild Xvfb build ourselves**: copied the binary
   + its ~12 non-universal shared libs into `tools/xvfb/{bin,lib}/` (7.1 MB,
   committed to git via `.gitignore` exception). Sourced the one missing lib
   (`libbz2.so.1.0`) from conda-forge's standalone `bzip2` package (public
   URL, pinned checksum). Also discovered and fixed a second missing
   dependency during testing — Xvfb's `xkbcomp` keymap-compile helper needed
   `libxkbfile.so.1`, added from the same EasyBuild tree.
5. Rewrote `XvfbDisplay` (`src/tarsus/env.py`) to launch `tools/xvfb/bin/Xvfb`
   directly with `LD_LIBRARY_PATH` pointed only at our own bundle — zero
   `module load`, zero cluster-specific paths at runtime. `$DISPLAY`, if
   already set by the user, is still honored and skips Xvfb entirely.
6. Added `make xvfb` / `make test-xvfb` Makefile targets (same pattern as
   JDK/.NET bundling) and documented the whole story in `tools/README.md`.

**Verified working:** `make xvfb` (checksum verification) and `make
test-xvfb` (standalone display test) both pass. Re-ran the actual PDV command
from the stalled pipeline run (125370) against the new bundle — the
`HeadlessException`/`AWTError` is completely gone.

**New, unrelated bug found one layer deeper (D-038, OPEN):** PDV now fails
with `ArrayIndexOutOfBoundsException` in `TextImport.parseTextFile` while
parsing our aggregated PSM/peptide files — a Step 6 data-format mismatch, not
a display issue. Also noticed the JVM hangs indefinitely after this exception
instead of exiting (would eat LSF wall-time budget in production). **Not yet
fixed** — flagged for the next session per scope discipline (this session's
task was specifically the Xvfb bug).

**Hard rule honored throughout:** none of the existing Step 6 outputs
(`psmrankall.txt` 167M, `mgfall.mgf` 5.7G, `peptides.txt` 14M, `ptmall.txt`
9.4G — representing hours of PepQuery + concatenation compute) were deleted
or regenerated. All testing read from these files as-is.

### D-038 fixed: blank-line aggregation bug + real LSF rerun (2026-07-06, same day)
**Root cause confirmed:** `grep -c "^$" psmrankall.txt` → 4568 blank lines,
matching the PepQuery chunk count exactly. Chunks with zero matched spectra
produce header-only `psm_rank.txt` files; `content.split("\n")` on a
newline-terminated file always yields a trailing empty string, so stripping
the header via `lines[1:]` left a stray blank line per zero-match chunk.
A blank line splits by `\t` into a 1-element array; PDV's
`TextImport.parseTextFile()` (decompiled with CFR to confirm) indexes into
column 3 (`spectrum_title`)/4 (`charge`) unconditionally → exact match for
the observed `ArrayIndexOutOfBoundsException: Index 3 out of bounds for
length 1`.
**Fix applied:** `step06_aggregate_query.py` now filters `if line.strip()`
when splitting/rejoining both `psmrankall.txt` and `ptmall.txt` concatenation
loops. Also added a `timeout=` to the PDV subprocess call (JVM doesn't
reliably exit on uncaught exceptions, D-038 note carried over).
**Verified fixed:** re-generated `psmrankall.txt` has 0 blank lines (was
4568). Confirmed unit tests (`test_step06_aggregate_query.py`, 5/5) and
mypy still pass.
**Resumed via LSF (as instructed — "rerun using the LSF"):** used the
existing sentinel-checkpoint resume mechanism (no `.done` for `06_aggregated`,
`.done` present for steps 1–5) — `tarsus run` with the same fasta/inputs/
output-dir skips straight to Step 6, no need to touch or re-derive earlier
steps.
- **Job 920703** (13:21–13:56): Step 6 re-ran, regenerated all 4 aggregation
  files correctly (0 blank lines confirmed), PDV started producing real
  spectrum-annotation PDFs (7153 generated, `pdv_spectra/*.pdf`) — but hit
  the newly-added 1800s (30 min) subprocess timeout before finishing. Killed
  by our own safety timeout, not a bug — the 30 min budget was sized for
  smaller test data and was too conservative for the real dataset (23,171
  unique peptides, 617k+ PSM rows, ~4 PDFs/sec observed throughput → real
  completion likely takes hours).
- **Fix:** raised the PDV subprocess timeout from 1800s to 28800s (8h).
  Confirmed `gsla-cpu` queue RUNLIMIT is 45000 min (750h) — no queue-level
  constraint. Backed up `master.log` before each resubmission
  (`master.log.job125370.bak`, `master.log.job920703.bak`) so LSF's `-oo`
  overwrite behavior doesn't lose prior run history.
- **Job 928042** (started 14:06): currently running, Step 6 in progress with
  the corrected 8h timeout. Steps 1–5 correctly skipped via `.done`
  sentinels. Not yet complete as of this session's end — check `bjobs 928042`
  and `output/trial/master.log` for status; expect Step 6 (and onward,
  Steps 7–11) to complete over the following hours without further
  intervention needed unless it fails.
**Hard rule honored:** the four aggregation files were intentionally
regenerated by Step 6 itself (this is standard, expected behavior of a
re-run step, not data loss — they are cheaply rederived from the intact
`05_pepquery/` chunk outputs, which were never touched). No PepQuery chunk
results or raw data were deleted at any point in this investigation.

---

## Session 2026-06-30 — Phase 3-4-5 Development Sprint

### Summary
Heavy development session with 27 commits. Full pipeline now produces real results.
Current LSF master job **994145** (`tarsus_master`) running Step 5 (PepQuery validation,
779 PepQuery chunk jobs) producing `psm_rank.txt` files with real spectrum matches.

### What was done

#### PepQuery Index Rewrite (D-027)
- Merge logic rewritten: flat `.mgf` at `pepquery_index/` root, decompress `.mgf.gz` → `.mgf`,
  append-mode concatenation for overlapping mass-bin files from HS+LS fractions
- Native `summary.txt` format with `ms_file=` key=value syntax, `_sub` stripped from paths
- Existing index migrated: 24,944 `.mgf` files, 14,983 bins concatenated

#### Pipeline Bug Fixes (D-028 through D-034)
- **Step 2 reordered after Step 3a**: PepQuery now indexes `*_sub.mzML` from FragPipe
  first pass, not original mzML (e143a46). Data flow changed — `02_index/` derives from
  `03a_first_pass/`
- **Step 3c `_sub.mzML` fix**: Second pass now searches unidentified spectra only (95c3494)
- **MSBooster fully disabled**: All 3 flags disabled (`run-msbooster`, `predict-rt`,
  `predict-spectra`) in Step 3c second pass (cfd4886)
- **`-db` flag fix**: PepQuery `-db` must point to raw FASTA, not PepQuery index.
  Fixed in both Steps 5 and 9 (d1cdd04)
- **Header removal from PepQuery chunks**: Step 4 output is now peptide-only (no
  spectrum_title column). Chunks no longer repeat the header line (79dff19)
- **Scan number mismatch workaround**: FragPipe 24.0 uses internal scan numbering that
  doesn't match mzML native scan numbers. Step 4 produces peptide-only output;
  PepQuery runs in open-search mode (`-aa` flag, no spectrum titles) (68957c2)
- **I/L normalization**: `I/L` → `I` in substitution matrix columns and variant peptide
  sequences. `/` is not a valid amino acid (4c2d9d6, D-026)
- **Target-decoy FASTA**: Steps 3a and 3c generate inline `protein_decoy.fasta` with
  reverse-sequence decoys (95c3494)
- **IonQuant 1.11.20**: Added as required tool — missing from FragPipe 24.0 Linux ZIP
  (677e548)
- **gsla-cpu universal queue**: All steps use gsla-cpu; removed "short" queue from
  Steps 5 and 9 (56ba4e8, D-024)

#### Mock Dev Data System (Phase 4)
- `scripts/make_mock_mzml.py` — index-based spectrum extraction from real mzML
- `data/test-mock/dev.mzML` — 2000 MS2 spectra (17.9 MB, 2574 total) extracted from
  real Orbitrap Astral DDA data
- Validation tests with golden-file capture for Steps 2, 3a, 7
- Step 7 test wired with synthetic-data fixtures (`tests/validation/expected/step07_fixtures/`)
- Golden files captured for Steps 2 and 3a
- `.gitignore` exception for `data/test-mock/**`
- Mock contains FragPipe-generated `.mzBIN` files (dev.mzBIN_all, dev_uncalibrated.mzBIN)

#### Resource Planning
- `.planning/resource-distribution.md` created — analysis of JVM heap vs LSF memory
  mismatch, step 3b offload proposal, thread/slot alignment plan

### Current state
- Master job **994145** running on cn479 (since 17:31)
- Steps 01-04: `.done` ✓
- Step 05: **running** — 779 PepQuery chunk jobs on cn114, producing non-zero
  `Matched spectra: N` results with `psm_rank.txt` files
- Pipeline producing real SAAV-validation results for the first time

### Files changed today
- `src/tarsus/steps/` — step02, 03a, 03b, 03c, 04, 05, 09
- `src/tarsus/orchestration.py` — Step 2 reorder, `-db` flag pass-through
- `tests/` — unit tests updated, validation tests created
- `Makefile` + `tools/README.md` — IonQuant support
- `data/test-mock/` — mock dev data (2000 spectra)
- `.context/architecture.md` — queue fix, I/L limitation
- `.memory/` — progress, decisions (D-024 through D-034)
- `.planning/resource-distribution.md` — new planning doc
- `.gitignore` — un-ignore data/test-mock/

---

## Phase 1: Pipeline Digestion and Documentation (completed)

### Completed
- Read and analyzed all 11 pipeline steps from `TARSUS_elizabev/` reference
- Documented reference pipeline in `.context/reference-pipeline.md`
- Documented architecture and data flow in `.context/architecture.md`
- Established project-specific agent rules in `.agents/project.md`
- Recorded initial architectural decisions (D-001 through D-006) in `.memory/decisions.md`
- Updated README with actual project description
- Verified all files are internally consistent
- Test data added to `data/` (protein.fasta, two .raw files — Orbitrap Astral DDA, LS/HS fractions)
- `.gitignore` updated: `data/*` (except README), `output/**`, build artifacts
- `data/README.md` created documenting the test fixtures
- Root-level stubs (`make_index.sh`, `mzML`) removed
- Decisions D-007 through D-010 recorded (no embedded ref, user-driven entry, git policy, organism flag deferred)
- D-004 revised: self-contained tools via Makefile (supersedes cluster-mounted approach)
- `tools/` directory created with Makefile and README — pinned versions for FragPipe 24.0, PepQuery 2.0.2, PDV 2.2.3, ThermoRawFileParser 2.0.0-dev

## Phase 2: Self-Contained Tool Environment (completed)

### Completed
- MSConvert ruled out (cannot read Thermo .raw natively on Linux); ThermoRawFileParser v2.0.0-dev adopted instead
- `.gitignore` updated for tools/ (Makefile+README tracked, binaries ignored)
- D-011: JDK 21 (jdk-21.0.11+10) and .NET 8 runtime (8.0.28) bundled in `tools/`
- `src/tarsus/env.py` created — ToolEnvironment class resolves paths and sets up env
- `make test-tools` smoke tests pass for all 6 tools (JDK, .NET, FragPipe, PepQuery, PDV, ThermoRawFileParser)
- PepQuery directory structure fixed (JAR + lib/ for manifest Class-Path)
- ThermoRawFileParser diagnosed — requires `DOTNET_GCHeapHardLimit` + `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT` on this system
- PDV smoke test data created in `data/test-pdv/` (git-tracked via `.gitignore` exception)
- `src/tarsus/` package scaffolded with cli.py, config.py, lsf.py, steps/
- `tarsus convert` command — wraps ThermoRawFileParser with LSF submission
- Validation framework: conftest.py, golden-file capture, test_step01_convert.py
- Decisions D-012 through D-015 recorded (LSF-only, golden files, click CLI, trial data reference)
- Added `click`, `pyyaml` dependencies; configured build system and console_scripts entry point

### Current State
All external tools downloaded, verified, and smoke-tested. All 11 pipeline steps ported as
Python modules. PDV 2.1.2 bundled (matches reference), works via cluster Xvfb module.
LSF verified working (bsub, gsla-cpu queue). Reference assets (generic.workflow,
subs_exclude.csv) bundled in `src/tarsus/assets/`. `tarsus run` command submits
`python -m tarsus.orchestration` via bsub. Sentinel checkpointing (.done files) allows
resuming from failed steps.

## Phase 3: CLI Wiring and Orchestration (completed)

### Completed
- D-016: LSF verified working (2025-06-29) — bsub functional, gsla-cpu queue Open:Active
- D-017: Master-job architecture — single LSF job orchestrates all 11 steps on a compute node
- D-018: Bundled assets — generic.workflow and subs_exclude.csv in `src/tarsus/assets/`
- D-019: Minimal CLI — only 3 required flags (--fasta, --input, --output-dir)
- D-020: PDV downgraded to 2.1.2, XvfbDisplay context manager added
- D-021: PYTHONUNBUFFERED=1 for real-time master job logging
- D-022: PDV export path fixed — Step 7 reads pdv_spectra/PDVExportResult.txt
- Step modules updated to use bundled asset paths (no more TARSUS_elizabev references)
- `tarsus run` command submits `python -m tarsus.orchestration` via bsub
- orchestration.py: sentinel checkpointing (.done markers per step)
- step02_make_index.py: per-file parallel PepQuery indexing with dynamic heap auto-scaling
- 142 unit tests passing, mypy clean, 7/7 tools verified

### Current State (superseded — see Session 2026-06-30)
Pipeline run 940573 was the first end-to-end attempt. It exposed the PepQuery zero-results
bug cluster (D-027 through D-032). All fixes applied in Session 2026-06-30. Master job
**994145** now running with working Step 5.

## Phase 4: Mock Dev Data for Fast Iteration ── EXECUTABLE PLAN (in progress — code done, LSF runs pending)

### Decision
D-023 recorded (2025-06-30): Mock dev dataset for fast iteration. 10 MB mzML with 50
spectra replaces 6-8 GB files for debugging. Full pipeline runs against mock data in ~2
minutes via LSF (each step submits bsub but completes in seconds on tiny data).

### Completed (2026-06-30)
1. ✅ Golden files captured for `expected/step02.yaml` and `expected/step03a.yaml`
   - Tests were run against LSF, golden files committed in 79dff19
   - Test code updated to use `output/_val/` shared directory instead of `tmp_path`
   - Test cleanup added (`shutil.rmtree` in `finally` block)
2. ✅ `test_step07_analyze.py` wired with synthetic-data fixtures in `expected/step07_fixtures/`
   - Six test functions: load PTMs, load base PTMs, filter single SAV, filter shared SAV,
     analyze end-to-end with fixture data, load PDV export
3. ✅ Mock upgraded from 50→2000 MS2 spectra (17.9 MB, 2574 total) to support strict
   FragPipe validation (1bc7559)

### Remaining (future)
1. Run full `uv run pytest tests/validation/ -m lsf` against LSF for complete validation
2. Implement resource distribution plan (`./planning/resource-distribution.md`)
3. Add CI workflow with mock-data validation on every push

## Phase N: PepQuery Zero-Results Investigation (mid-session, 2026-06-30)

### Problem (historical — resolved later in the same session)
Step 05 (PepQuery validation) ran to completion on LSF but produced zero results.
Every `detail.txt` was header-only; no `psm_rank.txt` files appeared. Pipeline
stalled here with no `.done` for step 05.

### Root cause cluster (D-027 through D-032)
The zero-results problem had **six contributing bugs** — all fixed sequentially:
1. **D-027**: MGF files in subdirs, `.mgz.gz` not decompressed, wrong `summary.txt` format
2. **D-028**: Step 2 ran before Step 3a — indexed wrong mzML files (original, not `_sub`)
3. **D-030**: `-db` flag pointed at PepQuery index, not raw FASTA
4. **D-031**: Header line repeated in every PepQuery input chunk (caused parse errors)
5. **D-032**: FragPipe scan numbers mismatched mzML — spectrum titles were wrong
6. Plus: MSBooster enabled in second pass (D-029) causing silent hangs

### What was eventually done
All fixes documented in **Session 2026-06-30** above. The final pipeline run (master
job **994145**) produces real `psm_rank.txt` results.
