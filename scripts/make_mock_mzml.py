#!/usr/bin/env python3
"""Extract first N MS2 spectra from an mzML file for mock testing.

Uses pyteomics streaming (use_index=False) to determine which spectra
(by sequential index) to keep, then scans the raw file to extract those
spectrum XML blocks.

Usage: uv run python scripts/make_mock_mzml.py <input.mzML> <output.mzML> [--spectra N]
"""
import argparse
import os
from pathlib import Path
from pyteomics import mzml


def extract(input_path: Path, output_path: Path, max_ms2: int) -> None:
    """Extract first N MS2 spectra plus surrounding MS1s from mzML."""
    # ── Pass 1: stream to determine which spectral indices to keep ──
    keep_indices: list[int] = []  # 0-based indices in spectrum list
    ms2_count = 0
    total_idx = 0

    with mzml.read(str(input_path), use_index=False) as reader:
        for spec in reader:
            ms_level = spec.get("ms level", 1)
            if ms_level == 2:
                if ms2_count < max_ms2:
                    keep_indices.append(total_idx)
                ms2_count += 1
            elif ms_level == 1:
                if ms2_count <= max_ms2:
                    keep_indices.append(total_idx)
            total_idx += 1
            if ms2_count >= max_ms2 and ms_level == 1:
                # We've passed the last MS2 — stop after collecting its MS1 context
                pass
            if ms2_count >= max_ms2 and ms_level == 2:
                break

    keep_set = set(keep_indices)
    print(f"Keeping {len(keep_indices)} spectra (MS2 count seen: {ms2_count})"
          f" out of {total_idx + 1} scanned")

    if not keep_indices:
        raise ValueError("No MS2 spectra found")

    # ── Pass 2: read header (before <spectrumList) ─────────────────
    header_bytes = b""
    with open(input_path, "rb") as f:
        while True:
            chunk = f.read(262144)
            if not chunk:
                break
            header_bytes += chunk
            idx = header_bytes.find(b"<spectrumList")
            if idx >= 0:
                header_bytes = header_bytes[:idx]
                break

    # ── Pass 3: read footer (from </spectrumList>, but strip
    #    chromatogramList and indexList to keep size small) ──
    footer_bytes = b"</spectrumList>\n"
    # Close run, mzML, indexedmzML — minimal valid closing
    has_indexed = b"<indexedmzML" in header_bytes
    if b"</run>" not in header_bytes and b"<run" in header_bytes:
        footer_bytes += b"  </run>\n"
    if b"</mzML>" not in header_bytes:
        footer_bytes += b"</mzML>\n"
    if has_indexed:
        footer_bytes += b"</indexedmzML>\n"

    # ── Pass 4: extract spectrum blocks by sequential index ─────────
    file_size = os.path.getsize(input_path)
    blocks: dict[int, bytes] = {}
    spec_idx = 0
    max_to_find = max(keep_indices) if keep_indices else 0

    with open(input_path, "rb") as f:
        # Skip to after <spectrumList ...>
        buf = b""
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            buf += chunk
            idx = buf.find(b"<spectrumList")
            if idx >= 0:
                tag_end = buf.find(b">", idx)
                if tag_end >= 0:
                    # Seek to after spectrumList opening tag
                    offset = f.tell() - len(buf) + tag_end + 1
                    f.seek(offset)
                break

        buf = b""
        while spec_idx <= max_to_find:
            chunk = f.read(1048576)
            if not chunk:
                break
            buf += chunk

            while True:
                start = _find_spec_start(buf)
                if start < 0:
                    break
                end = buf.find(b"</spectrum>", start)
                if end < 0:
                    break
                end += len(b"</spectrum>")

                if spec_idx in keep_set:
                    blocks[spec_idx] = buf[start:end]

                spec_idx += 1
                buf = buf[end:]

                if spec_idx > max_to_find:
                    break

    print(f"Extracted {len(blocks)}/{len(keep_indices)} blocks"
          f" (scanned {spec_idx} spectra)")

    # ── Pass 5: write output ──────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as out:
        out.write(header_bytes)
        out.write(f'  <spectrumList count="{len(keep_indices)}">\n'.encode())
        for si in keep_indices:
            blk = blocks.get(si)
            if blk:
                out.write(b"    ")
                out.write(blk)
                out.write(b"\n")
        out.write(footer_bytes)

    size_mb = output_path.stat().st_size / 1e6
    ms2_saved = sum(1 for i in keep_indices if True)  # approximate
    print(f"Output: {len(keep_indices)} spectra, {size_mb:.1f} MB → {output_path}")


def _find_spec_start(data: bytes) -> int:
    """Find start of a <spectrum element (not </spectrum, not <spectrumList)."""
    pos = 0
    while True:
        idx = data.find(b"<spectrum", pos)
        if idx < 0:
            return -1
        after = idx + 9  # len(b"<spectrum")
        if after >= len(data):
            return -1
        ch = data[after:after + 1]
        if ch in (b" ", b">"):
            # Verify it's not spectrumList
            if not data[idx:idx+13].startswith(b"<spectrumList"):
                return idx
        pos = after


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--spectra", type=int, default=50)
    args = parser.parse_args()

    extract(args.input, args.output, args.spectra)


if __name__ == "__main__":
    main()
