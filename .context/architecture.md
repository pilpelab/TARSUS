# TARSUS Pipeline — Architecture

## Data Flow

```
Raw MS files (.raw)
    | Step 1: convert_raw.sh (ThermoRawFileParser)
    v
mzML files
    | Step 2: make_index.sh (PepQuery index)
    |         +--- pepquery_index/
    |
    | Step 3a: search_pipeline_script.sh (FragPipe first pass)
    |         +--- psm.tsv, peptide.tsv, protein.tsv
    |         +--- *_sub.mzML (unidentified spectra)
    |
    | Step 3b: make_peptides.py (in-silico mutagenesis)
    |         +--- pep_candidates.fa
    |
    | Step 3c: search_pipeline_script.sh (FragPipe second pass, nocleavage)
    |         +--- second/psm.tsv
    |
    | Step 4: extract_psm.py
    |         +--- psm_input4pepquery.tsv
    |
    | Step 5: query_psm.sh (PepQuery parallel validation)
    |         +--- pepquery_result/**/psm_rank.txt, ptm_detail.txt, psm_rank.mgf
    |
    | Step 6: aggregate_query.sh (concatenate + PDV)
    |         +--- psmrankall.txt, ptmall.txt, mgfall.mgf
    |         +--- pdv_spectra/
    |
    | Step 7: analyze_outputs.py (filter confident SAVs)
    |         +--- subs.ipc
    |
    | Step 8: ref_validation_prep.py (fake MGF for rescoring)
    |         +--- mgfall_fakes.mgf
    |         +--- pepquery_input_base/
    |
    | Step 9: query_psm_base.sh (PepQuery rescoring)
    |         +--- pepquery_result_recheck_base/**/psm_rank.txt, ptm_detail.txt
    |
    | Step 10: aggregate_query_base.sh
    |         +--- psmrankall_base.txt, ptmall_base.txt, mgfall_base.mgf
    |
    | Step 11: localize.py (pyAscore localization)
    v
subs_localized.ipc  +  subs_localized.csv
```

## Component Dependency Graph

```
convert_raw.sh ----> mzML files ----> make_index.sh ----> pepquery_index/
                                            |
search_pipeline.sh ----> search_pipeline_script.sh
                          |-- generic.workflow (template)
                          |-- philosopher (decoy database)
                          |-- fragpipe (first pass)
                          |-- make_peptides.py (mutagenesis)
                          |       `-- subs_exclude.csv
                          |-- philosopher (decoy for variants)
                          `-- fragpipe (second pass, nocleavage)
                                 |
                                 v
                          extract_psm.py ----> psm_input4pepquery.tsv
                                 |
                                 v
                          query_psm.sh ----> pepquery result chunks
                                 |
                                 v
                          aggregate_query.sh ----> psmrankall.txt
                                                    ptmall.txt
                                                    mgfall.mgf
                              |                       |
                              v                       v
                        analyze_outputs.py    ref_validation_prep.py
                              |                       |
                              v                       v
                          subs.ipc              mgfall_fakes.mgf
                                                   pepquery_input_base/
                              |                       |
                              |                       v
                              |                query_psm_base.sh
                              |                       |
                              |                       v
                              |                aggregate_query_base.sh
                              |                       |
                              +----> localize.py <---+
                                       |
                                       v
                                subs_localized.ipc/.csv
```

## Tool Coupling Points

### Hardcoded Paths (must be externalized)

| Script | Hardcoded Path | Tool |
|--------|---------------|------|
| convert_raw.sh | /home/labs/pilpel/slavat/Thermo/ThermoRawFileParser.exe | ThermoRawFileParser |
| make_index.sh | /home/labs/pilpel/elizabev/pepquery-2.0.2/pepquery-2.0.2.jar | PepQuery |
| search_pipeline_script.sh | /home/labs/pilpel/elizabev/fragpipe-23.1/ | Philosopher |
| search_pipeline_script.sh | /home/labs/pilpel/slavat/fragpipe-23.1/ | FragPipe |
| search_pipeline_script.sh | /home/labs/pilpel/slavat/fragpipe-23.1/ | Philosopher (second pass) |
| query_psm.sh | /home/labs/pilpel/slavat/pepquery-2.0.2/pepquery-2.0.2.jar | PepQuery |
| query_psm_base.sh | /home/labs/pilpel/slavat/pepquery-2.0.2/pepquery-2.0.2.jar | PepQuery |
| aggregate_query.sh | /home/labs/pilpel/elizabev/PDV-2.1.2/PDV-2.1.2.jar | PDV |
| generic.workflow | /home/labs/pilpel/slavat/domains/fasta/... | Reference database |

### LSF Cluster Dependencies

| Script | Queue | Memory | CPUs |
|--------|-------|--------|------|
| convert_raw.sh | gsla-cpu | 7000MB | 1 |
| make_index.sh | gsla-cpu | 12000MB | 10 |
| search_pipeline.sh | gsla-cpu | 30000MB | 10 |
| query_psm.sh | short | 1500MB | 10 |
| query_psm_base.sh | short | 5000MB | 1 |

### Runtime Requirements

- **bash** (all shell scripts)
- **Python 3.11** with: polars, pandas, numpy, seaborn, matplotlib, pyteomics, pyascore
- **Java 21** (FragPipe, PepQuery, PDV)
- **Mono/.NET** (ThermoRawFileParser)
- **Linux x86_64** (Philosopher, Percolator binaries)

## Architecture Decisions

### Current (Reference)
- Bash orchestration with hardcoded paths
- LSF cluster for parallelism (bsub)
- Python scripts for analysis logic
- IPC format for intermediate data (Polars)
- No configuration file — paths embedded in scripts

### Target (TARSUS_BC)
- **LSF-native** — preserve cluster workflows, externalize parameters
- **Self-contained tools** — all external tools pinned in `tools/` via Makefile, checksum-verified
- **Configuration-driven** — environment variables or config file for all tool paths, DB paths, queues
- **Python orchestration** — replace bash glue with Python (subprocess for external tools)
- **Proper Python package** under src/tarsus/
- **Testing** — pytest for analysis logic, ruff/mypy for code quality
- **Logging** — structured logging for pipeline steps
- **Documentation** — setup guide for cross-lab adoption
- **Future: Docker image** — bundles tools + code for single-command deployment

### Runtime Requirements

- **Java 21** (bundled in `tools/jdk-21.0.11/`, Eclipse Temurin)
- **.NET 8 runtime** (bundled in `tools/dotnet-8.0.28/`, Microsoft)
- **Python 3.11** with polars, pandas, numpy, pyteomics, pyascore
- **Linux x86_64**
- **LSF cluster** for bsub job submission

No system-level installations needed beyond Python — `make setup` handles everything.

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


