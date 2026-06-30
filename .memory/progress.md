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
Python modules. PDV 2.1.2 bundled (matches reference), works via cluster Xvfb module.
LSF verified working (bsub, gsla-cpu queue). Reference assets (generic.workflow,
subs_exclude.csv) bundled in `src/tarsus/assets/`. `tarsus run` command submits
`python -m tarsus.orchestration` via bsub. Sentinel checkpointing (.done files) allows
resuming from failed steps.

## Phase 3: CLI Wiring and Orchestration (completed)

### Completed
- D-016: LSF verified working (2025-06-29) — bsub functional, gsla-cpu queue Open:Active
- D-017: Master-job architecture — single LSF job orchestrates all 11 steps on a compute node
- D-018: Bundled assets — generic.workflow and subs_exclude.csv in `src/tarsus/assets/`
- D-019: Minimal CLI — only 3 required flags (--fasta, --input, --output-dir)
- D-020: PDV downgraded to 2.1.2, XvfbDisplay context manager added
- D-021: PYTHONUNBUFFERED=1 for real-time master job logging
- D-022: PDV export path fixed — Step 7 reads pdv_spectra/PDVExportResult.txt
- Step modules updated to use bundled asset paths (no more TARSUS_elizabev references)
- `tarsus run` command submits `python -m tarsus.orchestration` via bsub
- orchestration.py: sentinel checkpointing (.done markers per step)
- step02_make_index.py: per-file parallel PepQuery indexing with dynamic heap auto-scaling
- 142 unit tests passing, mypy clean, 7/7 tools verified

### Current State
Pipeline run 940573 in progress: Step 1 skipped (sentinel), Step 2 running (2 parallel
PepQuery index jobs with 16 GB heap + -r flag fix). Dynamic heap auto-scaling committed
(e834a9f). The per-file parallel approach validated — HS-1 indexed in 60 min (339K spectra).

## Phase 4: Mock Dev Data for Fast Iteration ── EXECUTABLE PLAN (in progress — code done, LSF runs pending)

### Decision
D-023 recorded (2025-06-30): Mock dev dataset for fast iteration. 10 MB mzML with 50
spectra replaces 6-8 GB files for debugging. Full pipeline runs against mock data in ~2
minutes via LSF (each step submits bsub but completes in seconds on tiny data).

### Goal
Create `data/test-mock/dev.mzML` (50 spectra, ~10 MB, git-tracked) and validation tests
that run the full pipeline against it. On success, add `uv run pytest tests/validation/ -m lsf`
to CI/quick-check workflow.

### Step 1: Create mock mzML file
- Create `scripts/make_mock_mzml.py`:

```python
#!/usr/bin/env python3
"""Extract first N spectra from a real mzML file for mock testing.

Usage: uv run python scripts/make_mock_mzml.py <input.mzML> <output.mzML> [--spectra N]
"""
import sys, argparse
from pathlib import Path
from pyteomics import mzml

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spectra", type=int, default=50)
    args = parser.parse_args()

    output = {}
    count = 0
    with mzml.read(str(args.input)) as reader:
        for spec in reader:
            if spec.get("ms level") == 2:
                if count < args.spectra:
                    output[spec["id"]] = spec
                count += 1
            # Always pass through MS1 scans
            elif spec.get("ms level") == 1 and count <= args.spectra:
                output[spec["id"]] = spec

    # Read input mzML as XML, write only selected spectra
    with args.output.open("w") as out:
        with mzml.MzML(str(args.input)) as src:
            src.write(out, spectrum_ids=set(output.keys()))

    size_mb = args.output.stat().st_size / 1e6
    print(f"Wrote {len(output)} spectra ({size_mb:.1f} MB) → {args.output}")

if __name__ == "__main__":
    main()
```

- Run once against the real mzML file to generate the mock:
  ```bash
  uv run python scripts/make_mock_mzml.py \
    output/trial/01_mzml/HouYM-25-G140-AstralDDA-AlaGGC-HS-1.mzML \
    data/test-mock/dev.mzML --spectra 50
  ```
- Verify:
  ```bash
  ls -lh data/test-mock/dev.mzML   # ~10 MB
  python -c "from pyteomics import mzml; print(len(list(mzml.read('data/test-mock/dev.mzML'))))"
  # should print ~100-200 (both MS1 and MS2 scans)
  ```

