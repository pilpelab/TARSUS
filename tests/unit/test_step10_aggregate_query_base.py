"""Unit tests for Step 10 — base rescoring aggregation."""

from pathlib import Path

import pytest

from src.tarsus.env import ToolEnvironment
from src.tarsus.steps.step10_aggregate_query_base import step10_aggregate_query_base

HEADER = "peptide\tmodification\tn\tspectrum_title\tcharge\tscore\tconfident"
ROW_A = "PEPTIDE\tOxidation of M@9[15.9949]\t4\tf:112018:3_M14C0\t3\t12.5\tYes"
ROW_B = "OTHERPEP\t-\t1\tf:99:2_M0C0\t2\t9.0\tNo"


def _env(tmp_path: Path) -> ToolEnvironment:
    return ToolEnvironment(tools_dir=tmp_path / "tools")


def _chunk(result_dir: Path, name: str, rows: list[str]) -> None:
    d = result_dir / name
    d.mkdir(parents=True)
    (d / "psm_rank.txt").write_text(HEADER + "\n" + "\n".join(rows) + "\n")


class TestStep10AggregateQueryBase:
    def test_missing_result_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            step10_aggregate_query_base(
                tmp_path / "nope", tmp_path / "out", _env(tmp_path),
            )

    def test_no_rank_files_raises(self, tmp_path: Path) -> None:
        result_dir = tmp_path / "res"
        result_dir.mkdir()
        with pytest.raises(RuntimeError, match="No psm_rank.txt"):
            step10_aggregate_query_base(result_dir, tmp_path / "out", _env(tmp_path))

    def test_creates_output_dir_if_absent(self, tmp_path: Path) -> None:
        """Regression: Step 10 opened psmrankall_base.txt without mkdir'ing its parent.

        Steps 9 -> 10 had never run before, so this FileNotFoundError only
        surfaced on the first real pass through the pipeline.
        """
        result_dir = tmp_path / "res"
        _chunk(result_dir, "variants_1.txt", [ROW_A])
        out = tmp_path / "out"  # deliberately does not exist
        assert not out.exists()

        step10_aggregate_query_base(result_dir, out, _env(tmp_path))

        psmrankall = out / "psmrankall_base.txt"
        assert psmrankall.is_file()
        assert "f:112018:3_M14C0" in psmrankall.read_text()

    def test_keeps_one_header_across_chunks(self, tmp_path: Path) -> None:
        result_dir = tmp_path / "res"
        _chunk(result_dir, "variants_1.txt", [ROW_A])
        _chunk(result_dir, "variants_2.txt", [ROW_B])
        out = tmp_path / "out"

        step10_aggregate_query_base(result_dir, out, _env(tmp_path))

        lines = [
            ln for ln in (out / "psmrankall_base.txt").read_text().split("\n")
            if ln.strip()
        ]
        assert lines.count(HEADER) == 1
        assert len(lines) == 3  # header + 2 data rows

    def test_header_only_chunks_raise(self, tmp_path: Path) -> None:
        """A base rescoring that matched nothing must fail loudly.

        Step 11 joins psmrankall_base.txt to decide which variants beat their
        reference peptide. With zero data rows the inner join drops everything
        and subs_localized.csv silently comes out empty.
        """
        result_dir = tmp_path / "res"
        _chunk(result_dir, "variants_1.txt", [])
        with pytest.raises(RuntimeError, match="no data rows"):
            step10_aggregate_query_base(result_dir, tmp_path / "out", _env(tmp_path))
