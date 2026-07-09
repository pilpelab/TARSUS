"""Unit tests for Step 6 — PEPQuery result aggregation and PDV."""

from pathlib import Path
import pytest
from src.tarsus.steps.step06_aggregate_query import (
    step06_aggregate_query,
    _group_chunk_rows,
    _run_pdv_sharded,
    _check_shard_memory,
    DEFAULT_JAVA_HEAP_MB,
    DEFAULT_MEMORY_MB,
    DEFAULT_CHUNK_SIZE,
)
from src.tarsus.env import ToolEnvironment


class TestShardMemory:
    """Regression: the JVM heap must fit inside the LSF reservation.

    Step 6 shipped with java_heap_mb=4096 inside memory_mb=4000, so every PDV
    shard was killed with TERM_MEMLIMIT the moment the heap filled. It went
    unnoticed because open-search psmrankall.txt had ~4x row duplication per
    spectrum, so a 20k-row shard rendered far fewer distinct spectra.
    """

    def test_defaults_leave_headroom(self) -> None:
        _check_shard_memory(DEFAULT_JAVA_HEAP_MB, DEFAULT_MEMORY_MB)

    def test_heap_exceeding_reservation_raises(self) -> None:
        with pytest.raises(ValueError, match="JVM heap"):
            _check_shard_memory(java_heap_mb=4096, memory_mb=4000)

    def test_heap_equal_to_reservation_raises(self) -> None:
        with pytest.raises(ValueError, match="JVM heap"):
            _check_shard_memory(java_heap_mb=4000, memory_mb=4000)

    def test_insufficient_headroom_raises(self) -> None:
        # JVM non-heap (metaspace, thread stacks, native) plus the Python parent
        # need real room; a token 100 MB margin is not enough.
        with pytest.raises(ValueError, match="JVM heap"):
            _check_shard_memory(java_heap_mb=4000, memory_mb=4100)

    def test_ample_headroom_passes(self) -> None:
        _check_shard_memory(java_heap_mb=4096, memory_mb=8000)


class TestShardCountAtRealScale:
    """Targeted-mode psmrankall has ~1 row per spectrum, unlike open search."""

    HEADER = "peptide\tmodification\tn\tspectrum_title"

    def test_real_row_count_produces_multiple_shards(self) -> None:
        # 19,914 rows is the actual targeted-mode count for the trial dataset.
        rows = [f"PEP{i}\t-\t1\tf:{i}:2" for i in range(19_914)]
        chunks = _group_chunk_rows(self.HEADER, rows, chunk_size=DEFAULT_CHUNK_SIZE)
        assert len(chunks) > 1, "must shard, or PDV runs single-threaded and OOMs"
        assert all(len(c) <= DEFAULT_CHUNK_SIZE for c in chunks)
        assert sum(len(c) for c in chunks) == 19_914


