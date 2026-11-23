# Data Directory

This directory is a **gitignored workspace** for input data used during development and testing.

Place your reference FASTA and raw mass spectrometry files here for local use.
The pipeline never auto-discovers files in this directory — all inputs must be specified via CLI flags (`--fasta`, `--input`).

## Current test fixtures (not tracked)

- `protein.fasta` — E. coli K12 reference proteome (4,403 UniProt entries)
- `HouYM-25-G140-AstralDDA-AlaGGC-LS-1.raw` — Low Solubility fraction (11 GB)
- `HouYM-25-G140-AstralDDA-AlaGGC-HS-1.raw` — High Solubility fraction (7.3 GB)

Both raw files are from the same biological sample, acquired on an Orbitrap Astral in DDA mode.
LS/HS refers to solubility fractionation during detergent-based phase separation chromatography.

## Paper supplements (`paper/`)

`data/paper/` holds the open supplementary files of the TARSUS paper (Tretyachenko et al., Nature 2026): SI PDF, Reporting Summary, Peer Review File, and Supplementary Tables 1-18 as xlsx and TSV. Not tracked; regenerate with:

```bash
uv run python scripts/fetch_paper_supplements.py     # ~23 MB download, stdlib only
ls data/paper/tsv/ | wc -l                           # expect 36 TSV files (one per sheet)
wc -l data/paper/tsv/Supplementary_Table1__Supplementary_Table1.tsv   # expect 13911 (header + 13,910)
```

What the tables contain and how to read them: `.context/paper-supplementary-tables.md`.

## Validation mock spectra (`test-mock/dev.mzML`)

`dev.mzML` (50 spectra, ~18 MB) is used only by `tests/validation` and is **not**
tracked in git or shipped in the container. The validation suite `pytest.skip`s
cleanly when it is absent. To run validation locally, place a `dev.mzML` at
`data/test-mock/dev.mzML` (any small mzML with a handful of MS2 spectra works).