### Step 2: Create mock test data directory
- Create `data/test-mock/` directory (if it doesn't exist)
- Add `data/test-mock/mock_readme.md`:
  ```
  # Mock Test Data
  Small mzML file (50 MS2 spectra) extracted from real Orbitrap Astral DDA data.
  Used for fast pipeline validation without processing 6-8 GB files.
  
  Generated by: scripts/make_mock_mzml.py
  Source: HouYM-25-G140-AstralDDA-AlaGGC-HS-1.mzML (E. coli K12, LS fraction)
  ```

### Step 3: Update .gitignore
- In `.gitignore`, add exception for mock data:
  ```
  # ── After the existing data/* line ──
  !data/test-mock/**
  ```
- Verify: `git add -n data/test-mock/dev.mzML` should NOT say "ignored"

### Step 4: Add mock data fixture to conftest.py
- In `tests/validation/conftest.py`, add after the `trial_data` fixture:

```python
MOCK_DATA_DIR = DATA_DIR / "test-mock"

@pytest.fixture(scope="session")
def mock_data() -> dict:
    """Paths to mock test data (50 spectra, fast)."""
    return {
        "fasta": DATA_DIR / "protein.fasta",  # same FASTA, only 1.9 MB
        "mzml": MOCK_DATA_DIR / "dev.mzML",
    }
```

### Step 5: Create validation test for Step 2 (PepQuery index)
- Create `tests/validation/test_step02_index.py`:

```python
"""Step 2 validation: PepQuery index against mock data."""

import pytest
from pathlib import Path
from src.tarsus.steps.step02_make_index import step02_make_index
from .conftest import load_expected, capture_expected


@pytest.mark.lsf
def test_step02_index(mock_data, tool_env, tmp_path):
    """Build PepQuery index from mock mzML and verify output exists."""
    mzml = mock_data["mzml"]
    assert mzml.is_file(), f"Mock mzML not found: {mzml}"

    # Create a temp mzML directory (step02 expects a directory)
    mzml_dir = tmp_path / "01_mzml"
    mzml_dir.mkdir()
    (mzml_dir / mzml.name).symlink_to(mzml.resolve())

    output_dir = tmp_path / "02_index"
    result = step02_make_index(mzml_dir, output_dir, tool_env)

    # Build actual stats
    tmp_dir = result / "tmp"
    actual = {
        "index_dir_exists": result.is_dir(),
        "tmp_exists": tmp_dir.is_dir(),
        "fragment_count": len(list(tmp_dir.iterdir())) if tmp_dir.is_dir() else 0,
    }

    # Capture or compare
    expected = load_expected("step02")
    if expected is None:
        capture_expected("step02", actual)
        pytest.skip("Expected output captured — re-run to validate")
    else:
        assert actual["index_dir_exists"], "Index directory not created"
        assert actual["tmp_exists"], "tmp/ directory not created"
        assert actual["fragment_count"] >= 1, "No per-file fragments in tmp/"
        for key, val in expected.items():
            assert actual.get(key) == val, f"step02.{key}: expected {val}, got {actual.get(key)}"
```

### Step 6: Create validation test for Step 3a (FragPipe first pass)  
- Create `tests/validation/test_step03a_first_pass.py`:

```python
"""Step 3a validation: FragPipe first pass against mock data."""

import pytest
from pathlib import Path
from src.tarsus.steps.step03a_first_pass import step03a_first_pass
from .conftest import load_expected, capture_expected


@pytest.mark.lsf
def test_step03a_first_pass(mock_data, tool_env, tmp_path):
    """Run FragPipe first pass on mock mzML."""
    fasta = mock_data["fasta"]
    mzml = mock_data["mzml"]
    assert fasta.is_file()
    assert mzml.is_file()

    mzml_dir = tmp_path / "01_mzml"
    mzml_dir.mkdir()
    (mzml_dir / mzml.name).symlink_to(mzml.resolve())

    output_dir = tmp_path / "03a_first_pass"
    result = step03a_first_pass(fasta, mzml_dir, output_dir, tool_env)

    # Check key output files exist
    psm_tsv = result / "psm.tsv"
    peptide_tsv = result / "peptide.tsv"
    actual = {
        "psm_exists": psm_tsv.is_file(),
        "peptide_exists": peptide_tsv.is_file(),
        "psm_size_kb": psm_tsv.stat().st_size // 1024 if psm_tsv.is_file() else 0,
    }

    expected = load_expected("step03a")
    if expected is None:
        capture_expected("step03a", actual)
        pytest.skip("Expected output captured — re-run to validate")
    else:
        assert actual["psm_exists"], "psm.tsv not found"
        for key, val in expected.items():
            assert actual.get(key) >= val * 0.5, f"step03a.{key}: {actual.get(key)} < 50% of expected {val}"
```

### Step 7: Create validation test for Step 7 (analyze outputs)
- Create `tests/validation/test_step07_analyze.py`:

```python
"""Step 7 validation: SAV filtering against mock data pipeline output."""

import pytest
from pathlib import Path
from src.tarsus.steps.step07_analyze_outputs import analyze_outputs
from .conftest import load_expected, capture_expected


@pytest.mark.lsf
def test_step07_analyze(mock_data, tool_env, tmp_path):
    """Run Step 7 against mock pipeline outputs from Steps 2-6."""
    # This test needs the outputs from Steps 2-6. 
    # For first run: set up a mini pipeline run in tmp_path.
    # On subsequent runs: compare against golden file.
    
    # TODO: Wire this after Steps 2-6 are validated.
    # For now, skip with a message.
    pytest.skip("Requires Steps 2-6 outputs — wire after those pass")
```

### Step 8: Run and verify
- Run the new validation tests against mock data:
  ```bash
  uv run pytest tests/validation/test_step02_index.py -v -m lsf
  uv run pytest tests/validation/test_step03a_first_pass.py -v -m lsf
  ```
- On first run: golden files are captured, tests skip.
- On second run: tests compare against golden files.
- Full suite (excluding heavy LSF tests with real data):
  ```bash
  uv run pytest tests/validation/ -v  # runs mock data tests
  ```

### Verification checklist
- [x] `data/test-mock/dev.mzML` exists (0.7 MB, 92 spectra)
- [x] `scripts/make_mock_mzml.py` works (index-based streaming)
- [x] `.gitignore` allows `data/test-mock/**`
- [x] `test_step02_index.py` created (LSF golden-file)
- [x] `test_step03a_first_pass.py` created (LSF golden-file)
- [x] `test_step07_analyze.py` created (stubbed)
- [x] All 142 unit tests pass: `uv run pytest tests/unit/`
- [x] mypy clean: `uv run mypy src/tarsus`
- [x] Collection: `uv run pytest tests/validation/ -m "not lsf"` → 4 deselected in 1.42s

### Remaining
1. Run `test_step02_index.py` against LSF to capture `expected/step02.yaml`
2. Run `test_step03a_first_pass.py` against LSF to capture `expected/step03a.yaml`
3. Wire `test_step07_analyze.py` after Steps 2-6 are validated
