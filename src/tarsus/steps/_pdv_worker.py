"""Internal worker: run PDV on one shard of PSM data.

Not a public step — invoked as a subprocess (locally or via LSF bsub) by
step06_aggregate_query's parallel PDV sharding. Each worker owns its own
Xvfb display (self-contained, tools/xvfb/) since it may run as an
independent LSF child job on a different compute node than the master.

Usage:
    python -m tarsus.steps._pdv_worker <rank_file> <mgf_file> <peptides_file> \
        <output_dir> <java_heap_mb>
"""

import subprocess
import sys
from pathlib import Path

from ..env import ToolEnvironment, XvfbDisplay


def run_pdv_shard(
    rank_file: Path,
    mgf_file: Path,
    peptides_file: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    java_heap_mb: int = 4096,
    timeout: int = 28800,
) -> Path:
    """Run PDV against one shard of PSM data. Returns output_dir."""
    pdv_jar = tool_env.pdv_jar
    if not pdv_jar.is_file():
        raise FileNotFoundError(f"PDV JAR not found: {pdv_jar}")
    java_bin = tool_env.java_bin

    output_dir.mkdir(parents=True, exist_ok=True)

    with XvfbDisplay(tool_env.tools_dir) as display_env:
        pdv_env = tool_env.env()
        pdv_env["DISPLAY"] = display_env.get("DISPLAY", "")
        result = subprocess.run(
            [
                str(java_bin), f"-Xmx{java_heap_mb}m",
                "-jar", str(pdv_jar),
                "-r", str(rank_file),
                "-rt", "4",
                "-s", str(mgf_file),
                "-st", "1",
                "-i", str(peptides_file),
                "-k", "p",
                "-o", str(output_dir),
                "-ft", "report",
            ],
            env=pdv_env, check=False, capture_output=True, text=True, timeout=timeout,
        )

    export_file = output_dir / "PDVExportResult.txt"
    if result.returncode != 0 or not export_file.is_file():
        stderr_tail = "\n".join(result.stderr.splitlines()[-40:])
        stdout_tail = "\n".join(result.stdout.splitlines()[-20:])
        raise RuntimeError(
            f"PDV shard failed in {output_dir}: java rc={result.returncode}, "
            f"export_exists={export_file.is_file()}\n"
            f"STDERR tail:\n{stderr_tail}\nSTDOUT tail:\n{stdout_tail}"
        )

    return output_dir


def main() -> None:
    rank_file = Path(sys.argv[1])
    mgf_file = Path(sys.argv[2])
    peptides_file = Path(sys.argv[3])
    output_dir = Path(sys.argv[4])
    java_heap_mb = int(sys.argv[5]) if len(sys.argv) > 5 else 4096

    tool_env = ToolEnvironment.from_env()
    run_pdv_shard(rank_file, mgf_file, peptides_file, output_dir, tool_env, java_heap_mb)


if __name__ == "__main__":
    main()
