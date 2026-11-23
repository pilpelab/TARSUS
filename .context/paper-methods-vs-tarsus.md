# Paper methods vs our TARSUS implementation

Read before changing any step to "match the paper", and when a comparison against Slava's outputs disagrees. Each row traces one setting across five sources, because they do not agree with each other. Claims and definitions: `paper-digest.md`.

| Code | Source | Where |
|---|---|---|
| P | Paper prose: bioRxiv v2 Methods, SI Note 1, Peer Review File | `paper-digest.md` |
| G | Public code, github.com/treko90/tarsus, last commit 2026-01-16 (e8cd460) | 15 files, same names as `TARSUS_elizabev/` |
| E | Colleagues' reference copy we replicated | `TARSUS_elizabev/` (read-only) |
| R | Reference completed runs (artifacts, ground truth) | Slava GAPDH `slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/`; EVpar `elizabev/tRNA/EVpar/tarsus_analysis/` |
| O | Ours | `src/tarsus/` |

G vs E file diff: identical `analyze_outputs.py`, `extract_psm.py`, `generic.workflow`, `make_peptides.py`, `make_index.sh`, `query_psm.sh`, `ref_validation_prep.py`, `subs_exclude.csv`, `aggregate_query_base.sh`. Differences are in `localize.py`, `search_pipeline.sh`, `aggregate_query.sh`, `query_psm_base.sh` (rows below). E additionally has `convert_raw.sh` and `search_pipeline_script.sh` (G inlines the latter into `search_pipeline.sh`).

## Deviations that change results

