"""Step 3a: FragPipe first-pass database search.

Prepares inputs, submits a single LSF job that runs Philosopher workspace,
decoy database, and FragPipe headless search, then validates outputs.
"""

import re
from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs, _build_env_cmd


def _make_bash_script(
    output_dir: Path,
    philosopher: Path,
    fragpipe: Path,
    fasta_path: Path,
    first_workflow: Path,
    manifest: Path,
    fragpipe_ram_gb: int,
    env_cmd: str,
) -> str:
    """Generate the shell script that runs on the compute node."""
    return f"""#!/bin/bash
set -euo pipefail
{env_cmd}

PHILOSOPHER="{philosopher}"
FRAGPIPE="{fragpipe}"

echo "[step03a] Philosopher workspace --init"
"$PHILOSOPHER" workspace --init "{output_dir}"

echo "[step03a] Philosopher database --custom"
"$PHILOSOPHER" database --custom "{fasta_path}" "{output_dir}"

echo "[step03a] FragPipe --headless"
"$FRAGPIPE" --headless --ram {fragpipe_ram_gb} \
  --workflow "{first_workflow}" \
  --manifest "{manifest}" \
  --workdir "{output_dir}"

echo "[step03a] Done"
"""


def step03a_first_pass(
    fasta_path: Path,
    mzml_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int = 30000,
    cpus: int = 10,
    fragpipe_ram_gb: int = 125,
) -> Path:
    """Run FragPipe first-pass search via LSF.

    Returns path to the output directory containing search results.
    """
    if not fasta_path.is_file():
        raise FileNotFoundError(f"FASTA not found: {fasta_path}")
    if not mzml_dir.is_dir():
        raise FileNotFoundError(f"mzML directory not found: {mzml_dir}")
    mzml_files = sorted(mzml_dir.glob("*.mzML"))
    if not mzml_files:
        raise FileNotFoundError(f"No .mzML files found in {mzml_dir}")

    philosopher = tool_env.fragpipe_dir / "tools" / "Philosopher" / "philosopher-v5.1.3-RC9"
    if not philosopher.is_file():
        raise FileNotFoundError(f"Philosopher not found: {philosopher}")

    fragpipe = tool_env.fragpipe_bin
    if not fragpipe.is_file():
        raise FileNotFoundError(f"FragPipe not found: {fragpipe}")

    workflow_template = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "TARSUS_elizabev" / "generic.workflow"
    )
    if not workflow_template.is_file():
        raise FileNotFoundError(f"Workflow template not found: {workflow_template}")

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "step03a.log"

    # 1. Patch workflow template with the actual FASTA path
    first_workflow = output_dir / "first.workflow"
    with workflow_template.open("r") as f:
        content = f.read()
    db_line = f"database.db-path={fasta_path.resolve()}"
    content = re.sub(
        r"^database\.db-path=.*$", db_line,
        content, count=1, flags=re.MULTILINE,
    )
    with first_workflow.open("w") as f:
        f.write(content)

    # 2. Create FragPipe manifest
    manifest = output_dir / "first.manifest"
    with manifest.open("w") as f:
        for mzml in mzml_files:
            f.write(f"{mzml.resolve()}\t\t\tDDA\n")

    # 3. Write and submit the runner script
    runner = output_dir / "step03a_runner.sh"
    runner.write_text(_make_bash_script(
        output_dir=output_dir,
        philosopher=philosopher,
        fragpipe=fragpipe,
        fasta_path=fasta_path,
        first_workflow=first_workflow,
        manifest=manifest,
        fragpipe_ram_gb=fragpipe_ram_gb,
        env_cmd=_build_env_cmd(tool_env),
    ))
    runner.chmod(0o755)

    # 4. Submit via bsub as a single job
    cmd = ["bash", str(runner)]
    jid = submit_bsub(
        cmd,
        job_name="step03a",
        queue=queue,
        memory_mb=memory_mb,
        cpus=cpus,
        log_path=log_path,
        tool_env=tool_env,
    )
    wait_for_jobs([jid])

    # 5. Validate outputs
    psm_tsv = output_dir / "psm.tsv"
    peptide_tsv = output_dir / "peptide.tsv"
    if not psm_tsv.is_file():
        raise RuntimeError(f"First-pass psm.tsv not created. Check log: {log_path}")
    if not peptide_tsv.is_file():
        raise RuntimeError(f"First-pass peptide.tsv not created. Check log: {log_path}")

    return output_dir
