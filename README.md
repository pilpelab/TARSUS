# TARSUS

**TArgeted SUbstitution Search** — proteomics pipeline for detecting validated single amino acid substitutions (SAAVs) from mass spectrometry data.

Configurable, shareable implementation based on: Tretyachenko et al. (2026). Encoded and non-genetic protein variants expand the human functional proteome. *Nature*. https://doi.org/10.1038/s41586-026-11124-z (preprint: https://www.biorxiv.org/content/10.1101/2025.02.17.638604). Paper digest and its differences from this implementation: `.context/paper-*.md`.

Reference implementation: `TARSUS_elizabev/` (read-only symlink to the original pipeline — see `.context/reference-pipeline.md`)

**Status: code-replication goal closed.** Our pipeline reproduces the reference on both organisms:
- **Human (10-sample panel):** 100% substitution identity on shared spectra, dpbp r=0.96–1.000
- **E. coli (EVpar):** output identical — `in REF not ours: 0`, `in OURS not ref: 0`
- Remaining differences are tool-version effects (FragPipe MSBooster ML features), not code logic

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
- `--localize-tol` - Step 11 PyAscore fragment tolerance in Da. Default 0.01 (the paper's Orbitrap value, D-073); use 0.6 for ion-trap MS2.
- `--base-rescore-tol` - Step 9 PepQuery base-rescoring fragment tolerance (`-itol`) in Da. Default 0.05, the value Slava's production runs used: it reproduces his base scores exactly (D-076). The published `query_psm_base.sh` says 0.01.
- `--msbooster-models` - `best` (default; MSBooster picks Koina models, compute nodes need internet) or `dia-nn` (local models, offline). Step 3c reuses pass 1's choice (D-075).
- `--allow-dirty` — run despite uncommitted changes (results become unattributable; see
  *Provenance* below).

Every LSF job is submitted with `bsub -Q 255`: a job that dies at launch with exit 255 (seen on 2-6% of WEXAC jobs in Nov 2026) is requeued by LSF, at most 5 times, instead of failing the run (D-077).

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

**Who can read a run (D-074).** `tarsus run` and the master job set umask `027`, so everything a run writes is readable by your Unix group and closed to everyone else (directories `drwxr-x---`, files `-rw-r-----`), whatever your login umask. LSF jobs inherit it. Runs made before D-074 may be owner-only; open one to the group with `chmod -R g+rX output/<run>`. Check with `stat -c '%A %n' output/<run> output/<run>/11_localized/*`.

## Docs

| file | what |
|---|---|
| `docs/IL-AMBIGUITY.md` | the I/L problem and how it is handled (D-064, D-065) |
| `docs/PIPELINE-COMPARISON.md` | this pipeline vs the `elizabev/TARSUS` reference — every difference, verified |
| `docs/QUESTIONS-FOR-SCIENTISTS.md` | open questions blocking interpretation |
| `.context/paper-digest.md` | the Nature 2026 paper: claims, definitions, artifact classes, caveats, claims removed in review |
| `.context/paper-methods-vs-tarsus.md` | paper vs public code vs reference vs this pipeline, setting by setting |
| `.context/paper-supplementary-tables.md` | the 18 supplementary tables: contents, gotchas; fetch with `uv run python scripts/fetch_paper_supplements.py` |
| `.memory/decisions.md` | every decision (D-001…D-065) with evidence |
| `.memory/lessons.md` | failure modes worth not repeating |

## Architecture

All steps run on LSF. A single master job orchestrates heavy tools (ThermoRawFileParser, FragPipe, PepQuery) via child bsub jobs and runs Python analysis (mutagenesis, filtering, localization) inline on the compute node. The login node is only used for the initial submission.

**Spectrum-title contract.** Step 2 indexes the **original** mzML (Step 1 output), so PepQuery/PDV
title every spectrum `file:scan:charge` with no `_sub` suffix. Steps 4 and 7 both strip the `_sub`
that FragPipe writes into its `Spectrum` column. Breaking this contract silently zeroes Step 7 —
see D-047 in `.memory/decisions.md` before changing what Step 2 indexes.

> **Status: runs end-to-end, validated against reference.** The pipeline completes all 11 steps
> and has been verified against the reference implementation on two organisms:
> - **Human (GAPDH):** 100% substitution identity on shared spectra, 73/72 columns matched
> - **E. coli (EVpar):** 3,922 rows exactly reproduced (`in REF not ours: 0`, vice versa)
>
> See `docs/PIPELINE-COMPARISON.md` for the full diff and `docs/qc-history/` for QC reports.

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
uv run pytest tests/unit tests/eval    # 345 tests, ~10s — normal dev loop (no cluster needed)
uv run pytest                          # +3 @pytest.mark.lsf (real-tool tests, cluster + make setup)
uv run ruff check src/tarsus/          # lint
uv run mypy src/tarsus/                # type checking
make test-tools                        # tool integrity (8 tools including IonQuant)
make test-pdv-full                     # PDV + Xvfb integration
```

## Project Structure

```
src/tarsus/     Python package (steps, CLI, env, LSF helpers)
tests/          pytest tests (345: 317 unit + 25 eval + 3 lsf)
tools/          External tools (downloaded via make setup)
data/           Test datasets (gitignored)
docs/           Documentation (pipeline comparison, schema, specs)
container/      Apptainer recipe
scripts/        Utility scripts (build container, build test fixtures)
.context/       Architecture and reference docs
.memory/        Project memory, decisions, progress
.agents/        Agent operating instructions
TARSUS_elizabev/ READ-ONLY reference implementation (symlink)
```

## Container (Apptainer/Singularity)

TARSUS ships as a self-contained Apptainer image bundling all tools + runtimes +
code. Builds with `apptainer build --fakeroot` (tested on WEXAC login nodes with
apptainer 1.4.0 root-mapped namespace; docker-gpu NOT required).

Build (internal - bakes the already-validated `tools/` tree):

```bash
cd /path/to/TARSUS
ml apptainer
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