def _make_env(tmp_path: Path) -> ToolEnvironment:
    (tmp_path / "jdk-21.0.11" / "bin").mkdir(parents=True)
    (tmp_path / "jdk-21.0.11" / "bin" / "java").touch()
    (tmp_path / "PDV-2.1.2").mkdir()
    (tmp_path / "PDV-2.1.2" / "PDV-2.1.2.jar").touch()
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
    """Test the pure-Python concatenation logic (steps 1-4), never reaching
    real LSF or real Xvfb — parallel=False + a fake $DISPLAY short-circuits
    XvfbDisplay to its "use existing display" branch (no subprocess spawned),
    and the dummy non-executable 'java' stub fails fast on exec.
    """

    def test_writes_psmrankall(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DISPLAY", ":0")
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
            step06_aggregate_query(result_dir, tmp_path, env, parallel=False)

        psm = tmp_path / "psmrankall.txt"
        assert psm.is_file()
        content = psm.read_text()
        assert "val1\tval2" in content
        assert "val3\tval4" in content
        # Header should appear only once
        assert content.count("col1\tcol2") == 1

    def test_writes_peptides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DISPLAY", ":0")
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        (result_dir / "chunk1").mkdir(parents=True)
        (result_dir / "chunk1" / "psm_rank.txt").write_text(
            "peptide\tscore\nPEP1\t0.9\nPEP2\t0.8\n"
        )

        with pytest.raises(Exception):
            step06_aggregate_query(result_dir, tmp_path, env, parallel=False)

        pep = tmp_path / "peptides.txt"
        assert pep.is_file()
        lines = pep.read_text().strip().split("\n")
        assert "PEP1" in lines
        assert "PEP2" in lines
        assert "peptide" not in lines

    def test_drops_blank_lines_from_zero_match_chunks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression test for D-038: header-only chunk must not leave a
        blank line in the merged psmrankall.txt (PDV crashes on blank lines).
        """
        monkeypatch.setenv("DISPLAY", ":0")
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        (result_dir / "chunk1").mkdir(parents=True)
        (result_dir / "chunk1" / "psm_rank.txt").write_text("col1\tcol2\nval1\tval2\n")
        # Zero-match chunk: header only
        (result_dir / "chunk2").mkdir(parents=True)
        (result_dir / "chunk2" / "psm_rank.txt").write_text("col1\tcol2\n")
        (result_dir / "chunk3").mkdir(parents=True)
        (result_dir / "chunk3" / "psm_rank.txt").write_text("col1\tcol2\nval3\tval4\n")

        with pytest.raises(Exception):
            step06_aggregate_query(result_dir, tmp_path, env, parallel=False)

        psm = tmp_path / "psmrankall.txt"
        lines = psm.read_text().split("\n")
        assert "" not in [line for line in lines if line != lines[-1]] or all(
            line.strip() for line in lines if line
        )
        assert all(line.strip() != "" for line in lines[:-1])

    def test_handles_empty_dirs(self, tmp_path: Path) -> None:
        env = _make_env(tmp_path)
        result_dir = tmp_path / "results"
        result_dir.mkdir()
        (result_dir / "empty_chunk").mkdir()

        with pytest.raises(RuntimeError, match="No psm_rank.txt files"):
            step06_aggregate_query(result_dir, tmp_path, env)


class TestGroupChunkRows:
    """Pure-function tests for the spectrum_title-aware chunking (no I/O)."""

    HEADER = "peptide\tmodification\tn\tspectrum_title\tcharge"

    def test_keeps_same_spectrum_title_together(self) -> None:
        rows = [
            "PEP1\tmod1\t1\tspecA\t2",
            "PEP1\tmod2\t1\tspecA\t2",  # duplicate spectrum_title, different mod
            "PEP2\tmod1\t1\tspecB\t2",
        ]
        chunks = _group_chunk_rows(self.HEADER, rows, chunk_size=1)
        # Even with chunk_size=1, both specA rows must land in the same chunk
        specA_chunks = [c for c in chunks if any("specA" in r for r in c)]
        assert len(specA_chunks) == 1
        assert len(specA_chunks[0]) == 2

    def test_respects_chunk_size_across_groups(self) -> None:
        rows = [f"PEP{i}\tmod\t1\tspec{i}\t2" for i in range(10)]
        chunks = _group_chunk_rows(self.HEADER, rows, chunk_size=3)
        assert sum(len(c) for c in chunks) == 10
        for c in chunks[:-1]:
            assert len(c) <= 3

    def test_oversized_group_gets_own_chunk(self) -> None:
        # A single spectrum_title with more rows than chunk_size must still
        # end up in one chunk (never split), even though it exceeds the
        # nominal chunk_size.
        rows = [f"PEP{i}\tmod\t1\tspecA\t2" for i in range(5)]
        chunks = _group_chunk_rows(self.HEADER, rows, chunk_size=2)
        assert len(chunks) == 1
        assert len(chunks[0]) == 5

    def test_empty_rows(self) -> None:
        assert _group_chunk_rows(self.HEADER, [], chunk_size=10) == []


class TestPdvSharded:
    """Tests for _run_pdv_sharded with submit_bsub/wait_for_jobs mocked out
    (following the same pattern as test_step05_query_psm.py) — never touches
    real LSF.
    """

    def _setup(self, tmp_path: Path) -> ToolEnvironment:
        return _make_env(tmp_path)

    def test_submits_one_job_per_shard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = self._setup(tmp_path)
        psmrankall = tmp_path / "psmrankall.txt"
        psmrankall.write_text(
            "peptide\tmodification\tn\tspectrum_title\tcharge\n"
            "PEP1\tmod\t1\tspecA\t2\n"
            "PEP2\tmod\t1\tspecB\t2\n"
        )
        peptides = tmp_path / "peptides.txt"
        peptides.write_text("PEP1\nPEP2\n")
        mgf_path = tmp_path / "mgfall.mgf"
        mgf_path.write_text("")
        pdv_spectra = tmp_path / "pdv_spectra"
        output_dir = tmp_path

        submitted: list[list[str]] = []

        def fake_submit(cmd: list[str], **kw: object) -> int:
            submitted.append(cmd)
            return len(submitted)

        def fake_wait(job_ids: list[int]) -> None:
            # Simulate each shard producing a result before we "wait".
            # Shard directories aren't created until the (real) worker
            # process runs, so create them here by their deterministic name.
            for idx in range(len(job_ids)):
                shard_dir = tmp_path / "pdv_spectra_shards" / f"shard_{idx:04d}"
                shard_dir.mkdir(parents=True, exist_ok=True)
                (shard_dir / "PDVExportResult.txt").write_text(
                    "Spectrum_Title\tpeptide\tcharge\n" + "spec\tPEP\t2\n"
                )

        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.submit_bsub", fake_submit,
        )
        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.wait_for_jobs", fake_wait,
        )

        _run_pdv_sharded(
            psmrankall=psmrankall, peptides=peptides, mgf_path=mgf_path,
            pdv_spectra=pdv_spectra, output_dir=output_dir, tool_env=env,
            java_heap_mb=4096, chunk_size=1, queue="gsla-cpu",
            memory_mb=4000, cpus=1, shard_timeout=100,
        )

        # 2 unique spectrum_titles, chunk_size=1 -> 2 shards -> 2 submissions
        assert len(submitted) == 2
        for cmd in submitted:
            assert "tarsus.steps._pdv_worker" in cmd

    def test_resume_skips_completed_shards(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = self._setup(tmp_path)
        psmrankall = tmp_path / "psmrankall.txt"
        psmrankall.write_text(
            "peptide\tmodification\tn\tspectrum_title\tcharge\n"
            "PEP1\tmod\t1\tspecA\t2\n"
        )
        peptides = tmp_path / "peptides.txt"
        peptides.write_text("PEP1\n")
        mgf_path = tmp_path / "mgfall.mgf"
        mgf_path.write_text("")
        pdv_spectra = tmp_path / "pdv_spectra"

        # Pre-populate the shard as already-completed
        shard_dir = tmp_path / "pdv_spectra_shards" / "shard_0000"
        shard_dir.mkdir(parents=True)
        (shard_dir / "PDVExportResult.txt").write_text(
            "Spectrum_Title\tpeptide\tcharge\nspecA\tPEP1\t2\n"
        )

        submitted: list[list[str]] = []
        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.submit_bsub",
            lambda cmd, **kw: submitted.append(cmd) or 1,
        )
        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.wait_for_jobs", lambda job_ids: None,
        )

        _run_pdv_sharded(
            psmrankall=psmrankall, peptides=peptides, mgf_path=mgf_path,
            pdv_spectra=pdv_spectra, output_dir=tmp_path, tool_env=env,
            java_heap_mb=4096, chunk_size=10, queue="gsla-cpu",
            memory_mb=4000, cpus=1, shard_timeout=100,
        )

        assert submitted == []  # already-done shard was skipped
        assert (pdv_spectra / "PDVExportResult.txt").is_file()

    def test_merge_concatenates_export_and_moves_pdfs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = self._setup(tmp_path)
        psmrankall = tmp_path / "psmrankall.txt"
        psmrankall.write_text(
            "peptide\tmodification\tn\tspectrum_title\tcharge\n"
            "PEP1\tmod\t1\tspecA\t2\n"
            "PEP2\tmod\t1\tspecB\t2\n"
        )
        peptides = tmp_path / "peptides.txt"
        peptides.write_text("PEP1\nPEP2\n")
        mgf_path = tmp_path / "mgfall.mgf"
        mgf_path.write_text("")
        pdv_spectra = tmp_path / "pdv_spectra"

        def fake_submit(cmd: list[str], **kw: object) -> int:
            return 1

        def fake_wait(job_ids: list[int]) -> None:
            shard0 = tmp_path / "pdv_spectra_shards" / "shard_0000"
            shard0.mkdir(parents=True, exist_ok=True)
            (shard0 / "PDVExportResult.txt").write_text(
                "Spectrum_Title\tpeptide\tcharge\nspecA\tPEP1\t2\n"
            )
            (shard0 / "specA_PEP1.pdf").write_text("fake pdf 1")

            shard1 = tmp_path / "pdv_spectra_shards" / "shard_0001"
            shard1.mkdir(parents=True, exist_ok=True)
            (shard1 / "PDVExportResult.txt").write_text(
                "Spectrum_Title\tpeptide\tcharge\nspecB\tPEP2\t2\n"
            )
            (shard1 / "specB_PEP2.pdf").write_text("fake pdf 2")

        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.submit_bsub", fake_submit,
        )
        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.wait_for_jobs", fake_wait,
        )

        _run_pdv_sharded(
            psmrankall=psmrankall, peptides=peptides, mgf_path=mgf_path,
            pdv_spectra=pdv_spectra, output_dir=tmp_path, tool_env=env,
            java_heap_mb=4096, chunk_size=1, queue="gsla-cpu",
            memory_mb=4000, cpus=1, shard_timeout=100,
        )

        merged = (pdv_spectra / "PDVExportResult.txt").read_text()
        assert merged.count("Spectrum_Title\tpeptide\tcharge") == 1  # header once
        assert "specA\tPEP1\t2" in merged
        assert "specB\tPEP2\t2" in merged
        assert (pdv_spectra / "specA_PEP1.pdf").is_file()
        assert (pdv_spectra / "specB_PEP2.pdf").is_file()

    def test_no_shard_produces_output_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env = self._setup(tmp_path)
        psmrankall = tmp_path / "psmrankall.txt"
        psmrankall.write_text(
            "peptide\tmodification\tn\tspectrum_title\tcharge\nPEP1\tmod\t1\tspecA\t2\n"
        )
        peptides = tmp_path / "peptides.txt"
        peptides.write_text("PEP1\n")
        mgf_path = tmp_path / "mgfall.mgf"
        mgf_path.write_text("")

        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.submit_bsub", lambda cmd, **kw: 1,
        )
        monkeypatch.setattr(
            "src.tarsus.steps.step06_aggregate_query.wait_for_jobs", lambda job_ids: None,
        )

        with pytest.raises(RuntimeError, match="No shard produced"):
            _run_pdv_sharded(
                psmrankall=psmrankall, peptides=peptides, mgf_path=mgf_path,
                pdv_spectra=tmp_path / "pdv_spectra", output_dir=tmp_path, tool_env=env,
                java_heap_mb=4096, chunk_size=10, queue="gsla-cpu",
                memory_mb=4000, cpus=1, shard_timeout=100,
            )
