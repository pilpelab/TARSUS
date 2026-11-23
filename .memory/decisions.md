# Decisions Log

## D-070 (2026-07-24): `re.match` silently dropped every pre-modified substitution

**Issue:** On byte-identical reference inputs, our Step 7 produced **3521 rows vs
the reference's 3922** (−10%). Found while validating D-069, unrelated to it.

**Method:** Dry-ran our real `analyze_outputs()` against the reference's own
inputs (the reference pipeline's EVpar run), which holds `psm.tsv`,
`ptmall.txt` and `psmrankall.txt` constant. That **controls for the tool-version
upgrade**: with the search output fixed, any row gap is our code. All 197 missing
(spectrum, peptide) keys were present in the raw `second/psm.tsv`. Staged the
filters and found all 197 died at the PepQuery confident/saved filter; the
reference's `save_singles` returned 2419 titles including all 197, ours 2158
including none.

**Root cause:** `_parse_modification` used `re.match`, which anchors at position
0. PepQuery lists fixed/variable mods *before* the substitution::

    'Carbamidomethylation of C@5[57.0215];Gly->Ala of G@3[14.0157]'

`re.match` returns None for every such string; the reference's polars
`str.extract` is unanchored and matches. On the affected rows: `re.match` 0/201,
`re.search` 201/201.

**Why it mattered more than 10%:** the loss was *chemically biased*, not random —
it removed essentially every Cys-containing (carbamidomethyl) and Met-containing
(oxidation) PSM. That skews the substitution spectrum itself, which is the
paper's actual result, and plausibly explains why our top-substitution table
diverged from Slava's in the 2026-07-23 QC.

**Fix:** `re.search`, keeping the greedy `.*` so the trailing `@(\d+)[` binds to
the last modification exactly as the reference regex does.

**Verification:** dry run now returns **3922 rows — identical to the reference**,
with `in REF not ours: 0` and `in OURS not ref: 0` on `(spectrum, peptide)` keys.
Regression tests cover both prefixed-modification shapes.

**Lesson:** `re.match` vs `re.search` is not a stylistic choice when transcribing
polars `str.extract` — `str.extract` is unanchored. Check anchoring on every
regex ported between the two.

---

## D-069 (2026-07-24): SpectralSim/RTScore come from MSBooster — SUPERSEDES D-2026-07-23

**Issue:** `SpectralSim`/`RTScore` present in `subs.ipc` but null in every row (191/191),
against 0/259 null in Slava GAPDH. Also 69 cols vs GAPDH's 72.

**Method:** Ran the reference rather than grepping for it. Read
the reference's `analyze_outputs.py` — the file our Step 7 recapitulates — and
confirmed it **never computes these columns**. It reads the second-pass `psm.tsv`
and keeps *all* of its columns. Verified both canonical `second/psm.tsv` files
(reference GAPDH and EVpar runs) carry `SpectralSim` at col 18 and `RTScore` at col 19,
directly after `Delta Mass`.

**Root cause:** These are **FragPipe columns, written only when MSBooster runs.**
Commit `cfd4886` disabled MSBooster on the second pass to avoid "redundant
calibration PNGs that waste time and compute" — an *efficiency tidy-up, not a
correctness fix*, exactly the deviation `lessons.md` warns against. No MSBooster
→ no columns in `psm.tsv` → Step 7 null-filled them.

**Falsified along the way:** they are NOT the raw MSBooster `.pin` features.
Correlating Slava's `subs.ipc` against his `_edited.pin` gave r=0.16 for
`SpectralSim` vs `unweighted_spectral_entropy` and r=-0.08 for `RTScore` vs
`delta_RT_loess`. The psm.tsv values are post-rescoring, not the pin features.
**Do not "fix" this by reading the pin.**

**`ions`/`ion_mz`/`ion_int`:** a separate, unrelated source — PDV's
`PDVExportResult.txt` (`ions`/`ions_mz`/`ions_int`), stored as raw bracketed
Strings after `Traced Scans`. GAPDH-only; Slava himself `.drop()`s them
(`reviews.ipynb:1580`). Cosmetic annotation for mirror plots, not science.

**Solution:**
1. Stop patching MSBooster off in Steps 3a and 3c. Our `generic.workflow` template
   already matches the reference (`run-msbooster=true`, `predict-rt/spectra=true`,
   `find-best-*-model=false`, local DIA-NN models — no Koina/internet needed), so
   the patch chain must simply leave that block alone.
2. Step 7 needs **no** logic change for the scores — psm.tsv columns already flow
   through the join. Replaced the null-placeholder with a **loud failure**: their
   absence means MSBooster was off, and silently defaulting is what hid this for a
   whole session.
3. Step 7 joins the PDV trio on `(spectrum_title, dependent)`, deduped, left join.

**Expected side effect:** MSBooster rescoring should also raise sensitivity
(ours 191 vs Slava 259) — percolator gains the spectral/RT features.

**Status:** code + tests landed (310 pass). Awaiting clean end-to-end rerun.

---

## D-2026-07-23: Source of SpectralSim & RTScore Columns — ❌ WRONG, see D-069

> **This entry was wrong and its "COMPLETE" status was false.** It correctly named
> `psm.tsv` as the source but concluded Step 7's column *selection* was the bug and
> declared the fix verified. It was not: the columns were absent from `psm.tsv`
> altogether because MSBooster was disabled upstream, so the "fix" produced 69
> correctly-positioned columns full of nulls. Kept for the record — do not act on it.

**Issue:** Missing `SpectralSim` and `RTScore` columns in Step 11 output (67 vs 69 columns)

**Investigation:** Traced through entire pipeline looking for data source (PDV, PepQuery, IonQuant, MSBooster)

**Finding:** Columns exist in FragPipe's `psm.tsv` output (first-pass search results)
- Generated by Philosopher peptide spectrum matching
- Present at positions 18-19 in both reference and our FragPipe output
- Sample values: SpectralSim ≈ 0.98, RTScore ≈ 0.87

**Root Cause:** Step 7 was explicitly excluding these columns during the join operation
- `first_sub` selection did not include SpectralSim or RTScore
- These columns existed in `first_psms` but were discarded
- They were NOT present downstream, causing the output schema mismatch

**Solution:**
1. Add "SpectralSim" and "RTScore" to the column selection in `first_sub`
2. Reorder columns after join to place them at positions 18-19 (after Delta Mass)
3. Add validation in Step 11 to detect missing columns early

**Files Modified:**
- `src/tarsus/steps/step07_analyze_outputs.py`: Added column inclusion and reordering
- `src/tarsus/steps/step11_localize.py`: Added validation check

**Verification:** Full pipeline run confirms 69 columns with SpectralSim/RTScore at correct positions

**Status:** COMPLETE ✅

---

## D-071 (2026-07-28): Step-07/11 regression eval (`make eval`)

**Context:** Every correctness bug this project hit lived in step 07 (D-069,
D-070, the `rev_` decoy leak `7502692`) and was caught manually, late, by ad-hoc
QC. `tests/unit` covers pure helpers; `tests/validation` needs LSF+tools. Nothing
re-ran the analysis steps on known inputs and checked the output still matched.

**Decision:** Added `tests/eval/` - a fast, committed, tool-free regression check
that calls `analyze_outputs` and `localize` directly on frozen ~100-spectrum
slices of two reference runs (gapdh, evcoli) and gates on a snapshot + named
invariants (schema, no `rev_`, non-null MSBooster scores, finite dpbp,
`slava_compare` identity==100% / dpbp r>=0.99). Runs in ~1.3s, no cluster.
`scripts/build_eval_fixtures.py` (re)builds slices + goldens deterministically;
`TARSUS_EVAL_UPDATE=1` re-blesses (reviewed commit). See
`tests/eval/README.md` and the auto-memory lineage map.

**Key build facts:** the universal slice key is `spectrum_title`=`file:scan:charge`
(= Slava's `Spectrum` column; convert psm.tsv's `file_sub.scan.scan.charge` via
`_spectrum_to_title`; strip `_M..C..` off psmrankall_base). First-pass slice keeps
only the max-`Intensity` winner per (base,Charge) - result-identical to step 7's
own max filter, and shrinks first_psm.tsv from ~11 MB to ~64 KB. Neither reference
leaks a `rev_` row naturally, so gapdh injects one synthetic decoy row (ties the
max) to make the `7502692` guard fire - verified: reverting the drop trips both the
rev_ invariant and the snapshot.

**Spec:** `docs/superpowers/specs/2026-07-28-step07-11-regression-eval-design.md`.
**Status:** landed. 25 eval tests + 317 unit tests green; mypy/ruff clean.

---

## D-072 (2026-08-04): Biological-substitution Venn design for the QC report

**Scope:** Refine only `docs/qc-history/qc-values-report.html`. Do not change the
pipeline, invent filtering rules, or rerun TARSUS unless a required source cannot
be recovered.

**Decision:** Add ten fixed-layout Venn diagrams, grouped as four purified
proteins, four cell samples, and two tissue samples. Each diagram compares Slava
with Barc and displays Slava-only, shared, and Barc-only event counts. Fixed-size
circles are preferred over area-proportional circles because they remain readable
and comparable across all ten samples.

**Counting rule:** One item is one strict Slava-native biological substitution:
`Protein_right + misProt + origin + destination`. Repeated PSMs supporting the
same event count once. Candidate Step 7 `subs.ipc` events and final localized
events must remain separate. The initial Venn section represents candidate
`subs.ipc` events and must not be described as final localized substitutions.

**Target handling:** Purified-protein diagrams use the intended target proteins.
Non-target calls are retained in a separate diagnostic table. For hemoglobin, the
primary strict comparison preserves Slava's assigned `Protein_right`; HBA1/HBA2
ambiguity belongs only in a secondary biological annotation and must not duplicate
an event.

**Report content:** Use labels `Slava` and `Barc`, never `ours`. Below each Venn,
show Slava recovery and expandable exact lists of Slava-only and Barc-only events.
Missing files or required columns must fail loudly rather than produce an
incomplete figure.

**Data provenance:** The deleted Barc panel IPC files are recoverable from Git
history. Commit `3e1944d` contains the post-decoy-filter versions under
`docs/qc-history/subs/`, so no pipeline rerun is required. Slava reference paths
must be explicit and verified before report generation, including both tissue
references.

**Status:** Work in progress on branch `qc-venn-section` (moved there 2026-11-19 to keep `paper-d073-alignment` clean). 8 of 10 diagrams (4 purified + 4 cells); tissue pending, Slava tissue reference paths not identified. Unreviewed: `build_venn_html.py` draws area-proportional circles although this decision chose fixed-size ones, and the two scripts have 22 ruff errors. Spec: `docs/superpowers/specs/2026-08-04-qc-venn-section.md` (on that branch).

---

## D-073 (2026-11-05): Match Slava's published settings for Step 11 tolerance and MSBooster model selection

**Context:** ingesting the Nature paper (`.context/paper-methods-vs-tarsus.md` rows 1, 3) showed two result-changing settings where we followed `TARSUS_elizabev/` but the paper, the published `treko90/tarsus` code, and Slava's GAPDH reference run do otherwise. User directive: make the tolerance a parameter defaulting to Slava's value, and let the pipeline pick the best MSBooster model as Slava's runs did.

**Decision:**
1. Step 11 PyAscore fragment tolerance (`mz_error`) is `DEFAULT_LOCALIZE_TOL_DA = 0.01` (was 0.05), overridable with `tarsus run --localize-tol` (paper: 0.6 for ion-trap MS2). Effective value printed in `master.log`; CLI value recorded in `provenance.json`.
2. `src/tarsus/assets/generic.workflow` restored to the published file byte-for-byte (`find-best-rt-model=true`, `find-best-spectra-model=true`), so MSBooster selects the best Koina model in Step 3a and FragPipe writes the chosen models into `fragpipe-second-pass.workflow`, which Step 3c inherits. `tarsus run --msbooster-models dia-nn` is the offline fallback (pins local DIA-NN, find-best off; every patched key must exist or Step 3a raises).

**Evidence:** paper Methods ("pyAscore ... precision 0.01 Da (Orbitrap)"); public `localize.py` passes 0.01; Slava's `hoMS/GAPDH/2d/fragpipe_fullpipeline/fragpipe.workflow` has find-best true and its `fragpipe-second-pass.workflow` ran `AlphaPept_rt_generic`/`AlphaPept_ms2_generic`. Koina reachable from gsla-cpu node cn449 (LSF probe 2026-11-05: model endpoint returned `AlphaPept_ms2_generic` metadata; the bare `/v2/models/` listing timed out at 30 s, so Koina can be slow; hence the fallback).

**Measured effect of (1)** on the eval slices: gapdh localized 28 -> 19 rows (0.02 gives 26), evcoli 62 -> 58. Step 11 goldens re-blessed (`TARSUS_EVAL_UPDATE=1`); all invariants unchanged. Effect of (2) not yet measured: needs a real run.

**Sentinels for existing outputs:** (1) clear `11_localized/.done` and `12_visualize/.done`. (2) clear `03a_first_pass/.done` and every downstream `.done` (03b to 12): the first-pass PSMs, the candidate library, and everything after can change. `stale_artifacts` warns because both step files changed.

**Caveat recorded, not acted on:** 0.01 Da is tighter than the 20 ppm fragment tolerance of the MSFragger search for fragments above m/z 500, so some true site-determining fragments may be missed. We match Slava by choice.

---

## D-074 (2026-11-09): Run outputs are group-readable (umask 027 at both entry points)

**Context:** Liz (`elizabev`, same group `pilpel-wx-grp`) got "Permission denied" on `output/2026-11-05-d073` while building a TARSUS lesson, so her agent fell back to the 100-spectrum test fixture. Cause: Bar's login umask is 0077, so every run wrote owner-only files. A default ACL (`setfacl -d`) was tried first and failed: /home/labs is GPFS, where POSIX default ACLs are not supported.

**Decision:** `tarsus.lsf.use_group_readable_umask()` sets umask `0o027` (`GROUP_READABLE_UMASK`). It is called by the CLI group callback (`cli.main`, before any subcommand) and by the master entry point (`orchestration.main`, new; `__main__` now calls it). Group gets read/traverse, others nothing; the login umask is left alone for everything outside TARSUS.

**Evidence:** LSF probe 2026-11-09 (jobs 542135/542136, gsla-cpu): a job submitted from umask 0027 printed `0027` and created `drwxr-x---` / `-rw-r-----`; one from 0077 printed `0077`. So jobs inherit the submitter's umask and the CLI setting reaches the master and every child job. Tests: `tests/unit/test_group_umask.py` (2; both failed before the change: CLI gave 0700/0600, master had no `main`). Suite 363 passed, ruff clean; mypy not installed in the venv, not run.

**Not covered:** runs made before D-074 stay owner-only until `chmod -R g+rX`; scripts that call `bsub ... python -m tarsus.orchestration` directly are covered by `orchestration.main`, but their own LSF log file (`-oo`) is created by LSF with the submitting shell's umask.

---

## D-075 (2026-11-19): Step 3c pins the MSBooster models pass 1 chose

**Context:** D-073 assumed FragPipe writes pass 1's chosen MSBooster models into `fragpipe-second-pass.workflow`, so Step 3c would inherit them. False for FragPipe 24.0: that file keeps `find-best-rt-model=true`, `find-best-spectra-model=true` and DIA-NN defaults. Step 3c only turned RT find-best off, so in the 2026-11-05 runs pass 2 ran DIA-NN RT and re-selected MS2. PARK7 and PRDX6 picked `ms2pip_2021_HCD`, and MSBooster 1.4.14's citation writer crashed on it (name mismatch with its `koina_citations.yml`, NPE, exit 1). Hb ran AlphaPept RT in pass 1 and DIA-NN RT in pass 2.

**Decision:** Step 3c reads `rtModel`/`spectraModel` from Step 3a's `msbooster_params.txt` (MSBooster's own record of the models it used) and pins them into `second.workflow` with both `find-best-*` keys false. A missing file, a missing or empty key, or a missing workflow key raises before anything is submitted. Works for both `--msbooster-models` modes: in `dia-nn` mode the record says DIA-NN.

