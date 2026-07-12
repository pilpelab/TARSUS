"""Step 5: PepQuery validation of PSMs.

Splits the PSM input file into chunks, submits one bsub PepQuery job per
chunk, and waits for all to complete.
"""

from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs
from ..resources import check_heap_fits, estimate_pepquery_memory, stage_pepquery_db


def step05_query_psm(
    psm_input: Path,
    index_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    fasta_path: Path | None = None,
    queue: str = "gsla-cpu",
    memory_mb: int | None = None,
    cpus: int = 1,
    chunk_size: int = 10,
    java_heap_mb: int | None = None,
    pepquery_flags: str | None = None,
) -> Path:
    """Validate PSMs with PepQuery via LSF.

    Args:
        psm_input: Step 4 output (psm_input4pepquery.tsv).
        index_dir: Step 2 output (pepquery_index/).
        output_dir: Directory for results (pepquery_result/ created inside).
        tool_env: Resolved tool environment.
        fasta_path: Reference proteome FASTA (passed to PepQuery as -db).
        memory_mb: LSF reservation per chunk. Derived from *fasta_path* when
            omitted — PepQuery loads the reference proteome to compete each
            candidate against it, so its footprint tracks FASTA size. A default
            tuned for E. coli silently OOMs on a human proteome ~60x larger.
        java_heap_mb: JVM heap per chunk. Derived alongside *memory_mb*. An
            explicit pair is validated: a heap that cannot fit inside the
            reservation raises now rather than dying with TERM_MEMLIMIT on the
            first large input. See ``resources.py``.

    Returns:
        Path to pepquery_result/ directory.
    """
    if not psm_input.is_file():
        raise FileNotFoundError(f"PSM input not found: {psm_input}")
    if not index_dir.is_dir():
        raise FileNotFoundError(f"PepQuery index not found: {index_dir}")
    if fasta_path is not None and not fasta_path.is_file():
        raise FileNotFoundError(f"FASTA not found: {fasta_path}")
    pepquery_jar = tool_env.pepquery_jar
    if not pepquery_jar.is_file():
        raise FileNotFoundError(f"PepQuery JAR not found: {pepquery_jar}")
    java_bin = tool_env.java_bin
    if not java_bin.is_file():
        raise FileNotFoundError(f"Java binary not found: {java_bin}")

    if memory_mb is None or java_heap_mb is None:
        est_memory, est_heap = estimate_pepquery_memory(
            fasta_path if fasta_path is not None else Path("/nonexistent"),
        )
        memory_mb = est_memory if memory_mb is None else memory_mb
        java_heap_mb = est_heap if java_heap_mb is None else java_heap_mb
    check_heap_fits(java_heap_mb, memory_mb, what="Step 5 PepQuery")

    # PepQuery writes its FM-index sidecar next to -db, so -db must live somewhere
    # writable. Reference proteomes usually do not. See stage_pepquery_db.
    db_path = (
        stage_pepquery_db(fasta_path, output_dir) if fasta_path is not None else None
    )

    result_dir = output_dir / "pepquery_result"
    log_dir = output_dir / "pepquery_logs"
    result_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    lines = [ln for ln in psm_input.read_text().split("\n") if ln.strip()]

    if not lines:
        raise ValueError("PSM input file has no data rows")

    chunks = [lines[i:i + chunk_size] for i in range(0, len(lines), chunk_size)]
    inputs_dir = output_dir / "pepquery_inputs"
    inputs_dir.mkdir(exist_ok=True)

    job_ids: list[int] = []
    for idx, chunk in enumerate(chunks):
        chunk_file = inputs_dir / f"chunk_{idx:04d}.tsv"
        chunk_file.write_text("\n".join(chunk) + "\n")

        # Resume: skip chunks that already have results from a prior run
        if (result_dir / chunk_file.name / "psm_rank.txt").is_file():
            continue

        cmd = [
            str(java_bin),
            f"-Xmx{java_heap_mb}m",
            "-jar", str(pepquery_jar),
            "-ti", "0,1,2,3",
            "-maxLength", "50",
            "-tol", "20",
            "-itol", "0.05",
            "-hc",
            "-aa",
            "-m", "1",
            "-ms", str(index_dir.resolve()),
            "-db", str(db_path.resolve()) if db_path else "-",
            "-o", str((result_dir / chunk_file.name).resolve()),
            "-e", "2",
            "-c", "2",
            "-i", str(chunk_file.resolve()),
        ]
        if pepquery_flags:
            cmd.extend(pepquery_flags.split())

        log_path = log_dir / f"{chunk_file.name}.log"
        jid = submit_bsub(
            cmd,
            job_name=f"pq_{idx:04d}",
            queue=queue,
            memory_mb=memory_mb,
            cpus=cpus,
            log_path=log_path,
            tool_env=tool_env,
        )
        job_ids.append(jid)

    wait_for_jobs(job_ids)

    # Validate: at least one result file produced
    rank_files = sorted(result_dir.rglob("psm_rank.txt"))
    if not rank_files:
        raise RuntimeError(
            f"No psm_rank.txt files found in {result_dir}. "
            f"Check logs in {log_dir}"
        )

    return result_dir
