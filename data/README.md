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

## Validation mock spectra (`test-mock/dev.mzML`)

`dev.mzML` (50 spectra, ~18 MB) is used only by `tests/validation` and is **not**
tracked in git or shipped in the container. The validation suite `pytest.skip`s
cleanly when it is absent. To run validation locally, place a `dev.mzML` at
`data/test-mock/dev.mzML` (any small mzML with a handful of MS2 spectra works).