**Evidence:** Slava's FragPipe-generated `hoMS/GAPDH/2d/fragpipe_fullpipeline/fragpipe-second-pass.workflow` has both find-best keys false and `rt-model=AlphaPept_rt_generic`, `spectra-model=AlphaPept_ms2_generic`: the same form. On the four 2026-11-05 first passes the pin gives GAPDH DIA-NN/AlphaPept, Hb AlphaPept/AlphaPept, PARK7 and PRDX6 Deeplc_hela_hf/AlphaPept. Tests: 9 new in `tests/unit/test_step03c_second_pass.py` (one regression test from the real failure); suite 379 passed, ruff and mypy clean.

**Not covered:** Step 3a in `best` mode can itself pick `ms2pip_2021_HCD` and hit the same MSBooster crash. Not seen yet; the fallback is `--msbooster-models dia-nn`.

---

## D-076 (2026-11-23): Step 9 base rescoring uses Slava's production `-itol 0.05`, as a run parameter

**Context:** Step 9 (PepQuery base rescoring) hardcoded `-itol 0.01`, exactly as the published `TARSUS_elizabev/query_psm_base.sh`. Feeding Slava's own Step 7 output into our Steps 8-10 (2026-11-22, `.scratch/slava-steps8-10/`) gave an identical Step 8, but 38 of 116 PARK7 base scores differed for the same spectrum and peptide. Rerunning our exact command with only `-itol 0.05` reproduced his `psmrankall_base.txt` to full precision: PARK7 117/117, GAPDH 167/167 (every spectrum he scored). With those base scores, our Step 11 gives the published ST14 PARK7 list exactly (27/27, 0 extra; with 0.01: 26/27, 3 extra). Bar's decision: match the production run, but keep it flexible.

