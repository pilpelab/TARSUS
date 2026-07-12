# Lessons — read before changing pipeline code

Distilled from every bug that actually cost us time (D-026 → D-051). This is not a style guide;
each rule below is here because breaking it burned days of cluster time. Update it when a new bug
teaches something the list does not already cover.

---

## The one failure mode that caused most of our bugs

**Silent defaults over missing data.** Not one of our serious bugs was a crash. Every one of them
was code that *quietly did the wrong thing* when data was absent, and reported success:

| Pattern | Where it bit us | Cost |
|---|---|---|
| `.get(col, 0)` on a renamed column | Step 11 read `mistranslatedPos`; Step 7 emits `mistranslated_pos`. Default `0` made the expected position always 1 — unreachable. **Step 11 could never return a row.** | D-048 |
| `fill_null(0)` after a left join | Variants never rescored against base got `delta_score = score - 0 > 0` and were silently admitted | D-048 |
| Reading the wrong column | Step 8 keyed on `Spectrum` (`f_sub.101063.101063.2`) vs MGF titles (`f:101063:2`) → **0/1,113 matched, 0-byte MGF** | D-049 |
| `.done` stamped over empty output | Steps 7/8/9/10/11 marked complete over 0 rows; failure surfaced 3 steps later, misattributed | D-043, D-047 |
| Guardrail checking the wrong artifact | Step 8's guard counted input chunks (4,287 — non-empty!) while its MGF was 0 bytes | D-049 |
| `re.sub` on an absent key | A patch whose key is missing from the workflow is a **no-op**. No error, wrong science. | D-051 |
| Artifact written only at end-of-step | `.calibration_params` written at the end of Step 3a — which is *skipped* on resume via `.done`. Fix silently no-ops on every rerun. | D-051 |

**Rule: when data is missing, raise. Never default.** If a column, file, or key is absent, that is a
contract violation — say so loudly. Steps 7, 8 and 10 now have explicit guardrails. Steps 9 and 11
still do not; add them when you touch those files.

---

## Do not "optimize" a contract you have not read

Commit `e143a46` changed Step 2 to index `*_sub.mzML` instead of the original mzML. It looked free —
half the spectra, same result. It silently moved every spectrum title into a new namespace, and cost
**a full week**: it produced D-032's false scan-number diagnosis, which motivated the peptide-only
Step 4 rewrite (D-044), which produced the NPE (D-045) and the mass disagreement (D-046) — both
*self-inflicted* by the `-varMod 2,33` added to compensate. Step 7 emitted 0 rows for a month.

**Rule: before changing what a step consumes or produces, find what downstream depends on it.**
Spectrum titles, column names, and file namespaces are contracts. `.context/architecture.md` records
the spectrum-title invariant — read it.

---

## Ground truth beats reasoning

We spent a week theorizing about why targeted PepQuery "couldn't work" (D-045, D-046), and wrote a
959-line plan (Option C) to work around it. Then we found the colleagues' completed run at
`/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` — it used exact targeted validation, worked
fine, and its index titles answered the whole question in one `grep`. Option C's premise was false;
we cancelled it unimplemented.

**Rule: before building a workaround, go find a working example.** Read the reference's *artifacts*,
not just its scripts — `second.workflow`, `psmrankall.txt`, `subs.ipc` told us more than the source did.

---

## Reuse the tool's own output; don't reconstruct it

D-051 (first attempt) regex-scraped MSFragger's log for `New fragment_mass_tolerance = 10.0 PPM`
lines to rebuild calibration settings — while FragPipe had already written
`03a_first_pass/fragpipe-second-pass.workflow` containing exactly those values, which is the file the
reference actually consumes.

**Rule: if a tool emits a machine-readable artifact, use it. Parsing a human-readable log to recover
data that exists in structured form is a bug waiting to happen.**

---

## A test that does not call the code is not a test

