"""Unit tests for pipeline orchestration guardrails."""

from pathlib import Path

import polars as pl
import pytest

from src.tarsus.orchestration import run_pipeline


def _touch_done(outdir: Path, step_dir: str) -> None:
    path = outdir / step_dir
    path.mkdir(parents=True, exist_ok=True)
    (path / ".done").touch()


def _reached_step8(outdir: Path, subs_rows: int) -> None:
    """Stamp Steps 1-8 complete, with a *subs_rows*-row Step 7 result."""
    for step in [
        "01_mzml",
        "02_index",
        "03a_first_pass",
        "03b_candidates",
        "03c_second_pass",
        "04_psm_input",
        "05_pepquery",
        "06_aggregated",
        "07_analyze",
        "08_base_input",
    ]:
        _touch_done(outdir, step)
    pl.DataFrame({"dependent": ["VARIANT"] * subs_rows}).write_ipc(
        outdir / "07_analyze" / "subs.ipc",
    )


def test_empty_subs_ipc_stops_before_step8(tmp_path: Path) -> None:
    """Regression (D-047): a 0-row subs.ipc must stop the run, loudly.

    Step 7 stamps `.done` unconditionally, so a lineage break that zeroes
    subs.ipc would otherwise sail through Step 8's own guardrail message and
    misattribute the failure to Step 8.
    """
    outdir = tmp_path / "out"
    fasta = tmp_path / "protein.fasta"
    raw = tmp_path / "sample.raw"
    fasta.write_text(">p\nPEPTIDE\n")
    raw.write_text("not used by this test")

    _reached_step8(outdir, subs_rows=0)
    (outdir / "08_base_input" / "pepquery_input_base").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="Step 7 produced 0 candidate rows"):
        run_pipeline(outdir, fasta, [raw])

    assert not (outdir / "09_pepquery_base" / ".done").exists()


def test_no_base_input_does_not_mark_downstream_done(tmp_path: Path) -> None:
    """Regression: empty Step 8 input must stop, not fake-complete 9-11.

    A previous implementation treated an empty
    08_base_input/pepquery_input_base/ directory as a valid empty scientific
    outcome and stamped Steps 9, 10, and 11 `.done` without real execution.
    That hides upstream bugs. The orchestrator must fail loudly instead.
    """
    outdir = tmp_path / "out"
    fasta = tmp_path / "protein.fasta"
    raw = tmp_path / "sample.raw"
    fasta.write_text(">p\nPEPTIDE\n")
    raw.write_text("not used by this test")

    # Pretend the pipeline reached Step 8 with a healthy, non-empty Step 7.
    _reached_step8(outdir, subs_rows=3)

    # Step 8 created the directory but no chunk files.
    (outdir / "08_base_input" / "pepquery_input_base").mkdir(parents=True)

    with pytest.raises(RuntimeError, match="Step 8 produced no base-rescoring input files"):
        run_pipeline(outdir, fasta, [raw])

    assert not (outdir / "09_pepquery_base" / ".done").exists()
    assert not (outdir / "10_aggregated_base" / ".done").exists()
    assert not (outdir / "11_localized" / ".done").exists()


class TestParseMasterArgv:
    """The master job's argv: optional `--flag value` pairs, then positionals."""

    def test_positionals_only(self) -> None:
        from src.tarsus.orchestration import _parse_master_argv
        out, fasta, raws, kw = _parse_master_argv(["/o", "/p.fasta", "/a.raw", "/b.raw"])
        assert (out, fasta, raws, kw) == (
            Path("/o"), Path("/p.fasta"), [Path("/a.raw"), Path("/b.raw")], {},
        )

    def test_flags_anywhere_are_stripped(self) -> None:
        from src.tarsus.orchestration import _parse_master_argv
        out, fasta, raws, kw = _parse_master_argv(
            ["--localize-tol", "0.05", "/o", "/p.fasta", "--cds", "/c.fa", "/a.raw"],
        )
        assert out == Path("/o") and fasta == Path("/p.fasta") and raws == [Path("/a.raw")]
        assert kw == {"localize_tol": 0.05, "cds_fasta": Path("/c.fa")}

    def test_flag_without_value_raises(self) -> None:
        from src.tarsus.orchestration import _parse_master_argv
        with pytest.raises(ValueError, match="without a value"):
            _parse_master_argv(["/o", "/p.fasta", "/a.raw", "--localize-tol"])

    def test_too_few_positionals_raises(self) -> None:
        from src.tarsus.orchestration import _parse_master_argv
        with pytest.raises(ValueError, match="expected outdir"):
            _parse_master_argv(["--localize-tol", "0.05", "/o", "/p.fasta"])


class _Stop(Exception):
    pass


def _reached_step11(outdir: Path) -> None:
    _reached_step8(outdir, subs_rows=1)
    for step in ["09_pepquery_base", "10_aggregated_base"]:
        _touch_done(outdir, step)
    (outdir / "08_base_input" / "pepquery_input_base").mkdir(parents=True)
    (outdir / "08_base_input" / "pepquery_input_base" / "chunk").write_text("x")


@pytest.mark.parametrize("given, expected", [(None, None), (0.05, 0.05)])
def test_localize_tol_reaches_step11(tmp_path: Path, monkeypatch, given, expected) -> None:
    """`run_pipeline(localize_tol=...)` reaches Step 11; None leaves the step's default."""
    import tarsus.steps.step11_localize as s11

    seen: dict = {}

    def fake_localize(**kw):
        seen.update(kw)
        raise _Stop

    monkeypatch.setattr(s11, "localize", fake_localize)
    outdir = tmp_path / "out"
    fasta = tmp_path / "protein.fasta"
    fasta.write_text(">p\nPEPTIDE\n")
    _reached_step11(outdir)
    with pytest.raises(_Stop):
        run_pipeline(outdir, fasta, [tmp_path / "x.raw"], localize_tol=given)
    assert seen.get("precursor_tol") == expected


def test_parse_master_argv_msbooster_models() -> None:
    from src.tarsus.orchestration import _parse_master_argv
    *_, kw = _parse_master_argv(["--msbooster-models", "dia-nn", "/o", "/p.fasta", "/a.raw"])
    assert kw == {"msbooster_models": "dia-nn"}