**Decision:** `step09_query_psm_base.DEFAULT_BASE_RESCORE_TOL_DA = 0.05`, passed as `-itol`; `fragment_tol` must be > 0 or the step raises before submitting. Override per run with `tarsus run --base-rescore-tol` (CLI -> master argv `--base-rescore-tol` -> `run_pipeline(base_rescore_tol=...)` -> Step 9; `None` leaves the step default). Provenance records the CLI value as `base_rescore_tol_da` (null = default). `master.log` prints it at INIT.

**Not changed:** Step 11 `--localize-tol` stays 0.01 (D-073); the published lists imply 0.01 for PARK7 and closer to 0.05 for GAPDH (progress 2026-11-22).

**Tests:** `tests/unit/test_step09_query_psm_base.py` (default 0.05, override reaches the PepQuery command, non-positive raises before submitting), `test_orchestration.py` (argv flag, run_pipeline reaches Step 9), `tests/unit/test_cli_run.py` (flag reaches master argv and provenance; default leaves both unset; 0 rejected). Suite 390 passed, ruff clean on src, mypy clean.

**Sentinels for existing outputs:** clear `09_pepquery_base/` (the whole directory: Step 9 resumes chunk by chunk, so leftover 0.01 chunks would mix with 0.05 ones), `10_aggregated_base/.done`, `11_localized/.done`, `12_visualize/.done`. `stale_artifacts` warns on any `09_pepquery_base/.done` older than this change.

