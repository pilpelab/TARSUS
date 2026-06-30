"""Step 2: Build PepQuery index from mzML files (per-file parallel).

Submits one PepQuery index job per mzML file.  The Java heap is
auto-scaled to 2× the mzML file size (clamped to 8-24 GB), so both
small and large files get appropriate resources without wasted memory.

After all jobs complete, the per-file index fragments are merged
into a single ``pepquery_index/`` directory.

Override heap per file via ``TARSUS_PEPQUERY_HEAP_MB`` env var.
Override memory reservation via ``TARSUS_PEPQUERY_MEM_MB`` env var.
"""

import os
import shutil
from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs

_MIN_HEAP_MB = 8192
_MAX_HEAP_MB = 24576


def _resolve_heap_mb(
    mzml_path: Path,
    java_heap_mb: int | None = None,
    _size_gb: float | None = None,
) -> int:
    """Determine Java heap for a single mzML file.

    Priority:
      1. Explicit *java_heap_mb* argument
      2. ``TARSUS_PEPQUERY_HEAP_MB`` env var
      3. Auto: ``max(8192, min(file_gb * 2.0 * 1024, 24576))``

    The ``_size_gb`` parameter is for testing only — do not use in production.
    """
    if java_heap_mb is not None:
        return java_heap_mb
    env_val = os.environ.get("TARSUS_PEPQUERY_HEAP_MB")
    if env_val:
        return int(env_val)
    if _size_gb is not None:
        file_gb = _size_gb
    else:
        file_gb = mzml_path.stat().st_size / (1024**3)
    return max(_MIN_HEAP_MB, min(int(file_gb * 2.0 * 1024), _MAX_HEAP_MB))


def _resolve_mem_mb(heap_mb: int, memory_mb: int | None = None) -> int:
    """Determine LSF memory reservation.

    Priority:
      1. Explicit *memory_mb* argument
      2. ``TARSUS_PEPQUERY_MEM_MB`` env var
      3. *heap_mb* + 4096 (JVM overhead)
    """
    if memory_mb is not None:
        return memory_mb
    env_val = os.environ.get("TARSUS_PEPQUERY_MEM_MB")
    if env_val:
        return int(env_val)
    return heap_mb + 4096


def step02_make_index(
    mzml_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int | None = None,
    cpus: int = 1,
    java_heap_mb: int | None = None,
) -> Path:
    """Build PepQuery index — one LSF job per mzML file, then merge.

    The Java heap per file is auto-scaled based on mzML file size
    (see ``_resolve_heap_mb``).  After all jobs succeed, per-file
    index fragments are merged into ``pepquery_index/``.

    Returns:
        Path to the merged ``pepquery_index/`` directory.

    Raises:
        FileNotFoundError:  mzml_dir missing, no .mzML files, or tool missing.
        RuntimeError:       any indexing job failed or merge produced no output.
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

    # ── Per-file staging directories ──────────────────────────────────
    staging = output_dir / "_staging"
    staging.mkdir(parents=True, exist_ok=True)

    # ── Submit one PepQuery index job per mzML file ───────────────────
    job_ids: list[int] = []
    per_file_dirs: dict[Path, Path] = {}  # mzml_path → staging_dir

    for mzml_path in mzml_files:
        staging_dir = staging / mzml_path.stem
        staging_dir.mkdir(exist_ok=True)
        per_file_dirs[mzml_path] = staging_dir

        heap_mb = _resolve_heap_mb(mzml_path, java_heap_mb)
        mem_mb = _resolve_mem_mb(heap_mb, memory_mb)

        cmd = [
            str(java_bin),
            f"-Xmx{heap_mb}m",
            "-jar", str(pepquery_jar),
            "index",
            "-r",
            "-i", str(mzml_path.resolve()),
            "-o", str(staging_dir.resolve()),
        ]

        log_path = output_dir / f"step02_{mzml_path.stem}.log"
        jid = submit_bsub(
            cmd,
            job_name=f"pqidx_{mzml_path.stem[:30]}",
            queue=queue,
            memory_mb=mem_mb,
            cpus=cpus,
            log_path=log_path,
            tool_env=tool_env,
        )
        job_ids.append(jid)

    # ── Wait for all indexing jobs ────────────────────────────────────
    wait_for_jobs(job_ids)

    # ── Merge per-file fragments into final index ─────────────────────
    index_dir = output_dir / "pepquery_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = index_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    for idx, (mzml_path, staging_dir) in enumerate(per_file_dirs.items()):
        src_tmp = staging_dir / "tmp"
        if not src_tmp.is_dir():
            raise RuntimeError(
                f"PepQuery index tmp/ not created for {mzml_path.name}. "
                f"Check log: {output_dir / f'step02_{mzml_path.stem}.log'}"
            )
        # Copy each per-file fragment dir into the merged tmp/
        for fragment in sorted(src_tmp.iterdir()):
            if fragment.is_dir():
                dest = tmp_dir / f"{mzml_path.name}_{idx}"
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(fragment, dest)
                break  # only one per file

    # Generate summary.txt (PepQuery lists indexed files here)
    with (index_dir / "summary.txt").open("w") as f:
        for mzml_path in mzml_files:
            f.write(f"{mzml_path.resolve()}\n")

    if not tmp_dir.is_dir() or not any(tmp_dir.iterdir()):
        raise RuntimeError(
            f"PepQuery index merge produced no output at {index_dir}. "
            f"Check per-file logs in {output_dir}/"
        )

    return index_dir
