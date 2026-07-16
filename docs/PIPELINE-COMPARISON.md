# TARSUS_BC vs the reference (`elizabev/TARSUS`) — what differs and why

Every claim here was verified by reading or **executing** the reference's own code, or by
measuring both pipelines on the same data. Where a number could not be sourced, it is
marked as such rather than asserted.

**Reference:** `/home/labs/pilpel/elizabev/TARSUS` (13 scripts, FragPipe **23.1** /
Philosopher **5.1.2**).
**Ours:** `src/tarsus/` (12 orchestrated steps, FragPipe **24.0** / Philosopher **5.1.3**),
LSF-orchestrated, resumable, provenance-tracked.

---

## Step map

| stage | reference | ours |
|---|---|---|
| convert raw → mzML | `convert_raw.sh` | `step01_convert.py` |
| index spectra | `make_index.sh` | `step02_make_index.py` |
| first-pass search | `search_pipeline_script.sh` | `step03a_first_pass.py` |
| **build variant library** | `make_peptides.py` | `step03b_make_peptides.py` |
| second-pass search | `search_pipeline_script.sh` | `step03c_second_pass.py` |
| extract PSMs | `extract_psm.py` | `step04_extract_psm.py` |
| PepQuery validation | `query_psm.sh` | `step05_query_psm.py` |
| aggregate | `aggregate_query.sh` | `step06_aggregate_query.py` |
| **analyze → subs** | `analyze_outputs.py` | `step07_analyze_outputs.py` |
| reference-validation prep | `ref_validation_prep.py` | `step08_ref_validation_prep.py` |
| base rescoring | `query_psm_base.sh` | `step09_query_psm_base.py` |
| aggregate base | `aggregate_query_base.sh` | `step10_aggregate_query_base.py` |
| **localize (AScore)** | `localize.py` | `step11_localize.py` |
| visualize | *(separate: `tRNA/scripts/SubsToSixtyTwentyWithMask.py`)* | `step12_visualize.py` |

---

## A. Reference bugs we fixed (our output is more correct)

### 1. The substitution matrix was read transposed (D-061) — **ours was the broken one**
The CSV is **COLUMN=origin, ROW=destination**. The reference is right: it does
`pd.read_csv(...).to_dict()` → `{COLUMN: {ROW: v}}` and indexes `subs_allowed[origin][dest]`
(`make_peptides.py:42-43`). **We** had built `matrix[ROW][COLUMN]` and used it as
`matrix[origin][dest]`, transposing all 20 asymmetric pairs:
- `F→M` (an oxidised-Met artifact the reference excludes) → we generated **15,004** candidates,
  our single largest "finding".
- `T→S` (the reference's dominant substitution, **422/697 = 61%** of its localized SAAVs) → we
  generated **zero**. We were structurally incapable of finding it.

Fixed; a guard now pins it.

### 2. `rename(index={'I/L': 'I'})` is a silent no-op (D-064) — **the reference's bug**
`make_peptides.py:31`:
```python
subs_allowed = pd.read_csv('subs_exclude.csv', index_col=0).rename(index={'I/L': 'I'}).to_dict()
```
`rename(index=)` renames **rows**; `I/L` is a **column**. Verified by executing that exact
line: `'I/L'` survives as an origin key and `'I'` never becomes one. Line 44's
`if origin not in i` is then always true for `'I/L'`, so **the reference generates zero
substitutions from any I or L position, in any run, ever.** Had it said `rename(columns=)`
it would have worked — he clearly *intended* the collapse. This is the same row/column
transposition that caused D-061.

Measured in his own GAPDH output: origins are `V, N, M, S, T, G, …` — **no I, no L, no I/L**.

We implement the intent: origin class `I` matches **both** Ile and Leu residues.
→ trial **39**, alaggcpar **56**, orly **61** I/L-origin substitutions the reference cannot report.

### 3. Spectrum-title namespace (D-047)
`localize.py:11` joins on **`dependent`** (the peptide), so a candidate can borrow another
spectrum's evidence for the same peptide. We join on **`spectrum_title`**, keeping every
candidate bound to the spectrum it was identified on.

### 4. Philosopher double-decoy (D-062)
`search_pipeline_script.sh:12` calls `philosopher database --custom` on an **already-decoyed**
FASTA, producing a multi-GB `*-decoys-*.fas` full of `rev_rev_` entries. We removed the call —
FragPipe runs it itself from the workflow. Verified our searches use the single-decoyed
`protein_decoy.fasta` with **zero** `rev_rev_` entries.

### 5. Other reference defects we fixed
`localize.py` mod-suffix handling, `.get()→None→continue` silent drops, `fill_null(0)`
admitting variants never rescored against their base (D-048), PepQuery `.fmi` index race
(D-059), stale-artifact detection (D-057/D-063).

---

## B. Deliberate divergences (ours differs on purpose)

### 1. Origin is known; only the destination is ambiguous (D-065)
Ile/Leu are isobaric (113.08406 Da), but the two ends are **not** symmetric:
- **origin** — the residue *before* the error, read from the base peptide → reference
  proteome → **genome codon** (I=ATT/ATC/ATA, L=CTN/TTA/TTG). **Known.** It is
  `base[mistranslated_pos]`, a definite `I` or `L`. Verified: `origin == base[pos]` with
  **0 mismatches** on every non-isobaric row across all four runs.
- **destination** — the *misincorporated* residue, seen only by mass, not on the genome.
  Genuinely **`I/L`**.

The reference prints `I` for the destination (its `aa_mapping` maps both `Xle` and `Leu` → `I`,
`analyze_outputs.py:10`), which silently *means* "I or L". We say `I/L` out loud. There is no
such thing as an `I/L` **origin**.

Both pipelines use `[IL] → J` normalisation for base/variant sequence matching
(`analyze_outputs.py:72`) — identical.

### 2. `A→I/L` excluded as trimethylation
Merging the `I`/`L` destination rows exposed the matrix's one internal conflict: `A→I`
excluded but `A→L` allowed — incoherent, since **Ala→Ile/Leu is +42.04695 Da, exactly
trimethylation**, which is *why* `A→I` is excluded. We take the exclusion, dropping 41,085
artifact candidates (0 results either way).

### 3. Engineering (no scientific effect)
LSF orchestration, `.done` resumption, provenance (`git_sha` + dirty-tree refusal, D-063),
stale-artifact detection, library-spectrum guard, 308 tests. The reference is a set of
hand-run scripts.

### 4. Visualization
We ported the lab's canonical heatmap and extended it: **64×19** codons (all 64 incl. stops,
vs the original 61) and a fixed **20×19** amino-acid grid — axes hard-coded and complete, so
absent residues are drawn as empty cells rather than dropped, making runs comparable
cell-for-cell. Plus protein-burden and fraction-merging.

