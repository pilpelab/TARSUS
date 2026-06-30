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
- D-021: PYTHONUNBUFFERED=1 for real-time master job logging
- D-022: PDV export path fixed — Step 7 reads pdv_spectra/PDVExportResult.txt
- Step modules updated to use bundled asset paths
- orchestration.py: sentinel checkpointing (.done markers per step)
- step02_make_index.py: per-file parallel PepQuery indexing with dynamic heap auto-scaling
- 142 unit tests passing, mypy clean, 7/7 tools verified

### Current State
Pipeline run 940573 in progress: Step 1 skipped (sentinel), Step 2 running (2 parallel
PepQuery index jobs with 16 GB heap + -r flag fix). Dynamic heap auto-scaling committed.
The per-file parallel approach validated — HS-1 indexed in 60 min (339K spectra). LS-1 in
progress (~47 min est).

### Open Tasks
1. Monitor pipeline run to completion (should take ~hours depending on queue times)
2. Capture golden files for Steps 2-11
3. Compare final `subs_localized.csv` against reference pipeline output
4. Write user documentation for cross-lab setup

## Phase 4: Mock Dev Data for Fast Iteration (planned)

### Completed
- D-023: Mock dev dataset decision recorded

### Open Tasks (next agent execution)
1. Create `scripts/make_mock_mzml.py` — extract first 50 spectra from real mzML
   to produce `data/test-mock/dev.mzML` (~10 MB, git-tracked)
2. Add `data/test-mock/` directory with .gitignore exception
3. Create mock FASTA: small subset of `data/protein.fasta` in `data/test-mock/`
4. Create `tests/validation/test_step02_index.py` — validate PepQuery index against mock data
5. Create `tests/validation/test_step07_analyze.py` — validate SAV filtering
6. Run pipeline against mock data once, capture golden files for Steps 2-7
7. Add mock data fixture to `tests/validation/conftest.py`
8. Verify: `uv run pytest tests/validation/ -m "not lsf"` completes in < 60 seconds

### Design
- Mock mzML: 50 spectra → ~10 MB. Git-tracked. Generated once from real data.
- Mock FASTA: subset of real protein.fasta matching the mock spectra.
- Golden files: same pattern as Step 1 (capture on first run, compare on subsequent).
- Validation tests do NOT require LSF — steps are called directly (not via bsub).
