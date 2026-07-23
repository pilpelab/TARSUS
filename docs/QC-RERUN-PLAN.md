# Full QC and Rerun Plan for TARSUS_BC vs Slava Reference

**Date:** 2026-07-23
**Scope:** output schema comparison, pipeline health QC, scientific QC, and command lines to rerun available datasets.

---

## 1. QC Goals

### A. Schema QC

For every completed run, verify:

1. `07_analyze/subs.ipc` exists.
2. `11_localized/subs_localized.ipc` exists.
3. Column count is expected.
   - Target for Slava compatibility: 69 columns.
   - Current production outputs may be 67 until `SpectralSim` and `RTScore` are recovered.
4. Column order matches Slava's `subs.ipc` where possible.
5. Renamed columns are tracked explicitly:
   - `second Intensity` vs `second_intensity`
   - `first Intensity` vs `first_intensity`
   - `_right` vs `_first`
   - `mistranslatedPos` vs `mistranslated_pos`
6. `SpectralSim` and `RTScore` status is recorded as one of:
   - present and numeric
   - present but all null
   - absent from `subs.ipc`
   - absent already from `03c_second_pass/second/psm.tsv`

### B. Stage Count QC

For every run, count rows at key stages:

| Stage | File | Metric |
|---|---|---|
| Step 3a | `03a_first_pass/psm.tsv` | first-pass PSM count |
| Step 3b | `03b_candidates/pep_candidates.fa` | candidate count |
| Step 3c | `03c_second_pass/second/psm.tsv` | second-pass PSM count |
| Step 4 | `04_psm_input/*.tsv` | PepQuery input rows |
| Step 6 | `06_aggregated/psmrankall.txt` | PepQuery aggregated rows |
| Step 7 | `07_analyze/subs.ipc` | substitution candidates |
| Step 11 | `11_localized/subs_localized.ipc` | localized calls |
| Step 12 | `12_visualize/*.png`, `sixty_twenty.csv` | visualization complete |

### C. Biological QC

For each final `subs_localized.ipc`:

1. Count origin to destination substitutions.
2. Check I/L rule:
   - origin must be definite `I` or `L`, never `I/L`.
   - destination may be `I/L`.
3. Check forbidden artifacts:
   - `F->M` should be absent.
   - `A->I/L` should be absent if trimethylation exclusion is active.
4. Check codon heatmap output when `--cds` is supplied.
5. Check protein burden plot and top proteins.
6. Check dpbp distribution for extreme values and nulls.
7. Check duplicated spectrum calls.

### D. Slava Head-to-Head QC

Where Slava reference output exists for the same raw data:

1. Normalize spectrum IDs.
2. Compare shared spectra.
3. For shared spectra, compare:
   - origin
   - destination
   - mistranslated position
   - protein ID
4. Report:
   - shared count
   - Slava-only count
   - ours-only count
   - substitution agreement rate
   - position agreement rate

Known reference file:

```bash
/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc
/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs_localized.ipc
```

---

## 2. Preflight Commands

Run from project root:

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate
make test-tools
pytest tests/unit tests/validation
```

Check working tree before launching large reruns:

```bash
git status --short
```

If the tree is dirty, either commit/stash changes or intentionally pass `--allow-dirty` and record why.

---

## 3. Available Dataset Inventory

### Local small project datasets

| Run name | FASTA | RAW files | CDS |
|---|---|---|---|
| `qc_alaggc` | `data/protein.fasta` | AlaGGC HS-1, LS-1 | `data/ecoli_cds.fasta` |
| `qc_alaggcpar` | `data/protein.fasta` | AlaGGCpar LS-1, AlaGCCpar HS-1 | `data/ecoli_cds.fasta` |

### Slava coli tRNA datasets found at maxdepth 1

Root: `/home/labs/pilpel/slavat/coli_trna/`

Found 9 directories with 6 raw files each:

- `GluUUC`
- `GluUUCpar`
- `IleXCAU`
- `IleXCAUpar`
- `LeuUAG`
- `ProCGG`
- `ProCGGpar`
- `ProGGG`
- `ProGGGpar`

Expected names not found as immediate raw directories in this filesystem scan:

- `AlaUGC`
- `AlaUGCpar`
- `ProUGG`
- `ProUGGpar`
- `EV`
- `EVpar`
- `AlaGGC` full 6-raw set
- `AlaGGCpar` full 6-raw set
- `LeuUAGpar`

### hoMS dataset from existing provenance

Run names already used:

- `hoMS_24814`
- `hoMS_24814_gapdh`

Raw root:

```bash
/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/raw/
```

FASTA:

```bash
/home/labs/pilpel/slavat/tehilapaper/fasta/protein.fasta
```

CDS for human visualization:

```bash
/home/labs/pilpel/barc/TARSUS_BC/data/human_cds.fasta
```

---

## 4. Rerun Commands

All commands write into a new namespace so old outputs are preserved:

```bash
/home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/<run_name>
```

### 4a. Local project test runs

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

# AlaGGC test pair
tarsus run \
  --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta \
  --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/HouYM-25-G140-AstralDDA-AlaGGC-HS-1.raw \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/HouYM-25-G140-AstralDDA-AlaGGC-LS-1.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/alaggc

# AlaGGCpar control pair
tarsus run \
  --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta \
  --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/control/HouYM-25-G140-AstralDDA-AlaGGCpar-LS-1.raw \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/control/HouYM-25-G140-AstralDDA-AlaGCCpar-HS-1.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/alaggcpar
```

