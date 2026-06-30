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
