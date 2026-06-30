# Decisions Log

## D-034: IonQuant 1.11.20 Added as Required Tool Dependency
**Date:** 2026-06-30
**Context:** FragPipe 24.0's Linux ZIP distribution does not bundle IonQuant.jar (unlike the Windows distribution). The pipeline failed with missing IonQuant at Step 3a/3c when FragPipe internally calls IonQuant for quantification.
**Decision:** Add IonQuant 1.11.20 as a separate tool dependency in `tools/Makefile`. Copy the JAR from the reference installation at `/home/labs/pilpel/slavat/fragpipe-24.0/tools/IonQuant-1.11.20.jar`. Add `ionquant` target and `test-ionquant` check to `make setup`.
**Rationale:** IonQuant is a hard dependency of FragPipe's quantification module. Without it, FragPipe exits with an error before producing any results. Including it in `make setup` ensures it is always present.

## D-033: Target-Decoy FASTA Generated Inline for Both 3a and 3c Passes
**Date:** 2026-06-30
**Context:** FragPipe requires a target-decoy FASTA for FDR estimation (it reads the `rev_` tag to identify decoys). The reference pipeline assumed decoys were baked into the workflow configuration. Steps 3a and 3c both need decoys but the raw FASTA has none.
**Decision:** Add `_make_decoy_fasta()` to both `step03a_first_pass.py` and `step03c_second_pass.py`. This function reads the input FASTA, writes forward sequences plus reversed copies with `>rev_` prefix, outputting `protein_decoy.fasta`. The workflow `database.db-path` is set to the decoy FASTA, and `database.decoy-tag=rev_` is patched.
**Rationale:** Generates decoys inline without requiring pre-processed FASTA files. Both passes get independent decoy FASTA files in their own output directories. The reversed-sequence approach is the standard FragPipe convention.

## D-032: FragPipe 24.0 Scan Number Mismatch — Peptide-Only PepQuery Input
**Date:** 2026-06-30
**Context:** FragPipe 24.0 uses internal scan numbering that does not match the native mzML scan numbers. Step 4 originally extracted `peptide:scan:charge` spectrum titles for PepQuery's targeted search mode, but the scan numbers from FragPipe's `Spectrum` column did not correspond to PepQuery's indexed scan numbers. This caused "Matched spectra: 0" for every peptide.
**Decision:** Switch Step 4 output from two-column (peptide + spectrum_title) to one-column (peptide only). PepQuery runs in open-search mode (`-aa` flag), which searches all indexed spectra for each peptide without requiring a scan number match. Step 4's `extract_psm()` function now writes only peptide sequences.
**Rationale:** PepQuery's open-search mode finds matching spectra by peptide sequence alone — scan numbers are irrelevant. This bypasses the FragPipe/PepQuery scan numbering mismatch entirely. For the variant-peptide validation use case (confirming variant peptides exist in the data), open-search is correct: it returns all spectra matching the peptide sequence regardless of scan position.

## D-031: Header-Free PepQuery Input (Peptide-Only Format)
**Date:** 2026-06-30
**Context:** Step 4 output originally had a TSV header line (`peptide\tspectrum_title`). Step 5 (`step05_query_psm`) split this file into chunks and prepended the header to each chunk. PepQuery interpreted the header repetition as data, causing parse errors and zero matched spectra.
**Decision:** Remove the TSV header from Step 4 output entirely. Step 5 splits raw lines without header handling — each line is one peptide. PepQuery receives peptide-only input with no header, column names, or spectrum titles.
**Rationale:** PepQuery's open-search mode reads one peptide per line. Headers and spectrum titles are not expected and cause parse errors. Peptide-only input is simpler, faster, and correct for the use case.

