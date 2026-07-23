# What is Slava's Reference for TARSUS_BC?

**TL;DR:** Slava provided the **original TARSUS pipeline implementation** (13 scripts in Bash/Python) and **completed runs on experimental data** that we used to validate our rewrite.

---

## Part 1: Who is Slava?

**Full name:** Vyacheslav Tretyachenko  
**Email:** tretyacv@gmail.com  
**Role:** Original author of TARSUS  
**Paper:** Tretyachenko et al. (2025), bioRxiv — *"Encoded and non-genetic alternative protein variants expand human functional proteome"*

Slava ran the original TARSUS pipeline on E. coli tRNA overexpression data and discovered that the pipeline can detect amino acid substitutions caused by translational errors.

---

## Part 2: What Did Slava Provide?

### 2a — Reference Scripts (The Implementation)

**Location:** `/home/labs/pilpel/barc/TARSUS_BC/TARSUS_elizabev/` (symlink to his working directory)

**Contents:** 13 files (Bash scripts + Python scripts)

```
├── convert_raw.sh              # Step 1: .raw → .mzML
├── make_index.sh               # Step 2: PepQuery index
├── search_pipeline.sh          # Wrapper
├── search_pipeline_script.sh    # Step 3a + 3c: FragPipe searches
├── make_peptides.py            # Step 3b: in-silico mutagenesis
├── extract_psm.py              # Step 4: PSM extraction
├── query_psm.sh                # Step 5: PepQuery validation
├── aggregate_query.sh          # Step 6: aggregation
├── query_psm_base.sh           # Step 9: base rescoring
├── aggregate_query_base.sh     # Step 10: base aggregation
├── analyze_outputs.py          # Step 7: filtering → subs.ipc
├── ref_validation_prep.py      # Step 8: base prep
├── localize.py                 # Step 11: PyAscore localization
├── generic.workflow            # FragPipe workflow template
└── (+ log files, FragPipe configs)
```

**Characteristics:**
- Hand-run scripts (no orchestration)
- Bash wrappers calling tools directly
- Python analysis steps
- Hardcoded paths (cluster-specific)
- No unit tests, no CI
- No error checking in many places

### 2b — Reference Pipeline Runs (The Data)

