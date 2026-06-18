"""Unit tests for Step 6 — PEPQuery result aggregation and PDV."""

from pathlib import Path
import pytest
from src.tarsus.steps.step06_aggregate_query import step06_aggregate_query
from src.tarsus.env import ToolEnvironment


def _make_env(tmp_path: Path) -> ToolEnvironment:
    (tmp_path / "jdk-21.0.11" / "bin").mkdir(parents=True)
    (tmp_path / "jdk-21.0.11" / "bin" / "java").touch()
    (tmp_path / "PDV-2.2.3").mkdir()
    (tmp_path / "PDV-2.2.3" / "PDV-2.2.3.jar").touch()
    return ToolEnvironment(tools_dir=tmp_path)


class TestInputValidation:
    def test_missing_result_dir(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        with pytest.raises(FileNotFoundError, match="PepQuery result directory not found"):
            step06_aggregate_query(tmp_path / "no_results", tmp_path, env)

    def test_no_rank_files(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        with pytest.raises(RuntimeError, match="No psm_rank.txt files"):
            step06_aggregate_query(result_dir, tmp_path, env)


class TestConcatenation:
    def test_writes_psmrankall(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        (result_dir / "chunk1").mkdir(parents=True)
        (result_dir / "chunk1" / "psm_rank.txt").write_text(
            "col1\tcol2\nval1\tval2\n"
        )
        (result_dir / "chunk2").mkdir(parents=True)
        (result_dir / "chunk2" / "psm_rank.txt").write_text(
            "col1\tcol2\nval3\tval4\n"
        )

        with pytest.raises(Exception):  # will fail on PDV call, but concat happens first
            step06_aggregate_query(result_dir, tmp_path, env)

        psm = tmp_path / "psmrankall.txt"
        assert psm.is_file()
        content = psm.read_text()
        assert "val1\tval2" in content
        assert "val3\tval4" in content
        # Header should appear only once
        assert content.count("col1\tcol2") == 1

    def test_writes_peptides(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        (result_dir / "chunk1").mkdir(parents=True)
        (result_dir / "chunk1" / "psm_rank.txt").write_text(
            "peptide\tscore\nPEP1\t0.9\nPEP2\t0.8\n"
        )

        with pytest.raises(Exception):
            step06_aggregate_query(result_dir, tmp_path, env)

        pep = tmp_path / "peptides.txt"
        assert pep.is_file()
        lines = pep.read_text().strip().split("\n")
        assert "PEP1" in lines
        assert "PEP2" in lines
        assert "peptide" not in lines

    def test_handles_empty_dirs(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        (result_dir / "empty_chunk").mkdir()

        with pytest.raises(RuntimeError, match="No psm_rank.txt files"):
            step06_aggregate_query(result_dir, tmp_path, env)