## D-030: PepQuery `-db` Must Point to Raw FASTA, Not Index Directory
**Date:** 2026-06-30
**Context:** The `-db` flag in PepQuery validation (Steps 5 and 9) was set to `str(index_dir.resolve())` — the PepQuery index directory. PepQuery uses the `-db` path to resolve sequence annotations for matched spectra. Pointing it at the index caused PepQuery to fail silently (no error, no matches).
**Decision:** Pass the user's `--fasta` path through orchestration to both `step05_query_psm()` and `step09_query_psm_base()`. Use `str(fasta_path.resolve())` for the `-db` flag instead of the index directory. Add `fasta_path: Path | None = None` parameter to both functions.
**Rationale:** The FASTA file is required for PepQuery to annotate matched spectra with protein names and sequence context. The index directory path was a copy-paste error from the reference implementation.

## D-029: MSBooster Fully Disabled in Step 3c Second Pass
**Date:** 2026-06-30
**Context:** The FragPipe workflow template has `msbooster.run-msbooster=true`, `msbooster.predict-rt=true`, and `msbooster.predict-spectra=true` by default. Step 3c (variant-peptide second pass) was only disabling `find-best-rt-model=false`. MSBooster was still attempting to calibrate RT/spectra predictions on the nocleavage search results, causing silent hangs and excessive wall time (30+ minutes).
**Decision:** Add three additional MSBooster workflow patches to `step03c_second_pass.py`: `msbooster.run-msbooster=false`, `msbooster.predict-rt=false`, `msbooster.predict-spectra=false`.
**Rationale:** MSBooster calibration requires training data that does not exist for variant-peptide second-pass searches (different enzyme, different search space). Fully disabling all MSBooster features prevents wasted compute and potential hanging.

## D-028: Step 2 Reordered After Step 3a — Index `_sub.mzML`, Not Original mzML
**Date:** 2026-06-30
**Context:** Step 2 (PepQuery index) originally ran immediately after Step 1, indexing the full mzML files in `01_mzml/`. But PepQuery validation (Step 5) searches against `*_sub.mzML` — the unidentified spectra output by FragPipe's first pass. The index must contain only the spectra that Step 5 will actually search against. Indexing full mzML was also wasteful: 60 minutes to index spectra that would never be searched.
**Decision:** Reorder pipeline execution so Step 2 runs AFTER Step 3a. The index directory is built from `03a_first_pass/*_sub.mzML` instead of `01_mzml/*.mzML`. The `summary.txt` also strips `_sub` from `ms_file` paths (D-027) so PepQuery can match spectrum filenames. Data flow changes from `01_mzml → 02_index` to `03a_first_pass → 02_index`.
**Rationale:** Only the unidentified spectra from Step 3a's `_sub.mzML` files are searched by Step 5. Indexing the full mzML is a 2× waste (60 min indexing of already-identified spectra). The reorder also simplifies workflow: Step 3b (variant peptide generation) uses Step 3a's `peptide.tsv`, which is now produced before Step 2 runs. The `summary.txt` `_sub` stripping ensures PepQuery's internal filename matching works correctly.

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

## D-016: LSF Verified Working
**Date:** 2025-06-29
**Context:** Before building pipeline orchestration, needed to confirm the cluster is accessible.
**Decision:** Verified: `bsub` available (IBM Spectrum LSF 10.1.0.0), `gsla-cpu` queue Open:Active. Test job (ID 854986) submitted and completed. Trial data files present (protein.fasta 1.9 MB, two .raw files 7.3+11 GB). No blockers for LSF-based execution.
**Rationale:** Confirms the target environment matches the original architecture decision D-001.

## D-017: Master-Job Architecture (All-LSF)
**Date:** 2025-06-29
**Context:** User requires all pipeline steps to execute on LSF — nothing on the login node beyond initial submission.
**Decision:** A single "master" LSF job orchestrates the entire pipeline. Heavy-tool steps (1, 2, 3a, 3c, 5, 9) submit child bsub jobs and wait. Python analysis steps (3b, 4, 6, 7, 8, 10, 11) run inline on the master job's compute node. The login node is only used for `bsub` submission.
**Rationale:** Keeps login nodes free for interactive use. Child jobs get appropriate resource allocations (memory, CPUs) per step. Python steps are lightweight and don't need separate LSF jobs.

