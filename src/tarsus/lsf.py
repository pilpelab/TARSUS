import shlex
import subprocess
import time
from pathlib import Path
from .env import ToolEnvironment


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
            stderr = result.stderr.strip()
            # Purged from LSF records: "not found" on stderr, empty stdout
            if "not found" in stderr or not status:
                continue
            if status in ("RUN", "PEND", "WAIT"):
                active.append(jid)
            elif status == "EXIT":
                raise RuntimeError(f"LSF job {jid} exited with failure")
        if not active:
            break
        time.sleep(poll_seconds)
