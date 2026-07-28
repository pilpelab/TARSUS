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

Optional:
- `--cds` — CDS (nucleotide) FASTA. Enables Step 12's **64×19 codon heatmap**. Mistranslation
  happens in *codon* space — an engineered tRNA reads ONE codon — so without this the
  amino-acid-level counts smear the signal across synonymous codons. Absent → that figure is
  skipped **loudly**, never silently.
- `--allow-dirty` — run despite uncommitted changes (results become unattributable; see
  *Provenance* below).

## ⚠️ Read this before interpreting results

### Your search space is set by the first pass — but the result is robust to it

Step 3b mutagenizes **every peptide your first pass identified**. Identify 4,854 peptides →
~941,000 variant candidates; identify 42 → ~12,000. Nobody picks this; it falls out of the
first pass.

Search-space size **does** move the FragPipe search: more candidates → more decoys → a higher
score threshold at the same FDR. **Measured** on hoMS/GAPDH (identical spectra and parameters,
only the library scope changed):

| library | candidates | 2nd-pass PSMs | PepQuery confident | **localized (final)** |
|---|---|---|---|---|
| proteome-wide | 941,020 | 8,979 | 165 | **44** |
| GAPDH-only | 11,732 | **13,744** (+53%) | 160 | **45** |

**An 80× smaller library gave 53% more second-pass PSMs and changed the final answer by one
substitution.** The gain dies at PepQuery — the extra PSMs are ones it declines to confirm, and
the confident count is essentially invariant (165 vs 160).

**So: do not restrict the library hoping for sensitivity — it does not work.** The output is
robust to scope, which also means a proteome-wide search is *not* suppressing your results via
FDR. Restricting the library is only worth it for **runtime/cost** (an 80× smaller second-pass
search is far cheaper), never for yield.

Still check `12_visualize/protein_burden.png` to know what you are looking at: hoMS puts 43 of
44 substitutions on GAPDH (a purified reporter), while the E. coli tRNA runs spread across
84–174 proteins (a proteome-wide survey). That changes interpretation — it does not change how
you should search.

### Ile / Leu

Ile and Leu are isobaric (113.08406 Da), but the two ends of a substitution are **not**
equally knowable:

| | source | knowable? | reported as |
|---|---|---|---|
| **origin** | the base peptide → reference proteome → **genome codon** | **yes** | a definite `I` or `L` |
| **destination** | MS **mass** only | **no** | **`I/L`** |

There is no such thing as an `I/L` **origin**. Internally the pipeline collapses the pair to a
single letter `I` for matching and mass lookups, and only labels `I/L` at the last write — the
`/` must never reach a lookup key. See `docs/IL-AMBIGUITY.md` and decisions D-064 / D-065.

### Provenance

`tarsus run` **refuses to start from a dirty git tree** and records `git_sha` in
`provenance.json`. This is not pedantry: twice (D-057, D-061) a Step 3b library built by
since-fixed code silently invalidated every result, and nothing recorded which code produced
it. It also warns about any `.done` artifact older than the code that produced it.