## D-018: Bundled Reference Assets
**Date:** 2025-06-29
**Context:** Steps 3a/3c need `generic.workflow` (FragPipe workflow template). Step 3b needs `subs_exclude.csv` (AA substitution exclusion matrix). Both were referenced from `TARSUS_elizabev/`.
**Decision:** Bundle both files in `src/tarsus/assets/`. Import via module constant (`WORKFLOW_TEMPLATE`, `SUBS_EXCLUDE_CSV`). Remove all runtime dependencies on `TARSUS_elizabev/`.
**Rationale:** Makes the package fully self-contained — no external file references. Matches D-006 (TARSUS_elizabev is read-only reference). Users don't need the reference directory at all.

## D-019: Minimal CLI Interface
**Date:** 2025-06-29
**Context:** The pipeline has many internal paths (workflow templates, exclusion matrices, output subdirectories) but users should not need to know them.
**Decision:** `tarsus run` requires only 3 flags: `--fasta`, `--input` (repeatable), `--output-dir`. All other paths are auto-derived. Internal assets are bundled in the package. Advanced options (queue, memory, CPUs) have sensible defaults.
**Rationale:** Reduces cognitive load for new users. Follows the "convention over configuration" pattern. Advanced users can still override via environment variables.

## D-020: PDV 2.1.2 with Xvfb Display Manager
**Date:** 2025-06-29
**Context:** PDV requires an X11 display even in CLI mode (JFrame created in constructor). Both 2.1.2 and 2.2.3 crash with HeadlessException without a display. The cluster has Xvfb available via EasyBuild modules (no sudo).
**Decision:** Bundle PDV 2.1.2 JAR (matches reference), symlink lib/ from 2.2.3 for shared dependencies. Add `XvfbDisplay` context manager in env.py: automatically detects and starts Xvfb from the cluster module system when `$DISPLAY` is not set.
**Rationale:** No version-specific GUI workarounds needed. Xvfb is already on the cluster. The context manager pattern ensures clean startup/shutdown with zero GUI windows.

## D-021: Unbuffered Python Output for LSF Jobs
**Date:** 2025-06-29
**Context:** The master job's `print()` calls were fully buffered when stdout was redirected to a file by `bsub -oo`. Logs showed no progress until the buffer filled or the job exited.
**Decision:** Set `PYTHONUNBUFFERED=1` in `os.environ` before submitting the master bsub job. This propagates via `tool_env.env()` and ensures all Python output flushes immediately to the LSF log file.
**Rationale:** Real-time log visibility is critical for monitoring long-running pipeline jobs. No downside — all Python output, including from child subprocesses, becomes unbuffered.

## D-022: PDV Export Path Resolution
**Date:** 2025-06-29
**Context:** Step 7 (`analyze_outputs`) reads a TSV file with PDV ion annotations. The master.py orchestration script had the path hardcoded to `pdv_export.tsv`, but PDV actually writes `PDVExportResult.txt` inside the `pdv_spectra/` directory.
**Decision:** Corrected the path in the master.py template to `06_aggregated/pdv_spectra/PDVExportResult.txt`. Verified against the reference pipeline's actual file naming convention.
**Rationale:** The wrong path caused Step 7 to silently skip PDV ion data (the try/except caught the FileNotFoundError), which meant the two-fragment coverage filter was always bypassed. This fix restores the intended filtering behavior.

## D-023: Mock Dev Dataset for Fast Iteration
**Date:** 2025-06-30
**Context:** Pipeline debugging requires 60+ minute iterations because each step processes 6-8 GB mzML files. A 10 MB mock dataset with 50 spectra would reduce iteration time to seconds.
**Decision:** Create a small mock mzML file by extracting the first 50 spectra from the real mzML using a Python script (`scripts/make_mock_mzml.py`). Track it in `data/test-mock/` alongside a mock FASTA. Add validation tests (golden-file pattern) for Steps 2, 3a, 7 that run against the mock data without requiring LSF.
**Rationale:** Enables sub-minute feedback cycles for pipeline development. Uses the existing golden-file validation pattern (capture on first run, compare on subsequent). Does not require LSF — steps are called directly. The mock data is valid mzML (subset of real data), so pipeline behavior is representative.

