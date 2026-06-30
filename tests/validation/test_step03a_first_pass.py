"""Step 3a validation: FragPipe first pass — verify pipeline wiring."""

import time
import shutil
import pytest
from pathlib import Path
from src.tarsus.steps.step03a_first_pass import step03a_first_pass
from .conftest import load_expected, capture_expected

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.lsf
def test_step03a_first_pass(mock_data, tool_env):
    """Run FragPipe first pass on mock mzML — verify wiring, not PSMs."""
    fasta = mock_data["fasta"]
    mzml = mock_data["mzml"]
    assert fasta.is_file()
    assert mzml.is_file()

    run_id = f"step3a_{int(time.time())}_{id(mzml)}"
    shared = PROJECT_ROOT / "output" / "_val" / run_id

    mzml_dir = shared / "01_mzml"
    mzml_dir.mkdir(parents=True, exist_ok=True)
    (mzml_dir / mzml.name).symlink_to(mzml.resolve())

    output_dir = shared / "03a_first_pass"

    try:
        result = step03a_first_pass(fasta, mzml_dir, output_dir, tool_env)

        actual = {
            "output_dir_exists": result.is_dir(),
            "workflow_exists": (result / "first.workflow").is_file(),
            "manifest_exists": (result / "first.manifest").is_file(),
            "runner_exists": (result / "step03a_runner.sh").is_file(),
        }
        psm_tsv = result / "psm.tsv"
        if psm_tsv.is_file():
            actual["psm_size_kb"] = psm_tsv.stat().st_size // 1024

        expected = load_expected("step03a")
        if expected is None:
            capture_expected("step03a", actual)
            pytest.skip("Expected output captured — re-run to validate")
        else:
            assert actual["output_dir_exists"], "Output dir not created"
            assert actual["workflow_exists"], "Workflow file not created"
            assert actual["manifest_exists"], "Manifest file not created"
            assert actual["runner_exists"], "Runner script not created"
            if "psm_size_kb" in expected:
                assert actual.get("psm_size_kb", 0) >= expected["psm_size_kb"] * 0.5, \
                    f"psm.tsv too small: {actual.get('psm_size_kb', 0)}KB < 50% of {expected['psm_size_kb']}KB"
    finally:
        if shared.exists():
            shutil.rmtree(shared, ignore_errors=True)
