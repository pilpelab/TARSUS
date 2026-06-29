# Progress Log

## Phase 1: Pipeline Digestion and Documentation (completed)

### Completed
- Read and analyzed all 11 pipeline steps from `TARSUS_elizabev/` reference
- Documented reference pipeline in `.context/reference-pipeline.md`
- Documented architecture and data flow in `.context/architecture.md`
- Established project-specific agent rules in `.agents/project.md`
- Recorded initial architectural decisions (D-001 through D-006) in `.memory/decisions.md`
- Updated README with actual project description
- Verified all files are internally consistent
- Test data added to `data/` (protein.fasta, two .raw files — Orbitrap Astral DDA, LS/HS fractions)
- `.gitignore` updated: `data/*` (except README), `output/**`, build artifacts
- `data/README.md` created documenting the test fixtures
- Root-level stubs (`make_index.sh`, `mzML`) removed
- Decisions D-007 through D-010 recorded (no embedded ref, user-driven entry, git policy, organism flag deferred)
- D-004 revised: self-contained tools via Makefile (supersedes cluster-mounted approach)
- `tools/` directory created with Makefile and README — pinned versions for FragPipe 24.0, PepQuery 2.0.2, PDV 2.2.3, ThermoRawFileParser 2.0.0-dev

## Phase 2: Self-Contained Tool Environment (completed)

### Completed
- MSConvert ruled out (cannot read Thermo .raw natively on Linux); ThermoRawFileParser v2.0.0-dev adopted instead
- `.gitignore` updated for tools/ (Makefile+README tracked, binaries ignored)
- D-011: JDK 21 (jdk-21.0.11+10) and .NET 8 runtime (8.0.28) bundled in `tools/`
- `src/tarsus/env.py` created — ToolEnvironment class resolves paths and sets up env
- `make test-tools` smoke tests pass for all 6 tools (JDK, .NET, FragPipe, PepQuery, PDV, ThermoRawFileParser)
- PepQuery directory structure fixed (JAR + lib/ for manifest Class-Path)
- ThermoRawFileParser diagnosed — requires `DOTNET_GCHeapHardLimit` + `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT` on this system
- PDV smoke test data created in `data/test-pdv/` (git-tracked via `.gitignore` exception)
- `src/tarsus/` package scaffolded with cli.py, config.py, lsf.py, steps/
- `tarsus convert` command — wraps ThermoRawFileParser with LSF submission
- Validation framework: conftest.py, golden-file capture, test_step01_convert.py
- Decisions D-012 through D-015 recorded (LSF-only, golden files, click CLI, trial data reference)
- Added `click`, `pyyaml` dependencies; configured build system and console_scripts entry point

### Current State
All external tools downloaded, verified, and smoke-tested. All 11 pipeline steps ported as
Python modules with 134 unit tests passing. PDV 2.1.2 bundled (matches reference), works via
cluster Xvfb module. LSF verified working (bsub, gsla-cpu queue). Reference assets
(generic.workflow, subs_exclude.csv) bundled in `src/tarsus/assets/`. `tarsus run` command
wired — generates master orchestration script and submits as single LSF job. The pipeline is
ready for end-to-end validation against trial data.

## Phase 3: CLI Wiring and Orchestration (completed)

### Completed
- D-016: LSF verified working (2025-06-29) — bsub functional, gsla-cpu queue Open:Active
- D-017: Master-job architecture — single LSF job orchestrates all 11 steps on a compute node
- D-018: Bundled assets — generic.workflow and subs_exclude.csv in `src/tarsus/assets/`
- D-019: Minimal CLI — only 3 required flags (--fasta, --input, --output-dir)
- D-020: PDV downgraded to 2.1.2, XvfbDisplay context manager added
- Step modules updated to use bundled asset paths (no more TARSUS_elizabev references)
- `tarsus run` command generates master.py, submits it via bsub
- mypy clean, 134/134 unit tests pass

## Phase 4: First Pipeline Run on Trial Data (in progress)

### Completed
- D-021: PYTHONUNBUFFERED=1 — all master job output flushes immediately to log
- D-022: Fixed PDV export path — Step 7 now reads `pdv_spectra/PDVExportResult.txt`
- `tarsus run` submitted master job 874700 against trial data (E. coli K12, 2 raw files)
- Step 1 conversion completed successfully:
  - HouYM-25-G140-AstralDDA-AlaGGC-HS-1: 6.0 GB mzML (golden: 6,077 MB ✓)
  - HouYM-25-G140-AstralDDA-AlaGGC-LS-1: estimated 8.4 GB mzML (in progress)
- All 6 tools verified, 134 unit tests pass, mypy clean

### In Progress (2025-06-29)
- Pipeline run 874700: Step 1 conversion running (~22 min elapsed)
- HS-1: DONE (6.0 GB, golden 6,077 MB ✓)
- LS-1: 85% (7.2 GB of ~8.4 GB written, golden 8,427 MB) — estimated 3 min remaining

### Open Tasks
1. Monitor pipeline run to completion (should take ~hours depending on queue times)
2. Capture golden files for Steps 2-11
3. Compare final `subs_localized.csv` against reference pipeline output
4. Write user documentation for cross-lab setup
