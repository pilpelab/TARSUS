"""Step 6: Aggregate PepQuery results and run PDV.

Concatenates per-chunk PepQuery outputs (psm_rank.txt, ptm_detail.txt,
psm_rank.mgf), adds header rows, and runs PDV for ion extraction.
"""

import subprocess
from pathlib import Path
from ..env import ToolEnvironment


def step06_aggregate_query(
    result_dir: Path,
    output_dir: Path,
    tool_env: ToolEnvironment,
    java_heap_mb: int = 4096,
) -> Path:
    """Concatenate PepQuery results and extract PDV ions.

    Args:
        result_dir: pepquery_result/ directory from Step 5.
        output_dir: Output directory for aggregated files.
        tool_env: Resolved tool environment.

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

    psmrankall = output_dir / "psmrankall.txt"
    with psmrankall.open("w") as out:
        for i, f in enumerate(rank_files):
            content = f.read_text()
            lines = content.split("\n")
            if i > 0 and lines:
                lines = lines[1:]
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
                lines = content.split("\n")
                if i > 0 and lines:
                    lines = lines[1:]
                out.write("\n".join(lines) + "\n")

    # 4. Concatenate psm_rank.mgf → mgfall.mgf
    mgf_files = sorted(result_dir.rglob("psm_rank.mgf"))
    if mgf_files:
        mgfall = output_dir / "mgfall.mgf"
        with mgfall.open("w") as out:
            for f in mgf_files:
                out.write(f.read_text() + "\n")

    # 5. Run PDV
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
            "-ft", "pdf",
        ],
        env=tool_env.env(), check=True, capture_output=True, text=True,
    )

    if not pdv_spectra.is_dir() or not any(pdv_spectra.iterdir()):
        raise RuntimeError(f"PDV spectra not generated at {pdv_spectra}")

    return pdv_spectra
