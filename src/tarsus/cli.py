import click
from pathlib import Path
from .env import ToolEnvironment
from .steps.step01_convert import step01_convert


@click.group()
def main():
    """TARSUS — TArgeted SUbstitution Search pipeline."""


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
def convert(inputs, output_dir, queue, memory, cpus, local):
    """Step 1: Convert .raw files to .mzML."""
    tool_env = ToolEnvironment.from_env()
    raw_files = [Path(f) for f in inputs]
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    mzml_paths = step01_convert(
        raw_files=raw_files,
        output_dir=out,
        tool_env=tool_env,
        queue=queue,
        memory_mb=memory,
        cpus=cpus,
        local=local,
    )

    click.echo(f"Submitted {len(mzml_paths)} conversion job(s):")
    for p in mzml_paths:
        click.echo(f"  {p.name}")
    if not local:
        click.echo("Use 'bjobs' to monitor progress.")


if __name__ == "__main__":
    main()
