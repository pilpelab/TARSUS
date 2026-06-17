# TARSUS Pipeline — Reference Implementation

**Source of truth:** `TARSUS_elizabev/` (read-only reference from colleagues' directory)

**Paper:** Tretyachenko, V., Leiman, T., Dahan, O., Asraf, O., Dahary, D., & Pilpel, Y. T. (2025). Encoded and non-genetic alternative protein variants expand human functional proteome. bioRxiv, 2025-02.

**Purpose:** Process raw mass spectrometry data to detect validated single amino acid substitutions (SAAVs) by comparing experimental spectra against a reference proteome database using a substitution-targeted search strategy.

---

## Pipeline Overview

The pipeline uses a **two-pass FragPipe search**: first against the reference database, then against an in-silico mutagenized library of all detected reference peptides. Detected substitutions are validated by PepQuery and localized by pyAscore.

---

## Test Data

Test input files are placed in `data/` (gitignored — see `data/README.md`):

| File | Size | Description |
|------|------|-------------|
| `protein.fasta` | 1.9 MB | E. coli K12 reference proteome (4,403 UniProt entries) |
| `HouYM-25-G140-AstralDDA-AlaGGC-LS-1.raw` | 11 GB | Low Solubility fraction |
| `HouYM-25-G140-AstralDDA-AlaGGC-HS-1.raw` | 7.3 GB | High Solubility fraction |

Both raw files are from the **same biological sample** (E. coli K12 lysate), acquired on an **Orbitrap Astral** in **DDA** mode. The LS/HS designation reflects fractionation by detergent-based phase separation chromatography: the low-solubility fraction elutes slowly, the high-solubility fraction elutes rapidly. The pipeline processes them together as a multi-file batch.

These files are for **development and testing only**. Production runs use user-supplied references and data.

---

## Step 1: Convert RAW to mzML

**Script:** `convert_raw.sh`

**Purpose:** Convert vendor-format .raw mass spectrometry files to the open .mzML format.

**Input:** Directory containing .raw files

**Output:** Directory `mzml/` with converted .mzML files

**Tool invoked:**
```
mono /home/labs/pilpel/slavat/Thermo/ThermoRawFileParser.exe -i <file.raw> -o <mzml_dir>
```

**Key details:**
- Uses ThermoRawFileParser (requires Mono/.NET runtime)
- Submits one `bsub` job per raw file to LSF
- Queue: `gsla-cpu`, memory: 7000MB

**Pain points:**
- Hardcoded path to ThermoRawFileParser.exe
- Requires Mono runtime on cluster node
- No error checking on conversion

---

## Step 2: Create PepQuery Index

**Script:** `make_index.sh`

**Purpose:** Build spectral index from mzML files for PepQuery validation.

**Input:** Directory of .mzML files

**Output:** `pepquery_index/` directory

**Tool invoked:**
```
java -Xmx120G -Xms60G -jar /home/labs/pilpel/elizabev/pepquery-2.0.2/pepquery-2.0.2.jar index -r -i <mzml_dir> -o <output>
```

**Key details:**
- Single bsub job: memory 12GB, queue gsla-cpu
- Java heap: 120GB max / 60GB initial

**Pain points:**
- Hardcoded path to pepquery-2.0.2.jar
- Very high memory (120GB)
- Single job, no parallelism

---

## Step 3: FragPipe Two-Pass Search

**Scripts:** `search_pipeline.sh` (wrapper), `search_pipeline_script.sh` (logic), `make_peptides.py` (mutagenesis)

### 3a — First Pass: Reference Database Search

**Purpose:** Search spectra against reference database + decoys. Identified spectra are subtracted to leave unassigned spectra.

**Inputs:** FASTA database, .mzML files, `generic.workflow`

**Outputs:** `first.manifest`, `first.workflow`, standard FragPipe outputs (psm.tsv, peptide.tsv, protein.tsv), sub-mzML files

**Commands:** philosopher workspace/database, sed patch workflow, fragpipe --headless

### 3b — In-Silico Mutagenesis

**Script:** `make_peptides.py`

**Input:** `peptide.tsv` from first pass

**Output:** `pep_candidates.fa`

**Logic:**
1. Read peptide.tsv, filter Intensity > 0
2. For each unique peptide, generate all single-AA substitutions
3. Use subs_exclude.csv to control allowed substitutions
4. Skip variants already in reference set
5. Write: >REF_originPosDest\nVARIANT_SEQUENCE

### 3c — Second Pass: Targeted Variant Search

**Purpose:** Search unassigned spectra against mutagenized library (nocleavage mode).

**Inputs:** pep_candidates.fa, sub-mzML files, fragpipe-second-pass.workflow

**Outputs:** second/psm.tsv

**Workflow modifications:** nocleavage, clip_nTerm_M=false, minisotopes=1, minscans=1

**Pain points:**
- Hardcoded paths to FragPipe/Philosopher
- Database path patching via sed
- fragpipe-second-pass.workflow auto-generated, not version-controlled
- LSF bsub with hardcoded queue/memory

---

## Step 4: Extract PSM Data for PepQuery

**Script:** `extract_psm.py`

**Input:** `second/psm.tsv`

**Output:** `psm_input4pepquery.tsv` (peptide	spectrum_title)

**Logic:** For each row with Intensity > 0, construct spectrum_title as filename:scan:charge, removing _sub suffix.

**Pain points:** No input validation.

---

## Step 5: PepQuery PSM Validation

**Script:** `query_psm.sh`

**Purpose:** Validate each second-pass PSM via PepQuery against reference database.

**Inputs:** psm_input4pepquery.tsv, PepQuery index, reference FASTA

**Outputs:** Per-chunk psm_rank.txt, ptm_detail.txt, psm_rank.mgf in pepquery_result/

**Process:** Split input into 10-PSM chunks, submit one bsub job per chunk. PepQuery flags: -hc -aa -ti 0,1,2,3 -tol 20 -itol 0.05

**Pain points:** LSF cluster required (thousands of jobs), hardcoded PepQuery path, manual verification needed.

---

## Step 6: Aggregate PepQuery Outputs + PDV

**Script:** `aggregate_query.sh`

**Outputs:** psmrankall.txt, ptmall.txt, mgfall.mgf, pdv_spectra/ (PDF reports)

**Commands:** Concatenate psm_rank.txt/ptm_detail.txt (skip headers), cat MGF files, run PDV 2.1.2 jar for fragment ion visualization.

**Pain points:** Hardcoded PDV path, PDF output is slow.

---

## Step 7: Analyze Outputs

**Script:** `analyze_outputs.py`

**Output:** `subs.ipc` (Arrow IPC format)

**Filters (function mistranslations):**
1. Parse PTM details, extract origin/destination/position via regex
2. Keep only SAV-only PSMs (no PTM overlaps)
3. Resolve ambiguous matches: unique top score, one SAV per PSM
4. Fragment coverage filter: >=2 b/y ions covering substitution site
5. Connect reference-variant pairs, filter N-terminal subs
6. Calculate log10 abundance ratio (dpbp)

**Additional filters:** PepQuery confident=Yes, max intensity per (peptide, charge), equal charges for ref/variant pairs.

**Dependencies:** polars, pandas, numpy, seaborn, matplotlib

---

## Step 8: Prepare Reference Rescoring

**Script:** `ref_validation_prep.py`

**Purpose:** Create fake MGF with reference peptide precursor masses so PepQuery checks if spectrum matches reference.

**Inputs:** subs.ipc, mgfall.mgf

**Outputs:** mgfall_fakes.mgf, pepquery_input_base/ (1-PSM per file)

**Logic:** Compute theoretical m/z for reference peptide across all Ox/CAM mod states. Replace PEPMASS in MGF. Append mod state suffix to title.

**Pain points:** Exponential explosion (2^(nM+nC) per spectrum). No actual measured mass considered.

---

## Step 9: PepQuery Reference Rescoring

**Script:** `query_psm_base.sh`

**Purpose:** Score variant spectra against reference peptides via PepQuery.

**Key flags:** -fast, -fixMod 0, -varMod 1,2, -maxVar 4, -s 2, -indexType 2

**Outputs:** pepquery_result_recheck_base/ (per-chunk results)

**Pain points:** Same LSF dependency, hardcoded paths.

---

## Step 10: Aggregate Rescoring

**Script:** `aggregate_query_base.sh`

**Outputs:** psmrankall_base.txt, ptmall_base.txt, mgfall_base.mgf

---

## Step 11: Localize Substitutions

**Script:** `localize.py`

**Outputs:** subs_localized.ipc, subs_localized.csv

**Logic:**
1. Delta score filter: variant PepQuery score > reference score
2. Mass shift calculation from substitution_shifts dict
3. pyAscore localization: verify mass shift at expected position
4. Keep only where best localization matches expected position and beats second-best

**Dependencies:** polars, numpy, pyteomics, pyascore

**Pain points:** pyascore availability, pyteomics MGF parsing speed, computationally intensive.

---

## Configuration: subs_exclude.csv

20x20 boolean matrix (rows=origin, cols=destination). TRUE = exclude substitution.

**Excluded (TRUE):** Y>F, Q>D, Q>E, I>A, M>Y, T>R, N>D, D>M, D>R, D>E, E>N, E>Q, E>D, E>K, E>R, E>T

I/L column renamed to I in script (leucine and isoleucine treated identically).

---

## Tool Inventory

| Tool | Version | Reference Path | Type |
|------|---------|----------------|------|
| FragPipe | 23.1 | /home/labs/pilpel/slavat/fragpipe-23.1/ | Java |
| MSFragger | 4.3 | (bundled with FragPipe) | Java |
| Philosopher | 5.1.2 | (bundled with FragPipe) | Linux binary |
| IonQuant | 1.11.11 | (bundled with FragPipe) | Java |
| MSBooster | 1.3.17 | (bundled with FragPipe) | Java |
| Percolator | 3.7.1 | (bundled with FragPipe) | Linux binary |
| PepQuery | 2.0.2 | /home/labs/pilpel/elizabev/pepquery-2.0.2/ | Java |
| PDV | 2.1.2 | /home/labs/pilpel/elizabev/PDV-2.1.2/ | Java |
| ThermoRawFileParser | (?) | /home/labs/pilpel/slavat/Thermo/ | .NET/Mono |
| Python | 3.11.5 | system | Interpreter |
| Java | 21.0.7 | system | JRE |

---

## Known Gaps

1. fragpipe-second-pass.workflow and fragpipe-files-second-pass.fp-manifest auto-generated by FragPipe, not in version control.
2. generic.workflow is the template; diff to second-pass needs documentation.
3. PepQuery tolerance/charge parameters may need tuning per instrument.
