# I/L ambiguity — what we did, and why

**Decision record:** D-064 · **Commit:** `3803c96` · **Date:** 2026-07-14

---

## The problem in one paragraph

Isoleucine and leucine have **identical monoisotopic mass** (113.08406 Da). A mass spectrometer cannot
tell them apart — not with better instruments, not with better software. It is a hard physical limit.
Every proteomics pipeline must therefore decide two things: **(1)** do we search for substitutions
*at* an I/L position, and **(2)** what letter do we print when we find one?

The PI asked for `I/L` to be preserved in the outputs. Working out how to do that "without fucking the
pipeline" turned out to be the entire problem, and it exposed a bug in the reference implementation.

---

## Finding 1 — the reference *intends* to collapse I/L, and its code silently fails to

`TARSUS_elizabev/make_peptides.py:31`:

```python
subs_allowed = pd.read_csv('subs_exclude.csv', index_col=0).rename(index={'I/L': 'I'}).to_dict()
```

The intent is unmistakable: **rename `I/L` to `I` at the very first line**, then run the pipeline on a
single letter. That is a perfectly good design.

**It does not work.** `rename(index=...)` renames **rows**. `I/L` is a **column**.

The matrix (`subs_exclude.csv`) is **COLUMN = origin, ROW = destination** (its own README says so, and
D-061 confirmed it the hard way). It has **19 origin columns** — including one merged `I/L` — and **20
destination rows**, with `I` and `L` listed separately. There is no row named `I/L`, so the rename
matches nothing and does nothing.

Verified by executing that exact line:

```
origin keys the loop actually iterates over:
  ['A','C','D','E','F','G','H','I/L','K','M','N','P','Q','R','S','T','V','W','Y']

  is 'I/L' still an origin key?  True      <- the rename did nothing
  is 'I'   an origin key?        False
```

Line 44 then reads `if origin not in i: pass`. Since `'I/L'` is a two-character string, `'I/L' not in
peptide` is **always true** — so the branch always skips. **The reference generates zero substitutions
from any I or L position, in any run, ever.** Had it said `rename(columns=...)`, it would have worked.

This is the *same* row/column transposition that caused D-061. It is an easy mistake to make and an
almost impossible one to notice, because it fails silently and produces a plausible-looking library.

### Why this matters

When asked, the author said the skip was **"a feature, not a bug"** — a deliberate choice to report only
substitutions whose origin residue is unambiguous.

**Line 31 does not support that.** You do not write a rename to undo a feature. The code says he meant
to collapse I/L into one class and search it; the rename simply missed its target.

**Consequence for us:** our `_norm_aa` mapping `I/L` → `I` was *his intent, correctly implemented*. We
were never diverging from his design — we diverge from his **typo**.

> An earlier version of our plan proposed **deleting** our 188 `subs.ipc` / 23 localized I-origin
> results in order to match his count of zero. That would have been **deleting real detections to
> reproduce a bug.** The PI rejected it, correctly, on exactly that ground: *"it's not like the I→X
> didn't happen — it's that we can't know if it's I or L."*

---

## Finding 2 — our own implementation was half-right, and incoherent

`_norm_aa` renamed the `I/L` origin *column* to `I`, so the origin class `I` matched **Ile residues
only**. Leucine positions were never searched at all.

Our own output proved it:

| | count |
|---|---|
| origin `I` (Ile) in `subs.ipc` | **188** |
| origin `L` (Leu) in `subs.ipc` | **0** |

Same mass. Opposite treatment. Nobody chose this; it fell out of matching a one-character origin key
against a literal residue letter.

---

## Finding 3 — the `/` character cannot enter the pipeline

This is why the naive fix (just print `I/L` everywhere) is dangerous.

D-026 already recorded FragPipe dying on it outright:
`WARNING: Trying to compute mass of non-residue: /`

Two further sites fail **silently** — no error, no warning, just missing rows:

| site | what `/` does there |
|---|---|
| `step07_analyze_outputs.py:327` | The final `origin`/`destination` are extracted from the FASTA header by `_(\w)(\d+)(\w)`. **`\w` is `[A-Za-z0-9_]` — it does not match `/`.** A header `_T5I/L` yields destination `"I"`, with the `L` quietly dropped. |
| `step11_localize.py:222` | `SUBSTITUTION_SHIFTS.get(origin, {}).get(dest)` returns `None` for `I/L` (`AA_MONO` has no such key), and the next line is `continue`. **Every I/L substitution would vanish from the results.** |

Both are the `.get() → None → continue` failure mode behind D-048, D-049 and D-057 — the recurring
pattern in this project: **a silent default in place of missing data.**

A relabel done carelessly would have looked like a harmless cosmetic change while deleting ~19 real
localized calls.

---

## What we did

