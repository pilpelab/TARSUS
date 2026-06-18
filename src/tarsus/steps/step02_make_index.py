"""Step 2: Build PepQuery index from mzML files.

Submits a single LSF job to build a PepQuery database index from all
mzML files in the input directory. The index enables fast PepQuery
validation in later steps.
"""

from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs


def step02_make_index(
    mzml_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int = 12000,
    cpus: int = 10,
    java_heap_mb: int = 4096,
) -> Path:
    """Build PepQuery index from mzML files.

    Validates inputs before submitting, then waits for the LSF job.

    Returns:
        Path to the created index directory.

    Raises:
        FileNotFoundError: if mzml_dir does not exist or contains no .mzML files.
        FileNotFoundError: if PepQuery JAR does not exist.
    """
    if not mzml_dir.is_dir():
        raise FileNotFoundError(f"mzML directory not found: {mzml_dir}")
    mzml_files = sorted(mzml_dir.glob("*.mzML"))
    if not mzml_files:
        raise FileNotFoundError(f"No .mzML files found in {mzml_dir}")

    pepquery_jar = tool_env.pepquery_jar
    if not pepquery_jar.is_file():
        raise FileNotFoundError(f"PepQuery JAR not found: {pepquery_jar}")

    java_bin = tool_env.java_bin
    if not java_bin.is_file():
        raise FileNotFoundError(f"Java binary not found: {java_bin}")

    index_dir = output_dir / "pepquery_index"
    index_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(java_bin),
        f"-Xmx{java_heap_mb}m",
        "-jar", str(pepquery_jar),
        "index",
        "-r",
        "-i", str(mzml_dir.resolve()),
        "-o", str(index_dir.resolve()),
    ]

    log_path = output_dir / "step02_pepquery_index.log"
    jid = submit_bsub(
        cmd,
        job_name="pepquery_index",
        queue=queue,
        memory_mb=memory_mb,
        cpus=cpus,
        log_path=log_path,
        tool_env=tool_env,
    )
    wait_for_jobs([jid])

    if not index_dir.is_dir() or not any(index_dir.iterdir()):
        raise RuntimeError(
            f"PepQuery index not created at {index_dir}. "
            f"Check LSF log: {log_path}"
        )
    return index_dir
