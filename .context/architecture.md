# TARSUS Pipeline — Architecture

## Execution Model

All pipeline steps execute entirely on LSF. The login/head node is only used to submit a single master job:

```
Login node:
  tarsus run --fasta protein.fasta --input *.raw --output-dir output/
    └─ generates master.py + bsub → Job <N>

LSF compute node (master job):
  ┌──────────────────────────────────────────────────────┐
  │ master.py:                                           │
  │   Step 1:  bsub ThermoRawFileParser × N, wait        │
  │   Step 3a: bsub FragPipe first pass, wait (decoy)    │
  │   Step 2:  bsub PepQuery index, wait (from _sub.mzML)│
  │   Step 3b: Python (inline — in-silico mutagenesis)   │
  │   Step 3c: bsub FragPipe second pass, wait (decoy)   │
  │   Step 4:  Python (inline — extract PSMs)            │
  │   Step 5:  bsub PepQuery × chunks, wait              │
  │   Step 6:  Python (inline — concat + PDV via Xvfb)   │
  │   Step 7:  Python (inline — SAV filtering)           │
  │   Step 8:  Python (inline — ref validation prep)     │
  │   Step 9:  bsub PepQuery base × chunks, wait         │
  │   Step 10: Python (inline — concat base)             │
  │   Step 11: Python (inline — PyAscore localization)   │
  └──────────────────────────────────────────────────────┘
```

## Data Flow

```
Raw MS files (.raw)
    | Step 1: step01_convert (ThermoRawFileParser via LSF)
    v
01_mzml/ (.mzML files)
    |
    +---> Step 2: step02_make_index (PepQuery index via LSF)
    |             ← indexes the ORIGINAL mzML; titles are file:scan:charge (D-047)
    |             v
    |         02_index/ (pepquery_index/)
    |
    | Step 3a: step03a_first_pass (FragPipe via LSF)   ← parallel with Step 2
    |         +--- psm.tsv, peptide.tsv, protein.tsv
    |         +--- *_sub.mzML (unidentified spectra; original scan numbers preserved)
    v
03a_first_pass/
    | Step 3b: make_peptide_candidates (in-silico mutagenesis, inline)
    |         +--- pep_candidates.fa
    v
03b_candidates/
    | Step 3c: step03c_second_pass (FragPipe nocleavage via LSF)
    |         +--- second/psm.tsv
    v
03c_second_pass/
    | Step 4: extract_psm (inline)
    |         +--- psm_input4pepquery.tsv
    v
04_psm_input/
    | Step 5: step05_query_psm (PepQuery parallel validation via LSF)
    |         +--- pepquery_result/**/psm_rank.txt, ptm_detail.txt, psm_rank.mgf
    v
05_pepquery/
    | Step 6: step06_aggregate_query (concatenate + PDV via Xvfb, inline)
    |         +--- psmrankall.txt, ptmall.txt, mgfall.mgf
    |         +--- pdv_spectra/ (PDFs + PDVExportResult.txt)
    v
06_aggregated/
    | Step 7: analyze_outputs (filter confident SAAVs, inline)
    |         +--- subs.ipc
    v
07_analyze/
    | Step 8: prepare_base_rescoring (fake MGF for rescoring, inline)
    |         +--- mgfall_fakes.mgf
    |         +--- pepquery_input_base/
    v
08_base_input/
    | Step 9: step09_query_psm_base (PepQuery rescoring via LSF)
    |         +--- pepquery_result_recheck_base/**/psm_rank.txt, ptm_detail.txt
    v
09_pepquery_base/
    | Step 10: step10_aggregate_query_base (concatenate base, inline)
    |         +--- psmrankall_base.txt, ptmall_base.txt, mgfall_base.mgf
    v
10_aggregated_base/
    | Step 11: localize (PyAscore localization, inline)
    v
11_localized/subs_localized.ipc  +  subs_localized.csv
```

## Component Dependency Graph

