"""Step 3a validation: FragPipe first pass against mock data."""

import time
import shutil
import pytest
from pathlib import Path
from src.tarsus.steps.step03a_first_pass import step03a_first_pass
from .conftest import load_expected, capture_expected

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.lsf
def test_step03a_first_pass(mock_data, tool_env):
    """Run FragPipe first pass on mock mzML — verify PSM output exists."""
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

        psm_tsv = result / "psm.tsv"
        peptide_tsv = result / "peptide.tsv"
        actual = {
            "output_dir_exists": result.is_dir(),
            "psm_exists": psm_tsv.is_file(),
            "peptide_exists": peptide_tsv.is_file(),
            "psm_size_kb": psm_tsv.stat().st_size // 1024 if psm_tsv.is_file() else 0,
        }

        expected = load_expected("step03a")
        if expected is None:
            capture_expected("step03a", actual)
            pytest.skip("Expected output captured — re-run to validate")
        else:
            assert actual["psm_exists"], "psm.tsv not created"
            assert actual["peptide_exists"], "peptide.tsv not created"
            for key, val in expected.items():
                assert actual.get(key) >= val * 0.5, f"step03a.{key}: {actual.get(key)} < 50% of expected {val}"
    finally:
        if shared.exists():
            shutil.rmtree(shared, ignore_errors=True)
