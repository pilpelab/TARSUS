# Eval fixture: `gapdh`

Lineage-coherent slice of the reference TARSUS run at

    /home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline

Built by `scripts/build_eval_fixtures.py`. Do not hand-edit; re-bless with that
script. Total input size: ~0.7 MB.

## What this is

A 100-spectrum slice, every spectrum drawn from the run's Slava
reference `subs.ipc` so the reference-agreement invariants are meaningful. Each
step-07/11 input is filtered to exactly this spectrum set:

| input | rows kept |
|---|---|
| `ptmall.txt` | 85 |
| `psmrankall.txt` | 108 |
| `psmrankall_base.txt` | 562 |
| `pdv_export.txt` (from `pdv_spectra/PDVExportResult.txt`) | 108 |
| `second_psm.tsv` (from `second/psm.tsv`) | 100 |
| `first_psm.tsv` (from `psm.tsv`, kept by base) | 40 |
| `spectra.mgf` (from `mgfall.mgf`) | 100 blocks |

## Golden

- `golden/subs.ipc` - step07 output: **113 rows / 100 spectra**.
- `golden/subs_localized.ipc` / `.csv` - step11 output: **28 rows**.

Produced by current (post-`7502692`) code. Regenerate on an intentional change
with `TARSUS_EVAL_UPDATE=1 uv run pytest tests/eval` (see `tests/eval/README.md`).

## Coverage (guards it exercises)

- Cys-origin and Met-origin substitutions - D-070 (`re.match` anchoring drop).
- I/L-ambiguous destination - the isobaric labelling path.
- multiple precursor charges.

## Injected reverse-decoy row

`inputs/first_psm.tsv` carries **one synthetic `rev_`-prefixed row**, appended by the builder. Neither reference run produces a decoy leak naturally (their first-pass decoys never match a variant base in the join), so without this the `7502692` guard could never fire. The row duplicates a real first-pass PSM that joins into the golden, at an identical `first Intensity`, with its `Protein` renamed `rev_...`. Current code drops it, so `golden/subs.ipc` is unchanged; reverting the step07 decoy drop resurrects it and breaks both the `rev_`-count invariant and the snapshot.

## Reference agreement at build time

`slava_compare` vs the reference `subs.ipc`: 100/100
shared spectra substitution-identical, dpbp Pearson r = 1.0000.
