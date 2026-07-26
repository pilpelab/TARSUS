"""Unit tests for CDS default resolution in the CLI.

`--cds` is optional (A2): explicit flag > [tool.tarsus].cds in the nearest
pyproject.toml > TARSUS_CDS_FASTA env var > None (codon heatmap skipped). These
assert against the real resolver, not a re-implementation.
"""

from pathlib import Path

import pytest

from src.tarsus.cli import _project_config_cds, _resolve_cds


def _write_pyproject(d: Path, cds: str | None) -> None:
    body = "[project]\nname = 'x'\n"
    if cds is not None:
        body += f"\n[tool.tarsus]\ncds = '{cds}'\n"
    (d / "pyproject.toml").write_text(body)


class TestProjectConfigCds:
    def test_relative_cds_resolved_against_pyproject_dir(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, "data/human_cds.fasta")
        got = _project_config_cds(tmp_path)
        assert got == tmp_path / "data/human_cds.fasta"

    def test_absolute_cds_kept(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, "/abs/cds.fasta")
        assert _project_config_cds(tmp_path) == Path("/abs/cds.fasta")

    def test_walks_up_to_find_declaring_pyproject(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, "data/cds.fasta")
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        _write_pyproject(sub.parent, None)  # nearer pyproject without the key
        # first pyproject *with* the key wins, resolved against its own dir
        assert _project_config_cds(sub) == tmp_path / "data/cds.fasta"

    def test_none_when_no_pyproject_declares_cds(self, tmp_path: Path) -> None:
        _write_pyproject(tmp_path, None)
        assert _project_config_cds(tmp_path) is None


class TestResolveCds:
    def test_explicit_flag_wins(self, tmp_path: Path, monkeypatch) -> None:
        _write_pyproject(tmp_path, "data/config.fasta")
        monkeypatch.setenv("TARSUS_CDS_FASTA", "/env/cds.fasta")
        got = _resolve_cds("/explicit/cds.fasta", tmp_path)
        assert got == Path("/explicit/cds.fasta").resolve()

    def test_project_config_over_env(self, tmp_path: Path, monkeypatch) -> None:
        _write_pyproject(tmp_path, "data/config.fasta")
        monkeypatch.setenv("TARSUS_CDS_FASTA", "/env/cds.fasta")
        got = _resolve_cds(None, tmp_path)
        assert got == (tmp_path / "data/config.fasta").resolve()

    def test_env_var_when_no_config(self, tmp_path: Path, monkeypatch) -> None:
        _write_pyproject(tmp_path, None)
        monkeypatch.setenv("TARSUS_CDS_FASTA", "/env/cds.fasta")
        assert _resolve_cds(None, tmp_path) == Path("/env/cds.fasta").resolve()

    def test_none_when_nothing_set(self, tmp_path: Path, monkeypatch) -> None:
        _write_pyproject(tmp_path, None)
        monkeypatch.delenv("TARSUS_CDS_FASTA", raising=False)
        assert _resolve_cds(None, tmp_path) is None
