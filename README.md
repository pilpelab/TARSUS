# TARSUS_BC

**TArgeted SUbstitution Search** — proteomics pipeline for detecting validated single amino acid substitutions (SAAVs) from mass spectrometry data.

Configurable, shareable implementation based on: Tretyachenko et al. (2025). *bioRxiv*. https://www.biorxiv.org/content/10.1101/2025.02.17.638604v1

Reference implementation: `TARSUS_elizabev/` (read-only — see `.context/reference-pipeline.md`)

---

## Quick Start

```bash
# 1. Set up environment
make setup                  # download all external tools (JDK, .NET, FragPipe, etc.)
source .venv/bin/activate   # activate Python venv

# 2. Verify tools
make test-tools             # all 8 tools should pass (JDK, .NET, FragPipe, MSFragger, IonQuant, PepQuery, PDV, ThermoRawFileParser)

# 3. Run the pipeline (everything on LSF)
tarsus run --fasta protein.fasta \
           -i sample1.raw \
           -i sample2.raw \
           -o output/my-run/

# Monitor progress:
bjobs                        # check master job status
tail -f output/my-run/master.log  # real-time step progress
```

## CLI

```
tarsus run      Run the full 11-step pipeline (single LSF master job)
tarsus convert  Step 1 only: convert .raw → .mzML
```

`tarsus run` accepts three required flags:
- `--fasta` — reference proteome FASTA
- `--input` / `-i` — raw MS files (repeatable)
- `--output-dir` / `-o` — output directory (auto-structured)

## Output

```
output/my-run/
├── 01_mzml/               .mzML files
├── 02_index/              PepQuery index
├── 03a_first_pass/        FragPipe first pass
├── 03b_candidates/        pep_candidates.fa
├── 03c_second_pass/       FragPipe second pass
├── 04_psm_input/          PSM input for PepQuery
├── 05_pepquery/           PepQuery validation
├── 06_aggregated/         psmrankall.txt + PDV spectra
├── 07_analyze/            subs.ipc
├── 08_base_input/         Reference rescoring inputs
├── 09_pepquery_base/      PepQuery base rescoring
├── 10_aggregated_base/    Aggregated base results
├── 11_localized/          subs_localized.ipc + .csv  ← FINAL
├── master.py              Generated orchestration script
└── master.log             Step-by-step progress log
```

## Architecture

All steps run on LSF. A single master job orchestrates heavy tools (ThermoRawFileParser, FragPipe, PepQuery) via child bsub jobs and runs Python analysis (mutagenesis, filtering, localization) inline on the compute node. The login node is only used for the initial submission.

**Note:** Step 2 (PepQuery index) runs **after** Step 3a (FragPipe first pass) to index only the unidentified spectra (`_sub.mzML` files).

> **⚠️ Status: not end-to-end validated.** Step 4 emits peptide-only input, so Step 5 runs PepQuery in open-search mode and Step 7's exact spectrum-title join matches nothing — `subs.ipc` comes out with 0 rows and the Step 8 guardrail halts the run before Steps 9–11. A run that reaches Step 8 and stops is the *expected* current behaviour, not a crash. See the "OPEN BLOCKER" section of `.context/architecture.md` and decisions D-044/D-045/D-046.

See `.context/architecture.md` for full details.

## Setup

```bash
uv venv --python 3.11
source .venv/bin/activate
uv sync
make setup
make test-tools   # verify everything works
```

## Tests

```bash
uv run pytest -m "not lsf"                         # 163 tests, ~60s — the normal dev loop
uv run pytest                                      # 166 tests; the 3 extra are @pytest.mark.lsf
                                                   # real-tool tests (FragPipe/PepQuery) that take
                                                   # many minutes and need cluster + `make setup`
uv run mypy src/tarsus                              # type checking
make test-tools                                    # tool integrity (8 tools including IonQuant)
make test-pdv-full                                 # PDV + Xvfb integration
```

## Project Structure

```
src/tarsus/     Python package (steps, CLI, env, LSF helpers)
tests/          pytest tests (166)
tools/          External tools (downloaded via make setup)
data/           Test datasets (gitignored)
.context/       Architecture and reference docs
.memory/        Project memory, decisions, progress
.agents/        Agent operating instructions
TARSUS_elizabev/ READ-ONLY reference implementation
```