## D-024: gsla-cpu as Universal Default Queue
**Date:** 2025-06-30
**Context:** Steps 5 and 9 originally used the "short" queue, which was intermittently unavailable. All other steps already used gsla-cpu.
**Decision:** All pipeline steps default to gsla-cpu queue. No step uses "short" by default.
**Rationale:** Simplifies configuration, avoids queue-availability problems, and ensures consistent scheduling behavior across all steps.

## D-025: Step 3c Must Use _sub.mzML (Unidentified Spectra)
**Date:** 2025-06-30
**Context:** Step 3c (FragPipe second pass, nocleavage) was pointed at the original mzML files from Step 1 (`01_mzml/`). It should search against `*_sub.mzML` files from Step 3a (`03a_first_pass/`) — the unidentified spectra that didn't match in the first pass.
**Decision:** Changed `orchestration.py` line 87 from `mzml_dir=outdir / "01_mzml"` to `mzml_dir=outdir / "03a_first_pass"`.
**Rationale:** Running the second pass on ALL spectra instead of only unidentified spectra defeats the purpose of the two-pass pipeline. It wastes compute on already-identified peptides and artificially inflates the search space. The `*_sub.mzML` files are the correct input — they contain only the spectra that need variant-peptide searching.

## D-027: PepQuery Index Must Be Flat .mgf at Root, Multi-File Bins Concatenated
**Date:** 2026-06-30
**Context:** Step 05 (PepQuery validation) ran successfully (LSF exit 0) but produced zero results — every `detail.txt` was header-only and no `psm_rank.txt` appeared. Root cause investigation via chunk logs showed three bugs in step02's merge logic:
1. MGF files were placed in `pepquery_index/tmp/<mzml_name>_<idx>/` subdirectories, but PepQuery search looks for files flat at the root of the index directory.
2. Files were left as `.mgf.gz`; PepQuery search expects uncompressed `.mgf`.
3. The native `summary.txt` generated by PepQuery's own `index` command was overwritten with a custom version that stripped `_sub` from `ms_file` paths, pointing to non-existent files.
Additionally: PepQuery organises spectra into mass-bin files (named by `floor(precursor_mass × ~20)`). Both HS-1 and LS-1 `_sub.mzML` files share overlapping mass-bin ranges, so a naive flat merge overwrites one file's spectra with the other's. Files must be **concatenated** (append mode).
**Decision:** Rewrite step02 merge logic to: (a) decompress `.mgf.gz` → `.mgf`, (b) place files flat at `pepquery_index/` root, (c) open each dest in append mode so same-mass-bin spectra from multiple mzML files are concatenated, (d) preserve the native PepQuery `summary.txt` (merge across files) instead of generating a custom one.
**Rationale:** PepQuery's `MsLibrarySearchWorker` constructs paths as `<index_dir>/<bin_id>.mgf` directly — no subdirectory traversal. Subdirectories and `.gz` extensions both cause silent "File doesn't exist" warnings and 0 matched spectra. The FASTA `.sqldb` warning seen in logs is benign — PepQuery re-indexes on the fly and continues.

## D-026: I/L Ambiguity in Mass Spectrometry
**Date:** 2025-06-30
**Context:** The substitution exclusion matrix (`subs_exclude.csv`) uses "I/L" notation for isoleucine/leucine positions. This string was leaking into peptide sequences, causing FragPipe/MSBooster to fail with "WARNING: Trying to compute mass of non-residue: /".
**Decision:** Normalize "I/L" → "I" in both the matrix column headers and the `_single_substitutions` function. FASTA headers retain "I/L" for informational clarity, but the actual peptide sequences use only canonical amino acid codes.
**Rationale:** Mass spectrometry cannot distinguish isoleucine from leucine — they have identical monoisotopic mass (113.08406 Da). Using "I" as the canonical representation is the standard convention in proteomics. The "/" character is not a valid amino acid and breaks downstream tools.
