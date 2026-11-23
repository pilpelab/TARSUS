"""`tarsus run` passes run-level options to the master job and to provenance.

Everything outside the CLI's own wiring (git, LSF, tool lookup) is replaced by
recorders; the assertions are on what the real `run` command hands them.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner

import src.tarsus.cli as cli


@pytest.fixture()
def recorded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    rec: dict = {}
    monkeypatch.setattr(cli, "check_clean_tree", lambda allow_dirty=False: None)
    monkeypatch.setattr(cli, "stale_artifacts", lambda outdir: [])
    monkeypatch.setattr(cli, "git_sha", lambda: "abc123")
    monkeypatch.setattr(cli, "_resolve_cds", lambda cds, cwd: None)
    monkeypatch.setattr(cli.ToolEnvironment, "from_env", classmethod(lambda c: None))

    def fake_prov(outdir: Path, args: dict) -> Path:
        rec["prov"] = args
        return outdir / "provenance.json"

    def fake_submit(cmd: list[str], **kw: object) -> int:
        rec["cmd"] = cmd
        return 1

    monkeypatch.setattr(cli, "write_provenance", fake_prov)
    monkeypatch.setattr(cli, "submit_bsub", fake_submit)
    rec["fasta"] = tmp_path / "p.fasta"
    rec["fasta"].write_text(">p\nPEPTIDEK\n")
    rec["raw"] = tmp_path / "a.raw"
    rec["raw"].write_text("x")
    rec["out"] = tmp_path / "out"
    return rec


def _run(rec: dict, *extra: str):
    return CliRunner().invoke(cli.main, [
        "run", "--fasta", str(rec["fasta"]), "-i", str(rec["raw"]), "-o", str(rec["out"]), *extra,
    ])


def test_base_rescore_tol_reaches_master_and_provenance(recorded: dict) -> None:
    res = _run(recorded, "--base-rescore-tol", "0.01")
    assert res.exit_code == 0, res.output
    cmd = recorded["cmd"]
    assert cmd[cmd.index("--base-rescore-tol") + 1] == "0.01"
    assert recorded["prov"]["base_rescore_tol_da"] == 0.01


def test_base_rescore_tol_default_leaves_step_default(recorded: dict) -> None:
    res = _run(recorded)
    assert res.exit_code == 0, res.output
    assert "--base-rescore-tol" not in recorded["cmd"]
    assert recorded["prov"]["base_rescore_tol_da"] is None  # = step09 DEFAULT_BASE_RESCORE_TOL_DA


def test_base_rescore_tol_must_be_positive(recorded: dict) -> None:
    res = _run(recorded, "--base-rescore-tol", "0")
    assert res.exit_code != 0
    assert "cmd" not in recorded
