# Lessons — read before changing pipeline code

Distilled from every bug that actually cost us time (D-026 → D-058). This is not a style guide;
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
| `[ -s file ]` as a completeness check | A download killed by a timeout left a **truncated 1.6 GB** `.raw` (should be 10.9 GB). "Exists and non-empty" declared it complete and skipped the re-fetch. **I wrote this one myself, in the same session I wrote this table.** | D-055 |

**"Non-empty" is not "complete."** Size, checksum, or a parse is a completeness check. Existence is
not. This applies to downloads, to `.done` sentinels, and to every output file this pipeline writes.

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

## `.done` records THAT a step ran — not WHICH CODE ran it

The single most expensive bug in this project (D-057). `output/trial/03b_candidates` was built
**2026-06-30 13:14**. The fix `4c2d9d6 "I/L normalization in variant peptide generation"` landed
**14:30 — 76 minutes later.** That library therefore held **0 of 7,369,406 `→Ile` variants**, and was
preserved as "unaffected" by *every* subsequent invalidation (D-047's index fix, D-051's calibration
fix, all of them). Each of those judgments was individually correct **about its own change**. None
asked whether Step 3b's artifact predated a fix to *Step 3b*.

Result: **two weeks of AlaGGC results were computed against a search space that could not contain the
answer**, and it was only caught because the substitution spectrum showed an impossible pattern
(D→I = 0 vs 249; N→I = 0 vs 76 — all-or-nothing is technical, never biological).

**Rule: justify every preserved sentinel by artifact provenance, not by reasoning about scope.**

```bash
find output/<run>/<step> -name '<artifact>' -printf '%TY-%Tm-%Td %TH:%TM\n'
git log -1 --format='%ad' --date=format:'%Y-%m-%d %H:%M' -- src/tarsus/steps/<that_step>.py
```

If the artifact is older than the code, it is stale — no matter how confident you are that your
change "doesn't touch that step."

**Corollary — an impossible data pattern is a bug, not a discovery.** Zero-vs-hundreds, perfectly
absent categories, or effects far larger than the biology permits: suspect the pipeline first.

---

## Do not edit source that a running job is importing

Both `TARSUS_BC` and `~/LIS1_mutant_organoids__Orly_Reiner` execute **one shared, editable source
tree**. `orchestration.py` imports each step module **lazily**, when the master reaches it — so a
master running for hours picks up whatever is on disk at that moment. A live edit is executed by a
live pipeline; a briefly-broken file kills a run hours in; and a changed signature meets an `lsf`
module cached in `sys.modules` since Step 1, raising `TypeError` mid-run.

```bash
bjobs | grep us_master     # any master running -> src/tarsus/ is FROZEN
```

Docs, tests, `.memory/` are always safe. Only `src/` is live. **Nothing records which commit produced
a given result** — which is the same disease as D-057 in a different organ.

---

## Test the whole hypothesis, not the piece you happened to name

For weeks I tested **G→A** as *the* signature of `AlaGGC`, on the assumption that the three letters
were the codon read. They are the **anticodon** (D-058). Anticodon `GGC` decodes codon `GCC` = Ala, so
the tRNA is *cognate*; the real prediction is near-cognate misreading giving **X→Ala** from **six**
origins {D,G,P,S,T,V}.

G→A happened to be in that set — **by coincidence**, because the anticodon `GGC` and the Gly codon
`GGC` are the same three letters. So every "G→A is depleted!" test was (a) a sixth of the hypothesis
and (b) underpowered (n=8 vs 5, p=0.171).

**Rules:**
- **Derive the prediction from the mechanism before testing it.** Ask the domain expert for the
  expected result on day one; do not infer it from a filename.
- **A right answer for the wrong reason is not a validated method** — it will not generalise to the
  next condition.
- Beware effects the design makes invisible: all three wobble changes from GCC (GCA/GCG/GCU) are *also
  Alanine*, i.e. **silent** — and wobble is where misreading is most common. A small or null result may
  be the true biology, not a broken pipeline.

---

## A shared lazily-built artifact is a race. Build it ONCE, up front.

