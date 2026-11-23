"""Run outputs must be readable by the owner's Unix group (D-074).

The owner's login umask is 0077, so before D-074 every file a run wrote was
owner-only: a labmate in the same group (pilpel-wx-grp) got "Permission denied"
on a finished run directory. Both entry points set umask 0o027 before writing
anything: the ``tarsus`` CLI on the login node, and the master job on the
compute node (``python -m tarsus.orchestration``).
"""

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.tarsus import orchestration
from src.tarsus.cli import main


@pytest.fixture
def private_umask():
    """Start from the owner-only umask that caused the problem; restore after."""
    old = os.umask(0o077)
    yield
    os.umask(old)


def _modes_of_new_outputs(root: Path) -> tuple[int, int]:
    """Create a directory and a file under *root*; return their permission bits."""
    d = root / "run"
    d.mkdir()
    f = d / "result.tsv"
    f.write_text("x\n")
    return stat.S_IMODE(d.stat().st_mode), stat.S_IMODE(f.stat().st_mode)


def test_cli_entry_makes_outputs_group_readable(private_umask, tmp_path: Path) -> None:
    result = CliRunner().invoke(main, ["run", "--help"])

    assert result.exit_code == 0, result.output
    assert _modes_of_new_outputs(tmp_path) == (0o750, 0o640)


def test_master_entry_makes_outputs_group_readable(
    private_umask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, tuple[int, int]] = {}

    def fake_run_pipeline(outdir: Path, fasta: Path, raw_files: list[Path], **kw) -> None:
        seen["modes"] = _modes_of_new_outputs(outdir)

    monkeypatch.setattr(orchestration, "run_pipeline", fake_run_pipeline)
    tmp_out = tmp_path / "out"
    tmp_out.mkdir()

    orchestration.main([str(tmp_out), "proteome.fasta", "sample.raw"])

    assert seen["modes"] == (0o750, 0o640)