**Addendum (same day), resume guard:** Step 9 resumes chunk by chunk, so making the tolerance a parameter opened a silent-mixing path: a resume at another `--base-rescore-tol`, or of a pre-D-076 run (0.01, unrecorded), would reuse old chunks. Step 9 now writes `09_pepquery_base/fragment_tol.txt` on a fresh start and raises before submitting if it differs from the requested tolerance, or if chunk results exist without it. Tests: `TestResumeNeverMixesTolerances` (4). Suite 394 passed.

---

## D-077 (2026-11-23): Every LSF job is submitted with `bsub -Q 255` (requeue launch failures)

**Context:** on 2026-11-19 and 2026-11-22, 2-6% of WEXAC jobs exited 255 at launch, before the program ran (0-1 s, "CPU time used is unknown", no output), spread over many nodes that each also had many successes. `wait_for_jobs` raises on any failed child, so one such job killed a multi-hour master. Whole-step resumes cannot outrun it either: a resume reruns every chunk without `psm_rank.txt` (GAPDH Step 9: 182 chunks, mostly legitimately empty), and the attempt fails if any of them hits the 255. Bar: "add the 255 to submit to avoid rerunning it in the trap of the [cluster] configuration".

**Decision:** `tarsus.lsf.submit_bsub` adds `-Q REQUEUE_EXIT_VALUES` (`"255"`), so LSF requeues just the failed job under the same id. The cluster caps requeues at `MAX_JOB_REQUEUE = 5` (`bparams -a`), so a job that always exits 255 cannot loop; it then ends as EXIT and fails loudly as before. Other exit codes (real tool errors) are unaffected.