`TestWorkflowPatching` re-implemented step03c's regex patches *inside the test* and asserted against
its own copy. It would have stayed green if the real function were deleted. Meanwhile the actual
`_patch_workflow` had zero coverage.

**Rules:**
- Every test must import and call the function under test.
- When a bug is found, the regression test must *fail* against the old code first. Verify that.
- Pin invariants that fail silently: e.g. "every key we `re.sub` exists in the template."

---

## Verify the load-bearing assumption before spending cluster time

Before the D-047 rerun (days of compute) we checked the single assumption everything rested on: that
`_sub.mzML` preserves the original scan numbers. First probe said **no** — which would have made the
whole fix wrong. It was a parser bug: ThermoRawFileParser writes `value="2" name="ms level"`,
FragPipe writes them in the opposite order, and an order-sensitive regex silently reported "no
precursor found." Re-probed correctly: identical m/z, charge, msLevel. The fix was sound.

**Rule: name the one assumption the change depends on, and test it directly — cheaply — before
launching. And when a quick check contradicts a well-evidenced conclusion, suspect the check.**

---

## Some bugs are only findable by running it

Steps 8–11 had *never executed successfully*. The moment they did, four bugs surfaced in one hour
(D-049, D-050): a JVM heap larger than its own LSF reservation; an Xvfb display race that only bites
when two shards land on the same host; a missing `mkdir`; PepQuery emitting 26-field rows against its
own 22-column header (4 of 19,913 — zero in the reference's data).

**Rule: green tests are not evidence the pipeline works. Drive it end-to-end.** Prefer a cheap dry
run on real artifacts (`python -c` against `output/trial/...`) before submitting to LSF — that is how
Steps 10 and 11 landed in a single pass.

---

## Faithful ≠ efficient, and that is fine

Step 9 submits one LSF job **per peptide** (4,287 jobs; one JVM + one 150 MB MGF parse each). This
looks broken. It is not — the reference does the same (`n=1`, 6,664 files). It is wasteful, and
batching would probably be result-identical.

**"Probably result-identical" is exactly the reasoning behind `e143a46`.** Deviations from the
reference are allowed, but each one is a deliberate, tested, documented decision — never a passing
tidy-up. Known deliberate deviations: D-048 defect 4 (title-suffix strip), msbooster disabled.

---

## Pre-flight checklist for any pipeline change

1. **Contract:** what does this step consume/produce? Who downstream reads it? (`architecture.md`)
2. **Reference:** what does `TARSUS_elizabev/` — and the real run under `elizabev/` — actually do?
3. **Missing data:** does every new read raise on absence, or does it default? Remove the defaults.
4. **Resume:** does this still work when upstream steps are skipped via `.done`? (D-051's trap)
5. **Silent no-ops:** any `re.sub`/`.get`/join that does nothing when its key is absent? Pin it.
6. **Test:** does it call the real function? Does it fail against the old code?
7. **Assumption:** name the one thing this rests on. Test it cheaply on real data.
8. **Sentinels:** which `.done` files must be invalidated for the change to take effect? State it.
   *Move* stale outputs aside; do not delete.
9. **Results:** will this change the SAAV counts? If yes, say so — and mark progress.md stale.

---

## Still open

- **Biological positive control fails.** Dataset is named `AlaGGC`, yet G→A is 0.3% of calls
  (rank 60/156). Nobody has confirmed what `AlaGGC` should produce. **The pipeline is mechanically
  correct; that is not the same as right.** Ask the scientists before trusting the SAAV list.
- **No CI.** Nothing runs the 223 tests, mypy, or ruff automatically. 3 ruff errors sit unfixed.
- **Config not externalized.** 9 steps hardcode `queue="gsla-cpu"`; `--queue` reaches only the master
  job. `.agents/project.md` promises per-lab overridability — the repo does not deliver it yet.
- **Unexplained writes to `output/trial/`.** `01_mzml/*.mzML` were regenerated 2026-07-09 by jobs no
  session launched, while `.done` stayed stale so orchestration never noticed.
