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
  │   Step 1: bsub ThermoRawFileParser × N, wait         │
  │   Step 2: bsub PepQuery index, wait                   │
  │   Step 3a: bsub FragPipe first pass, wait              │
  │   Step 3b: Python (inline — in-silico mutagenesis)    │
  │   Step 3c: bsub FragPipe second pass, wait             │
  │   Step 4:  Python (inline — extract PSMs)              │
  │   Step 5:  bsub PepQuery × chunks, wait                │
  │   Step 6:  Python (inline — concat + PDV via Xvfb)    │
  │   Step 7:  Python (inline — SAV filtering)             │
  │   Step 8:  Python (inline — ref validation prep)       │
  │   Step 9:  bsub PepQuery base × chunks, wait           │
  │   Step 10: Python (inline — concat base)               │
  │   Step 11: Python (inline — PyAscore localization)     │
  └──────────────────────────────────────────────────────┘
```

## Data Flow

```
Raw MS files (.raw)
    | Step 1: step01_convert (ThermoRawFileParser via LSF)
    v
01_mzml/ (.mzML files)
    | Step 2: step02_make_index (PepQuery index via LSF)
    v
02_index/ (pepquery_index/)
    |
    | Step 3a: step03a_first_pass (FragPipe via LSF)
    |         +--- psm.tsv, peptide.tsv, protein.tsv
    |         +--- *_sub.mzML (unidentified spectra)
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
step01_convert ──> 01_mzml/ ──> step02_make_index ──> 02_index/
                              │
                              └──> step03a_first_pass ──> 03a_first_pass/
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
| 3c | FragPipe second pass | gsla-cpu | 30000 MB | 10 |
| 5 | PepQuery validation | short / gsla-cpu | 1500 MB | 1 |
| 9 | PepQuery base rescoring | short / gsla-cpu | 5000 MB | 1 |
| master | orchestration | gsla-cpu | 4000 MB | 1 |

## Output Directory Convention

```
--output-dir/
├── 01_mzml/               Step 1: .mzML files
├── 02_index/              Step 2: PepQuery index
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

## Runtime Requirements

- **Java 21** (bundled in `tools/jdk-21.0.11/`, Eclipse Temurin)
- **.NET 8 runtime** (bundled in `tools/dotnet-8.0.28/`, Microsoft)
- **Python 3.11** with polars, numpy, pyteomics, pyascore
- **Linux x86_64** with shared filesystem (LSF compute nodes access same paths)
- **LSF cluster** with `gsla-cpu` queue for bsub job submission
- **Xvfb** available via EasyBuild module (for PDV headless rendering)
- **No sudo** — all dependencies are user-level

## Directory Structure

```
TARSUS_BC/
├── src/tarsus/            # Python package (tracked)
│   ├── assets/            # Bundled ref. assets (generic.workflow, subs_exclude.csv)
│   ├── steps/             # 11 pipeline step modules
│   ├── cli.py             # click CLI (convert, run)
│   ├── env.py             # tool env resolver + XvfbDisplay
│   └── lsf.py             # bsub submission helpers
├── tests/                 # pytest tests (134 unit tests)
├── data/                  # gitignored workspace (test fixtures tracked)
├── tools/                 # External tool Makefile + runtimes (gitignored)
├── .context/              # Architecture and reference docs
├── .memory/               # Project memory, decisions, progress
└── TARSUS_elizabev/       # READ-ONLY reference (do not modify)
```

## Directory Structure

```
TARSUS_BC/
|-- src/tarsus/              # Python package (tracked)
|-- tests/                   # pytest tests (tracked)
|-- scripts/                 # utility scripts (tracked)
|-- docs/                    # user documentation (tracked)
|-- tools/                   # External tool Makefile + README (tracked)
|   |-- Makefile             #   downloads, verifies, installs tools
|   |-- README.md            #   version table
|   |-- pepquery-2.0.2.jar   #   (downloaded, gitignored)
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


