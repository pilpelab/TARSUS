# Eval fixture: `evcoli`

Lineage-coherent slice of the reference TARSUS run at

    /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis

Built by `scripts/build_eval_fixtures.py`. Do not hand-edit; re-bless with that
script. Total input size: ~3.8 MB.

## What this is

A 100-spectrum slice, every spectrum drawn from the run's Slava
reference `subs.ipc` so the reference-agreement invariants are meaningful. Each
step-07/11 input is filtered to exactly this spectrum set:

| input | rows kept |
|---|---|
| `ptmall.txt` | 91 |
| `psmrankall.txt` | 101 |
| `psmrankall_base.txt` | 1511 |
| `pdv_export.txt` (from `pdv_spectra/PDVExportResult.txt`) | 101 |
| `second_psm.tsv` (from `second/psm.tsv`) | 100 |
| `first_psm.tsv` (from `psm.tsv`, kept by base) | 311 |
| `spectra.mgf` (from `mgfall.mgf`) | 100 blocks |

## Golden

- `golden/subs.ipc` - step07 output: **229 rows / 100 spectra**.
- `golden/subs_localized.ipc` / `.csv` - step11 output: **58 rows** at the 0.01 Da PyAscore default (62 at the former 0.05; D-073).

Produced by current (post-`7502692`) code. Regenerate on an intentional change
with `TARSUS_EVAL_UPDATE=1 uv run pytest tests/eval` (see `tests/eval/README.md`).

## Coverage (guards it exercises)

- Cys-origin and Met-origin substitutions - D-070 (`re.match` anchoring drop).
- I/L-ambiguous destination - the isobaric labelling path.
- multiple precursor charges.

## Reference agreement at build time

`slava_compare` vs the reference `subs.ipc`: 100/100
shared spectra substitution-identical, dpbp Pearson r = 1.0000.