> **Collapse Ile and Leu onto one letter at Step 3b, run the whole pipeline on that letter, and relabel
> it `I/L` at the very last write.**

This is the reference's own intent, implemented correctly, plus the honest label the PI asked for.

**1. Step 3b — collapse (`step03b_make_peptides.py`)**
- **Origin:** the class `I` matches **both** Ile and Leu residues (`_residue_class`). This is the fix
  for Finding 2 — Leu positions are now searched.
- **Destination:** the `I` and `L` rows merge into one letter, **excluded if either is excluded.**

  Exactly one of the 19 origins disagrees: **`A→I` is excluded but `A→L` is allowed.** That is
  incoherent — **Ala→Ile/Leu is +42.04695 Da, which is *exactly* trimethylation**, and that mass
  collision is precisely why `A→I` is excluded in the first place. Taking the exclusion also drops
  41,085 `A→L` trimethylation-artifact candidates (which yielded 0 results anyway) for free.
- The `I/L → I/L` diagonal becomes `I→I` and is skipped by the existing `origin == dest` check —
  correct, since I→L is a zero mass shift and undetectable *by definition*.

**2. Step 11 — relabel (`step11_localize.py`, `_label_isobaric_il`)**
`I` → `I/L`, as the **last statement before the write**, after the mass lookup. The `/` therefore never
enters a computation — which is why **`AA_MONO` needs no `I/L` entry at all.** That is the point of the
ordering, not an accident of it.

`subs.ipc` (Step 7) deliberately keeps single letters: it is an intermediate, Step 8 does not read those
columns, and Step 11 needs `I` for its lookup.

**3. Step 12** — `_AA_ORDER` carries `I/L`; neither bare letter can reach a plot any more.

**4. The guard** (`check_library_spectrum`, from D-062) now pins the contract:
- **no stray `L`** as origin or destination. This needs its own check — the matrix lookup **cannot**
  catch it, because after the collapse `matrix["L"]` does not exist, so `.get("L", {})` returns `{}`
  and a stray `L` would sail straight through.
- `A→I == 0` (trimethylation) · `I→V > 0` (zero the instant anyone reintroduces the reference's skip) ·
  plus D-061's `T→S > 0` and D-062's `F→M == 0`.

---

## Verification (measured, not predicted)

Rebuilt library — **7,315,846 candidates**, guard passed:

| check | result | |
|---|---|---|
| `L` as origin/destination | **0** | collapse holds |
| `A→I` (trimethylation) | **0** | merge rule excluded it |
| `F→M` | **0** | D-062 intact |
| `T→S` | **22,923** | D-061 intact — the dominant substitution |
| `I→V` | **68,921** | I/L origins are finally searched |

| | before | after |
|---|---|---|
| **I-origin candidates** | 478,996 (Ile only) | **1,240,782** (Ile + Leu) |
| `X→I` destinations | 298,946 + 337,917 duplicates | **314,242** (merged) |

The relabel was proven non-destructive on the **real** table, not a fixture:
`subs_localized.ipc` **349 → 349 rows**; origin `I`=23 → `I/L`=23; destination `I`=19 → `I/L`=19.

Suite: **278 tests pass**, mypy clean, ruff clean on `src/`.

A regression test now pins the ordering: it asserts `SUBSTITUTION_SHIFTS["T"]["I"]` **resolves** while
`SUBSTITUTION_SHIFTS["T"]["I/L"]` **does not**, and that `AA_MONO` stays free of `I/L`. If anyone moves
the relabel earlier, that test fails instead of the data silently disappearing.

> While writing it we found a **local `AA_MONO` dict inside `test_step11_localize.py` shadowing the
> import** from the module. It would have kept this very test green while the landmine re-armed —
> "a test that re-implements the logic tests nothing." Deleted.

---

## What this means for comparing numbers with the reference

**Our totals will exceed the reference's for the I/L-origin class, because its library contains none of
them.** This is correct, not a discrepancy, and it should be stated plainly rather than discovered later:

- The reference reports **0** substitutions originating from any I or L position — not by choice, but
  because `rename(index=)` renamed the wrong axis.
- We report them, labelled `I/L → X`, because **those substitutions happened.** The spectra are real,
  the PSMs cleared FDR, PepQuery and AScore. What we cannot do is *name* the origin residue — so we
  don't. We label it honestly and keep the evidence.

Everything outside the I/L class is unaffected and remains directly comparable.

---

## The transferable lesson

**An isobaric ambiguity is plumbing, not science.**

Collapse it to a single symbol at the boundary, compute on the symbol, and label it honestly on the way
out. **Never let a display label into a lookup key** — `I/L` is a fine thing to print and a catastrophic
thing to index with, and the difference between those two is one `.get()` returning `None`.
