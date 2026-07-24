"""Step 3a: FragPipe first-pass database search.

Prepares inputs, submits a single LSF job that runs Philosopher workspace,
decoy database, and FragPipe headless search, then validates outputs.
"""

import re
from pathlib import Path
from ..assets import WORKFLOW_TEMPLATE
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs, _build_env_cmd


def _make_decoy_fasta(fasta_path: Path, output_dir: Path) -> Path:
    """Generate a target-decoy FASTA with rev_ prefix decoy sequences."""
    decoy_fasta = output_dir / "protein_decoy.fasta"
    if decoy_fasta.is_file():
        return decoy_fasta

    with fasta_path.open("r") as fin, decoy_fasta.open("w") as fout:
        header = None
        seq_lines: list[str] = []
        for line in fin:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(">"):
                if header:
                    seq = "".join(seq_lines)
                    fout.write(f"{header}\n")
                    for i in range(0, len(seq), 60):
                        fout.write(seq[i:i + 60] + "\n")
                    decoy_seq = seq[::-1]
                    fout.write(f">rev_{header[1:]}\n")
                    for i in range(0, len(decoy_seq), 60):
                        fout.write(decoy_seq[i:i + 60] + "\n")
                header = stripped
                seq_lines = []
            else:
                seq_lines.append(stripped)
        if header:
            seq = "".join(seq_lines)
            fout.write(f"{header}\n")
            for i in range(0, len(seq), 60):
                fout.write(seq[i:i + 60] + "\n")
            decoy_seq = seq[::-1]
            fout.write(f">rev_{header[1:]}\n")
            for i in range(0, len(decoy_seq), 60):
                fout.write(decoy_seq[i:i + 60] + "\n")

    return decoy_fasta


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

# NOTE: no `philosopher database --custom` here. FragPipe runs it itself, from the
# workflow's `database.db-path` (verified in step03a.log). Calling it ourselves on
# an ALREADY-DECOYED fasta made Philosopher decoy it a second time, producing a
# multi-GB `*-decoys-protein_decoy.fasta.fas` full of `rev_rev_` entries — written
# to CWD and never used by anything. See D-062.

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

    workflow_template = WORKFLOW_TEMPLATE
    if not workflow_template.is_file():
        raise FileNotFoundError(f"Workflow template not found: {workflow_template}")

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "step03a.log"

    # 1. Generate target-decoy FASTA (FragPipe requires decoys in the FASTA)
    decoy_fasta = _make_decoy_fasta(fasta_path, output_dir)

    # 2. Patch workflow template: decoy FASTA path.
    #
    # MSBooster is deliberately NOT disabled here. It used to be, purely to skip
    # "redundant calibration PNGs" (cfd4886) — an efficiency tidy-up, not a
    # correctness fix. That deviation silently emptied `SpectralSim`/`RTScore`:
    # FragPipe writes those two psm.tsv columns (18-19, right after `Delta Mass`)
    # only when MSBooster runs, and Step 7 carries psm.tsv columns through
    # verbatim. The reference workflows (EVpar `fragpipe.workflow` and
    # `fragpipe-second-pass.workflow`) both ship `run-msbooster=true` with
    # `predict-rt`/`predict-spectra=true` and local DIA-NN models, and our
    # `generic.workflow` template already matches them — so leave the template's
    # MSBooster block alone. See D-069.
    first_workflow = output_dir / "first.workflow"
    with workflow_template.open("r") as f:
        content = f.read()
    db_line = f"database.db-path={decoy_fasta.resolve()}"
    patches: list[tuple[str, str]] = [
        (r"^database\.db-path=.*$", db_line),
    ]
    for pattern, replacement in patches:
        content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
    with first_workflow.open("w") as f:
        f.write(content)

    # 3. Create FragPipe manifest
    manifest = output_dir / "first.manifest"
    with manifest.open("w") as f:
        for mzml in mzml_files:
            f.write(f"{mzml.resolve()}\t\t\tDDA\n")

    # 4. Write and submit the runner script
    runner = output_dir / "step03a_runner.sh"
    runner.write_text(_make_bash_script(
        output_dir=output_dir,
        philosopher=philosopher,
        fragpipe=fragpipe,
        fasta_path=decoy_fasta,
        first_workflow=first_workflow,
        manifest=manifest,
        fragpipe_ram_gb=fragpipe_ram_gb,
        env_cmd=_build_env_cmd(tool_env),
    ))
    runner.chmod(0o755)

    # 5. Submit via bsub as a single job
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

    # 6. Validate outputs
    psm_tsv = output_dir / "psm.tsv"
    peptide_tsv = output_dir / "peptide.tsv"
    if not psm_tsv.is_file():
        raise RuntimeError(f"First-pass psm.tsv not created. Check log: {log_path}")
    if not peptide_tsv.is_file():
        raise RuntimeError(f"First-pass peptide.tsv not created. Check log: {log_path}")

    return output_dir
