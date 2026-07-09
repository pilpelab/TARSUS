# D-047: Restore Reference Targeted-Lineage Contract

**Goal:** Make Step 7 produce > 0 rows and let Steps 8–11 run, by restoring the exact
spectrum-title lineage the reference implementation uses and which is *proven* to work
(3,922-row `subs.ipc` on the same Orbitrap Astral DDA instrument family).

**Supersedes:** `2026-07-08-step7-proximity-lineage.md` (Option C) — cancelled, do not implement.

**Decision record:** D-047 in `.memory/decisions.md`.

---

## Root cause (one sentence)

Commit `e143a46` moved Step 2 to index `*_sub.mzML` instead of the original mzML, shifting the
PepQuery index into a `_sub`-bearing spectrum-title namespace; every subsequent "bug" and workaround
(D-032's false scan-number claim, D-044's lineage break, D-045's NPE, D-046's mass disagreement)
is a downstream artifact of that single change.

## Reference contract (the target state)

| Stage | Reference behaviour | Verified from |
|---|---|---|
| Step 2 index source | **original** mzML | `make_index.sh`; index `TITLE=...-EVpar-LS-3:121018:2` (no `_sub`) |
| Index title namespace | `file:scan:charge` | reference `pepquery_index/*.mgf.gz` |
| Step 4 output | 2 cols, `peptide\tspectrum_title`, `_sub` **stripped** | `extract_psm.py`; `second/psm_input4pepquery.tsv` |
| Step 5 flags | `-ti 0,1,2,3 -maxLength 50 -tol 20 -itol 0.05 -hc -aa -m 1 -e 2 -c 2` | `query_psm.sh` — **already identical**, no `-varMod` |
| Step 7 title conversion | `_sub` **stripped** | `analyze_outputs.py` line ~141 |

## Global constraints

- Steps 01, 03a, 03b, 03c outputs are **preserved**. They cost ~46 GB and days of cluster time.
- Do **not** add `-varMod`, `-indexType`, or `-s` to Step 5. The reference passes none of them; the
  D-045 NPE only appears once `-varMod 2,33` is present.
- Step 4 does **not** deduplicate — the reference writes one row per `Intensity > 0` PSM row.
- Nothing under `/home/labs/pilpel/elizabev/` is ever written to.
- Type annotations + docstrings on all functions; Polars for tabular data; pytest, no real-tool calls
  in unit tests.

---

## Task 1 — Step 4 emits targeted two-column input

**Files:** `src/tarsus/steps/step04_extract_psm.py`, `tests/unit/test_step04_extract_psm.py`

- [ ] Update unit tests: expect `peptide\tspectrum_title`; `file_sub.00100.00100.2` → `file:100:2`
      (strip `_sub`, strip leading zeros, charge from the `Charge` column).
- [ ] Run tests → verify they fail.
- [ ] Rewrite `extract_psm()` to mirror reference `extract_psm.py`; add `_spectrum_to_title()` helper.
      Rewrite the module docstring (it currently repeats the false scan-number claim).
- [ ] Run tests → pass.

## Task 2 — Step 7 strips `_sub` again

**Files:** `src/tarsus/steps/step07_analyze_outputs.py`, `tests/unit/test_step07_analyze_outputs.py`,
`tests/validation/test_step07_analyze.py`, `tests/validation/expected/step07_fixtures/*`

- [ ] Update unit tests: `_spectrum_to_title("file_sub.100.100.2") == "file:100:2"`.
- [ ] Update validation fixtures from the `dev_sub:1:2` namespace to `dev:1:2`
      (`ptmall.txt`, `psmrankall.txt`, `pdv_export.txt` titles; `second_psm.tsv` keeps `dev_sub.1.1.2`
      in its `Spectrum` column, since FragPipe really does emit `_sub` there).
- [ ] Run tests → verify they fail.
- [ ] Revert `_spectrum_to_title()` to strip `_sub`. Delete the now-dead `_normalize_spectrum_title()`.
- [ ] Run tests → pass.

## Task 3 — Step 2 indexes the original mzML

**Files:** `src/tarsus/orchestration.py`, `src/tarsus/steps/step02_make_index.py`

- [ ] Point Step 2 at `outdir / "01_mzml"`; move it back above Step 3a (it now depends only on Step 1).
- [ ] Update the Step 2 comment/log line and `step02_make_index` docstring.
- [ ] `step02_make_index` needs no logic change — it globs `*.mzML`, which now matches the originals.

## Task 4 — Guardrail on Step 7

**Files:** `src/tarsus/orchestration.py`, `tests/unit/test_orchestration.py`

- [ ] Step 7 currently stamps `.done` over a 0-row `subs.ipc`. Add a loud failure, mirroring the
      existing Step 8 guardrail, so a future lineage break cannot silently pass.
- [ ] Test: 0-row `subs.ipc` → `RuntimeError`, no `.done`.

## Task 5 — Verify, then rerun

- [ ] `uv run pytest -m "not lsf"` → all green.
- [ ] `uv run mypy src/tarsus`; `uv run ruff check src/tarsus`.
- [ ] Invalidate sentinels **02, 04, 05, 06, 07, 08** only. Preserve 01/03a/03b/03c.
      Move stale `02_index/`, `05_pepquery/`, `06_aggregated/` aside rather than deleting outright.
- [ ] Resubmit the master job; watch `master.log`.

## Acceptance criteria

1. `uv run pytest -m "not lsf"` green.
2. Step 2 index MGF `TITLE=` lines contain **no** `_sub`.
3. Step 4 output has **2** tab-separated columns.
4. Step 5 PepQuery logs report `Matched spectra: N` with N > 0.
5. `07_analyze/subs.ipc` has **> 0** rows (reference magnitude: 3,922 from 2 Astral DDA files).
6. `08_base_input/pepquery_input_base/` non-empty; `mgfall_fakes.mgf` > 0 bytes.
7. Steps 09/10/11 exist; `subs_localized.csv` has > 1 line.
8. `master.log` ends `DONE: Pipeline complete.`