### 4b. Slava coli tRNA panel, available raw directories

Use one command per dataset. These use the E. coli FASTA and CDS bundled in this project.

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

for sample in GluUUC GluUUCpar IleXCAU IleXCAUpar LeuUAG ProCGG ProCGGpar ProGGG ProGGGpar; do
  raw_dir="/home/labs/pilpel/slavat/coli_trna/${sample}"
  out_dir="/home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/${sample,,}"

  tarsus run \
    --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta \
    --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
    $(find "$raw_dir" -maxdepth 1 -type f -iname '*.raw' | sort | sed 's#^#-i #') \
    -o "$out_dir"
done
```

Expanded non-loop version if you want copy-paste per run:

```bash
# GluUUC
tarsus run --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-HS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-HS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-HS-3.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-LS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-LS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUC/HouYM-25-G140-AstralDDA-GluUUC-LS-3.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/gluuuc

# GluUUCpar
tarsus run --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-HS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-HS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-HS-3.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-LS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-LS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/GluUUCpar/HouYM-25-G140-AstralDDA-GluUUCpar-LS-3.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/gluuucpar

# IleXCAU
tarsus run --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-HS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-HS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-HS-3.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-LS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-LS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAU/HouYM-25-G140-AstralDDA-IleXCAU-LS-3.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/ilexcau

# IleXCAUpar
tarsus run --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-HS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-HS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-HS-3.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-LS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-LS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/IleXCAUpar/HouYM-25-G140-AstralDDA-IleXCAUpar-LS-3.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/ilexcaupar

# LeuUAG
tarsus run --fasta /home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta --cds /home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-HS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-HS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-HS-3.raw \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-LS-1.raw \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-LS-2.raw \
  -i /home/labs/pilpel/slavat/coli_trna/LeuUAG/HouYM-25-G140-AstralDDA-LeuUAG-LS-3.raw \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/leuuag
```

For the Pro datasets, use the loop form above to avoid mistakes. The loop is safer than manual copy-paste.

### 4c. hoMS reruns

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

# hoMS full proteome rerun
tarsus run \
  --fasta /home/labs/pilpel/slavat/tehilapaper/fasta/protein.fasta \
  --cds /home/labs/pilpel/barc/TARSUS_BC/data/human_cds.fasta \
  $(for i in $(seq 1 15); do echo -i /home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/raw/EX1_24814_Fraction-${i}_03092025.raw; done) \
  -o /home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723/homs_24814
```

Note: `hoMS_24814_gapdh` in prior output used the same FASTA in provenance. If a true GAPDH-restricted rerun is desired, first identify or create the GAPDH-only FASTA and use that path instead.

---

## 5. Post-Run QC Commands

### 5a. Quick schema and count report

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

python3 - <<'PY'
from pathlib import Path
import polars as pl

root = Path('/home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723')
slava = Path('/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc')
slava_cols = pl.read_ipc(slava).columns if slava.exists() else []

