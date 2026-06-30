"""Unit tests for Step 2 — PepQuery index (per-file parallel).

Tests cover:
  - Input validation (missing dir, empty dir, missing JAR, missing Java)
  - Command construction (one bsub job per mzML file)
  - Merge logic (per-file fragments → unified pepquery_index/)
  - Heap/memory auto-scaling
  - Edge cases
"""

from pathlib import Path
import pytest
from src.tarsus.steps.step02_make_index import (
    step02_make_index, _resolve_heap_mb, _resolve_mem_mb,
    _MIN_HEAP_MB, _MAX_HEAP_MB,
)
from src.tarsus.env import ToolEnvironment


class TestHeapAutoScale:
    def test_small_file_uses_min(self) -> None:
        assert _resolve_heap_mb(None, _size_gb=1) == _MIN_HEAP_MB  # type: ignore

    def test_medium_file_scales(self) -> None:
        heap = _resolve_heap_mb(None, _size_gb=5)  # type: ignore
        assert heap == 10240  # 5 GB × 2 × 1024

    def test_large_file_clamped(self) -> None:
        heap = _resolve_heap_mb(None, _size_gb=15)  # type: ignore
        assert heap == _MAX_HEAP_MB  # clamped to 24 GB

    def test_explicit_overrides(self) -> None:
        assert _resolve_heap_mb(None, java_heap_mb=4096, _size_gb=10) == 4096  # type: ignore

    def test_env_var_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TARSUS_PEPQUERY_HEAP_MB", "32768")
        assert _resolve_heap_mb(None, _size_gb=10) == 32768  # type: ignore


class TestMemAutoScale:
    def test_mem_from_heap(self) -> None:
        assert _resolve_mem_mb(8192) == 12288  # 8192 + 4096

    def test_mem_explicit_overrides(self) -> None:
        assert _resolve_mem_mb(8192, memory_mb=16000) == 16000


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
        """Create flat .mgf.gz files PepQuery writes directly in staging dir."""
        staging = output / "_staging" / mzml_stem
        staging.mkdir(parents=True)
        (staging / "1.mgf.gz").touch()
        (staging / "2.mgf.gz").touch()

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
        assert "-Xmx8192m" in cmd  # auto-scaled: 0-byte file → minimum 8 GB
        assert "-jar" in cmd
        assert "pepquery-2.0.2.jar" in str(cmd[3])
        assert "index" in cmd
        assert "-r" in cmd  # required for per-file tmp/ output format
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
        with pytest.raises(RuntimeError, match="No .mgf.gz files in staging"):
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