**Do not edit `src/` while a run is in flight.** Orchestration imports step modules *lazily*, so
a mid-run edit is executed by the live job at an arbitrary future step.

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
├── 12_visualize/          plots (see below)
├── provenance.json        git_sha + args that produced this run
├── master.py              Generated orchestration script
└── master.log             Step-by-step progress log
```

**Step 12 figures** (`12_visualize/`):

| file | what |
|---|---|
| `sixty_twenty.png` / `_log.png` | **64×19 codon heatmap** — all 64 codons × 19 destination classes. Needs `--cds`. |
| `substitution_heatmap.png` | fixed **20×19** grid: 20 origin AAs (I/L separate) × 19 destinations (`I/L` merged) |
| `protein_burden.png` | which proteins carry the substitutions — **check this first** (see the search-space note above) |
| `origin_frequencies.png`, `top_substitutions.png`, `dpbp_distribution.png` | supporting |
| `sixty_twenty.csv` | the codon matrix as data |

Both heatmaps are **fixed grids**: an origin/destination/codon that does not occur is drawn as
an empty cell, never dropped, so runs are comparable cell-for-cell.

## Docs

| file | what |
|---|---|
| `docs/IL-AMBIGUITY.md` | the I/L problem and how it is handled (D-064, D-065) |
| `docs/PIPELINE-COMPARISON.md` | this pipeline vs the `elizabev/TARSUS` reference — every difference, verified |
| `docs/QUESTIONS-FOR-SCIENTISTS.md` | open questions blocking interpretation |
| `.memory/decisions.md` | every decision (D-001…D-065) with evidence |
| `.memory/lessons.md` | failure modes worth not repeating |

## Architecture

All steps run on LSF. A single master job orchestrates heavy tools (ThermoRawFileParser, FragPipe, PepQuery) via child bsub jobs and runs Python analysis (mutagenesis, filtering, localization) inline on the compute node. The login node is only used for the initial submission.

**Spectrum-title contract.** Step 2 indexes the **original** mzML (Step 1 output), so PepQuery/PDV
title every spectrum `file:scan:charge` with no `_sub` suffix. Steps 4 and 7 both strip the `_sub`
that FragPipe writes into its `Spectrum` column. Breaking this contract silently zeroes Step 7 —
see D-047 in `.memory/decisions.md` before changing what Step 2 indexes.

> **Status: runs end-to-end.** On the 2-file Orbitrap Astral DDA trial dataset the full 11-step
> pipeline completes with `DONE: Pipeline complete.`, producing 2,888 candidate SAAVs and 293
> localized substitutions.
>
> **Not yet proven equivalent to the reference implementation.** The reference has only ever been
> run on a *different* sample (`EVpar`), whose original `.mzML`/`.raw` inputs no longer exist on
> disk — so no back-to-back comparison on identical input has been made. What matches is the output
> *schema* (69 columns, identical semantics) and the order of magnitude (ours 2,888 → 293; reference
> 3,922 → 697). One deliberate deviation changes results: see D-048, defect 4.

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
uv run pytest -m "not lsf"                         # 203 tests, ~60s — the normal dev loop
uv run pytest                                      # 206 tests; the 3 extra are @pytest.mark.lsf
                                                   # real-tool tests (FragPipe/PepQuery) that take
                                                   # many minutes and need cluster + `make setup`
uv run mypy src/tarsus                              # type checking
make test-tools                                    # tool integrity (8 tools including IonQuant)
make test-pdv-full                                 # PDV + Xvfb integration
```

## Project Structure

```
src/tarsus/     Python package (steps, CLI, env, LSF helpers)
tests/          pytest tests (206; 3 marked `lsf` need the cluster)
tools/          External tools (downloaded via make setup)
data/           Test datasets (gitignored)
.context/       Architecture and reference docs
.memory/        Project memory, decisions, progress
.agents/        Agent operating instructions
TARSUS_elizabev/ READ-ONLY reference implementation
```

## Container (Apptainer/Singularity)

TARSUS ships as a self-contained Apptainer image bundling all tools + runtimes +
code. **Build only on `docker-gpu.wexac.weizmann.ac.il`** (the sole host with
`--fakeroot` privileges); every other WEXAC node can run the `.sif`.

Build (internal - bakes the already-validated `tools/` tree):

```bash
ssh docker-gpu.wexac.weizmann.ac.il
cd /path/to/TARSUS_BC
ml Singularity
scripts/build_container.sh --internal --out tarsus.sif
```

Build (public/portable - you supply MSFragger + IonQuant under the nesvilab
academic license; the rest download automatically):

```bash
scripts/build_container.sh --public \
  --msfragger MSFragger-4.4.1.zip --ionquant IonQuant-1.11.20.jar --out tarsus.sif
```

Distribute: copy `tarsus.sif` to a shared `/home/labs/...` path (run it in place),
or `scp tarsus.sif login1:~/`, or push to the internal `ops:5000` registry.

Run on LSF today (CPU; bind the shared tree that holds inputs/outputs/references):

```bash
bsub -q gsla-cpu -R "rusage[mem=32GB]" -oo %J.out -eo %J.err \
  'ml Singularity; singularity exec --bind /home/labs/pilpel:/home/labs/pilpel \
     /home/labs/pilpel/<shared>/tarsus.sif tarsus run -i <raw> --fasta <fasta> -o <outdir>'
```

**Known limitation (deferred):** the master submits child `bsub` jobs whose tool
paths exist only inside the image, so those child jobs must also run via
`ml Singularity; singularity exec ... tarsus.sif`. Wiring that (or a no-LSF local
backend) is a separate spec; this image is validated as a reproducible environment
(tools resolve; `pytest tests/unit tests/eval` green inside it).
