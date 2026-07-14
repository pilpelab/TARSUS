"""Record which code produced which result — and refuse to run when we cannot.

**`.done` records *that* a step ran. It has never recorded *which code* ran it.**
That gap has silently invalidated every result in this project twice:

- **D-057** — `03b_candidates/pep_candidates.fa` was built at 13:14; the fix
  `4c2d9d6 "I/L normalization"` landed at 14:30, **76 minutes later**. The library
  was preserved as "unaffected" by every subsequent invalidation and held **0 of
  7.37M** ``->Ile`` variants. Two weeks of results were computed against a search
  space that could not contain the answer.
- **D-061** — the same artifact, built from a transposed exclusion matrix.

Both were invisible because nothing compared the artifact's age against the age of
the code that produced it.

There is a second hazard this closes. ``~/LIS1_mutant_organoids__Orly_Reiner`` has
no ``src/`` of its own — it is an editable install importing *this* package — and
``orchestration.py`` imports each step module **lazily**, when the master reaches
it. So an edit made mid-run is executed by a live pipeline, and a run can span
several commits. Refusing to start on a dirty tree makes that impossible.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROVENANCE_FILE = "provenance.json"

#: Which module produces which step's artifact. Used to detect an artifact that
#: predates the last change to the code that made it.
STEP_SOURCES: dict[str, str] = {
    "01_mzml": "src/tarsus/steps/step01_convert.py",
    "02_index": "src/tarsus/steps/step02_make_index.py",
    "03a_first_pass": "src/tarsus/steps/step03a_first_pass.py",
    "03b_candidates": "src/tarsus/steps/step03b_make_peptides.py",
    "03c_second_pass": "src/tarsus/steps/step03c_second_pass.py",
    "04_psm_input": "src/tarsus/steps/step04_extract_psm.py",
    "05_pepquery": "src/tarsus/steps/step05_query_psm.py",
    "06_aggregated": "src/tarsus/steps/step06_aggregate_query.py",
    "07_analyze": "src/tarsus/steps/step07_analyze_outputs.py",
    "08_base_input": "src/tarsus/steps/step08_ref_validation_prep.py",
    "09_pepquery_base": "src/tarsus/steps/step09_query_psm_base.py",
    "10_aggregated_base": "src/tarsus/steps/step10_aggregate_query_base.py",
    "11_localized": "src/tarsus/steps/step11_localize.py",
}


class DirtyTreeError(RuntimeError):
    """The working tree has uncommitted changes, so the run is unreproducible."""


def _git(*args: str, repo: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def repo_root() -> Path:
    """Root of the installed package's git repo (this file's repo)."""
    return Path(__file__).resolve().parent.parent.parent


def git_sha(repo: Path | None = None) -> str | None:
    return _git("rev-parse", "HEAD", repo=repo or repo_root())


def is_dirty(repo: Path | None = None) -> bool:
    """True if tracked files have uncommitted changes.

    Untracked files are ignored — they cannot change what the pipeline executes.
    """
    out = _git("status", "--porcelain", "--untracked-files=no", repo=repo or repo_root())
    return bool(out)


def check_clean_tree(repo: Path | None = None, allow_dirty: bool = False) -> None:
    """Refuse to launch a pipeline from a dirty tree.

    Raises:
        DirtyTreeError: tracked files are modified and *allow_dirty* is False.
    """
    if allow_dirty:
        return
    repo = repo or repo_root()
    if not is_dirty(repo):
        return
    changed = _git("status", "--porcelain", "--untracked-files=no", repo=repo) or ""
    raise DirtyTreeError(
        f"Refusing to run: {repo} has uncommitted changes, so the results would not "
        f"be attributable to any commit.\n{changed}\n\n"
        f"This is not pedantry — TWICE (D-057, D-061) a Step 3b library built by "
        f"since-fixed code silently invalidated every result in this project, and "
        f"nothing recorded which code produced it. A live edit is also executed by "
        f"any running pipeline: orchestration imports step modules lazily, and "
        f"LIS1_mutant_organoids__Orly_Reiner imports this same source tree.\n\n"
        f"Commit (or stash) the changes, or pass --allow-dirty."
    )


def write_provenance(
    outdir: Path, args: dict[str, object], repo: Path | None = None,
) -> Path:
    """Record the exact code and inputs that produced this run."""
    repo = repo or repo_root()
    outdir.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(repo),
        "git_dirty": is_dirty(repo),
        "repo": str(repo),
        "args": args,
    }
    path = outdir / PROVENANCE_FILE
    path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return path


def stale_artifacts(outdir: Path, repo: Path | None = None) -> list[str]:
    """Preserved `.done` steps whose artifact predates the code that produced it.

    This is the D-057 detector: a Step 3b library built **76 minutes before** its
    own fix, then preserved through every later invalidation as "unaffected".

    Returns a list of human-readable warnings (empty when everything is current).
    """
    repo = repo or repo_root()
    warnings: list[str] = []
    for step, source in STEP_SOURCES.items():
        done = outdir / step / ".done"
        if not done.exists():
            continue
        iso = _git("log", "-1", "--format=%cI", "--", source, repo=repo)
        if not iso:
            continue
        try:
            code_t = datetime.fromisoformat(iso).timestamp()
        except ValueError:
            continue
        if done.stat().st_mtime < code_t:
            warnings.append(
                f"{step}/.done was stamped BEFORE the last change to {source}. "
                f"The artifact was produced by superseded code — delete it and rerun, "
                f"or its results are void (this is exactly D-057/D-061)."
            )
    return warnings
