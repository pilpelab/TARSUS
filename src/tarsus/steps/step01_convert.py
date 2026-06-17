import subprocess
from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs


def step01_convert(
    raw_files: list[Path],
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int = 7000,
    cpus: int = 1,
    local: bool = False,
) -> list[Path]:
    """Step 1: Convert .raw files to .mzML via ThermoRawFileParser.

    Each raw file is processed independently (one LSF job per file).
    Returns list of expected mzML output paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    mzml_paths: list[Path] = []
    job_ids: list[int] = []

    for raw in raw_files:
        stem = raw.stem
        mzml_path = output_dir / f"{stem}.mzML"
        mzml_paths.append(mzml_path)

        cmd = [
            str(tool_env.thermorawfileparser_bin),
            "-i", str(raw.resolve()),
            "-o", str(output_dir.resolve()),
        ]

        if local:
            env = tool_env.env()
            subprocess.run(cmd, env=env, check=True)
        else:
            jid = submit_bsub(
                cmd,
                job_name=stem,
                queue=queue,
                memory_mb=memory_mb,
                cpus=cpus,
                log_path=output_dir / f"{stem}.log",
                tool_env=tool_env,
            )
            job_ids.append(jid)

    if job_ids:
        wait_for_jobs(job_ids)

    return mzml_paths