PepQuery builds `<db>.fmi` lazily on first use. All 4,784 Step 5 chunks share one `-db`, so with the
index absent **they all raced to write the same file** — and did not merely trip over each other, they
**permanently corrupted it**: the raced index came out **238 MB against a correct 191 MB**, inflated by
concurrent truncate-and-rewrite at different offsets. *Everything* crashes against it, forever, even
single-process hours later (D-059).

**Rule: any artifact that N parallel jobs build lazily on shared state must be built once, serially,
before the fan-out.** The same shape appeared in Step 2's index and in `stage_pepquery_db` — check for
it whenever you add a fan-out.

**Corollary — a fix that addresses *where* but not *how many* is half a fix.** D-054 staged the FASTA
into a writable directory (fixing the permission error) and left the concurrency untouched. I named the
race in that very commit message, said "build it once, serially", and shipped only the staging half.
**Write the guard when you notice the hazard, not later.**

---

## Diagnose from evidence; a plausible mechanism is not a diagnosis

On the FMIndex crash I produced **three** explanations, and the first two were wrong:

1. *"PepQuery bug on large FASTAs"* (the note) — wrong; PepQuery indexes the 101 MB proteome fine.
2. *"A transient race — readers catch the file mid-write"* (mine) — **wrong, and confidently asserted.**
   It fit the symptoms (interleaved crashes and successes, index mtime moving for hours) and I wrote it
   into a decision record. **A transient race predicts the crashes stop once the writing stops.** They
   did not: 11/11 chunks still crashed, single-process, against the stable file.
3. The truth, only from running the experiment: **the file is permanently corrupt.** Deleting it and
   rebuilding cleanly (191 MB) fixed everything.

**Rules:**
- **State what your hypothesis predicts, then test that prediction** — not just whether it "explains"
  what you already saw. Mine made a falsifiable claim (crashes stop) and I never checked it.
- **Then check the blast radius.** I next assumed the 1,992 "successes" must be poisoned too and advised
  discarding all 4,784. Re-running a sample against a clean index proved **3/3 byte-identical** across
  the entire race window — the successes were fine. **PepQuery fails loudly on a bad index rather than
  returning wrong matches.** Over-caution has a cost too: it would have thrown away hours of valid work.
- The user caught both errors. **When a user pushes back on an unproven claim, they are usually right —
  the claim was unproven.**

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

## Mechanically correct ≠ scientifically right

We spent weeks making the pipeline faithful to the reference. It now is: same spectrum-title
contract, same PepQuery flags, same second-pass search parameters, completes end-to-end. **And the
biology still does not validate.** The dataset is named `AlaGGC` — which should mean Ala
misincorporated at Gly codons, i.e. G→A substitutions — and G→A comes out **8x *depleted*** relative
to the reference's EVpar dataset (0.31% vs 2.58%), while the substitutions that *are* enriched
cluster at ±1/±2/±16 Da, the signature of isotope and oxidation misassignment rather than
mistranslation. See D-053.

**Rules:**
- **Get the expected result before you start optimizing toward it.** Nobody ever wrote down what
  `AlaGGC` should produce. We built, debugged and validated a pipeline for weeks against a target
  that was never stated. Ask for the positive control on day one.
- **A green pipeline is not a correct one.** Every acceptance criterion passed while the headline
  scientific claim remained unsupported.
- **Never tune parameters until the expected signal appears.** That is fitting to a number nobody
  supplied. If the signal is absent, the honest outputs are "the experiment did not work", "the
  method cannot detect it", or "we misunderstood the design" — decide which *with the scientists*.
- **Check the artifact signature.** Substitutions whose Δmass is ≈ ±1 Da (C13), ±2 Da (2×C13),
  ±16 Da (oxidation), or ≈ 0 Da (near-isobaric, e.g. Q→K at +0.036 Da) are chemistry, not biology.
  If those dominate the results, treat the result set as suspect regardless of how clean the code is.

## Still open

- **The validation is a clean NULL, and it is UNDERPOWERED (D-060).** AlaGGC vs its paired control:
  X→A **0.94x, p=0.65**. Same code, same params, same-commit libraries — the comparison is finally
  sound. But it is **one replicate pair**. The panel has **3 replicates x 9 tRNAs** (PRIDE PXD071134).
  **Do not conclude "the strain does not mistranslate." Do not tune parameters until a signal appears.**
  The power is in analysing all replicates and the whole panel as a dose-response.
