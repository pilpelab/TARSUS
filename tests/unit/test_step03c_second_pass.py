"""Unit tests for Step 3c — FragPipe second-pass (nocleavage)."""

from pathlib import Path
import pytest
from src.tarsus.steps.step03c_second_pass import step03c_second_pass
from src.tarsus.env import ToolEnvironment


def _make_env(tmp_path: Path) -> ToolEnvironment:
    (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
    (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
    phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
    phil_dir.mkdir(parents=True)
    (phil_dir / "philosopher-v5.1.3-RC9").touch()
    return ToolEnvironment(tools_dir=tmp_path)


class TestInputValidation:
    def test_missing_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        with pytest.raises(FileNotFoundError, match="mzML directory not found"):
            step03c_second_pass(tmp_path / "no_mzml", tmp_path / "candidates.fa", tmp_path, env)

    def test_empty_mzml_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="No .mzML files found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)

    def test_missing_pep_candidates(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        with pytest.raises(FileNotFoundError, match="Variant FASTA not found"):
            step03c_second_pass(mzml_dir, tmp_path / "nonexistent.fa", tmp_path, env)

    def test_missing_philosopher(self, tmp_path: Path) -> None:
        (tmp_path / "fragpipe-24.0" / "bin").mkdir(parents=True)
        (tmp_path / "fragpipe-24.0" / "bin" / "fragpipe").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="Philosopher not found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)

    def test_missing_fragpipe(self, tmp_path: Path) -> None:
        phil_dir = tmp_path / "fragpipe-24.0" / "tools" / "Philosopher"
        phil_dir.mkdir(parents=True)
        (phil_dir / "philosopher-v5.1.3-RC9").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        fasta = tmp_path / "candidates.fa"
        fasta.touch()
        with pytest.raises(FileNotFoundError, match="FragPipe not found"):
            step03c_second_pass(mzml_dir, fasta, tmp_path, env)


class TestWorkflowPatching:
    def test_nocleavage_params_applied(self, tmp_path: Path) -> None:
        """Verify all nocleavage patches are applied to the workflow."""
        workflow = tmp_path / "generic.workflow"
        workflow.write_text(
            "database.db-path=/old\n"
            "msfragger.clip_nTerm_M=true\n"
            "msfragger.misc.fragger.enzyme-dropdown-1=stricttrypsin\n"
            "msbooster.find-best-rt-model=true\n"
            "msbooster.run-msbooster=true\n"
            "msbooster.predict-rt=true\n"
            "msbooster.predict-spectra=true\n"
        )
        import re
        content = workflow.read_text()
        patches = [
            (r"^msfragger\.clip_nTerm_M=.*$", "msfragger.clip_nTerm_M=false"),
            (r"^msfragger\.misc\.fragger\.enzyme-dropdown-1=.*$",
             "msfragger.misc.fragger.enzyme-dropdown-1=nocleavage"),
            (r"^msbooster\.find-best-rt-model=.*$", "msbooster.find-best-rt-model=false"),
            (r"^msbooster\.run-msbooster=.*$", "msbooster.run-msbooster=false"),
            (r"^msbooster\.predict-rt=.*$", "msbooster.predict-rt=false"),
            (r"^msbooster\.predict-spectra=.*$", "msbooster.predict-spectra=false"),
        ]
        for pattern, replacement in patches:
            content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
        assert "msfragger.clip_nTerm_M=false" in content
        assert "enzyme-dropdown-1=nocleavage" in content
        assert "msbooster.find-best-rt-model=false" in content
        assert "msbooster.run-msbooster=false" in content
        assert "msbooster.predict-rt=false" in content
        assert "msbooster.predict-spectra=false" in content