| # | Setting | P | G | E | R | O | Status |
|---|---|---|---|---|---|---|---|
| 1 | pyAscore fragment tolerance (Step 11) | 0.01 Da Orbitrap, 0.6 Da ion trap | `localize_shift(..., 0.01)` | 0.05 | not checked | 0.01 default since D-073 (`DEFAULT_LOCALIZE_TOL_DA`), override `--localize-tol`; was 0.05 | RESOLVED 2026-11-05. Effect on eval slices: gapdh 28 -> 19 localized rows, evcoli 62 -> 58. Caveat: 0.01 Da is tighter than the 20 ppm search fragment tolerance above m/z 500. ST14 check 2026-11-22 (our Step 11 on Slava's own Step 7-10 files): PARK7 27/27 with 0 extra at 0.01 (exact); GAPDH 27/38 at 0.01, closest at 0.05 (35/38, 3 extra), so the published GAPDH list was not made at 0.01 and the rest of its gap is unexplained |
| 8 | PepQuery base rescoring fragment tolerance (Step 9 `-itol`) | not checked against the paper text | `query_psm_base.sh`: 0.01 | 0.01 | **0.05**: our Step 9 with `-itol 0.05` reproduces Slava's `psmrankall_base.txt` to full precision (PARK7 117/117, GAPDH 167/167); with 0.01 only 78 of 116 PARK7 scores match | 0.05 default (`DEFAULT_BASE_RESCORE_TOL_DA`), override with `tarsus run --base-rescore-tol`; hardcoded 0.01 until 2026-11-23 | RESOLVED 2026-11-23 (D-076): match Slava's production, keep it a parameter. Third place the production runs differ from the published scripts (with row 1 GAPDH and row 4). With base at 0.05, our Steps 8-11 on Slava's PARK7 Step 7 give ST14 27/27, 0 extra |
| 9 | Step 7 two-fragment filter: which y ions count | not stated | `analyze_outputs.py:106`: `range(len-pos+2, len+1)`, against its own docstring (`len-pos`) | same as G | same bug (ST14 was built with it) | `range(n - position, n + 1)` since D-078; `+2` until 2026-11-23 | FIXED 2026-11-23 (D-078, found by Liz; Slava: a bug). Deliberate divergence from Slava's output: on the D-073 runs Step 7 keeps 970 spectra instead of 893 (+9%), none lost, ST14 at Step 7 unchanged |
| 2 | Localization scope | strict Ascore only for substitutions without RNA-seq support | applied to all rows | applied to all rows | n/a | applied to all rows; no RNA-seq input exists | O is stricter than the paper for genetic variants; cannot be matched without RNA-seq |
| 3 | MSBooster models, first pass | DIA-NN RT + AlphaPept MS2 generic | `find-best-rt-model=true`, `find-best-spectra-model=true` (Koina, needs internet) | same as G | GAPDH: `find-best=true`; FragPipe-generated second pass then ran `AlphaPept_rt_generic` + `AlphaPept_ms2_generic`. EVpar: `find-best=false`, DIA-NN | `find-best=true` default since D-073 (`--msbooster-models best`); `dia-nn` mode pins local models offline; was `find-best=false` + DIA-NN since 987edbc | RESOLVED 2026-11-05 for new runs. Koina verified reachable from a gsla-cpu node. Earlier outputs: `SpectralSim`/`RTScore` differ from Slava's human runs because the model differed. Untested whether this changes which PSMs pass Percolator |
| 4 | I/L as substitution origin | ST1 has origin I (519) and L (642); destination only I | `rename(index={'I/L':'I'})` is a no-op, so no I or L origin is ever generated | same as G | GAPDH library (`hoMS/GAPDH/pep_candidates.fa`, 2025-05-07, 23,280 candidates, the one searched in Sept): zero I/L origins, so the bug was live in that run | intent implemented (D-064): I and L are one origin class, emitted as `I` | Production code that made the paper's tables differed from G. O matches the paper's data, not G |
| 5 | Excluded pairs in `subs_exclude.csv` (column = origin, row = destination) | ST1 contains three pairs the CSV excludes: E>Q 71 rows, D>N 98, F>M 12; F>M is synthetic-peptide validated (ST18 KPLIIFTPK > KPLIIMTPK) | CSV excludes them | same CSV | GAPDH library excludes exactly {A>S, D>N, D>S, E>D, E>P, E>Q, E>S, E>T, Q>E, Q>N, Y>F}, mostly the transposed reading, and contains F>M, F>Y, A>I/L, S>T, N>D | follows the CSV (D-061) and fails loudly if they appear | O cannot find E>Q, D>N, F>M. The other 11 excluded pairs are 0 in ST1, confirming the column=origin reading. Slava ran different library versions for different datasets (GAPDH: I/L bug live, transposed-like set; tissues: I/L fixed). D-061's "F>M is excluded by the reference" is true of the CSV, not of his runs. Effect on our GAPDH QC Venn: 0 of 39 Slava-only events are in classes our library blocks; 18 of 40 Barc-only events are in classes his library could not produce (mostly I/L origins). Our library is the self-consistent one; this is a comparability note, not a bug |
| 6 | A>I vs A>L exclusion (CSV has only A>I) | ST6 A>I/L = 0 | A>L allowed, A>I excluded | same | n/a | exclusion wins: both excluded | O matches the paper's data |
| 7 | PepQuery index input | v2 Methods: "spectral index from first-search unidentified spectra" | `make_index.sh` on whatever mzML dir is passed | same | EVpar index titles carry no `_sub` (original mzML) | original mzML (D-047) | Paper prose conflicts with the reference artifacts. Keep D-047; the `_sub` index broke the title contract for a month |

## Settings that agree

| Setting | Value (P/G/E/O agree unless noted) |
|---|---|
| First pass (`generic.workflow`, identical in G, E, O except row 3) | `stricttrypsin`, 2 missed cleavages, length 7-50, precursor +-20 ppm, fragment 20 ppm, `isotope_error=0/1/2/3`, CAM-Cys fixed, Met-ox variable, `calibrate_mass=2`, MBR off, Percolator `min-prob 0.5`, `phi-report --sequential --picked --prot 0.01`, decoy tag `rev_` |
| Second-pass patches | `nocleavage` (cut and nocut `@`), `clip_nTerm_M=false`, `remove_precursor_peak=0`, IonQuant `minisotopes=1`, `minscans=1`, `find-best-rt-model=false`; O patches every key G's sed chain patches (`step03c_second_pass.py`) |
| Mutagenesis | every position of every first-pass peptide with `Intensity > 0`, skip variants already in the reference set, header `>REF_{origin}{pos0}{dest}` |
| PepQuery validation (Step 5) | `-ti 0,1,2,3 -maxLength 50 -tol 20 -itol 0.05 -hc -aa -m 1 -e 2 -c 2`, 10-PSM chunks; ties discarded; P adds `-itol 0.6` for ion-trap data |
| Step 7 filters | PepQuery confident, SAV-only PSMs, unique top score, >=2 fragments covering the site, no N-terminal (position 0) subs, max intensity per (peptide, charge), equal ref/variant charges |
| Non-quantified variants | P excludes substituted PSMs without MS1 intensity; G/E/O drop `Intensity <= 0` at Step 4 |
| Labile-PTM filter (Steps 8-10) | MS2-only rescoring against the unmodified reference via a fake-PEPMASS MGF; keep `delta_score > 0`; base flags `-fast -fixMod 0 -varMod 1,2 -maxVar 4 -s 2 -indexType 2 -itol 0.01` (G, E; Slava's production runs, and O since D-076, use `-itol 0.05`, row 8) |

## Paper steps not implemented in G, E or O

- RNA-seq classification (genetic vs non-genetic, binomial test, read thresholds).
- `ambiguous` flag for C>A, C>S, H>D, M>D, W>D.
- Filtered (quantification) set; reconstructed rule in `paper-supplementary-tables.md`.
- Codon / mutational-distance annotation from Ensembl CDS (O has `src/tarsus/codons.py` for codon mapping with `--cds`).
- Immunoglobulin flag, gnomAD, AlphaMissense, functional-site joins.

## Reference-code bugs and quirks (G and/or E)

- `make_peptides.py`: I/L rename no-op (row 4).
- `localize.py` (G): `mz_diff` references undefined `AA_MONO` (lowercase `aa_mono` exists); harmless because `mz_diff` is unused. E fixed it.
- `localize.py` (G): renames `Protein_right` to `ensembl` (keeps text before the first `.`) and writes only `.ipc`; E keeps `Protein_right` and also writes `.csv`.
- `aggregate_query.sh` (G): writes outputs to `${parent_directory}../` and runs PDV `-ft report`; E writes beside the chunks and uses `-ft pdf`.
- `query_psm_base.sh` (G): runs Java inline; E wraps each chunk in `bsub -q short`.
- `analyze_outputs.py` (G = E): no decoy filter after the first/second join; `rev_` rows leak when a decoy first-pass PSM collides on (base, Charge). O drops them (`7502692`, lessons 2026-07-27).
- Public README says FragPipe 23.1 and PDV 2.2.0; the public script hardcodes `fragpipe-22.1-build07` and PDV 2.1.2; Reporting Summary says FragPipe 23.1, PDV 2.1.2, pyAscore 1.0.1, Python 3.11.5. O pins FragPipe 24.0, PDV 2.2.3.

## Stale statements elsewhere in this repo

- `.context/reference-pipeline.md` section "Configuration: subs_exclude.csv" says rows = origin and lists exclusions as row>column (Y>F, Q>D, ...). That is the transposed reading D-061 fixed; the code-correct pairs are F>Y, E>Q, N>Q, A>I, F>M, S>T, D>N, N>D, S>D, D>E, P>E, Q>E, S>E, T>E. Its citation is still the 2025 bioRxiv preprint.
- `.memory/decisions.md` D-069 and `.memory/progress.md` 2026-07-24 describe our MSBooster block as matching the reference; true only for EVpar. Superseded for new runs by D-073 (row 3).
