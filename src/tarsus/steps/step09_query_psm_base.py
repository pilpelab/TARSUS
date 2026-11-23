"""Step 9: PepQuery rescoring of base peptides (reference validation).

Submits PepQuery jobs against the fake MGF with adjusted precursor masses,
one per input chunk file from Step 8.
"""

from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs
from ..resources import (
    check_heap_fits,
    ensure_pepquery_index,
    estimate_pepquery_memory,
    stage_pepquery_db,
)


#: PepQuery fragment tolerance (``-itol``, Da) for base rescoring. 0.05 is what
#: Slava's production runs used: with it this step reproduced his
#: ``psmrankall_base.txt`` to full precision (PARK7 117/117, GAPDH 167/167
#: spectra, 2026-11-22), and Step 11 then gave the published ST14 PARK7 list
#: exactly. The published ``query_psm_base.sh`` (and this step until 2026-11-23)
#: pass 0.01, which changed 38 of 116 PARK7 base scores. Override per run with
#: ``tarsus run --base-rescore-tol``. See D-076.
DEFAULT_BASE_RESCORE_TOL_DA = 0.05

#: File in Step 9's output directory recording the ``-itol`` its chunks used.
#: Step 9 resumes chunk by chunk, so without it a resume at another tolerance
#: (or of a pre-D-076 run, always 0.01) would silently mix base scores.
FRAGMENT_TOL_RECORD = "fragment_tol.txt"


def _check_or_record_fragment_tol(output_dir: Path, result_dir: Path, fragment_tol: float) -> None:
    """Refuse to resume Step 9 at a tolerance other than the one its results used.

    Raises:
        ValueError: the recorded tolerance differs, or chunk results exist with no
            record (their tolerance is unknown).
    """
    record = output_dir / FRAGMENT_TOL_RECORD
    if record.is_file():
        recorded = float(record.read_text().strip())
        if recorded != fragment_tol:
            raise ValueError(
                f"{output_dir} holds base scores computed with -itol {recorded}, but this run "
                f"asks for {fragment_tol}. Resuming would mix the two: clear {output_dir} "
                f"or rerun with --base-rescore-tol {recorded}."
            )
        return
    done = list(result_dir.glob("*/psm_rank.txt"))
    if done:
        raise ValueError(
            f"{result_dir} has {len(done)} chunk results but no record of their -itol "
            f"({FRAGMENT_TOL_RECORD}): they predate D-076, when Step 9 always used 0.01. "
            f"Resuming would mix tolerances: clear {output_dir} and rerun Step 9."
        )
    record.write_text(f"{fragment_tol}\n")


def step09_query_psm_base(
    input_dir: Path,
    index_dir: Path,
    mgf_path: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    fasta_path: Path | None = None,
    queue: str = "gsla-cpu",
    memory_mb: int | None = None,
    cpus: int = 1,
    java_heap_mb: int | None = None,
    fragment_tol: float = DEFAULT_BASE_RESCORE_TOL_DA,
) -> Path:
    """Run PepQuery base rescoring on chunked input files.

    Args:
        input_dir: pepquery_input_base/ directory from Step 8.
        index_dir: pepquery_index/ from Step 2.
        mgf_path: mgfall_fakes.mgf from Step 8.
        output_dir: Output directory for results.
        fasta_path: Reference proteome FASTA (passed to PepQuery as -db).
        fragment_tol: PepQuery ``-itol`` in Da; see :data:`DEFAULT_BASE_RESCORE_TOL_DA`.
        memory_mb: LSF reservation per chunk. Derived from *fasta_path* when
            omitted — see :func:`tarsus.resources.estimate_pepquery_memory`.
            (Measured: these jobs peak at 279 MB on E. coli, against the old
            hardcoded 5000 MB reservation — 18x over-provisioned.)
        java_heap_mb: JVM heap per chunk. Derived alongside *memory_mb*, and
            validated to fit inside it.

    Returns:
        Path to pepquery_result_recheck_base/ directory.

    Raises:
        ValueError: ``fragment_tol`` is not positive, or existing chunk results were
            computed at another (or an unrecorded) tolerance; see
            :func:`_check_or_record_fragment_tol`.
    """
    if not fragment_tol > 0:
        raise ValueError(f"PepQuery fragment tolerance must be > 0 Da, got {fragment_tol!r}")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    if not index_dir.is_dir():
        raise FileNotFoundError(f"PepQuery index not found: {index_dir}")
    if not mgf_path.is_file():
        raise FileNotFoundError(f"Fake MGF not found: {mgf_path}")
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
    check_heap_fits(java_heap_mb, memory_mb, what="Step 9 PepQuery base rescoring")

    # PepQuery writes its FM-index sidecar next to -db, so -db must live somewhere
    # writable. Reference proteomes usually do not. See stage_pepquery_db.
    db_path = (
        stage_pepquery_db(fasta_path, output_dir) if fasta_path is not None else None
    )

    result_dir = output_dir / "pepquery_result_recheck_base"
    log_dir = output_dir / "pepquery_logs_base"
    result_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    _check_or_record_fragment_tol(output_dir, result_dir, fragment_tol)

    # Build the FM index ONCE, before fanning out — otherwise every chunk races to
    # write the same .fmi and most die in FMIndex. See D-059.
    if db_path is not None:
        ensure_pepquery_index(
            db_path, index_dir, tool_env, java_heap_mb,
            log_path=log_dir / "_fmindex_build.log",
        )

    input_files = sorted(input_dir.glob("*"))
    if not input_files:
        raise ValueError(f"No input files found in {input_dir}")

    job_ids: list[int] = []
    job_labels: dict[int, str] = {}
    job_logs: dict[int, Path] = {}
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
            "-itol", str(fragment_tol),
            "-fixMod", "0",
            "-varMod", "1,2",
            "-maxVar", "4",
            "-hc",
            "-m", "1",
            "-s", "2",
            "-ms", str(mgf_path.resolve()),
            "-indexType", "2",
            "-db", str(db_path.resolve()) if db_path else "-",
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
        # Record chunk + log per job so a failure is diagnosable, and so its
        # verdict can be read from the job's own LSF log rather than `bjobs`.
        job_labels[jid] = f.name
        job_logs[jid] = log_path

    if job_ids:
        wait_for_jobs(job_ids, job_labels=job_labels, job_logs=job_logs)

    rank_files = sorted(result_dir.rglob("psm_rank.txt"))
    if not rank_files:
        raise RuntimeError(
            f"No psm_rank.txt files found in {result_dir}. Check logs in {log_dir}"
        )

    return result_dir
