import subprocess
import time
from pathlib import Path
from .env import ToolEnvironment


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
    """Submit a bsub job. Returns the job ID."""
    bsub_cmd = [
        "bsub",
        "-J", job_name,
        "-q", queue,
        "-n", str(cpus),
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


def wait_for_jobs(job_ids: list[int], poll_seconds: int = 30) -> None:
    """Block until all bsub jobs complete."""
    while True:
        active = []
        for jid in job_ids:
            result = subprocess.run(
                ["bjobs", "-noheader", "-o", "stat", str(jid)],
                capture_output=True, text=True,
            )
            status = result.stdout.strip()
            if status in ("RUN", "PEND", "WAIT", ""):
                active.append(jid)
        if not active:
            break
        time.sleep(poll_seconds)