**Evidence:** `bhist` shows `Requeue Exit Values <255>` on jobs submitted this way. End-to-end on the cluster (`.scratch/slava-steps8-10/requeue_e2e.py`, job 574831): through the real `submit_bsub`, a job that exits 255 on its first run and 0 on its second was dispatched twice under one id (07:57:44, 07:57:57), its log ended "second-run" / "Successfully completed.", and the real `wait_for_jobs` returned no failures. Unit test `TestSubmitBsubRequeue` (bsub argv carries `-Q 255`, job command last and untouched).

**Caveat found on the way:** `bsub` joins its arguments into one command line without quoting, so a job command must be plain tokens (pipeline commands are); an inline `bash -c "<script>"` is split into words and fails with exit 2.

---

## D-078 (2026-11-23): Step 7 counts every y ion that contains the substitution (reference off-by-two fixed)

**Context:** reported by Liz (2026-11-10) while re-deriving David's beta-lactamase analysis. Step 7's two-fragment filter keeps a spectrum only if at least two observed b/y ions contain the substituted residue (only those carry its mass shift). `_compute_expected_ions` started the y ions at `n - position + 2`; with Step 3b's 0-based position (`step03b_make_peptides.py:228`, `enumerate`) the first y ion containing the residue is `y(n - position)`. The two shortest containing y ions, often the clearest peaks, were never counted, and positions 0 and 1 had no y ion at all (FPMMXTFK pos 4: y4, y5 missed; WXPELNEAIPNDER pos 1: none). The b range was right. The same line is in `TARSUS_elizabev/analyze_outputs.py:106`, whose own docstring (`:100`) says y ions start at `len(dependent)-position`; Slava: "sounds like a bug". `tests/validation/test_step07_analyze.py` expected y4 in a comment but asserted only y6, and `tests/unit/test_step07_analyze_outputs.py` pinned the buggy output.

