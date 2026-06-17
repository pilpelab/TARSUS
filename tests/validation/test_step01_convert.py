"""Step 1 validation: RAW to mzML conversion."""

import pytest
from pathlib import Path

from src.tarsus.steps.step01_convert import step01_convert
from .conftest import load_expected, capture_expected, validate_mzml


@pytest.mark.lsf
def test_step01_convert(trial_data, tool_env):
    """Convert trial .raw files to .mzML via ThermoRawFileParser (LSF)."""
    output_dir = trial_data["mzml_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    raw_files = trial_data["raw_files"]
    assert len(raw_files) == 2, f"Expected 2 .raw files, got {len(raw_files)}"

    mzml_paths = step01_convert(
        raw_files=raw_files,
        output_dir=output_dir,
        tool_env=tool_env,
        local=False,
    )

    # Build actual results
    actual = {}
    for path in mzml_paths:
        assert path.exists(), f"Missing mzML: {path}"
        valid, stats = validate_mzml(path)
        assert valid, f"Invalid mzML: {path} ({stats.get('error')})"
        actual[path.name] = stats

    # Capture or compare against expected
    expected = load_expected("step01")
    if expected is None:
        capture_expected("step01", actual)
        pytest.skip("Expected output captured — re-run to validate")
    else:
        for fname, exp in expected.items():
            assert fname in actual, f"Unexpected file: {fname}"
            act = actual[fname]
            assert act["scan_count"] >= exp["scan_count"], (
                f"{fname}: scan count {act['scan_count']} < expected {exp['scan_count']}"
            )
            assert act["size_mb"] >= exp["size_mb"] * 0.8, (
                f"{fname}: size {act['size_mb']}MB < 80% of expected {exp['size_mb']}MB"
            )
