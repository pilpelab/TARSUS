# hoMS_24814 -- TARSUS_BC Second Validation Results

**Run completed:** 2026-07-14
**Pipeline:** TARSUS_BC (commit `17a224a`, D-064 I/L fix, D-063 provenance, D-061 matrix fix)
**Sample:** EX1_24814 -- 15 fractions (human, GRCh38)
**FASTA:** 81 MB, 123,495 sequences (GRCh38 with immune genes)

---

## Pipeline Funnel

| Stage | Artifact | Count |
|---|---|---|
| Step 6 | `psmrankall.txt` | 5,082 rows |
| Step 7 | `subs.ipc` (SAAV candidates) | **191 rows** x 67 columns |
| Step 11 | `subs_localized.ipc` (localized) | **44 rows** x 67 columns |
| Step 12 | Visualizations | 5 plots (see below) |

## Top 10 Localized Substitutions

| Rank | Substitution | Count |
|---|---|---|
| 1 | G -> D | 5 |
| 2 | M -> I/L | 4 |
| 3 | V -> H | 4 |
| 4 | C -> S | 4 |
| 5 | M -> F | 3 |
| 6 | C -> Y | 2 |
| 7 | M -> A | 2 |
| 8 | S -> N | 2 |
| 9 | H -> D | 2 |
| 10 | V -> M | 1 |

## Visualizations

Plots in `12_visualize/`:

| File | Description |
|---|---|
| `substitution_heatmap.png` | Full origin x destination matrix |
| `top_substitutions.png` | Bar plot of top substitution types |
| `origin_frequencies.png` | Which residues are being substituted |
| `protein_burden.png` | SAAVs per protein |
| `dpbp_distribution.png` | Localization score distribution |

---

## Comparison to Original Pipeline (soft reference)

Original pipeline output: `/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/`

| Metric | TARSUS_BC (this run) | Original pipeline | Ratio |
|---|---|---|---|
| `psmrankall.txt` rows | 5,082 | 7,395 | 0.69x |
| `subs.ipc` SAAV candidates | 191 | 259 | 0.74x |
| `subs_localized.ipc` | 44 | (not in reference) | -- |

Same order of magnitude on both key metrics (~70% yield relative to the original).
The original pipeline's `subs.ipc` has 72 columns vs our 67 (extra `_right` suffix columns from a different join strategy).

> **Note:** These are NOT regression targets. The original pipeline used different FragPipe/MSFragger versions and different join/filter logic. This comparison is a soft sanity check only.

---

## Run Parameters

- **Raw files:** 15 fractions (EX1_24814_Fraction-1 through -15)
- **FASTA:** `/home/labs/pilpel/slavat/tehilapaper/fasta/protein.fasta`
- **Master memory:** 64 GB
- **PepQuery memory:** ~5.5 GB (auto-derived from FASTA size)
- **Queue:** gsla-cpu
- **Orchestration:** Single LSF master job with child bsub jobs per step