print('run\tsubs_rows\tsubs_cols\tlocalized_rows\tlocalized_cols\tSpectralSim\tRTScore\tpsm_has_scores')
for run in sorted([p for p in root.iterdir() if p.is_dir()]):
    subs = run / '07_analyze' / 'subs.ipc'
    loc = run / '11_localized' / 'subs_localized.ipc'
    psm = run / '03c_second_pass' / 'second' / 'psm.tsv'

    subs_rows = subs_cols = loc_rows = loc_cols = 'NA'
    spectral = rtscore = 'NA'
    psm_has_scores = 'NA'

    if subs.exists():
        df = pl.read_ipc(subs)
        subs_rows = len(df)
        subs_cols = len(df.columns)
        spectral = 'present' if 'SpectralSim' in df.columns else 'absent'
        rtscore = 'present' if 'RTScore' in df.columns else 'absent'
        if 'SpectralSim' in df.columns:
            spectral += f':nulls={df["SpectralSim"].null_count()}'
        if 'RTScore' in df.columns:
            rtscore += f':nulls={df["RTScore"].null_count()}'
    if loc.exists():
        lf = pl.read_ipc(loc)
        loc_rows = len(lf)
        loc_cols = len(lf.columns)
    if psm.exists():
        cols = pl.read_csv(psm, separator='\t', n_rows=1).columns
        psm_has_scores = str(('SpectralSim' in cols) and ('RTScore' in cols))

    print(f'{run.name}\t{subs_rows}\t{subs_cols}\t{loc_rows}\t{loc_cols}\t{spectral}\t{rtscore}\t{psm_has_scores}')
PY
```

### 5b. Biological QC report

```bash
cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

python3 - <<'PY'
from pathlib import Path
import polars as pl

root = Path('/home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723')
for run in sorted([p for p in root.iterdir() if p.is_dir()]):
    loc = run / '11_localized' / 'subs_localized.ipc'
    if not loc.exists():
        print(f'\n## {run.name}: missing localized output')
        continue
    df = pl.read_ipc(loc)
    print(f'\n## {run.name}: {len(df)} localized rows')
    if len(df) == 0:
        continue

    origin_col = 'origin' if 'origin' in df.columns else 'origin_aa'
    dest_col = 'destination' if 'destination' in df.columns else 'destination_aa'

    bad_il_origin = df.filter(pl.col(origin_col) == 'I/L') if origin_col in df.columns else None
    print('bad I/L origin rows:', len(bad_il_origin) if bad_il_origin is not None else 'NA')

    if origin_col in df.columns and dest_col in df.columns:
        forbidden_fm = df.filter((pl.col(origin_col) == 'F') & (pl.col(dest_col) == 'M'))
        forbidden_ai = df.filter((pl.col(origin_col) == 'A') & (pl.col(dest_col).is_in(['I', 'L', 'I/L'])))
        print('F->M rows:', len(forbidden_fm))
        print('A->I/L rows:', len(forbidden_ai))
        print('top substitutions:')
        print(df.group_by([origin_col, dest_col]).len().sort('len', descending=True).head(15))

    if 'Protein' in df.columns:
        print('top proteins:')
        print(df.group_by('Protein').len().sort('len', descending=True).head(10))
PY
```

---

## 6. Acceptance Criteria

A run passes QC if:

1. All expected step directories exist through `11_localized`.
2. `subs.ipc` is non-empty unless the biological sample is expected negative.
3. `subs_localized.ipc` exists and has sane row count.
4. Column status is explicitly one of:
   - Slava-compatible 69 columns with numeric `SpectralSim` and `RTScore`
   - 69 columns with placeholder nulls, marked not scientifically equivalent
   - 67 columns, documented as FP24.0 score-column gap
5. No `I/L` origin values.
6. No forbidden `F->M` or `A->I/L` calls.
7. Step 12 plots exist when `--cds` was supplied.
8. Shared-spectrum comparisons with Slava show no origin-destination disagreement.

---

## 7. Open Blockers

1. `SpectralSim` and `RTScore` are not in our FragPipe 24.0 `psm.tsv` files.
2. Need to identify whether FP24.0 stores equivalent MSBooster fields elsewhere.
3. Several expected coli tRNA raw directories are not present at the scanned location.
4. `hoMS_24814_gapdh` needs clarification: prior provenance used full human FASTA, not an obvious GAPDH-only FASTA.
