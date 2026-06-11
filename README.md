# TARSUS_BC

## Description

Describe your project here.

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
