# TARSUS_BC — Project-Specific Agent Rules

## Source of Truth

This repository (`TARSUS_BC/`) is the source of truth for the TARSUS pipeline implementation.
`TARSUS_elizabev/` is a **read-only reference** copy of the colleagues' working directory.
**Never modify files inside `TARSUS_elizabev/`.**

## Project Purpose

Containerized, configurable, shareable implementation of the TARSUS pipeline for detecting
single amino acid substitutions (SAAVs) from mass spectrometry data.
Designed for **cross-lab use within the institute** on the shared LSF cluster.

## Target Platform

- **Execution:** LSF cluster (`bsub`) — the institute's existing infrastructure
- **No Docker** in current scope
- **Operating System:** Linux x86_64 (cluster nodes)
- **Runtime requirements:** Python 3.11, Java 21 (bundled), .NET 8 (bundled)

## Development Conventions

### Scope Discipline
- **Never fix a bug the user only mentions.** When the user describes a bug,
  ask whether they want it fixed before writing any code. Mentioning is not
  requesting. If the user wants a fix, they will explicitly say "fix it",
  "implement this", "run this", or similar.
- When scope is unclear, ask — do not assume.
- Completing the requested task cleanly beats adding unrequested improvements.

### Python
- All Python code goes in `src/tarsus/` as a proper package
- Use `uv` for environment management (`uv venv`, `uv sync`, `uv add`)
- Use `uv run` to execute commands (never assume .venv is activated)
- Test with `uv run pytest`
- Lint with `uv run ruff check`
- Type check with `uv run mypy`

### Configuration
- **No hardcoded paths** in code — all tool paths, database paths, and parameters
  must be externalized to environment variables or a config file
- Configuration should be overridable per-lab without code changes

### Shell Scripts
- Prefer Python orchestration over bash for pipeline logic
- Use subprocess to invoke external tools (FragPipe, PepQuery, PDV, etc.)
- Keep LSF job submission wrappers where bsub is unavoidable

### Code Quality
- All Python code must have type annotations
- All functions must have docstrings
- Test analysis logic with pytest (not the external tool invocations)
- Use Polars for tabular data (consistent with reference implementation)

## Memory Rules

### Session Start Protocol
Before any work, run through this checklist:
- [ ] Read `.memory/lessons.md` — **how this pipeline fails.** Every rule in it cost days of
      cluster time to learn. Read it before touching any step.
- [ ] Read `.memory/progress.md` — know current state and open tasks
- [ ] Read `.memory/decisions.md` — know prior decisions (do not re-litigate)
- [ ] Read `.memory/session.md` — (if exists) resume from last session

### Before Changing Any Pipeline Step
Work the pre-flight checklist at the bottom of `.memory/lessons.md`. In short:
- **Never default on missing data** — `.get(k, 0)`, `fill_null(0)`, `except: pass` and a `re.sub`
  whose key is absent are how this pipeline fails. They do not crash; they return wrong answers and
  stamp `.done`. Raise instead.
- **Never "optimize" a data contract you have not traced downstream.** One such change (`e143a46`)
  cost a week and produced four phantom bugs.
- **Check the reference before inventing** — `TARSUS_elizabev/` for scripts, and the colleagues' real
  completed run under `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/` for artifacts.
- **State which `.done` sentinels must be cleared** for your change to take effect, and whether it
  changes SAAV counts. Move stale outputs aside; do not delete.

### After Fixing a Bug
Append the lesson to `.memory/lessons.md` if it teaches something the list does not already cover.
That file is the project's self-improvement loop — it is only useful if it stays current.

### During Session
- Update `.memory/progress.md` after every meaningful work item
  - Format: `YYYY-MM-DD | <what was done>`
  - Update "Current State" paragraph
  - Move completed items out of "Open Tasks"
- Append to `.memory/decisions.md` only for architectural/tooling/workflow decisions
  - Format: `## D-NNN: <title>` with date, context, decision, rationale

### At Session End
- `.memory/progress.md` must accurately reflect actual state
- `.memory/decisions.md` must be consistent with progress
- `git status` should show clean tracked tree (new files may be unstaged)

## Tool Management

- All external tools and runtimes are pinned in `tools/` via Makefile — run `make setup` from repo root
- Versions are explicit and checksum-verified — update intentionally
- `tools/README.md` is tracked; downloaded binaries are gitignored (`tools/**`)
- `src/tarsus/env.py` provides `ToolEnvironment` class — canonical resolver for all tool paths
- Python CLI is the primary entry point; env.py sets `JAVA_HOME`, `DOTNET_ROOT`, `PATH` before subprocess calls
- **Current toolset:** JDK 21 (Temurin), .NET 8 runtime, FragPipe 24.0, PepQuery 2.0.2, PDV 2.2.3, ThermoRawFileParser 2.0.0-dev
- Run `make test-tools` to verify all tools are working

## Data Directory

- `data/` is a gitignored workspace for test input files — only `data/README.md` is tracked
- Do not hardcode paths to `data/` in production code
- Pipeline inputs are always user-specified via CLI flags (`--fasta`, `--input`)

## Reference Pipeline Documentation

See `.context/reference-pipeline.md` for full documentation of all 11 steps.
See `.context/architecture.md` for data flow diagrams and component coupling.
