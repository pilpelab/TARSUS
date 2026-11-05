"""Fetch the TARSUS paper's open supplementary files and convert the tables to TSV.

Paper: Tretyachenko et al., "Encoded and non-genetic protein variants expand the
human functional proteome", Nature (2026), doi:10.1038/s41586-026-11124-z.

Downloads the four Electronic Supplementary Material (ESM) files that Springer
serves without a subscription (Supplementary Information PDF, Reporting Summary,
Peer Review File, Supplementary Tables 1-18 ZIP) into ``<out>/raw/``, extracts the
ZIP into ``<out>/xlsx/`` and writes every sheet of every workbook as
``<out>/tsv/Supplementary_TableN__<sheet>.tsv``.

Standard library only (no openpyxl / pandas), so it runs on any python3.

Usage::

    uv run python scripts/fetch_paper_supplements.py            # -> data/paper/
    uv run python scripts/fetch_paper_supplements.py --out DIR

Interpretation of the tables lives in ``.context/paper-supplementary-tables.md``.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ESM_BASE = (
    "https://static-content.springer.com/esm/"
    "art%3A10.1038%2Fs41586-026-11124-z/MediaObjects/"
)
#: published name -> (ESM file name, minimum plausible size in bytes)
ESM_FILES: dict[str, tuple[str, int]] = {
    "supplementary_information.pdf": ("41586_2026_11124_MOESM1_ESM.pdf", 4_000_000),
    "reporting_summary.pdf": ("41586_2026_11124_MOESM2_ESM.pdf", 50_000),
    "peer_review_file.pdf": ("41586_2026_11124_MOESM3_ESM.pdf", 8_000_000),
    "supplementary_tables.zip": ("41586_2026_11124_MOESM4_ESM.zip", 10_000_000),
}
EXPECTED_TABLES = 18
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def download(url: str, dest: Path, min_bytes: int) -> None:
    """Download *url* to *dest* and fail loudly if the result is implausibly small.

    Args:
        url: Source URL.
        dest: Destination file path.
        min_bytes: Size below which the download is treated as truncated or an error page.

    Raises:
        RuntimeError: The downloaded file is smaller than ``min_bytes``.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "tarsus-paper-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    if len(data) < min_bytes:
        raise RuntimeError(
            f"{url} returned {len(data):,} bytes (< {min_bytes:,}); "
            "truncated download or an error page, not the file."
        )
    dest.write_bytes(data)


def _col_index(ref: str) -> int:
    """Convert an A1-style cell reference (``"AB12"``) to a 0-based column index."""
    match = re.match(r"[A-Z]+", ref)
    if match is None:
        raise ValueError(f"bad cell reference: {ref!r}")
    n = 0
    for ch in match.group(0):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(path: Path) -> list[tuple[str, list[list[str]]]]:
    """Read every sheet of an .xlsx workbook as a list of string rows.

    Args:
        path: Workbook path.

    Returns:
        ``[(sheet_name, rows), ...]`` in workbook order; cells are strings, tabs and
        newlines inside cells are replaced by spaces.
    """
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
    workbook = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target", "") for r in rels}
    sheets_el = workbook.find("m:sheets", NS)
    if sheets_el is None:
        raise ValueError(f"{path}: workbook has no <sheets>")
    out: list[tuple[str, list[list[str]]]] = []
    for sheet in sheets_el:
        name = sheet.get("name", "")
        target = targets[sheet.get(f"{{{NS['r']}}}id")].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        rows: list[list[str]] = []
        for row in ET.fromstring(z.read(target)).iter(f"{{{NS['m']}}}row"):
            cells: dict[int, str] = {}
            for c in row.findall("m:c", NS):
                v = c.find("m:v", NS)
                kind = c.get("t")
                if kind == "s" and v is not None and v.text is not None:
                    val = shared[int(v.text)]
                elif kind == "inlineStr":
                    val = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                else:
                    val = v.text if v is not None and v.text is not None else ""
                cells[_col_index(c.get("r", "A1"))] = val.replace("\t", " ").replace("\n", " ")
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        out.append((name, rows))
    return out


def main() -> int:
    """Download, extract and convert; print a per-sheet summary.

    Returns:
        Process exit code (0 on success).
    """
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("data/paper"), help="output directory")
    args = ap.parse_args()
    raw, xlsx_dir, tsv_dir = args.out / "raw", args.out / "xlsx", args.out / "tsv"
    for d in (raw, xlsx_dir, tsv_dir):
        d.mkdir(parents=True, exist_ok=True)

    for local, (esm, min_bytes) in ESM_FILES.items():
        dest = raw / local
        print(f"download {esm} -> {dest}")
        download(ESM_BASE + esm, dest, min_bytes)

    with zipfile.ZipFile(raw / "supplementary_tables.zip") as z:
        z.extractall(xlsx_dir)
    workbooks = sorted(
        xlsx_dir.glob("Supplementary_Table*.xlsx"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)),  # type: ignore[union-attr]
    )
    if len(workbooks) != EXPECTED_TABLES:
        raise RuntimeError(f"expected {EXPECTED_TABLES} workbooks, found {len(workbooks)}")

    for wb in workbooks:
        for sheet, rows in read_xlsx(wb):
            if not rows:
                raise RuntimeError(f"{wb.name} sheet {sheet!r} is empty")
            stem = f"{wb.stem}__{re.sub(r'[^A-Za-z0-9]+', '_', sheet).strip('_')}"
            with (tsv_dir / f"{stem}.tsv").open("w") as fh:
                for r in rows:
                    fh.write("\t".join(r) + "\n")
            print(f"  {stem}.tsv  {len(rows) - 1} data rows")
    print(f"done: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