**Decision:** y ions start at `n - position` (`step07_analyze_outputs.py`, `_compute_expected_ions`). Correctness over parity: our Step 7 now admits more than Slava's code, which made the published tables (ST14 was built with the bug). The `+2` was not a terminal-position filter (it shifts the range for every position and excludes none); if one is wanted, it belongs in an explicit position rule.

**Evidence:** measured before the change on the four D-073 runs (real `analyze_outputs`, only the y range corrected; the unpatched run reproduces each on-disk `subs.ipc` exactly): Step 7 spectra GAPDH 240 -> 248, Hb 371 -> 400, PARK7 121 -> 136, PRDX6 161 -> 186 (893 -> 970, +9%); peptides 772 -> 835; none lost; ST14 at Step 7 unchanged (146/152). Tests: `TestComputeExpectedIons` rewritten with exact hand-computed lists plus Liz's two examples (5 red before the fix); the validation test now asserts the whole y range and fails on the old code. Suite 396 passed, mypy clean. Eval goldens unchanged: the fixtures are slices of spectra that already passed the old filter, so they cannot see this loosening.

**Sentinels for existing outputs:** clear `07_analyze/.done` and everything after it (08 to 12); `stale_artifacts` flags S07 automatically. Effect on Step 11 needs that rerun.
