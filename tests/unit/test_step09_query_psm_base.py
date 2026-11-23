"""Unit tests for Step 9: PepQuery base rescoring (no LSF, no PepQuery run)."""

from pathlib import Path

import pytest

import src.tarsus.steps.step09_query_psm_base as s9
from src.tarsus.env import ToolEnvironment


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[dict, list[list[str]]]:
    """One input chunk, stub tools, and LSF/index helpers replaced by recorders."""
    tools = tmp_path / "tools"
    (tools / "pepquery-2.0.2").mkdir(parents=True)
    (tools / "pepquery-2.0.2" / "pepquery-2.0.2.jar").touch()
    env = ToolEnvironment(tools_dir=tools)
    env.java_bin.parent.mkdir(parents=True)
    env.java_bin.touch()

    input_dir = tmp_path / "pepquery_input_base"
    input_dir.mkdir()
    (input_dir / "variants_1.txt").write_text("PEPTIDEK\tf:1:2_M0C0\n")
    index_dir = tmp_path / "pepquery_index"
    index_dir.mkdir()
    mgf = tmp_path / "mgfall_fakes.mgf"
    mgf.write_text("BEGIN IONS\nEND IONS\n")
    fasta = tmp_path / "protein.fasta"
    fasta.write_text(">p\nPEPTIDEK\n")
    out = tmp_path / "09_pepquery_base"

    cmds: list[list[str]] = []

    def fake_submit(cmd: list[str], **kw: object) -> int:
        cmds.append(cmd)
        return len(cmds)

    def fake_wait(job_ids: list[int], **kw: object) -> None:
        chunk = out / "pepquery_result_recheck_base" / "variants_1.txt"
        (chunk / "psm_rank.txt").write_text("peptide\tscore\n")

    monkeypatch.setattr(s9, "submit_bsub", fake_submit)
    monkeypatch.setattr(s9, "wait_for_jobs", fake_wait)
    monkeypatch.setattr(s9, "stage_pepquery_db", lambda fasta, out_dir: fasta)
    monkeypatch.setattr(s9, "ensure_pepquery_index", lambda *a, **kw: None)
    kwargs = dict(input_dir=input_dir, index_dir=index_dir, mgf_path=mgf,
                  output_dir=out, tool_env=env, fasta_path=fasta,
                  memory_mb=6000, java_heap_mb=4000)
    return kwargs, cmds


def _itol(cmd: list[str]) -> str:
    i = cmd.index("-itol")
    return cmd[i + 1]


class TestBaseRescoreTolerance:
    """PepQuery's fragment tolerance for base rescoring (D-076).

    Slava's production runs used -itol 0.05: with it our Step 9 reproduced his
    psmrankall_base.txt to full precision (PARK7 117/117, GAPDH 167/167 spectra);
    the published query_psm_base.sh and our old hardcoded value say 0.01, which
    changed 38 of 116 PARK7 base scores and the final localized list.
    """

    def test_default_is_slavas_production_value(self, tmp_path, monkeypatch) -> None:
        kwargs, cmds = _setup(tmp_path, monkeypatch)
        s9.step09_query_psm_base(**kwargs)
        assert s9.DEFAULT_BASE_RESCORE_TOL_DA == 0.05
        assert _itol(cmds[0]) == "0.05"

    def test_override_reaches_pepquery(self, tmp_path, monkeypatch) -> None:
        kwargs, cmds = _setup(tmp_path, monkeypatch)
        s9.step09_query_psm_base(**kwargs, fragment_tol=0.01)
        assert _itol(cmds[0]) == "0.01"

    @pytest.mark.parametrize("bad", [0.0, -0.05])
    def test_non_positive_tolerance_fails_loudly(self, tmp_path, monkeypatch, bad) -> None:
        kwargs, cmds = _setup(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="> 0"):
            s9.step09_query_psm_base(**kwargs, fragment_tol=bad)
        assert cmds == []  # nothing submitted


class TestResumeNeverMixesTolerances:
    """Step 9 resumes chunk by chunk, so a tolerance change must not mix results.

    Chunks that already have psm_rank.txt are skipped. Resuming with another
    -itol, or resuming a run from before D-076 (always 0.01, no record), would
    silently combine base scores computed at two tolerances. Step 9 records its
    tolerance and refuses such a resume before submitting anything.
    """

    def _chunk(self, kwargs: dict) -> Path:
        return kwargs["output_dir"] / "pepquery_result_recheck_base" / "variants_1.txt"

    def test_fresh_run_records_tolerance(self, tmp_path, monkeypatch) -> None:
        kwargs, _ = _setup(tmp_path, monkeypatch)
        s9.step09_query_psm_base(**kwargs, fragment_tol=0.05)
        assert (kwargs["output_dir"] / s9.FRAGMENT_TOL_RECORD).read_text().strip() == "0.05"

    def test_resume_with_same_tolerance_is_allowed(self, tmp_path, monkeypatch) -> None:
        kwargs, _ = _setup(tmp_path, monkeypatch)
        s9.step09_query_psm_base(**kwargs, fragment_tol=0.05)
        s9.step09_query_psm_base(**kwargs, fragment_tol=0.05)  # chunk done -> skipped

    def test_resume_with_other_tolerance_raises(self, tmp_path, monkeypatch) -> None:
        kwargs, cmds = _setup(tmp_path, monkeypatch)
        s9.step09_query_psm_base(**kwargs, fragment_tol=0.05)
        (self._chunk(kwargs) / "psm_rank.txt").unlink()  # one chunk left to do
        n = len(cmds)
        with pytest.raises(ValueError, match="0.05"):
            s9.step09_query_psm_base(**kwargs, fragment_tol=0.01)
        assert len(cmds) == n  # nothing submitted

    def test_unrecorded_existing_results_raise(self, tmp_path, monkeypatch) -> None:
        """Results from before D-076 carry no record; their tolerance is unknown."""
        kwargs, cmds = _setup(tmp_path, monkeypatch)
        chunk = self._chunk(kwargs)
        chunk.mkdir(parents=True)
        (chunk / "psm_rank.txt").write_text("peptide\tscore\n")
        with pytest.raises(ValueError, match="no record"):
            s9.step09_query_psm_base(**kwargs)
        assert cmds == []
