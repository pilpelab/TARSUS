"""TARSUS CLI — single-entry-point for the pipeline.

Usage:
    tarsus run --fasta <path> --input <raw...> --output-dir <path>
    tarsus convert ...
"""

import os
import sys
import tomllib
from pathlib import Path

import click

from .env import ToolEnvironment
from .lsf import submit_bsub, use_group_readable_umask
from .provenance import (
    git_sha,
    DirtyTreeError,
    check_clean_tree,
    stale_artifacts,
    write_provenance,
)


# ── CDS default resolution ───────────────────────────────────────────


def _project_config_cds(start: Path) -> Path | None:
    """Return ``[tool.tarsus].cds`` from the nearest ``pyproject.toml``.

    Walks up from *start*; the first ``pyproject.toml`` carrying a
    ``[tool.tarsus].cds`` value wins. A relative value is resolved against the
    directory of the ``pyproject.toml`` that declared it, so a project can pin
    ``cds = "data/human_cds.fasta"`` and have it work from any cwd. Returns
    ``None`` when no project declares one — keeping the CDS optional.
    """
    for d in [start, *start.parents]:
        pp = d / "pyproject.toml"
        if not pp.is_file():
            continue
        try:
            data = tomllib.loads(pp.read_text())
        except tomllib.TOMLDecodeError:
            continue
        cds = data.get("tool", {}).get("tarsus", {}).get("cds")
        if cds:
            p = Path(cds)
            return p if p.is_absolute() else (d / p)
    return None


def _resolve_cds(cds: str | None, cwd: Path) -> Path | None:
    """Resolve the CDS FASTA: explicit flag > project config > env var > none.

    Externalized per project rules — no hardcoded path. ``--cds`` overrides
    everything; otherwise the nearest ``pyproject.toml``'s ``[tool.tarsus].cds``
    is used; otherwise ``TARSUS_CDS_FASTA``; otherwise ``None`` (Step 12's codon
    heatmap is skipped, as before).
    """
    if cds:
        return Path(cds).resolve()
    cfg = _project_config_cds(cwd)
    if cfg:
        return cfg.resolve()
    env = os.environ.get("TARSUS_CDS_FASTA")
    if env:
        return Path(env).resolve()
    return None


# ── CLI group ────────────────────────────────────────────────────────


@click.group()
def main() -> None:
    """TARSUS — TArgeted SUbstitution Search pipeline."""
    use_group_readable_umask()


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
@click.option("--cds", default=None, type=click.Path(exists=True, dir_okay=False),
              help="CDS (nucleotide) FASTA for the 64x19 codon heatmap. Optional: "
                   "falls back to [tool.tarsus].cds in the nearest pyproject.toml, then "
                   "the TARSUS_CDS_FASTA env var; if none resolve, the codon heatmap is "
                   "skipped. Mistranslation happens in codon space (an engineered tRNA "
                   "reads ONE codon), so this maps substitutions back to codons.")
@click.option("--localize-tol", default=None,
              type=click.FloatRange(min=0, min_open=True),
              help="Step 11 PyAscore fragment tolerance in Da. Default 0.01 "
                   "(Slava's published value, Orbitrap MS2); the paper uses 0.6 "
                   "for ion-trap MS2.")
@click.option("--msbooster-models", type=click.Choice(["best", "dia-nn"]),
              default="best", show_default=True,
              help="MSBooster RT/MS2 model selection. 'best' lets MSBooster pick "
                   "the best Koina model (Slava's setting; compute nodes need "
                   "internet to koina.wilhelmlab.org). 'dia-nn' pins the local "
                   "DIA-NN models, offline.")
@click.option("--base-rescore-tol", default=None,
              type=click.FloatRange(min=0, min_open=True),
              help="Step 9 PepQuery base-rescoring fragment tolerance (-itol) in Da. "
                   "Default 0.05 (Slava's production runs; reproduces his base "
                   "scores exactly). The published query_psm_base.sh says 0.01.")
@click.option("--allow-dirty", is_flag=True,
              help="Run despite uncommitted changes (results become unattributable)")
def run(
    fasta: str, inputs: tuple[str, ...], output_dir: str, queue: str, memory: int,
    cds: str, localize_tol: float | None, msbooster_models: str,
    base_rescore_tol: float | None, allow_dirty: bool,
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

    cds_path = _resolve_cds(cds, Path.cwd())
    if cds_path is not None and not cds_path.is_file():
        raise click.ClickException(f"CDS FASTA not found: {cds_path}")
    if cds_path is None:
        click.echo(
            "Note: no CDS resolved (no --cds, no [tool.tarsus].cds, no "
            "TARSUS_CDS_FASTA) — Step 12's codon heatmap will be skipped.",
            err=True,
        )

    prov = write_provenance(outdir, {
        "fasta": str(fasta_path),
        "inputs": [str(f) for f in raw_files],
        "output_dir": str(outdir),
        "cds": str(cds_path) if cds_path else None,
        "localize_tol_da": localize_tol,  # None = step11 DEFAULT_LOCALIZE_TOL_DA
        "msbooster_models": msbooster_models,
        "base_rescore_tol_da": base_rescore_tol,  # None = step09 DEFAULT_BASE_RESCORE_TOL_DA
        "queue": queue,
        "memory_mb": memory,
        "allow_dirty": allow_dirty,
    })

    # Submit master job — runs tarsus.orchestration on a compute node
    os.environ["PYTHONUNBUFFERED"] = "1"
    python_bin = sys.executable
    tool_env = ToolEnvironment.from_env()
    log_path = outdir / "master.log"

    cds_args = ["--cds", str(cds_path)] if cds_path else []
    tol_args = ["--localize-tol", repr(localize_tol)] if localize_tol is not None else []
    if base_rescore_tol is not None:
        tol_args += ["--base-rescore-tol", repr(base_rescore_tol)]
    jid = submit_bsub(
        cmd=[python_bin, "-m", "tarsus.orchestration", *cds_args, *tol_args,
             "--msbooster-models", msbooster_models,
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
