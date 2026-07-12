"""Unit tests for JVM/LSF resource sizing."""

import os
from pathlib import Path

import pytest

from src.tarsus.resources import (
    NON_HEAP_HEADROOM_MB,
    PEPQUERY_MIN_HEAP_MB,
    ResourceConfigError,
    check_heap_fits,
    estimate_pepquery_memory,
)

_MB = 1024 * 1024


def _fasta(tmp_path: Path, megabytes: float, name: str = "protein.fasta") -> Path:
    p = tmp_path / name
    p.write_bytes(b"A" * int(megabytes * _MB))
    return p


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARSUS_PEPQUERY_HEAP_MB", raising=False)
    monkeypatch.delenv("TARSUS_PEPQUERY_MEM_MB", raising=False)


class TestCheckHeapFits:
    """Regression (D-049 defect 1): -Xmx is a ceiling, not a reservation.

    PDV shipped a 4096 MB heap inside a 4000 MB LSF reservation. It survived
    for months because open-search data never grew the heap; the moment targeted
    mode made the shards render real data, every one was killed with
    TERM_MEMLIMIT and no Java stack trace. Step 5 shipped the same shape: a
    4096 MB heap inside a 1500 MB reservation.
    """

    def test_heap_larger_than_reservation_raises(self) -> None:
        with pytest.raises(ResourceConfigError, match="does not fit"):
            check_heap_fits(java_heap_mb=4096, memory_mb=1500)

    def test_heap_equal_to_reservation_raises(self) -> None:
        with pytest.raises(ResourceConfigError, match="does not fit"):
            check_heap_fits(java_heap_mb=4000, memory_mb=4000)

    def test_insufficient_headroom_raises(self) -> None:
        with pytest.raises(ResourceConfigError, match="does not fit"):
            check_heap_fits(java_heap_mb=4000, memory_mb=4000 + NON_HEAP_HEADROOM_MB - 1)

    def test_exact_headroom_passes(self) -> None:
        check_heap_fits(java_heap_mb=4000, memory_mb=4000 + NON_HEAP_HEADROOM_MB)

    def test_ample_headroom_passes(self) -> None:
        check_heap_fits(java_heap_mb=1024, memory_mb=8000)


class TestEstimatePepqueryMemory:
    """The model is fitted to two real measurements and must predict both."""

    def test_ecoli_fasta_is_modest(self, tmp_path: Path) -> None:
        # Measured: 279 MB peak RSS across 3,869 Step 9 jobs on this FASTA.
        memory_mb, heap_mb = estimate_pepquery_memory(_fasta(tmp_path, 1.8))
        assert heap_mb == PEPQUERY_MIN_HEAP_MB  # model predicts ~428 MB; floor wins
        assert memory_mb == heap_mb + NON_HEAP_HEADROOM_MB
        # Must comfortably cover the measured peak.
        assert memory_mb > 279

    def test_human_proteome_gets_gigabytes(self, tmp_path: Path) -> None:
        # A 106 MB proteome needs ~4 GB; the old hardcoded 1500 MB would OOM.
        memory_mb, heap_mb = estimate_pepquery_memory(_fasta(tmp_path, 106.0))
        assert heap_mb > 4000, "human proteome must get a multi-GB heap"
        assert memory_mb > 1500, "must exceed the old hardcoded default"

    def test_scales_monotonically_with_fasta(self, tmp_path: Path) -> None:
        small = estimate_pepquery_memory(_fasta(tmp_path, 5.0, "small.fasta"))
        large = estimate_pepquery_memory(_fasta(tmp_path, 200.0, "large.fasta"))
        assert large[1] > small[1]
        assert large[0] > small[0]

    def test_result_always_satisfies_the_invariant(self, tmp_path: Path) -> None:
        for mb in (0.1, 1.8, 25.0, 106.0, 500.0):
            memory_mb, heap_mb = estimate_pepquery_memory(
                _fasta(tmp_path, mb, f"f{mb}.fasta"),
            )
            check_heap_fits(heap_mb, memory_mb)  # must not raise

    def test_missing_fasta_falls_back_to_floor(self, tmp_path: Path) -> None:
        memory_mb, heap_mb = estimate_pepquery_memory(tmp_path / "nope.fasta")
        assert heap_mb == PEPQUERY_MIN_HEAP_MB
        assert memory_mb == heap_mb + NON_HEAP_HEADROOM_MB


class TestEnvOverrides:
    """Per-lab tuning must not require a code change (.agents/project.md)."""

    def test_heap_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TARSUS_PEPQUERY_HEAP_MB", "2048")
        memory_mb, heap_mb = estimate_pepquery_memory(_fasta(tmp_path, 1.8))
        assert heap_mb == 2048
        assert memory_mb == 2048 + NON_HEAP_HEADROOM_MB

    def test_memory_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TARSUS_PEPQUERY_MEM_MB", "16000")
        memory_mb, _ = estimate_pepquery_memory(_fasta(tmp_path, 1.8))
        assert memory_mb == 16000

    def test_impossible_override_pair_fails_immediately(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An 8 GB heap in a 2 GB reservation must fail now, not on the first big input."""
        monkeypatch.setenv("TARSUS_PEPQUERY_HEAP_MB", "8192")
        monkeypatch.setenv("TARSUS_PEPQUERY_MEM_MB", "2000")
        with pytest.raises(ResourceConfigError, match="does not fit"):
            estimate_pepquery_memory(_fasta(tmp_path, 1.8))
