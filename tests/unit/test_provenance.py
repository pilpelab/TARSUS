"""Unit tests for provenance recording (D-063)."""

import json
import subprocess
from pathlib import Path

import pytest

from src.tarsus.provenance import (
    PROVENANCE_FILE,
    DirtyTreeError,
    check_clean_tree,
    git_sha,
    is_dirty,
    stale_artifacts,
    write_provenance,
)


def _repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed source file."""
    r = tmp_path / "repo"
    (r / "src" / "tarsus" / "steps").mkdir(parents=True)
    src = r / "src" / "tarsus" / "steps" / "step03b_make_peptides.py"
    src.write_text("# v1\n")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}
    subprocess.run(["git", "init", "-q"], cwd=r, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=r, check=True, env=env)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=r, check=True, env=env)
    return r


class TestDirtyTree:
    """A run from a dirty tree is unattributable to any commit — refuse it."""

    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        assert is_dirty(r) is False
        check_clean_tree(r)  # must not raise

    def test_dirty_tree_refuses(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        (r / "src" / "tarsus" / "steps" / "step03b_make_peptides.py").write_text("# v2\n")
        assert is_dirty(r) is True
        with pytest.raises(DirtyTreeError, match="uncommitted changes"):
            check_clean_tree(r)

    def test_allow_dirty_escape_hatch(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        (r / "src" / "tarsus" / "steps" / "step03b_make_peptides.py").write_text("# v2\n")
        check_clean_tree(r, allow_dirty=True)  # must not raise

    def test_untracked_files_do_not_count_as_dirty(self, tmp_path: Path) -> None:
        """An untracked scratch file cannot change what the pipeline executes."""
        r = _repo(tmp_path)
        (r / "scratch.txt").write_text("notes")
        assert is_dirty(r) is False


class TestWriteProvenance:
    def test_records_sha_and_args(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        out = tmp_path / "out"
        p = write_provenance(out, {"fasta": "protein.fasta"}, repo=r)
        rec = json.loads(p.read_text())
        assert p.name == PROVENANCE_FILE
        assert rec["git_sha"] == git_sha(r)
        assert rec["git_dirty"] is False
        assert rec["args"]["fasta"] == "protein.fasta"


class TestStaleArtifacts:
    """The D-057 detector.

    `03b_candidates` was built 2026-06-30 13:14; the I/L fix landed at 14:30 — 76
    minutes later. The library was preserved as "unaffected" by every subsequent
    invalidation and held 0 of 7.37M `->Ile` variants. Nothing anywhere compared
    the artifact's age against the age of the code that produced it.
    """

    def test_artifact_older_than_its_code_is_flagged(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        out = tmp_path / "out"
        done = out / "03b_candidates" / ".done"
        done.parent.mkdir(parents=True)
        done.touch()
        import os
        os.utime(done, (0, 0))  # artifact from 1970 — long before the code

        warns = stale_artifacts(out, repo=r)
        assert len(warns) == 1
        assert "03b_candidates" in warns[0]
        assert "superseded code" in warns[0]

    def test_current_artifact_is_not_flagged(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        out = tmp_path / "out"
        done = out / "03b_candidates" / ".done"
        done.parent.mkdir(parents=True)
        done.touch()  # now — newer than the commit
        assert stale_artifacts(out, repo=r) == []

    def test_absent_step_is_not_flagged(self, tmp_path: Path) -> None:
        r = _repo(tmp_path)
        assert stale_artifacts(tmp_path / "out", repo=r) == []
