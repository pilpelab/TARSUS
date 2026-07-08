"""Step 6: Aggregate PepQuery results and run PDV.

Concatenates per-chunk PepQuery outputs (psm_rank.txt, ptm_detail.txt,
psm_rank.mgf), adds header rows, and runs PDV for ion extraction
(PDVExportResult.txt).

PDV requires an X11 display even in CLI mode. We use the self-contained
Xvfb bundle (tools/xvfb/) to provide one without GUI windows.

PDV itself is single-threaded (no thread/parallelism CLI flag exists —
confirmed by decompiling PDVCLIMainClass, see D-039). For real datasets
(tens of thousands of unique peptides) a single PDV process is too slow
(observed to be minutes-to-hours at full scale). We parallelize ourselves by sharding the PSM rows
across N independent PDV processes submitted as LSF child jobs (same
pattern as Step 5's PepQuery chunking), then merge PDFs + PDVExportResult.txt
from all shards. Set parallel=False to fall back to a single local process
(useful for small/test data where LSF submission overhead isn't worth it).
"""

import subprocess
import sys
from pathlib import Path
from ..env import ToolEnvironment, XvfbDisplay
from ..lsf import submit_bsub, wait_for_jobs


def step06_aggregate_query(
    result_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    java_heap_mb: int = 4096,
    parallel: bool = True,
    chunk_size: int = 20000,
    queue: str = "gsla-cpu",
    memory_mb: int = 4000,
    cpus: int = 1,
    shard_timeout: int = 28800,
) -> Path:
    """Concatenate PepQuery results and extract PDV ions.

    Args:
        result_dir: pepquery_result/ directory from Step 5.
        output_dir: Output directory for aggregated files.
        tool_env: Resolved tool environment.
        parallel: If True (default), shard PSM rows across N parallel PDV
            LSF child jobs. If False, run a single local PDV process
            (simpler, but much slower on real-scale data).
        chunk_size: PSM rows per shard when parallel=True.
        queue: LSF queue for shard jobs.
        memory_mb: Memory per shard job.
        cpus: CPUs per shard job.
        shard_timeout: Per-shard subprocess timeout in seconds.

    Returns:
        Path to pdv_spectra/ directory.
    """
    if not result_dir.is_dir():
        raise FileNotFoundError(f"PepQuery result directory not found: {result_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Concatenate psm_rank.txt → psmrankall.txt
    rank_files = sorted(result_dir.rglob("psm_rank.txt"))
    if not rank_files:
        raise RuntimeError(f"No psm_rank.txt files found in {result_dir}")

    # NOTE: blank lines must be dropped here. Chunks where PepQuery found
    # zero matching spectra produce header-only psm_rank.txt files
    # ("header\n"); content.split("\n") always yields a trailing empty
    # string for a newline-terminated file, so naively stripping the header
    # via lines[1:] left a stray blank line per zero-match chunk. With
    # thousands of chunks (most finding no matches), this produced
    # thousands of blank lines scattered through psmrankall.txt, which
    # crashed PDV's TextImport.parseTextFile() with
    # ArrayIndexOutOfBoundsException (a blank line splits by "\t" into a
    # single-element array, and PDV indexes into column 3/4). See D-038.
    psmrankall = output_dir / "psmrankall.txt"
    with psmrankall.open("w") as out:
        for i, f in enumerate(rank_files):
            content = f.read_text()
            lines = [line for line in content.split("\n") if line.strip()]
            if i > 0 and lines:
                lines = lines[1:]
            if lines:
                out.write("\n".join(lines) + "\n")

    # 2. Generate peptides.txt (first column)
    peptides = output_dir / "peptides.txt"
    with psmrankall.open("r") as fin, peptides.open("w") as fout:
        for line in fin:
            col = line.split("\t")[0].strip()
            if col and col != "peptide":
                fout.write(col + "\n")

    # 3. Concatenate ptm_detail.txt → ptmall.txt
    ptm_files = sorted(result_dir.rglob("ptm_detail.txt"))
    if ptm_files:
        ptmall = output_dir / "ptmall.txt"
        with ptmall.open("w") as out:
            for i, f in enumerate(ptm_files):
                content = f.read_text()
                lines = [line for line in content.split("\n") if line.strip()]
                if i > 0 and lines:
                    lines = lines[1:]
                if lines:
                    out.write("\n".join(lines) + "\n")

    # 4. Concatenate psm_rank.mgf → mgfall.mgf
    mgf_files = sorted(result_dir.rglob("psm_rank.mgf"))
    if mgf_files:
        mgfall = output_dir / "mgfall.mgf"
        with mgfall.open("w") as out:
            for f in mgf_files:
                out.write(f.read_text() + "\n")

    # 5. Run PDV report extraction (requires X11 — use bundled Xvfb if no $DISPLAY)
    pdv_jar = tool_env.pdv_jar
    if not pdv_jar.is_file():
        raise FileNotFoundError(f"PDV JAR not found: {pdv_jar}")
    java_bin = tool_env.java_bin

    pdv_spectra = output_dir / "pdv_spectra"
    pdv_spectra.mkdir(exist_ok=True)

    mgf_path = output_dir / "mgfall.mgf"
    if not mgf_path.is_file():
        mgf_path = output_dir / "mgfall.mgf"
        mgf_path.touch()

    if not parallel:
        # Single local process. NOTE: PDV's JVM does not reliably exit after
        # an uncaught exception (observed hanging indefinitely instead of
        # exiting with a non-zero code, see D-038) — the explicit timeout
        # prevents this from eating the full LSF wall-time budget.
        with XvfbDisplay(tool_env.tools_dir) as display_env:
            pdv_env = tool_env.env()
            pdv_env["DISPLAY"] = display_env.get("DISPLAY", "")
            subprocess.run(
                [
                    str(java_bin), f"-Xmx{java_heap_mb}m",
                    "-jar", str(pdv_jar),
                    "-r", str(psmrankall),
                    "-rt", "4",
                    "-s", str(mgf_path),
                    "-st", "1",
                    "-i", str(peptides),
                    "-k", "p",
                    "-o", str(pdv_spectra),
                    "-ft", "report",
                ],
                env=pdv_env, check=True, capture_output=True, text=True, timeout=shard_timeout,
            )
    else:
        _run_pdv_sharded(
            psmrankall=psmrankall,
            peptides=peptides,
            mgf_path=mgf_path,
            pdv_spectra=pdv_spectra,
            output_dir=output_dir,
            tool_env=tool_env,
            java_heap_mb=java_heap_mb,
            chunk_size=chunk_size,
            queue=queue,
            memory_mb=memory_mb,
            cpus=cpus,
            shard_timeout=shard_timeout,
        )

    if not pdv_spectra.is_dir() or not any(pdv_spectra.iterdir()):
        raise RuntimeError(f"PDV spectra not generated at {pdv_spectra}")

    return pdv_spectra


def _pdv_export_usable(export_file: Path, log_file: Path) -> bool:
    """Return True if a prior shard report exists and its log is not failed.

    PDV report mode may validly emit fewer rows than the input rank file when
    peptide filtering excludes entries, so line-count equality is not a safe
    completeness check. Instead, rely on the worker/LSF exit status recorded in
    the shard log: if the log contains a Python traceback or LSF exit-code
    footer, the export may be partial and must be regenerated.
    """
    if not export_file.is_file():
        return False
    if not log_file.is_file():
        return True
    log_text = log_file.read_text(errors="replace")
    failed_markers = ("Traceback", "Exited with exit code", "LSF job", "PDV shard failed")
    return not any(marker in log_text for marker in failed_markers)


def _group_chunk_rows(header: str, data_rows: list[str], chunk_size: int) -> list[list[str]]:
    """Chunk PSM rows into shards, keeping same-spectrum_title rows together.

    PDV assigns each row an internal rank key (spectrum_title + "_rank_" + N,
    N incrementing per repeated spectrum_title within ONE PDV process). This
    key never reaches the output columns, but PDV's downstream ion-annotation
    dict (built by Step 7) collapses duplicate (peptide, spectrum_title) rows
    to whichever is encountered last (see D-040 — inherited from the
    original reference pipeline, not something we introduce). Splitting a
    single spectrum_title's duplicate rows across different shards would add
    a *new* source of nondeterminism (shard-merge order) on top of the
    existing one (HashMap iteration order). Grouping rows by spectrum_title
    before chunking means every group is processed by exactly one PDV
    process, exactly reproducing the non-sharded tool's per-spectrum
    behavior — just parallelized, with no new cross-shard ambiguity.
    """
    header_cols = header.split("\t")
    try:
        title_idx = header_cols.index("spectrum_title")
    except ValueError:
        title_idx = 3  # fallback: known column position in psmrankall.txt

    groups: dict[str, list[str]] = {}
    for row in data_rows:
        cols = row.split("\t")
        key = cols[title_idx] if title_idx < len(cols) else row
        groups.setdefault(key, []).append(row)

    chunks: list[list[str]] = []
    current: list[str] = []
    for rows in groups.values():
        if current and len(current) + len(rows) > chunk_size:
            chunks.append(current)
            current = []
        current.extend(rows)
    if current:
        chunks.append(current)
    return chunks


def _run_pdv_sharded(
    psmrankall: Path,
    peptides: Path,
    mgf_path: Path,
    pdv_spectra: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    java_heap_mb: int,
    chunk_size: int,
    queue: str,
    memory_mb: int,
    cpus: int,
    shard_timeout: int,
) -> None:
    """Shard psmrankall.txt across N parallel PDV report jobs, then merge."""
    pdv_spectra.mkdir(parents=True, exist_ok=True)
    lines = [line for line in psmrankall.read_text().split("\n") if line.strip()]
    if not lines:
        raise RuntimeError(f"{psmrankall} has no data")
    header, data_rows = lines[0], lines[1:]
    if not data_rows:
        raise RuntimeError(f"{psmrankall} has a header but no PSM rows")

    chunks_dir = output_dir / "pdv_chunks"
    chunks_dir.mkdir(exist_ok=True)
    shard_root = output_dir / "pdv_spectra_shards"
    shard_root.mkdir(exist_ok=True)

    row_chunks = _group_chunk_rows(header, data_rows, chunk_size)

    python_bin = sys.executable
    job_ids: list[int] = []
    shard_dirs: list[Path] = []
    for idx, rows in enumerate(row_chunks):
        shard_id = f"{idx:04d}"
        shard_rank = chunks_dir / f"psmrank_{shard_id}.txt"
        shard_pep = chunks_dir / f"peptides_{shard_id}.txt"
        shard_out = shard_root / f"shard_{shard_id}"
        shard_dirs.append(shard_out)
        log_path = chunks_dir / f"shard_{shard_id}.log"

        # Resume: skip only shards that produced a report without a failed
        # shard log. PDV can leave a partial report before returning non-zero,
        # so file existence alone is not enough.
        if _pdv_export_usable(shard_out / "PDVExportResult.txt", log_path):
            continue

        shard_rank.write_text(header + "\n" + "\n".join(rows) + "\n")
        shard_peptide_seqs = sorted({row.split("\t")[0] for row in rows if row.split("\t")[0]})
        shard_pep.write_text("\n".join(shard_peptide_seqs) + "\n")

        cmd = [
            python_bin, "-m", "tarsus.steps._pdv_worker",
            str(shard_rank.resolve()), str(mgf_path.resolve()),
            str(shard_pep.resolve()), str(shard_out.resolve()), str(java_heap_mb),
        ]
        jid = submit_bsub(
            cmd, job_name=f"pdv_{shard_id}", queue=queue,
            memory_mb=memory_mb, cpus=cpus, log_path=log_path, tool_env=tool_env,
        )
        job_ids.append(jid)

    wait_for_jobs(job_ids)

    # Merge: concatenate PDVExportResult.txt (single header). If a shard
    # was run in image mode during debugging and produced PDFs, move them too;
    # production Step 6 uses `-ft report` because Step 7 consumes the report,
    # not the figures.
    export_path = pdv_spectra / "PDVExportResult.txt"
    header_written = False
    with export_path.open("w") as out:
        for shard_out in shard_dirs:
            result_file = shard_out / "PDVExportResult.txt"
            shard_id = shard_out.name.split("_")[-1]
            log_path = chunks_dir / f"shard_{shard_id}.log"
            if not _pdv_export_usable(result_file, log_path):
                continue
            shard_lines = [line for line in result_file.read_text().split("\n") if line.strip()]
            if not shard_lines:
                continue
            if not header_written:
                out.write(shard_lines[0] + "\n")
                header_written = True
            for line in shard_lines[1:]:
                out.write(line + "\n")
            for pdf in shard_out.glob("*.pdf"):
                dest = pdv_spectra / pdf.name
                # Replace stale partial PDFs from earlier failed/killed runs.
                # This mirrors a normal rerun's overwrite behavior and avoids
                # leaving old single-process PDV output mixed into the final
                # sharded output directory.
                pdf.replace(dest)

    if not header_written:
        raise RuntimeError(
            f"No shard produced PDVExportResult.txt — check logs in {chunks_dir}"
        )
