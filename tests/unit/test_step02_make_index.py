"""Unit tests for Step 2 — PepQuery index (per-file parallel).

Tests cover:
  - Input validation (missing dir, empty dir, missing JAR, missing Java)
  - Command construction (one bsub job per mzML file)
  - Merge logic (per-file fragments → unified pepquery_index/)
  - Edge cases
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

    def _make_staging_output(self, output: Path, mzml_stem: str) -> None:
        """Create the staging tmp/ directory PepQuery would produce."""
        frag_dir = output / "_staging" / mzml_stem / "tmp" / f"{mzml_stem}.mzML_0"
        frag_dir.mkdir(parents=True)
        (frag_dir / "1.mgf").touch()

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

        self._make_staging_output(output, "test")

        step02_make_index(mzml_dir, output, env)

        assert len(submitted_cmds) == 1  # one job per mzML file
        cmd = submitted_cmds[0]
        assert "java" in str(cmd[0])
        assert "-Xmx8192m" in cmd  # default java_heap_mb=8192
        assert "-jar" in cmd
        assert "pepquery-2.0.2.jar" in str(cmd[3])
        assert "index" in cmd
        assert "-i" in cmd
        assert str((mzml_dir / "test.mzML").resolve()) in cmd  # per-file path, not dir
        assert "-o" in cmd
        assert str(output / "_staging" / "test") in cmd  # staging directory

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

        self._make_staging_output(output, "test")

        step02_make_index(mzml_dir, output, env, java_heap_mb=12288)
        cmd = submitted_cmds[0]
        assert "-Xmx12288m" in cmd

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

        self._make_staging_output(output, "test")

        result = step02_make_index(mzml_dir, output, env)
        assert result == output / "pepquery_index"
        assert result.is_dir()

    def test_empty_staging_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

        # No staging output created → merge should fail
        with pytest.raises(RuntimeError, match="PepQuery index tmp/ not created"):
            step02_make_index(mzml_dir, output, env)

    def test_two_files_parallel(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Two mzML files → two parallel LSF jobs, each with per-file -i path."""
        env = self._make_env(tmp_path)
        mzml_dir = tmp_path / "mzml"
        mzml_dir.mkdir()
        (mzml_dir / "file_a.mzML").touch()
        (mzml_dir / "file_b.mzML").touch()
        output = tmp_path / "output"

        submitted_cmds: list[list[str]] = []

        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted_cmds.append(cmd)
            return len(submitted_cmds) + 1000

        def fake_wait(job_ids: list[int]) -> None:
            return

        monkeypatch.setattr("src.tarsus.steps.step02_make_index.submit_bsub", fake_submit)
        monkeypatch.setattr("src.tarsus.steps.step02_make_index.wait_for_jobs", fake_wait)

        self._make_staging_output(output, "file_a")
        self._make_staging_output(output, "file_b")

        step02_make_index(mzml_dir, output, env)

        assert len(submitted_cmds) == 2, "Two mzML files → two parallel jobs"
        # Each job's -i should point to its own single file
        assert str(mzml_dir / "file_a.mzML") in str(submitted_cmds[0])
        assert str(mzml_dir / "file_b.mzML") in str(submitted_cmds[1])
