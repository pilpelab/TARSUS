# Spec: Step-07/11 Regression Eval

**Status:** approved design, ready for implementation by a fresh agent.
**Date:** 2026-07-28

## Context

The TARSUS_BC pipeline reproduces Slava's TARSUS/FragPipe substitution pipeline.
Every correctness bug this project has hit lived in **step 07 (`analyze_outputs`)**:
D-069 (MSBooster disabled → null `SpectralSim`/`RTScore`), D-070 (`re.match`
anchoring silently dropped Cys/Met substitutions), and the `rev_` decoy leak
(decoy proteins reaching `subs.ipc`; fixed in commit `7502692`). These were all
caught **manually, late**, by ad-hoc QC against Slava's references.

There is no repeatable guard. `tests/unit` covers pure helpers; `tests/validation`
needs LSF + real tools (slow, not CI-able). Nothing re-runs the analysis steps on
known inputs and checks the output still matches.

**This eval closes that gap:** a fast, committed, CI-style regression check that
re-runs the two deterministic analysis steps on frozen reference inputs and fails
if a commit silently changes the output or breaks reproduction of Slava.

## Goal & scope

Exercise the two pure-Python, deterministic steps that build the deliverable
tables, called **directly as functions** (no orchestration, no LSF, no external
tools), so the whole eval runs in seconds under `pytest`:

- **Step 07** — `analyze_outputs(...)` → `subs.ipc`
- **Step 11** — `localize(...)` → `subs_localized.ipc` / `.csv`

**In scope:** fixtures, the two step calls, snapshot + invariant checks, a fixture
builder, a `make eval` entry point.
**Out of scope:** steps 01-06/08-10/12, any cluster/tool run, the tRNA-vs-MaxQuant
cross-method comparison, and the broad multi-organism benchmark (possible later,
separate spec).

## Exact function signatures (source of truth — read the code, don't guess)

From `src/tarsus/steps/step07_analyze_outputs.py`:
```
analyze_outputs(first_psm_path, second_psm_path, ptmall_path,
                psmrankall_path, pdv_path, output_ipc, sample=None) -> pl.DataFrame
```
Inputs map to pipeline artifacts: `first_psm_path`=`03a_first_pass/psm.tsv`,
`second_psm_path`=`03c_second_pass/second/psm.tsv`, `ptmall_path`=`06_aggregated/ptmall.txt`,
`psmrankall_path`=`06_aggregated/psmrankall.txt`, `pdv_path`=`06_aggregated/pdv_spectra/PDVExportResult.txt`.

From `src/tarsus/steps/step11_localize.py`:
```
localize(subs_ipc, psmrankall_path, psmrankall_base_path,
         spectra_mgf, output_ipc, output_csv) -> ...
```
Extra inputs vs step 07: `psmrankall_base_path`=`10_aggregated_base/psmrankall_base.txt`,
`spectra_mgf`=`06_aggregated/mgfall.mgf`. (Confirm the exact signature in the code;
the orchestrator calls both at `orchestration.py:156` and `:250`.)

## Fixtures

Two fixtures, both organisms, both with a **like-for-like Slava reference `subs.ipc`**:

| name | reference run dir (source of inputs + golden) |
|---|---|
| `evcoli` | `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` |
| `gapdh`  | `/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/` |

**First discovery task:** these reference dirs hold the step-07/11 inputs, but the
exact filenames/subpaths may differ from the pipeline layout above (e.g. `ptmall.txt`,
`psmrankall.txt`, the PDV export, `mgfall.mgf`, and the base `psmrankall_base.txt`
may sit at different paths). Locate each required input in each reference dir before
building; if one is genuinely absent for a fixture, drop that fixture's step-11 half
(keep step 07) and record why in the spec's fixture README.

Each fixture is a **lineage-coherent ~100-spectrum slice**, not the full inputs
(full first-pass `psm.tsv` is ~250k rows — do NOT commit that). The slice must:

- Select spectra that are **present in Slava's reference `subs.ipc`** for that run
  (so the identity/dpbp invariants are meaningful).
- Filter **all** inputs consistently to that spectrum set — the same `spectrum_title`
  lineage must survive across `03a psm.tsv`, `03c second/psm.tsv`, `ptmall`,
  `psmrankall`, the PDV export, `mgfall.mgf`, and `psmrankall_base.txt`. Mismatched
  keys across files silently yield 0 rows (see D-047) — the builder MUST assert the
  sliced step-07 output is non-empty.