**Location:** `/home/labs/pilpel/elizabev/tRNA/` (Elizabeth's completed run)

**Most important:** `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/`

```
├── 01_mzml/                    # Original .mzML files
├── 02_index/                   # PepQuery index (24,944 MGF files)
├── 03a_first_pass/             # First-pass FragPipe results
│   ├── psm.tsv
│   ├── peptide.tsv
│   ├── *_sub.mzML             # Unidentified spectra
│   └── second/ (second-pass results)
├── pep_candidates.fa           # In-silico mutagenized library
├── pepquery_result/            # PepQuery chunks (3,775 dirs)
├── psmrankall.txt              # Aggregated PSM file (15,232 rows)
├── 06_aggregated/
│   ├── pdv_spectra/            # PDV ion evidence
│   └── PDVExportResult.txt
├── subs.ipc                    # Step 7 output: 3,922 spectra
└── subs_localized.ipc          # Step 11 output: 697 localized SAAVs
```

**Key numbers:**
- Input: 2 .raw files (EVpar-HS-3, EVpar-LS-3)
- Database: E. coli K12 proteome (4,403 proteins, 5 MB FASTA)
- First-pass PSMs: 6,820
- Variants library: 251 MB FASTA (from first-pass peptides)
- Second-pass PSMs: 16,341
- Final SAAVs: 697 localized

### 2c — Experimental Data (The Biology)

**Location:** `/home/labs/pilpel/slavat/coli_trna/`

**9-tRNA overexpression panel:** (same experiment as TARSUS paper)

```
AlaGGC (+ control AlaGGCpar)     ← This is what we've been testing
AlaUGC (+ control AlaUGCpar)
GluUUC (+ control GluUUCpar)
IleXCAU (+ control IleXCAUpar)
LeuUAG (+ control LeuUAGpar)
ProCGG (+ control ProCGGpar)
ProGGG (+ control ProGGGpar)
ProUGG (+ control ProUGGpar)
EV (empty vector + control EVpar)
```

Each condition has multiple raw files (fractionated, typically 5-15 fractions each).

---

## Part 3: How We Use Slava's Reference

### In Development

1. **Comparing code logic** — We read his scripts to understand the pipeline
2. **Schema validation** — Our output `.ipc` files should match his 69-column format
3. **Debugging** — When our pipeline fails, we trace through his scripts to see where the difference is

### In Testing

1. **Golden-file validation** — We capture expected output properties from his runs
2. **Regression tests** — We make sure our changes don't silently break things his pipeline does correctly
3. **Head-to-head comparison** — On hoMS/GAPDH data, we compare row-by-row

### What We Found

**Bugs in his code (not execution, but code quality):**
- D-064: I/L matrix rename is a no-op (renames rows instead of columns)
- D-048: Camel-case typo (`mistranslatedPos` never gets set)
- D-048: PyAscore aux-mod array is empty (should mark the substitution site)
- D-045: Spectrum-title join allows unrelated spectra to borrow evidence

**Things we kept the same:**
- Overall pipeline architecture (11 steps)
- Output schema (69 columns)
- Scientific filtering logic (confident OR single-SAV)
- FragPipe workflow patches
- PDV ion evidence extraction

---

## Part 4: Where We Diverge (On Purpose)

### D-047: Index Namespace
- **His:** indexes original mzML (correct)
- **Ours (v1, broken):** indexed `_sub.mzML` (wrong namespace)
- **Ours (fixed):** back to original mzML (correct)

### D-064: I/L Matrix
- **His:** 0 I/L-origin substitutions (bug: no-op rename)
- **Ours:** 1,240,782 I/L-origin candidates (implemented the intent)

### Library Scope (hoMS/GAPDH)
- **His:** GAPDH-only (79 base peptides, ~23,280 candidates)
- **Ours:** Proteome-wide (4,667 base peptides, ~941,020 candidates)
- **Why:** His appears to be a focused run; ours is general-purpose

### Python vs Bash/Shell
- **His:** shell scripts + manual orchestration
- **Ours:** Python + LSF orchestration + resumable via `.done`

---

## Part 5: The Reference Runs We Can Use

### EVpar (the paper's main data)
- **Status:** Complete, validated
- **Scale:** 2 raw files, E. coli K12
- **Output:** 697 localized SAAVs
- **Where:** `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/`
- **Use case:** Ground truth for schema, column names, order of magnitude

### hoMS/GAPDH (the only head-to-head)
- **Status:** Both pipelines ran on identical data
- **Scale:** 15 .raw files (human GAPDH), 106 MB FASTA
- **Our output:** 44 localized SAAVs (Step 11)
- **His output:** (never localized, but Step 7: 259 spectra)
- **Agreement:** 115/115 shared spectra (100% agreement)
- **Where:** `/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/`
- **Use case:** Validation of correctness (100% call agreement on shared spectra)

### AlaGGC (our test case)
- **Status:** Our pipeline complete (Jan 2026)
- **Scale:** 2 raw files, E. coli K12
- **Output:** 293 localized SAAVs (after D-047/D-048/D-064)
- **His output:** (not run by Slava; our own replication)
- **Where:** `/home/labs/pilpel/barc/TARSUS_BC/output/trial/`
- **Use case:** Development/testing of our rewrite

---

## Part 6: How To Use the Reference in Practice

### If you want to understand a step:
```
# Read his code
cat /home/labs/pilpel/barc/TARSUS_BC/TARSUS_elizabev/analyze_outputs.py

# Compare to ours
diff -u TARSUS_elizabev/analyze_outputs.py src/tarsus/steps/step07_analyze_outputs.py

# Look up what changed in memory
grep -A 5 "D-047\|D-048\|D-064" .memory/decisions.md
```

### If you want to validate output:
```
# Compare hoMS/GAPDH head-to-head
python scripts/compare_pipelines.py \
  /home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/subs.ipc \
  output/hoMS_validation/subs.ipc

# Read the detailed comparison report
cat docs/PIPELINE-COMPARISON.md
```

### If you want to understand data flow:
```
# Trace one spectrum through EVpar (ground truth)
grep "file:121018:2" /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc

# Look at the original PSM for that spectrum
grep "121018:2" /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/psmrankall.txt

# See the PDV ion evidence
grep "EVpar.*121018" /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/pdv_spectra/PDVExportResult.txt

# Then trace the same spectrum through our pipeline on hoMS
grep "hoMS.*spectrum_title" output/hoMS_validation/subs.ipc
```

---

## Part 7: Slava's Original Paper

**Title:** "Encoded and non-genetic alternative protein variants expand human functional proteome"

**Authors:** Tretyachenko et al.

**Published:** bioRxiv, 2025-02-17

**DOI:** https://www.biorxiv.org/content/10.1101/2025.02.17.638604v1

**Key claims:**
- Demonstrates TARSUS can detect translational errors (SAAVs) from MS data
- Tested on E. coli tRNA overexpression panel
- Found 697 localized substitutions in EVpar condition
- Validates novel peptides against reference + ion evidence

**Datasets:** PRIDE PXD071134 (under reviewer embargo at submission, hence undocumented until paper acceptance)

---

## Part 8: What We're NOT Changing

- **His experimental design** — 9-tRNA panel, paired controls
- **His biology interpretations** — anticodon naming, mistranslation rates
- **His data** — all .raw files, all runs

We are **replicating the computational pipeline**, not the experiment. If the experiment produces SAAVs X and Y, our job is to find X and Y correctly. It's not our job to design new experiments.

---

## Part 9: When You Need the Reference

| Situation | Action |
|---|---|
| "Our subs.ipc has 69 columns; reference has 69 columns" | ✅ Schema is correct |
| "Our hoMS output differs from his on spectrum S" | ✅ Check `docs/PIPELINE-COMPARISON.md` for expected differences |
| "We got 2,888 SAAVs, reference got 3,922" | ✅ Normal (different samples, FragPipe version 24.0 vs 23.1) |
| "We get 0 spectra at Step 7" | ❌ Bug (reference gets thousands) — trace with reference code |
| "The code says `mistranslatedPos` but we fixed it to `mistranslated_pos`" | ✅ We fixed a reference bug (D-048) |
| "Can we remove the I/L handling?" | ❌ Reference's intent was to include I/L; we implemented it correctly (D-064) |

---

## Part 10: Reference Location Summary

```
Reference code:
  └─ /home/labs/pilpel/barc/TARSUS_BC/TARSUS_elizabev/
     (13 scripts: Bash + Python)

Reference EVpar run (ground truth):
  └─ /home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/
     (Complete run: 697 localized SAAVs)

Reference hoMS/GAPDH run (validation):
  └─ /home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/
     (Head-to-head comparison data)

Slava's raw experimental data:
  └─ /home/labs/pilpel/slavat/coli_trna/
     (9-tRNA panel, all 18 conditions with replicates)

Original paper:
  └─ Tretyachenko et al. (2025), bioRxiv
     https://www.biorxiv.org/content/10.1101/2025.02.17.638604v1
```
