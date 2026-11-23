import os
import shlex
import subprocess
import time
from pathlib import Path
from .env import ToolEnvironment


# Run outputs must be readable by the owner's Unix group (D-074). The owner's
# login umask is 0077, which made every result owner-only. LSF jobs inherit the
# submitting process's umask (probed 2026-11-09), so setting it at each entry
# point covers the master job and every child job it submits.
GROUP_READABLE_UMASK = 0o027


def use_group_readable_umask() -> None:
    """Make what this process and its LSF jobs create group-readable, not world-readable."""
    os.umask(GROUP_READABLE_UMASK)


def _build_env_cmd(tool_env: ToolEnvironment) -> str:
    """Generate shell 'export' commands for the tool environment.

    These are intended to be sourced in a bash script running on a
    compute node (e.g., inside a bsub job).
    """
    env = tool_env.env()
    parts: list[str] = []
    for key in ("JAVA_HOME", "DOTNET_ROOT", "DOTNET_GCHeapHardLimit"):
        val = env.get(key)
        if val:
            parts.append(f'export {key}={shlex.quote(str(val))}')
    path_val = env.get("PATH")
    if path_val:
        parts.append(f'export PATH={shlex.quote(str(path_val))}')
    return "\n".join(parts)


#: Exit values LSF requeues instead of reporting as failed (``bsub -Q``). On
#: WEXAC 2-6% of jobs exited 255 at launch, before the program ran (0 s, CPU time
#: unknown, no output), on many nodes (2026-11-19/22). One such job made
#: wait_for_jobs raise and killed the whole master, and a whole-step resume cannot
#: outrun it (every chunk without results reruns). Requeue reruns just that job,
#: under the same id; the cluster caps it at MAX_JOB_REQUEUE = 5. See D-077.
REQUEUE_EXIT_VALUES = "255"


def submit_bsub(
    cmd: list[str],
    *,
    job_name: str,
    queue: str,
    memory_mb: int,
    cpus: int,
    log_path: Path,
    tool_env: ToolEnvironment,
) -> int:
    """Submit a bsub job. Returns the job ID.

    Jobs exiting with :data:`REQUEUE_EXIT_VALUES` are requeued by LSF (``-Q``).
    """
    bsub_cmd = [
        "bsub",
        "-J", job_name,
        "-q", queue,
        "-n", str(cpus),
        "-Q", REQUEUE_EXIT_VALUES,
        "-R", f"rusage[mem={memory_mb}] span[hosts=1]",
        "-oo", str(log_path),
    ] + cmd
    result = subprocess.run(
        bsub_cmd,
        env=tool_env.env(),
        capture_output=True, text=True,
    )
    result.check_returncode()
    return _parse_job_id(result.stdout)


def _parse_job_id(output: str) -> int:
    """Extract job ID from bsub output like 'Job <12345> is submitted to queue <name>'."""
    for word in output.split():
        if word.startswith("<") and word.endswith(">"):
            try:
                return int(word.strip("<>"))
            except ValueError:
                pass
    raise ValueError(f"Cannot parse job ID from: {output}")


_ACTIVE_STATES = ("RUN", "PEND", "WAIT", "PROV", "PSUSP", "USUSP", "SSUSP")
_SUCCESS_STATES = ("DONE",)

#: LSF appends an epilogue to every ``-oo`` log when the job ends.
_LOG_SUCCESS = "Successfully completed."
_LOG_FAILURE_MARKERS = ("Exited with exit code", "TERM_", "Exited with signal")


def job_log_verdict(log_path: Path) -> str | None:
    """Read LSF's own verdict out of a job's ``-oo`` log.

    LSF writes an epilogue when the job ends — ``Successfully completed.`` or
    ``Exited with exit code N`` / ``TERM_MEMLIMIT`` — and **that log outlives the
    job record**, which ``bjobs`` does not: completed jobs are purged after ~1h.
    So for anything long-running the log is the only durable, per-job ground
    truth we have.

    Returns ``"success"``, ``"failure"``, or ``None`` when the log has no
    epilogue yet (job still running, or the log was never written).
    """
    try:
        text = log_path.read_text(errors="replace")
    except OSError:
        return None
    if _LOG_SUCCESS in text:
        return "success"
    if any(m in text for m in _LOG_FAILURE_MARKERS):
        return "failure"
    return None


