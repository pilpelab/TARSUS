"""Step 2 validation: PepQuery index against mock data."""

import time
import shutil
import pytest
from pathlib import Path
from src.tarsus.steps.step02_make_index import step02_make_index
from .conftest import load_expected, capture_expected

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.lsf
def test_step02_index(mock_data, tool_env):
    """Build PepQuery index from mock mzML and verify output exists."""
    mzml = mock_data["mzml"]
    assert mzml.is_file(), f"Mock mzML not found: {mzml}"

    run_id = f"step2_{int(time.time())}_{id(mzml)}"
    shared = PROJECT_ROOT / "output" / "_val" / run_id

    mzml_dir = shared / "01_mzml"
    mzml_dir.mkdir(parents=True, exist_ok=True)
    (mzml_dir / mzml.name).symlink_to(mzml.resolve())

    output_dir = shared / "02_index"

    try:
        result = step02_make_index(mzml_dir, output_dir, tool_env)

        tmp_dir = result / "tmp"
        actual = {
            "index_dir_exists": result.is_dir(),
            "tmp_exists": tmp_dir.is_dir(),
            "fragment_count": len(list(tmp_dir.iterdir())) if tmp_dir.is_dir() else 0,
        }

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
    finally:
        if shared.exists():
            shutil.rmtree(shared, ignore_errors=True)