**The lab's own axis is 19 with `I/L` merged** (`SubsToSixtyTwentyWithMask.py:42`):
```python
ALL_AA = ['A','Q','Y','W','N','S','R','G','M','H','C','V','K','F','T','E','D','I/L','P']
```
That figure cannot be drawn without the isobaric collapse — independent confirmation that
D-064/D-065 match what the analysis always assumed.

---

## C. Head-to-head on the same data (hoMS / GAPDH)

The only dataset where both pipelines ran: his
`tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/subs.ipc` vs ours.

⚠️ **Stage mismatch.** His GAPDH directory has `first.ipc` and `subs.ipc` but **no
`subs_localized.ipc`** — his *other* datasets do. **He never localized GAPDH.** His `subs.ipc`
is the pre-localization stage = our **Step 7**, not our Step 11. So "his 259 vs our 44" compares
his mid-pipeline to our final.

Stage-matched, after normalizing the spectrum IDs (his `file:scan:charge` vs our
`file_sub.scan.scan.charge`):

| | his `subs.ipc` | our Step 7 |
|---|---|---|
| rows | 259 | 191 |
| unique spectra | **233** | **167** |
| shared | **115** | **115** |
| unique to each | 118 | 52 |

**On the 115 shared spectra: 115/115 (100%) agree on origin→destination.** Position matches
exactly on 113, off-by-4 on 2. **Zero substitution disagreements.**

Of our 44 localized calls (38 spectra), **30 (79%)** are in his set; 8 are ours-only.

**Read:** *correctness is confirmed* — where both fire, we call the identical substitution
every time. *Sensitivity differs* — he finds ~40% more at Step 7. Most likely the
FragPipe/MSFragger version gap (23.1 vs 24.0), not a defect. This is the same cross-pipeline
confound that invalidated D-053.

---

## D. What is NOT established

- **Why he finds 233 vs our 167 at Step 7.** Unknown. Version/parameter differences are the
  leading hypothesis, untested.
- **Whether our extra localization filtering (191→44) is correctly strict** — his GAPDH never
  localized, so there is nothing to compare against.
- **D-053 (EVpar yield comparison) is RETRACTED** — it compared our FragPipe 24.0/MSFragger
  4.4.1 run against his 23.1/4.3 run. Cross-pipeline confound; the conclusion is void.
- Earlier quoted counts from his `pep_candidates.fa` are **retracted** — that file is generated
  per-run and is not in his repo, so the figures were unsourced. The `0 I→X` conclusion stands
  because it is derived from his *code*, which is stronger.

---

## Bottom line

| | |
|---|---|
| **Agreement where both fire** | **100%** (115/115 shared spectra, hoMS) |
| **Bugs found in the reference** | 4 real (I/L rename no-op, double-decoy, peptide-join, plus defects in `localize.py`) |
| **Bugs found in ours** | 1 catastrophic (transposed matrix, D-061) — since fixed and guarded |
| **Deliberate divergence** | I/L origin reported (his: structurally zero); `I/L` destination labelled honestly; `A→I/L` excluded |
| **Confound** | FragPipe 23.1 vs 24.0 — never compare yields across it |
