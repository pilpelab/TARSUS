"""Step 9: PepQuery rescoring of base peptides (reference validation).

Submits PepQuery jobs against the fake MGF with adjusted precursor masses,
one per input chunk file from Step 8.
"""

from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs


def step09_query_psm_base(
    input_dir: Path,
    index_dir: Path,
    mgf_path: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int = 5000,
    cpus: int = 1,
    java_heap_mb: int = 4096,
) -> Path:
    """Run PepQuery base rescoring on chunked input files.

    Args:
        input_dir: pepquery_input_base/ directory from Step 8.
        index_dir: pepquery_index/ from Step 2.
        mgf_path: mgfall_fakes.mgf from Step 8.
        output_dir: Output directory for results.

    Returns:
        Path to pepquery_result_recheck_base/ directory.
    """
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not index_dir.is_dir():
        raise FileNotFoundError(f"PepQuery index not found: {index_dir}")
    if not mgf_path.is_file():
        raise FileNotFoundError(f"Fake MGF not found: {mgf_path}")
    pepquery_jar = tool_env.pepquery_jar
    if not pepquery_jar.is_file():
        raise FileNotFoundError(f"PepQuery JAR not found: {pepquery_jar}")
    java_bin = tool_env.java_bin
    if not java_bin.is_file():
        raise FileNotFoundError(f"Java binary not found: {java_bin}")

    result_dir = output_dir / "pepquery_result_recheck_base"
    log_dir = output_dir / "pepquery_logs_base"
    result_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(input_dir.glob("*"))
    if not input_files:
        raise ValueError(f"No input files found in {input_dir}")

    job_ids: list[int] = []
    for f in input_files:
        chunk_result = result_dir / f.name
        chunk_result.mkdir(exist_ok=True)

        # Skip if already processed
        if (chunk_result / "psm_rank.txt").is_file():
            continue

        cmd = [
            str(java_bin),
            f"-Xmx{java_heap_mb}m",
            "-jar", str(pepquery_jar),
            "-ti", "0,1,2,3",
            "-maxLength", "50",
            "-tol", "20",
            "-fast",
            "-itol", "0.01",
            "-fixMod", "0",
            "-varMod", "1,2",
            "-maxVar", "4",
            "-hc",
            "-m", "1",
            "-s", "2",
            "-ms", str(mgf_path.resolve()),
            "-indexType", "2",
            "-db", str(index_dir.resolve()),
            "-o", str(chunk_result.resolve()),
            "-e", "2",
            "-c", "2",
            "-plot",
            "-i", str(f.resolve()),
        ]

        log_path = log_dir / f"{f.name}.log"
        jid = submit_bsub(
            cmd,
            job_name=f"pqbase_{f.name[:20]}",
            queue=queue,
            memory_mb=memory_mb,
            cpus=cpus,
            log_path=log_path,
            tool_env=tool_env,
        )
        job_ids.append(jid)

    if job_ids:
        wait_for_jobs(job_ids)

    rank_files = sorted(result_dir.rglob("psm_rank.txt"))
    if not rank_files:
        raise RuntimeError(
            f"No psm_rank.txt files found in {result_dir}. Check logs in {log_dir}"
        )

    return result_dir
