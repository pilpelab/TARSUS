# Decisions Log

## D-001: LSF Cluster as Deployment Target
**Date:** 2025-06-11
**Context:** The reference pipeline relies on LSF (bsub) for job submission. The institute operates an LSF cluster.
**Decision:** Keep LSF as the execution environment. Do not introduce Docker or other containerization at this stage.
**Rationale:** The target audience (academic labs within the institute) already uses the LSF cluster. Containerization adds complexity without immediate benefit. All tool paths and cluster parameters must be externalized for cross-lab portability.

## D-002: Python Package Structure
**Date:** 2025-06-11
**Context:** The reference implementation is a loose collection of scripts without a package structure.
**Decision:** Organize all Python code as a proper package under `src/tarsus/`.
**Rationale:** Enables import-based reuse, testing, type checking, and dependency management via uv.

## D-003: Configuration-Driven Design
**Date:** 2025-06-11
**Context:** Every script in the reference implementation contains hardcoded paths to tool installations and databases.
**Decision:** All tool paths, database paths, and cluster parameters must be externalized via environment variables or a config file.
**Rationale:** Different labs within the institute have different tool installation directories and data locations. No code changes should be required to adapt the pipeline.

## D-004: Self-Contained Tool Distribution (supersedes original D-004)
**Date:** 2025-06-16 (revised)
**Context:** Original D-004 assumed tools were pre-installed on cluster. We now want full control over versions and distribution, independent of the cluster.
**Decision:** All external tools are downloaded and pinned in `tools/` via a Makefile. Each tool version is explicit, checksum-verified. The pipeline discovers tools at a configurable path (default `tools/`).
**Rationale:** Removes dependency on cluster administrators for tool maintenance. Enables reproducible deployments. The Makefile pattern means anyone can run `make setup` and have a working environment. Dockerization in the future will bundle these tools.

## D-005: Python Orchestration
**Date:** 2025-06-11
**Context:** The reference pipeline uses bash for orchestration (job submission, file management, tool invocation).
**Decision:** Replace bash orchestration with Python where feasible, using subprocess for external tool calls. Keep minimal bash wrappers for LSF job submission where unavoidable.
**Rationale:** Python provides better error handling, logging, configuration management, and testability compared to bash.

## D-006: TARSUS_elizabev is Read-Only Reference
**Date:** 2025-06-11
**Context:** The `TARSUS_elizabev/` directory is a symlink to the colleagues' working directory.
**Decision:** Never modify files inside `TARSUS_elizabev/`. It is read-only reference material for understanding pipeline logic.
**Rationale:** It is someone else's code. Our job is to re-implement, not modify. Changes to the reference would cause confusion.

## D-007: No Embedded Reference Database
**Date:** 2025-06-16
**Context:** The reference implementation hardcodes a specific organism's FASTA path.
**Decision:** The pipeline does not ship with a default reference database. Users always supply `--fasta` explicitly.
**Rationale:** The project supports multiple organisms (E. coli, human, mouse, etc.). An embedded default would imply E. coli is special. The `data/` directory contains test fixtures only.

## D-008: User-Driven Pipeline Entry
**Date:** 2025-06-16
**Context:** The reference pipeline assumes specific file paths and a fixed batch.
**Decision:** The pipeline requires explicit `--fasta`, `--input` (one or more), and `--output-dir` flags. No auto-discovery of files.
**Rationale:** Users need full control over which files to process and in what batches. The same raw file can be analyzed against different references.

## D-009: Git Tracking Policy
**Date:** 2025-06-16
**Context:** Raw MS files are 7-11 GB each. Reference FASTA is user-supplied.
**Decision:** Only source code, documentation, and configuration are tracked. All of `data/` (except `data/README.md`) and `output/` are gitignored.
**Rationale:** Large binary files have no place in git. Every lab brings their own data and reference.
*Note: Small test fixtures in `data/test-pdv/` are tracked via `.gitignore` exception (`!data/test-pdv/**`).*

## D-010: Organism-Based Reference (Future)
**Date:** 2025-06-16
**Context:** The pipeline currently requires manual FASTA download for each organism.
**Decision:** Deferred. A future `--organism` flag will auto-fetch Uniprot proteomes on demand.
**Rationale:** The feature adds non-trivial download/caching logic. Not needed until the pipeline is used by multiple labs.

## D-011: Bundle Java 21 and .NET 8 Runtimes
**Date:** 2025-06-16
**Context:** The system lacks Java and .NET runtimes, making FragPipe, PepQuery, PDV, and ThermoRawFileParser unusable.
**Decision:** Download and pin JDK 21 (Eclipse Temurin, jdk-21.0.11+10) and .NET 8 runtime (8.0.28) into `tools/` via Makefile. The pipeline sets `JAVA_HOME`, `DOTNET_ROOT`, and `PATH` at runtime via `src/tarsus/env.py`.
**Rationale:** Full self-containment — a developer can clone the repo, run `make setup`, and have a complete working environment. No system package manager or cluster module dependencies. The Makefile pins exact versions with SHA256 verification.

## D-012: LSF-Only Pipeline Execution
**Date:** 2025-06-16
**Context:** Raw MS files are 7-11 GB each; conversion and search steps are computationally intensive.
**Decision:** Steps 1, 2, 3, 5, 6, 9, and 10 run exclusively via LSF cluster (bsub). The pipeline submits one job per file per step and waits for completion. Python analysis steps (3b, 4, 7, 8, 11) run locally.
**Rationale:** The reference pipeline was designed for cluster execution. Single-machine processing of multi-GB raw files is impractical. The `--local` flag exists for debugging, not production.

## D-013: Golden-File Validation Framework
**Date:** 2025-06-16
**Context:** Every pipeline step must be validated against the trial data to ensure correctness.
**Decision:** Validation uses a golden-file capture pattern. On first run, expected output properties (scan counts, file sizes, row counts) are captured to `tests/validation/expected/*.yaml`. Subsequent runs compare against these values. Captured values are tracked in git and reviewed manually.
**Rationale:** Scientific pipelines have stable, data-specific output characteristics. Golden-file capture automates the process while keeping human review in the loop.

## D-014: CLI and Configuration Stack
**Date:** 2025-06-16
**Context:** The pipeline needs a consistent CLI interface and configuration mechanism.
**Decision:** Use `click` for CLI, environment variables for configuration (with `--flag` overrides), and `pyproject.toml` console_scripts for entry point. No config file format — env vars are simpler for cluster environments and Docker.
**Rationale:** click is the standard Python CLI library. Env vars work naturally with LSF job submission and Docker. No config file parsing needed.

## D-015: Trial Data as Validation Reference
**Date:** 2025-06-16
**Context:** Test data exists in `data/` (protein.fasta + two .raw files from the same E. coli K12 sample).
**Decision:** The trial data is the canonical reference for all validation. Every validation test uses these exact files. Expected output schemas are derived from running on this data. Adding new trial data requires updating the validation expected files.
**Rationale:** Using real rather than synthetic data ensures the validation catches real pipeline issues. The trial data is small enough (relative to production) for iteration.
