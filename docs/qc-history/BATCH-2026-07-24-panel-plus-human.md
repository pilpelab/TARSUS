# Batch rerun 2026-07-24: E. coli panel + human tRNA

Clean pass with the D-069 + D-070 fixes (commit `d3d43ff`), following
`docs/rerun_qc_20260723.sh` plus the human tRNA sub-samples. Job IDs in
`batch_2026-07-24_jobs.txt`. GAPDH (`homs_24814`) was done separately and
recapitulated.

## Launched (20 samples)

| group | samples | organism / FASTA | source |
|---|---|---|---|
| AlaGGC | alaggc, alaggcpar | E. coli (`data/protein.fasta`) | our data + control |
| coli tRNA panel | gluuuc, gluuucpar, ilexcau, ilexcaupar, leuuag, procgg, procggpar, proggg, progggpar | E. coli | `slavat/coli_trna/<sample>` |
| single-protein human | hemoglobin (EX1_24813), park7 (EX1_25033), prdx6 (EX1_24839) | human GRCh38 (`slavat/tehilapaper/fasta/protein.fasta`) | `hoMS/raw` |
| cell lines | cells_2A, cells_2B, cells_3A, cells_3B (EX1_25145) | human GRCh38 | `hoMS/cells/raw`, split by `_2A_`/`_2B_`/`_3A_`/`_3B_` tag |
| tissue atlas | tissue_brain_sds, tissue_brain_sol | human GRCh38 | `tissue_atlas/Simon_S1510/brain/{sds,sol}` |

All use the validated GAPDH-style workflow: full-proteome first pass, nocleavage
second pass, MSBooster on, unlabeled. Each maps 1:1 to a Slava `subs.ipc` for QC.

## Deliberately EXCLUDED (need a different workflow — not "the same clean pass")

| sample | Slava subs.ipc | why excluded |
|---|---|---|
| CA (EX_TP_26272 D1) | `hoMS/CA/fragpip` | 18O metabolic labeling + DDA_inc; turnover experiment, not the unlabeled substitution workflow |
| WD (EX_TP_26272 18o) | `hoMS/WD/fragpipe` | 18O labeling |
| fractionsWDCA (WD/WDlab/CA2) | `hoMS/fractionsWDCA/...` | 18O/D2O labeling; WD and WDlab share raws and differ only by search params (label-aware) |
| nachiatb (EX1_24426) | `hoMS/nachiatb/fragpipe2` | database is `pep_candidates`, a second-pass-only variant, not the full GRCh38 first pass |
| hoMS/coli (hf2, lumos) | `hoMS/coli/fragpipe/...` | E. coli under hoMS; different DB — belongs with a coli config, not this human batch |

These are legitimate parts of Slava's paper but use FragPipe workflows our
pipeline does not replicate (metabolic labeling, candidate-only search). Running
them through the unlabeled substitution workflow would not recapitulate his
result. They need explicit per-experiment config decisions.

## The wider universe (context for "recapitulate everything")

127 `subs.ipc` total across 11 experiment areas (agami 33, ubiquitinome 21,
RBC 17, hoMS 17, cancer 11, aging 11, oxdam 5, coli_trna 4, quasispecies 3,
codon_usage 3, tissue_atlas 2). Each non-hoMS/coli area is a different organism
and PRIDE dataset needing its own reference DB + CDS; cancer and quasispecies
have no raw files at all. That is a multi-organism reanalysis of the whole paper,
not a uniform pass — scope it per-area, not as a sweep.

## QC (pending, once runs finish)

Per sample, compare our `07_analyze/subs.ipc` to Slava's reference on:
row/unique-spectra count, 0-null scores, origin/destination/position agreement on
shared spectra, and Cys/Met representation (D-070 check).
