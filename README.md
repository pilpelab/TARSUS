# TARSUS_BC

## Description

Configurable, shareable implementation of the **TARSUS** (TArgeted SUbstitution Search) proteomics pipeline for detecting validated single amino acid substitutions (SAAVs) from mass spectrometry data. Designed for cross-lab use on the institute's LSF cluster.

Based on: Tretyachenko et al. (2025). Encoded and non-genetic alternative protein variants expand human functional proteome. *bioRxiv*. https://www.biorxiv.org/content/10.1101/2025.02.17.638604v1

**Reference implementation:** `TARSUS_elizabev/` (read-only — see `.context/reference-pipeline.md`)

## Setup

This project uses `uv` for Python environment and dependency management.

### Create environment

```bash
uv venv --python 3.11
```

### Activate environment

```bash
source .venv/bin/activate
```

### Install dependencies

```bash
uv sync
```

### Add dependencies

```bash
uv add package-name
```

### Add development dependencies

```bash
uv add --dev pytest ruff mypy
```

### Run the project

```bash
uv run python main.py
```

### Run tests

```bash
uv run pytest
```

## Structure

```
src/       Source code
tests/     Tests
docs/      Documentation
data/      Local datasets
scripts/   Utility scripts
.agents/   Agent operating instructions
.memory/   Project memory, decisions, and progress
```
