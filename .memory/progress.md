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

---

## 2026-07-27 — CODE-REPLICATION GOAL CLOSED

**Verdict (user: "call it done"):** our pipeline reproduces Slava's TARSUS/FragPipe
pipeline. Evidenced on both organisms with like-for-like TARSUS references:
- **Human:** 10-sample panel, 100% substitution identity, dpbp r 0.96–1.000
  (`docs/qc-history/qc-values-report.html`).
- **E. coli:** EVpar TARSUS reference (`elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc`,
  3,922 rows) matched exactly by the D-070 fix (`in REF not ours: 0`,
  `in OURS not ref: 0`).

Remaining differences are tool-version effects (MSBooster ML features, which
spectra clear FDR), not code-logic divergence. The only genuine output-level code
gap is the `_rev` decoy leak (fix staged, below). The E. coli tRNA panel and Orly
are **new-data production runs**, not replication tests — the tRNA samples' only
Slava reference is MaxQuant (cross-method, not code-replication).

## 2026-07-27 — panel done, Orly rerun launched, `_rev` fix pending

### Recapitulation is CLOSED (human panel)
The "does our pipeline match Slava's?" question is answered and holds: 10 human
samples, 100% substitution identity on shared spectra, dpbp r 0.96–1.000, ΔMass
exact; only MSBooster ML features (SpectralSim/RTScore) diverge, by version, as
expected. See `docs/qc-history/qc-values-report.html`. No further runs are needed
to support that conclusion.

### E. coli tRNA panel — all 11 `subs.ipc` produced; references live in `elizabev/tRNA`
All 11 coli samples (alaggc(+par), gluuuc(+par), ilexcau(+par), leuuag,
procgg(+par), proggg(+par)) reached step07; SpectralSim null = 0 everywhere
(MSBooster-on confirmed on E. coli too). **References DO exist** (I first wrongly
said they didn't — see lessons 2026-07-27): `elizabev/tRNA/` holds the counterpart
experiment. BUT distinguish the reference *method*:
- `elizabev/tRNA/csvs_from_Slava/<tRNA>_subs_qdp_ratios.csv` — **MaxQuant**
  dependent-peptide output. Comparing our FragPipe/TARSUS panel to these is
  **method concordance (TARSUS vs MaxQuant)**, NOT code replication.
- `elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc` (3,922 rows, FragPipe schema) —
  the **only like-for-like TARSUS reference** on E. coli; the 3,922 is what D-070
  already matched. So the real E. coli code-replication check is **EV/EVpar**, not
  the tRNA samples.

### Orly (LIS1 #26227) rerun LAUNCHED 2026-07-26
9 runs (L73a-d, WTa1-4, aggregated) on commit `e56070f`, clean tree, into
`LIS1_.../output/2026-07-26-*`; old `2026-07-24-*` kept. CDS auto-resolves from
`[tool.tarsus].cds` (A2). Started running 07-27 after the panel's S05 wave drained.
Orly is NEW data (no Slava reference) — a produce-results goal, not recapitulation.

### `_rev` decoy fix — DIAGNOSED + STAGED, not yet applied
Fix (drop rows whose `Protein`/`Protein_right` starts with `rev_` after the
step07 join) is written in `.claude/plans/i-want-us-to-cozy-kitten.md`, ready to
apply. **Blocked**: Orly masters are live and will pass through step07. Apply +
reprocess the 12 panel + 9 Orly `subs.ipc` (cheap, no LSF) once all masters clear.
A2 (`--cds` default) is already landed + committed (`e56070f`).

---

## 2026-07-28 — Step-07/11 regression eval landed (D-071)

Implemented the eval from `docs/superpowers/specs/2026-07-28-step07-11-regression-eval-design.md`
on branch `eval/step07-11-regression`.

- `tests/eval/eval_lib.py` — canonicalize (sort+round), named invariant guards,
  `slava_compare`; `tests/eval/test_eval_lib.py` (15 unit tests, TDD).
- `tests/eval/test_eval_step07_11.py` — snapshot + invariants, parametrized over
  gapdh + evcoli (10 tests). `make eval` runs all 25 in ~1.3s, no cluster/tools.
- `scripts/build_eval_fixtures.py` — slices both reference runs to lineage-coherent
  ~100-spectrum fixtures (`tests/eval/fixtures/`, 5.5 MB total), builds goldens,
  gates on non-empty + invariants + Slava match at build time. Deterministic
  (identical golden checksums across rebuilds).
- gapdh fixture injects one synthetic `rev_` decoy row so the `7502692` guard is
  live; verified reverting the drop fails both the invariant and the snapshot.
- Both fixtures reproduce Slava exactly on their slices (identity 100%, dpbp r=1.0).

317 unit + 25 eval tests pass; mypy + ruff clean. Not yet committed to master.

---

## 2026-07-28 — Containerization (Apptainer/Singularity) landed + build-validated

Merged `container/singularity-image` -> master (11 commits, e00607c). Spec+plan in
`docs/superpowers/{specs,plans}/2026-07-28-tarsus-singularity-container*`.

- `container/tarsus.def` (rockylinux:9) + `scripts/build_container.sh` (internal/public
  modes, `singularity build --fakeroot`). Provenance now falls back to a baked
  `TARSUS_BUILD_COMMIT`/`BUILD_COMMIT` when git is absent (container).
- Repo publish-readiness: MIT LICENSE; untracked data/test-mock/dev.mzML (18MB) +
  docs/qc-history/subs/*.ipc (8MB); validation conftest skips when dev.mzML absent.
- BUILD VALIDATED on login5 (apptainer 1.4.0 root-mapped namespace — docker-gpu NOT
  required despite the wiki; login nodes can build). tarsus.sif = 2.9G, %test green
  (344 passed/1 skipped, all tools resolve), `tarsus --help` runs, git_sha() returns
  the baked commit with no git in-image.
- Build debugging captured 3 recipe fixes: allowlist the context (was copying the
  TARSUS_elizabev symlink tree), dnf `--allowerasing` (curl-minimal conflict), exclude
  .superpowers. See WEXAC container workflow in auto-memory.
- Execution model deferred (documented): the master's child bsub jobs must also run
  `singularity exec`; separate spec. Image validated as a reproducible environment only.

---

## 2026-07-29 — Built container image: persistent location

The validated Apptainer image lives at:

    /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif   (2.9 GB, commit e00607c)

Gitignored (`*.sif`), so it is never committed/pushed. Built on login5 (apptainer
1.4.0 root-mapped namespace; docker-gpu NOT required). Contains all tools+runtimes
(TARSUS_TOOLS_DIR=/opt/tarsus/tools) + the tarsus package; %test was green at build.

Use:
- `apptainer exec /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif tarsus --help`
- LSF: `bsub -q gsla-cpu -R "rusage[mem=32GB]" 'ml Singularity; singularity exec \
    --bind /home/labs/pilpel:/home/labs/pilpel \
    /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif tarsus run -i <raw> --fasta <fa> -o <out>'`

Rebuild/re-bless anytime (~4 min): `scripts/build_container.sh --internal --out <path>`
(public/portable: add `--public --msfragger <zip> --ionquant <jar>`). Recipe:
`container/tarsus.def`; see [[wexac-container-workflow]] and D-071-adjacent notes.
