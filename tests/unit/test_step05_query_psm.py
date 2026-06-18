"""Unit tests for Step 5 — PepQuery PSM validation."""

from pathlib import Path
import pytest
from src.tarsus.steps.step05_query_psm import step05_query_psm
from src.tarsus.env import ToolEnvironment


def _make_env(tmp_path: Path) -> ToolEnvironment:
    (tmp_path / "jdk-21.0.11" / "bin").mkdir(parents=True)
    (tmp_path / "jdk-21.0.11" / "bin" / "java").touch()
    pq_dir = tmp_path / "pepquery-2.0.2"
    pq_dir.mkdir()
    (pq_dir / "pepquery-2.0.2.jar").touch()
    return ToolEnvironment(tools_dir=tmp_path)


class TestInputValidation:
    def test_missing_psm_input(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        with pytest.raises(FileNotFoundError, match="PSM input not found"):
            step05_query_psm(
                tmp_path / "nonexistent.tsv", tmp_path / "index",
                tmp_path, env,
            )

    def test_missing_index(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        psm = tmp_path / "input.tsv"
        psm.touch()
        with pytest.raises(FileNotFoundError, match="PepQuery index not found"):
            step05_query_psm(psm, tmp_path / "no_index", tmp_path, env)

    def test_missing_pepquery_jar(self, tmp_path: Path) -> None:
        env = ToolEnvironment(tools_dir=tmp_path)
        psm = tmp_path / "input.tsv"
        psm.touch()
        index = tmp_path / "index"
        index.mkdir()
        with pytest.raises(FileNotFoundError, match="PepQuery JAR not found"):
            step05_query_psm(psm, index, tmp_path, env)

    def test_empty_psm_file(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        psm = tmp_path / "input.tsv"
        psm.write_text("peptide\tspectrum_title\n")
        index = tmp_path / "index"
        index.mkdir()
        with pytest.raises(ValueError, match="no data rows"):
            step05_query_psm(psm, index, tmp_path, env)


class TestChunking:
    def test_single_chunk(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = _make_env(tmp_path)
        psm = tmp_path / "input.tsv"
        psm.write_text("peptide\tspectrum_title\nPEP1\tspec1\n")
        index = tmp_path / "index"
        index.mkdir()

        submitted: list[list[str]] = []
        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted.append(cmd)
            return 1
        def fake_wait(job_ids: list[int]) -> None:
            pass
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.wait_for_jobs", fake_wait)

        # Stub output to pass validation
        (tmp_path / "pepquery_result" / "chunk_0000").mkdir(parents=True)
        (tmp_path / "pepquery_result" / "chunk_0000" / "psm_rank.txt").touch()

        step05_query_psm(psm, index, tmp_path, env)
        assert len(submitted) == 1
        cmd = submitted[0]
        assert "pepquery-2.0.2.jar" in str(cmd[3])
        assert "-i" in cmd
        assert "-o" in cmd

    def test_multiple_chunks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = _make_env(tmp_path)
        psm = tmp_path / "input.tsv"
        lines = ["peptide\tspectrum_title"]
        for i in range(25):
            lines.append(f"PEP{i}\tspec{i}")
        psm.write_text("\n".join(lines) + "\n")
        index = tmp_path / "index"
        index.mkdir()

        submitted: list[list[str]] = []
        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted.append(cmd)
            return len(submitted)
        def fake_wait(job_ids: list[int]) -> None:
            pass
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.wait_for_jobs", fake_wait)

        # Stub all 3 output dirs (25 rows → 3 chunks of 10)
        for i in range(3):
            (tmp_path / "pepquery_result" / f"chunk_{i:04d}").mkdir(parents=True)
            (tmp_path / "pepquery_result" / f"chunk_{i:04d}" / "psm_rank.txt").touch()

        step05_query_psm(psm, index, tmp_path, env, chunk_size=10)
        assert len(submitted) == 3

    def test_chunk_files_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = _make_env(tmp_path)
        psm = tmp_path / "input.tsv"
        psm.write_text("peptide\tspectrum_title\nPEP1\tspec1\nPEP2\tspec2\n")
        index = tmp_path / "index"
        index.mkdir()

        def fake_submit(cmd: list[str], **kw: object) -> int:
            return 1
        def fake_wait(job_ids: list[int]) -> None:
            pass
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step05_query_psm.wait_for_jobs", fake_wait)

        (tmp_path / "pepquery_result" / "chunk_0000").mkdir(parents=True)
        (tmp_path / "pepquery_result" / "chunk_0000" / "psm_rank.txt").touch()

        step05_query_psm(psm, index, tmp_path, env, chunk_size=10)
        inputs_dir = tmp_path / "pepquery_inputs"
        assert inputs_dir.is_dir()
        chunk_files = sorted(inputs_dir.glob("*.tsv"))
        assert len(chunk_files) == 1
        content = chunk_files[0].read_text()
        assert "peptide\tspectrum_title" in content
        assert "PEP1" in content
        assert "PEP2" in content