```
step01_convert ──> 01_mzml/ ──┬─> step02_make_index (indexes the ORIGINAL mzML)
                              │        │
                              │   02_index/
                              │
                              └─> step03a_first_pass ──> 03a_first_pass/
                                   │                          │
                                   │                    make_peptide_candidates
                                   │                          │
                                   │                     pep_candidates.fa
                                   │                          │
                                   └─────────────────────> step03c_second_pass
                                                                  │
                                                             extract_psm
                                                                  │
                                                             step05_query_psm
                                                                  │
                                                             step06_aggregate_query
                                                              │           │
                                                              │           v
                                                              │    pdv_spectra/PDVExportResult.txt
                                                              v
                                                         analyze_outputs ──> subs.ipc
                                                              │           │
                                                              │           v
                                                              │    prepare_base_rescoring
                                                              │           │
                                                              │           v
                                                              │     mgfall_fakes.mgf
                                                              │           │
                                                              │           v
                                                              │     step09_query_psm_base
                                                              │           │
                                                              │           v
                                                              │     step10_aggregate_query_base
                                                              │           │
                                                              └──> localize <──┘
                                                                       │
                                                                       v
                                                                subs_localized.ipc/.csv
```

## CLI Usage

```
tarsus run --fasta <path> --input <raw...> --output-dir <path>
```

Three required flags. Assets bundled in package. Output directory auto-structured.

```bash
tarsus run --fasta data/protein.fasta \
           -i data/*.raw \
           -o output/run-001/
# Submits master job → monitor with: bjobs <id>
```

## LSF Resource Allocation

| Step | Tool | Queue | Memory | CPUs |
|------|------|-------|--------|------|
| 1 | ThermoRawFileParser | gsla-cpu | 7000 MB | 1 |
| 2 | PepQuery index | gsla-cpu | 12000 MB | 10 |
| 3a | FragPipe first pass | gsla-cpu | 30000 MB | 10 |
| 3b | in-silico mutagenesis | inline (master) | 4000 MB | 1 |
| 3c | FragPipe second pass | gsla-cpu | 30000 MB | 10 |
| 5 | PepQuery validation | gsla-cpu | 1500 MB | 1 |
| 9 | PepQuery base rescoring | gsla-cpu | 5000 MB | 1 |
| master | orchestration | gsla-cpu | 4000 MB | 1 |

Note: Steps 3a and 3c generate inline target-decoy FASTA (`protein_decoy.fasta`).
Step 3c has MSBooster fully disabled (`run-msbooster=false`, `predict-rt=false`, `predict-spectra=false`).

## Output Directory Convention

```
--output-dir/
├── 01_mzml/               Step 1: .mzML files
├── 02_index/              Step 2: PepQuery index (from _sub.mzML, runs after Step 3a)
├── 03a_first_pass/        Step 3a: FragPipe first pass
├── 03b_candidates/        Step 3b: pep_candidates.fa
├── 03c_second_pass/       Step 3c: FragPipe second pass
├── 04_psm_input/          Step 4: PSM input for PepQuery
├── 05_pepquery/           Step 5: PepQuery per-chunk results
├── 06_aggregated/         Step 6: psmrankall.txt + PDV spectra
├── 07_analyze/            Step 7: subs.ipc
├── 08_base_input/         Step 8: fake MGF + rescoring inputs
├── 09_pepquery_base/      Step 9: PepQuery base rescoring
├── 10_aggregated_base/    Step 10: aggregated base results
├── 11_localized/          Step 11: subs_localized.ipc + .csv
├── master.py              Generated orchestration script
└── master.log             LSF log with step-by-step progress
```

## Known Limitations

### I/L Ambiguity
Mass spectrometry cannot distinguish isoleucine (I) from leucine (L) — they have identical monoisotopic mass (113.08406 Da). The pipeline uses "I" as the canonical representation in peptide sequences. The FASTA header retains "I/L" notation to indicate the positional ambiguity, but the actual sequence never contains "/".

### RESOLVED (2026-07-09): The Spectrum-Title Contract — do not break it again
The pipeline runs end-to-end. This section records the invariant that took a week to find, because
breaking it fails *silently* rather than loudly.

**The invariant.** PepQuery names every indexed spectrum after the file it indexed. Step 2 indexes
the **original** mzML, so index/PDV titles are `file:scan:charge`. FragPipe writes
`file_sub.scan.scan.charge` in its `Spectrum` column. Steps 4, 7 and 8 must therefore strip `_sub`
and address spectra as `file:scan:charge`. `_sub.mzML` preserves the original scan numbers (verified
on 5 scans: identical precursor m/z, charge, msLevel), so the mapping is exact.

