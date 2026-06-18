"""Step 3c: FragPipe second-pass (nocleavage) against variant peptides.

Depends on Step 3a output directory and Step 3b pep_candidates.fa.
"""

import re
from pathlib import Path
from ..env import ToolEnvironment
from ..lsf import submit_bsub, wait_for_jobs, _build_env_cmd


def step03c_second_pass(
    mzml_dir: Path,
    pep_candidates: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    queue: str = "gsla-cpu",
    memory_mb: int = 30000,
    cpus: int = 10,
    fragpipe_ram_gb: int = 125,
) -> Path:
    """Run FragPipe second-pass (nocleavage) search against variant peptides."""
    if not mzml_dir.is_dir():
        raise FileNotFoundError(f"mzML directory not found: {mzml_dir}")
    mzml_files = sorted(mzml_dir.glob("*.mzML"))
    if not mzml_files:
        raise FileNotFoundError(f"No .mzML files found in {mzml_dir}")
    if not pep_candidates.is_file():
        raise FileNotFoundError(f"Variant FASTA not found: {pep_candidates}")

    philosopher = (
        tool_env.fragpipe_dir / "tools" / "Philosopher" / "philosopher-v5.1.3-RC9"
    )
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

    second_dir = output_dir / "second"
    second_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "step03c.log"

    patches = [
        (r"^database\.db-path=.*$", f"database.db-path={pep_candidates.resolve()}"),
        (r"^database\.decoy-tag=.*$", "database.decoy-tag=rev_"),
        (r"^ionquant\.minisotopes=.*$", "ionquant.minisotopes=1"),
        (r"^ionquant\.minscans=.*$", "ionquant.minscans=1"),
        (r"^msfragger\.clip_nTerm_M=.*$", "msfragger.clip_nTerm_M=false"),
        (r"^msfragger\.misc\.fragger\.enzyme-dropdown-1=.*$",
         "msfragger.misc.fragger.enzyme-dropdown-1=nocleavage"),
        (r"^msfragger\.remove_precursor_peak=.*$", "msfragger.remove_precursor_peak=0"),
        (r"^msfragger\.search_enzyme_cut_1=.*$", "msfragger.search_enzyme_cut_1=@"),
        (r"^msfragger\.search_enzyme_name_1=.*$", "msfragger.search_enzyme_name_1=nocleavage"),
        (r"^msfragger\.search_enzyme_nocut_1=.*$", "msfragger.search_enzyme_nocut_1=@"),
        (r"^msbooster\.find-best-rt-model=.*$", "msbooster.find-best-rt-model=false"),
    ]
    with workflow_template.open("r") as f:
        content = f.read()
    for pattern, replacement in patches:
        content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)

    second_workflow = output_dir / "second.workflow"
    with second_workflow.open("w") as f:
        f.write(content)

    manifest = output_dir / "second.manifest"
    with manifest.open("w") as f:
        for mzml in mzml_files:
            f.write(f"{mzml.resolve()}\t\t\tDDA\n")

    runner = output_dir / "step03c_runner.sh"
    runner.write_text(f"""#!/bin/bash
set -euo pipefail
{_build_env_cmd(tool_env)}
PHILOSOPHER="{philosopher}"
FRAGPIPE="{fragpipe}"
"$PHILOSOPHER" workspace --init "{output_dir}"
"$PHILOSOPHER" database --custom "{pep_candidates}" "{output_dir}"
"$FRAGPIPE" --headless --ram {fragpipe_ram_gb} \
  --workflow "{second_workflow}" \
  --manifest "{manifest}" \
  --workdir "{second_dir}"
""")
    runner.chmod(0o755)

    jid = submit_bsub(
        ["bash", str(runner)],
        job_name="step03c",
        queue=queue,
        memory_mb=memory_mb,
        cpus=cpus,
        log_path=log_path,
        tool_env=tool_env,
    )
    wait_for_jobs([jid])

    psm_tsv = second_dir / "psm.tsv"
    if not psm_tsv.is_file():
        raise RuntimeError(f"Second-pass psm.tsv not found. Check log: {log_path}")

    return second_dir
