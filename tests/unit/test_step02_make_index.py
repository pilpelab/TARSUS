"""Unit tests for Step 2 — PepQuery index.

Tests cover:
  - Input validation (missing dir, empty dir, missing JAR, missing Java)
  - Command construction (bsub command structure)
  - Edge cases (empty output dir, mixed files)
"""

from pathlib import Path
import pytest
from src.tarsus.steps.step02_make_index import step02_make_index
from src.tarsus.env import ToolEnvironment


class TestInputValidation:
    def test_missing_mzml_dir(self, tmp_path: Path) -> None:
        env = ToolEnvironment(tools_dir=tmp_path)
        output = tmp_path / "output"
        missing = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError, match="mzML directory not found"):
            step02_make_index(missing, output, env)

    def test_empty_mzml_dir(self, tmp_path: Path) -> None:
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        output = tmp_path / "output"
        with pytest.raises(FileNotFoundError, match="No .mzML files found"):
            step02_make_index(mzml_dir, output, env)

    def test_no_pepquery_jar(self, tmp_path: Path) -> None:
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"
        with pytest.raises(FileNotFoundError, match="PepQuery JAR not found"):
            step02_make_index(mzml_dir, output, env)

    def test_no_java_bin(self, tmp_path: Path) -> None:
        pq_dir = tmp_path / "pepquery-2.0.2"
        pq_dir.mkdir()
        (pq_dir / "pepquery-2.0.2.jar").touch()
        env = ToolEnvironment(tools_dir=tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"
        with pytest.raises(FileNotFoundError, match="Java binary not found"):
            step02_make_index(mzml_dir, output, env)


class TestCommandConstruction:
    def _make_env(self, tmp_path: Path) -> ToolEnvironment:
        """Create a valid ToolEnvironment with stubs for all required tools."""
        (tmp_path / "jdk-21.0.11" / "bin").mkdir(parents=True)
        (tmp_path / "jdk-21.0.11" / "bin" / "java").touch()
        pq_dir = tmp_path / "pepquery-2.0.2"
        pq_dir.mkdir()
        (pq_dir / "pepquery-2.0.2.jar").touch()
        return ToolEnvironment(tools_dir=tmp_path)

    def test_submits_basic_job(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = self._make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"

        submitted_cmds: list[list[str]] = []

        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted_cmds.append(cmd)
            return 12345

        def fake_wait(job_ids: list[int]) -> None:
            return

        monkeypatch.setattr("src.tarsus.steps.step02_make_index.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step02_make_index.wait_for_jobs", fake_wait)

        (output / "pepquery_index").mkdir(parents=True)
        (output / "pepquery_index" / "index.dat").touch()

        step02_make_index(mzml_dir, output, env)

        assert len(submitted_cmds) == 1
        cmd = submitted_cmds[0]
        assert "java" in str(cmd[0])
        assert "-Xmx4096m" in cmd
        assert "-jar" in cmd
        assert "pepquery-2.0.2.jar" in str(cmd[3])
        assert "index" in cmd
        assert "-r" in cmd
        assert "-i" in cmd
        assert str(mzml_dir.resolve()) in cmd
        assert "-o" in cmd
        assert str(output / "pepquery_index") in cmd

    def test_java_heap_configurable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = self._make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"

        submitted_cmds: list[list[str]] = []

        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted_cmds.append(cmd)
            return 12345

        def fake_wait(job_ids: list[int]) -> None:
            return

        monkeypatch.setattr("src.tarsus.steps.step02_make_index.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step02_make_index.wait_for_jobs", fake_wait)

        (output / "pepquery_index").mkdir(parents=True)
        (output / "pepquery_index" / "index.dat").touch()

        step02_make_index(mzml_dir, output, env, java_heap_mb=8192)
        cmd = submitted_cmds[0]
        assert "-Xmx8192m" in cmd

    def test_index_dir_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = self._make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"

        def fake_submit_2(cmd: list[str], **kw: object) -> int:
            return 12345

        def fake_wait_2(job_ids: list[int]) -> None:
            pass

        monkeypatch.setattr("src.tarsus.steps.step02_make_index.submit_bsub", fake_submit_2)
        monkeypatch.setattr("src.tarsus.steps.step02_make_index.wait_for_jobs", fake_wait_2)

        (output / "pepquery_index").mkdir(parents=True)
        (output / "pepquery_index" / "index.dat").touch()

        result = step02_make_index(mzml_dir, output, env)
        assert result == output / "pepquery_index"
        assert result.is_dir()

    def test_empty_index_dir_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env = self._make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "test.mzML").touch()
        output = tmp_path / "output"

        def fake_submit_3(cmd: list[str], **kw: object) -> int:
            return 12345

        def fake_wait_3(job_ids: list[int]) -> None:
            pass

        monkeypatch.setattr("src.tarsus.steps.step02_make_index.submit_bsub", fake_submit_3)
        monkeypatch.setattr("src.tarsus.steps.step02_make_index.wait_for_jobs", fake_wait_3)

        (output / "pepquery_index").mkdir(parents=True)

        with pytest.raises(RuntimeError, match="PepQuery index not created"):
            step02_make_index(mzml_dir, output, env)