def _poll_statuses(job_ids: list[int]) -> dict[int, str] | None:
    """Ask LSF for the status of every job in ONE call.

    Returns ``{job_id: status}``, or ``None`` if the ``bjobs`` call itself
    failed — which is *not* the same as "the jobs are gone".  Jobs LSF has
    purged are simply absent from the mapping.

    One call, not one per job: the old code spawned a ``bjobs`` subprocess per
    job per poll — 4,784 of them every 30s on a full Step 5 — which hammers the
    LSF daemon and is the most likely source of the transient failures that
    corrupted its own status reads.
    """
    result = subprocess.run(
        ["bjobs", "-noheader", "-o", "jobid stat"] + [str(j) for j in job_ids],
        capture_output=True, text=True,
    )
    # `bjobs` exits non-zero when *any* id is unknown, so a non-zero code alone
    # is not an error — but a non-zero code with no usable output is.
    statuses: dict[int, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            statuses[int(parts[0])] = parts[1].strip()
    if not statuses and result.returncode != 0 and "not found" not in result.stderr:
        return None  # the query failed; we learned nothing
    return statuses


def wait_for_jobs(
    job_ids: list[int],
    poll_seconds: int = 30,
    *,
    job_labels: dict[int, str] | None = None,
    job_logs: dict[int, Path] | None = None,
    raise_on_failure: bool = True,
) -> list[int]:
    """Block until every job reaches a terminal state. Return the failed ones.

    **LSF status is not a reliable completion signal — the produced artifact is.**
    This function reports what LSF claims; callers must verify their own outputs.

    Three defects this replaces, all of which failed *silently*:

    1. ``bjobs``'s return code was never checked. A transient failure yields
       empty stdout, and the old code read "empty" as "gone, therefore fine" —
       so a job that died was recorded as **successful**.
    2. A purged job (``not found``) was likewise assumed successful. Purge means
       the outcome is **unknown**, not good.
    3. It raised on the *first* ``EXIT``, throwing away thousands of still-running
       jobs' work.

    Args:
        job_labels: ``{job_id: name}`` used in the failure message. Without it a
            failure reads "LSF job 689403 exited" and nobody can tell which chunk
            that was — the exact reason a real crash proved undiagnosable.
        raise_on_failure: if False, return the failures instead of raising, so the
            caller can check whether the work actually landed anyway.

    Returns:
        Job IDs whose success LSF did **not** confirm — either a definite
        ``EXIT``, or purged from its records before we saw a terminal state.
        Purge is *not* failure: LSF drops completed jobs after ~1h, so on a
        75-minute Step 5 the early jobs disappear precisely *because* they
        finished. Only a definite ``EXIT`` raises; a purged job is returned for
        the caller to settle against its output.
    """
    pending = set(job_ids)
    failed: set[int] = set()      # definite: LSF said EXIT
    unconfirmed: set[int] = set()  # unknown: purged before we saw it finish

    while pending:
        statuses = _poll_statuses(sorted(pending))
        if statuses is None:
            time.sleep(poll_seconds)  # the query failed — retry; assume nothing
            continue

        for jid in sorted(pending):
            status = statuses.get(jid)
            if status is None:
                pending.discard(jid)
                unconfirmed.add(jid)  # purged — verify via the artifact
            elif status in _ACTIVE_STATES:
                continue
            elif status in _SUCCESS_STATES:
                pending.discard(jid)
            else:  # EXIT, ZOMBI, UNKWN, ...
                pending.discard(jid)
                failed.add(jid)

        if pending:
            time.sleep(poll_seconds)

    # LSF's live status is not authoritative. Where we know the job's log, LSF's
    # own epilogue in that log is — and it survives the purge that erases the job
    # record. A job whose log says "Successfully completed." did complete, no
    # matter what `bjobs` said a moment earlier.
    logs = job_logs or {}
    for jid in sorted(failed | unconfirmed):
        verdict = job_log_verdict(logs[jid]) if jid in logs else None
        if verdict == "success":
            failed.discard(jid)
            unconfirmed.discard(jid)
        elif verdict == "failure":
            unconfirmed.discard(jid)
            failed.add(jid)

    if failed and raise_on_failure:
        labels, lg = job_labels or {}, logs
        listed = "\n".join(
            f"  job {jid}"
            + (f" ({labels[jid]})" if jid in labels else "")
            + (f" — log: {lg[jid]}" if jid in lg else "")
            for jid in sorted(failed)
        )
        raise RuntimeError(
            f"{len(failed)} LSF job(s) failed:\n{listed}\n"
            f"(Verdict taken from each job's own LSF log epilogue where available, "
            f"not from `bjobs` — completed jobs are purged from `bjobs` after ~1h.)"
        )
    return sorted(failed | unconfirmed)
