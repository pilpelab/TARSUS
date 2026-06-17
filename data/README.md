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