**How it broke.** Commit `e143a46` moved Step 2 to index `*_sub.mzML` — a compute optimization that
silently shifted the whole title namespace. Everything after it was a downstream artifact:
- D-032 misdiagnosed the resulting mismatch as a FragPipe 24.0 / mzML scan-number incompatibility.
  **That claim was tested and is false** (D-045, Finding 1).
- That false diagnosis motivated `68957c2`, dropping Step 4 to peptide-only input — the actual
  lineage break (D-044) that zeroed Step 7.
- D-045's `NullPointerException` and D-046's ~900 Da precursor-mass disagreement were **self-inflicted**
  by the `-varMod 2,33` added to compensate. The reference passes no `-varMod` and hits neither.

**Ground truth.** The colleagues' completed run at
`/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` uses *exact targeted* PepQuery validation on
the same Orbitrap Astral DDA instrument family and yields a 3,922-row `subs.ipc`. Its index titles
carry no `_sub` (`TITLE=...-EVpar-LS-3:121018:2`).

**Guardrails now in place.** Step 7 raises on a 0-row `subs.ipc`; Step 8 raises when 0 spectrum
titles match the MGF; Step 10 raises on a header-only aggregate. Before these, each failure stamped
`.done` over empty output and surfaced misleadingly several steps later.

Option C (proximity acceptance) is **cancelled** — its spec and plan under `docs/superpowers/` are
retained for history only and must not be implemented. See D-047 through D-050.

### PepQuery Index Must Cover the Original mzML
Step 2 indexes the **original** `01_mzml/*.mzML`, not FragPipe's `*_sub.mzML` remainder. Indexing the
remainder looks like a free compute saving — it is roughly half the spectra — but PepQuery titles each
spectrum after the file it indexed, so a `_sub` index puts every title in a namespace that Steps 4, 7
and 8 do not address. Step 7 then joins nothing and silently emits 0 rows.

Step 2 therefore depends only on Step 1 and runs in parallel with Step 3a.
**Do not "optimize" this back.** See D-047.

## Runtime Requirements

- **Java 21** (bundled in `tools/jdk-21.0.11/`, Eclipse Temurin)
- **.NET 8 runtime** (bundled in `tools/dotnet-8.0.28/`, Microsoft)
- **Python 3.11** with polars, numpy, pyteomics, pyascore
- **IonQuant 1.11.20** (bundled in `tools/IonQuant-1.11.20.jar`; note: not bundled in FragPipe Linux ZIP)
- **Linux x86_64** with shared filesystem (LSF compute nodes access same paths)
- **LSF cluster** — all steps use `gsla-cpu` queue by default
- **Xvfb** available via EasyBuild module (for PDV headless rendering)
- **No sudo** — all dependencies are user-level

## Directory Structure

```
TARSUS_BC/
|-- src/tarsus/              # Python package (11 pipeline steps, CLI, env, LSF)
|   |-- assets/              #   bundled ref. assets (generic.workflow, subs_exclude.csv)
|   |-- steps/               #   step01_convert through step11_localize
|-- tests/                   # pytest tests (142 unit + 9 validation)
|-- scripts/                 # utility scripts (tracked)
|-- .planning/               # planning documents (tracked)
|-- tools/                   # External tool Makefile + README (tracked)
|   |-- Makefile             #   downloads, verifies, installs tools
|   |-- README.md            #   version table
|   |-- pepquery-2.0.2.jar   #   (downloaded, gitignored)
|   |-- IonQuant-1.11.20.jar #   (downloaded, gitignored)
|   |-- fragpipe-24.0/       #   (downloaded, gitignored)
|   |-- PDV-2.2.3/           #   (downloaded, gitignored)
|   `-- thermorawfileparser-2.0.0-dev/  # (downloaded, gitignored)
|-- data/                    # gitignored workspace (except README.md)
|-- .context/                # reference documentation (tracked)
|-- .memory/                 # project memory (tracked)
|-- .agents/                 # agent rules (tracked)
|-- TARSUS_elizabev/         # READ-ONLY reference (do not modify)
|-- Makefile                 # top-level: setup, test, clean (tracked)
|-- pyproject.toml           # Python project config (tracked)
`-- README.md                # project overview (tracked)
```

Outputs are written to a user-specified `--output-dir` (never inside the repo).


