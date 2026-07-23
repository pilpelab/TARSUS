"""TARSUS CLI — single-entry-point for the pipeline.

Usage:
    tarsus run --fasta <path> --input <raw...> --output-dir <path>
    tarsus convert ...
"""

import os
import sys
from pathlib import Path

import click

from .env import ToolEnvironment
from .lsf import submit_bsub
from .provenance import (
    git_sha,
    DirtyTreeError,
    check_clean_tree,
    stale_artifacts,
    write_provenance,
)


# ── CLI group ────────────────────────────────────────────────────────


@click.group()
def main() -> None:
    """TARSUS — TArgeted SUbstitution Search pipeline."""


# ── Step 1: convert (already implemented, kept for backward compat) ──


@main.command()
@click.option("--input", "-i", "inputs", multiple=True, required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="Raw MS file(s) to convert")
@click.option("--output-dir", "-o", required=True, type=click.Path(),
              help="Output directory for mzML files")
@click.option("--queue", default="gsla-cpu", show_default=True,
              help="LSF queue")
@click.option("--memory", default=7000, type=int, show_default=True,
              help="Memory per job in MB")
@click.option("--cpus", default=1, type=int, show_default=True,
              help="CPUs per job")
@click.option("--local", is_flag=True,
              help="Run locally instead of submitting to LSF")
def convert(inputs: tuple[str, ...], output_dir: str, queue: str,
            memory: int, cpus: int, local: bool) -> None:
    """Step 1: Convert .raw files to .mzML."""
    from .steps.step01_convert import step01_convert

    tool_env = ToolEnvironment.from_env()
    raw_files = [Path(f) for f in inputs]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    mzml_paths = step01_convert(
        raw_files=raw_files, output_dir=out, tool_env=tool_env,
        queue=queue, memory_mb=memory, cpus=cpus, local=local,
    )

    click.echo(f"Submitted {len(mzml_paths)} conversion job(s):")
    for p in mzml_paths:
        click.echo(f"  {p.name}")
    if not local:
        click.echo("Use 'bjobs' to monitor progress.")


# ── tarsus run — full pipeline orchestration ──────────────────────────


@main.command()
@click.option("--fasta", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Reference proteome FASTA file")
@click.option("--input", "-i", "inputs", multiple=True, required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="Raw MS file(s) (.raw)")
@click.option("--output-dir", "-o", required=True, type=click.Path(),
              help="Output directory (will be created)")
@click.option("--queue", default="gsla-cpu", show_default=True,
              help="LSF queue for all jobs")
@click.option("--memory", default=32000, type=int, show_default=True,
              help="Memory for the master orchestration job in MB")
@click.option("--cds", required=True, type=click.Path(exists=True, dir_okay=False),
              help="CDS (nucleotide) FASTA — required for the 64x19 codon heatmap. "
                   "Mistranslation happens in codon space: an engineered tRNA reads ONE "
                   "codon, so amino-acid-level counts smear the signal across synonymous codons.")
@click.option("--allow-dirty", is_flag=True,
              help="Run despite uncommitted changes (results become unattributable)")
def run(
    fasta: str, inputs: tuple[str, ...], output_dir: str, queue: str, memory: int,
    cds: str, allow_dirty: bool,
) -> None:
    """Run the full TARSUS pipeline on LSF.

    Submits a single master job that orchestrates all 11 steps on
    an LSF compute node.  Monitor with: bjobs
    """
    raw_files = [Path(f).resolve() for f in inputs]
    fasta_path = Path(fasta).resolve()
    outdir = Path(output_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    # Validate inputs
    for f in raw_files:
        if f.suffix.lower() != ".raw":
            raise click.BadParameter(
                f"Expected .raw file, got: {f.name}", param_hint="--input")
    if fasta_path.suffix.lower() not in (".fasta", ".fa", ".faa"):
        click.echo(f"Warning: FASTA file has unexpected extension: {fasta_path.suffix}",
                   err=True)

    # A run from a dirty tree is attributable to no commit. TWICE (D-057, D-061) a
    # Step 3b library built by since-fixed code silently voided every result, and
    # nothing recorded which code produced it.
    try:
        check_clean_tree(allow_dirty=allow_dirty)
    except DirtyTreeError as exc:
        raise click.ClickException(str(exc)) from exc

    # Warn loudly about any preserved .done that predates its own step's code.
    for warning in stale_artifacts(outdir):
        click.echo(f"WARNING: {warning}", err=True)

    cds_path = Path(cds).resolve()

    prov = write_provenance(outdir, {
        "fasta": str(fasta_path),
        "inputs": [str(f) for f in raw_files],
        "output_dir": str(outdir),
        "cds": str(cds_path) if cds_path else None,
        "queue": queue,
        "memory_mb": memory,
        "allow_dirty": allow_dirty,
    })

    # Submit master job — runs tarsus.orchestration on a compute node
    os.environ["PYTHONUNBUFFERED"] = "1"
    python_bin = sys.executable
    tool_env = ToolEnvironment.from_env()
    log_path = outdir / "master.log"

    cds_args = ["--cds", str(cds_path)]
    jid = submit_bsub(
        cmd=[python_bin, "-m", "tarsus.orchestration", *cds_args,
             str(outdir), str(fasta_path),
             *[str(f) for f in raw_files]],
        job_name="tarsus_master",
        queue=queue,
        memory_mb=memory,
        cpus=1,
        log_path=log_path,
        tool_env=tool_env,
    )

    click.echo(f"\nSubmitted master job <{jid}> to queue '{queue}'.")
    click.echo(f"  Monitor:  bjobs {jid}")
    click.echo(f"  Log:      {log_path}")
    click.echo(f"  Output:   {outdir}/")
    click.echo(f"  Code:     {prov.name} (git {git_sha() or 'unknown'})")


if __name__ == "__main__":
    main()