- Deliberately include, if present in the source: a `rev_` decoy-anchored row, at
  least one Cys- and one Met-origin substitution (D-070 guard), a multi-charge
  spectrum, and an I/L-ambiguous peptide.

Committed at `tests/eval/fixtures/<name>/inputs/…` (~1-5 MB total).

## Pass/fail — snapshot gate + invariant guards (both)

1. **Snapshot gate.** Commit `tests/eval/fixtures/<name>/golden/subs.ipc` and
   `subs_localized.ipc`, produced by current (known-good, post-`7502692`) code.
   The eval canonicalizes both the fresh output and the golden — **sort rows** by
   `(Spectrum, dependent, Charge)` (use columns that exist; fall back gracefully),
   **round floats** to ~6 dp — then asserts frame equality. A regeneration path
   (`--update` pytest option or `TARSUS_EVAL_UPDATE=1`) rewrites the goldens when a
   change is intentional; blessing is a deliberate, reviewed commit.

2. **Invariant guards** (named assertions so failures say *what* broke):
   - schema: output columns == the documented `subs.ipc` schema (`docs/SUBS-SCHEMA.md`).
   - `rev_` count across `Protein`/`Protein_right` == 0.
   - `SpectralSim` and `RTScore` null count == 0.
   - `dpbp` all finite (no null/inf/NaN).
   - vs the sliced Slava reference `subs.ipc`: substitution (origin+dest+position)
     identity on shared spectra == 100%; `dpbp` Pearson r ≥ 0.99. (Reuse the
     comparison logic from the manual QC; I/L-normalize the peptide key.)

## Layout

```
tests/eval/
  __init__.py
  eval_lib.py                 # canonicalize(df), invariant checks, slava_compare(ours, ref)
  test_eval_step07_11.py      # pytest, parametrized over fixtures: run step07(+11) → canonicalize → snapshot + invariants
  fixtures/
    evcoli/{inputs/, golden/, README.md}
    gapdh/{inputs/, golden/, README.md}
scripts/build_eval_fixtures.py   # one-time slice builder; re-runnable to (re)bless goldens
Makefile: add `eval:` target → `uv run pytest tests/eval -q`
```

`build_eval_fixtures.py` is the tricky component: it slices the reference inputs,
writes `fixtures/<name>/inputs/`, runs `analyze_outputs`/`localize` on the slice,
writes `golden/`, and asserts the sliced Slava-reference invariants hold at build
time (fail loudly if the slice is empty or diverges — that means the slice broke
lineage, not that the code is wrong).

## Risks the implementer must handle

1. **Cross-file lineage subsetting** (main risk). Getting the spectrum set consistent
   across all inputs is fiddly; a key-format mismatch yields a silent empty result.
   Mitigation: build the slice from one spectrum-id set, filter every file by it,
   and assert non-empty + reference-matching output inside the builder.
2. **Float / row-order non-determinism.** Never compare raw IPC bytes — canonicalize
   (sort + round) first. Pick the rounding precision so real reference values still
   compare equal.
3. **Schema drift is intended sometimes.** The snapshot will fail on any legitimate
   schema/behavior change; that's the point — the fix is `--update` + a reviewed
   commit, documented in `tests/eval/README` so it isn't blessed blindly.

## Acceptance criteria

- `make eval` (== `uv run pytest tests/eval -q`) passes on `HEAD`, runs in < ~15 s,
  needs no cluster/tools/network.
- Reverting the `7502692` decoy fix makes the `rev_`-count invariant (and the
  snapshot) fail — i.e. the eval actually catches that regression.
- Fixtures total < ~10 MB; no full-size `psm.tsv` committed.
- `build_eval_fixtures.py` regenerates fixtures + goldens deterministically from the
  reference dirs.

## Handoff

Implementation is for a fresh agent. Suggested order: (1) `eval_lib.py`
canonicalize + invariants + slava_compare; (2) `build_eval_fixtures.py` for one
fixture (`gapdh`) end-to-end, verifying non-empty + invariants at build time;
(3) `test_eval_step07_11.py` snapshot+invariant test, green on that fixture;
(4) add `evcoli`; (5) `make eval` target + `tests/eval/README`. Use TDD where the
helper logic (canonicalize, slava_compare) is pure.