- **No provenance recording.** `tarsus run` should stamp `git rev-parse HEAD` + a dirty flag into the
  output dir and **refuse to run on a dirty tree**. Direct fix for D-057 (stale artifact) *and* the
  shared-mutable-source hazard. **Highest-value engineering item remaining.**
- **LIS1 shares TARSUS_BC's mutable source tree.** Pin it, or snapshot source per run.
- **Config not externalized.** 9 steps hardcode `queue="gsla-cpu"`; `--queue` reaches only the master
  job. `.agents/project.md` promises per-lab overridability; the repo does not deliver it. This is the
  real blocker for the stated cross-lab goal.

## polars `read_ipc` mmaps by default — writing back to the same path destroys the file

**Date:** 2026-07-16 (during D-065)

`pl.read_ipc(path)` **memory-maps** the file. String columns keep pointing into that
mapping. `write_ipc(path)` to the **same path** then truncates the file *while the
mapping is live*, so the write reads freed pages → **SIGBUS/SIGSEGV, and the file is
left at 0 bytes.**

This destroyed `output/trial/07_analyze/subs.ipc` (2,940 rows → 0 bytes), and it is
the real cause of two earlier crashes I misdiagnosed:
- exit 139 during the D-065 relabel loop — I blamed **matplotlib**. It was this.
- `hoMS/11_localized/subs_localized.csv` at 0 bytes — I blamed the same phantom
  matplotlib segfault. It was the `.csv` write that followed the `.ipc` write-back.

It does **not** reproduce on a small synthetic frame (polars materialises those), so a
quick repro will lie to you. It bites on real files.

**The rule for any read-modify-write of an `.ipc`:**

```python
d = pl.read_ipc(p, memory_map=False)   # do not mmap the file we are about to clobber
out = d.with_columns(...)
tmp = p.with_suffix(".ipc.tmp")
out.write_ipc(tmp)                     # write elsewhere...
os.replace(tmp, p)                     # ...then replace atomically
```

`memory_map=False` removes the hazard; the temp+`os.replace` makes the write atomic, so
a crash leaves the **old** file intact instead of a 0-byte stub.

**Transferable lesson.** In-place rewrite of a memory-mapped file is not an edit, it is
a use-after-free with a filename. And when a crash and a truncated file appear together,
suspect *the writer*, not whatever library happened to run next — I blamed matplotlib
twice because it was the noisiest thing in the traceback's neighbourhood, and it was
innocent both times.

## A bigger search library makes you LESS sensitive, not more

**Date:** 2026-07-16

Step 3b mutagenizes **every peptide the first pass identified**. That is the whole search space,
and nobody chooses it explicitly — it falls out of how many peptides you happened to identify.

FragPipe holds FDR by counting **decoys**, and every candidate gets a decoy twin. More
candidates → more decoys scoring well by chance → MSFragger **raises the score threshold** to
keep FDR at 1%. **The same spectrum, same evidence, same parameters, passes in a small search
and fails in a large one.**

Measured (hoMS/GAPDH, identical raw data and parameters):

| | library base peptides | forward candidates | second-pass PSMs |
|---|---|---|---|
| GAPDH-focused (reference) | 79 | 23,280 | **16,341** |
| proteome-wide (ours) | 4,667 | 941,020 | **8,979** |

A **40x larger library gave 1.8x FEWER PSMs**, and that gap propagates untouched: PepQuery
tested 7,113 vs 4,814 spectra → output 233 vs 167. For a long time I read this as "he is more
sensitive" and hunted for a defect in our filtering. **There was no defect.** He was searching a
smaller haystack.

**How to tell which situation you are in:** look at `protein_burden.png`. If one protein carries
almost everything (hoMS: 43 of 44 rows on GAPDH), you are paying a huge FDR penalty to search
thousands of peptides you will report nothing from — restrict the library to the target protein.
If the substitutions are spread across the proteome (E. coli tRNA panel: 84–174 proteins),
proteome-wide is correct.

**Transferable lesson.** In FDR-controlled search, *the size of the question changes the answer*.
Comparing yields between two runs is meaningless unless their search spaces are the same size —
this is the same class of error as D-053 (comparing across FragPipe versions). Before concluding
"they found more than us," check **what each one searched**.
