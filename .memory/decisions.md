# Decisions Log

## D-070 (2026-07-24): `re.match` silently dropped every pre-modified substitution

**Issue:** On byte-identical reference inputs, our Step 7 produced **3521 rows vs
the reference's 3922** (−10%). Found while validating D-069, unrelated to it.

**Method:** Dry-ran our real `analyze_outputs()` against the reference's own
inputs (`elizabev/tRNA/EVpar/tarsus_analysis`), which holds `psm.tsv`,
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
`elizabev/TARSUS/analyze_outputs.py` — the file our Step 7 recapitulates — and
confirmed it **never computes these columns**. It reads the second-pass `psm.tsv`
and keeps *all* of its columns. Verified both canonical `second/psm.tsv` files
(Slava GAPDH, elizabev EVpar) carry `SpectralSim` at col 18 and `RTScore` at col 19,
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
