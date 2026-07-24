# QC: hoMS finished runs vs Slava GAPDH reference

Slava GAPDH reference: `/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/GAPDH/2d/fragpipe_fullpipeline/subs.ipc`
Slava EVpar schema reference: `/home/labs/pilpel/elizabev/tRNA/EVpar/tarsus_analysis/subs.ipc`

## Executive summary

- Both completed hoMS reruns finished through Step 12 and produced `subs.ipc`, `subs_localized.ipc`, CSVs, and visualizations.
- Our Step 7 outputs have 69 columns. This matches Slava EVpar canonical schema, but Slava GAPDH `subs.ipc` has 72 columns in this particular reference file.
- Our `SpectralSim` and `RTScore` columns are present but all null. Slava GAPDH has numeric values for both. This confirms the remaining score-value gap is upstream FragPipe/MSBooster output, not missing Step 7 columns.
- On shared Step 7 spectra, origin/destination agreement is 100%. Position agreement is 98.5%.
- Localized calls are compared against Slava Step 7 because no Slava GAPDH localized file was found at the known path. After I/L normalization, localized substitution agreement is higher than the raw label agreement.

## Schema and score status

| run | stage | rows | cols | unique spectra | SpectralSim | RTScore |
|---|---|---:|---:|---:|---|---|
| homs_24814 | Step 7 subs | 191 | 69 | 167 | present, null 191/191 | present, null 191/191 |
| homs_24814 | Step 11 localized | 44 | 69 | 38 | present, null 44/44 | present, null 44/44 |
| homs_24814_gapdh | Step 7 subs | 191 | 69 | 167 | present, null 191/191 | present, null 191/191 |
| homs_24814_gapdh | Step 11 localized | 44 | 69 | 38 | present, null 44/44 | present, null 44/44 |
| Slava GAPDH | Step 7 subs | 259 | 72 | 233 | present, null 0/259 | present, null 0/259 |
| Slava EVpar | Step 7 subs | 3922 | 69 | 1474 | present, null 0/3922 | present, null 0/3922 |

## Slava GAPDH schema nuance

- GAPDH-only Slava file has 72 columns, while Slava EVpar has 69 columns.
- Columns in Slava GAPDH but not Slava EVpar: `['ions', 'ion_mz', 'ion_int']`
- Columns in Slava EVpar but not Slava GAPDH: `[]`

## Head-to-head agreement against Slava GAPDH Step 7

| our run/stage | our rows | Slava rows | shared rows | shared spectra | exact substitution agreement | I/L-normalized substitution agreement | position agreement |
|---|---:|---:|---:|---:|---:|---:|---:|
| homs_24814 Step 7 subs | 191 | 259 | 137 | 115 | 137/137 (100.0%) | 137/137 (100.0%) | 135/137 (98.5%) |
| homs_24814 Step 11 localized | 44 | 259 | 36 | 30 | 31/36 (86.1%) | 36/36 (100.0%) | 36/36 (100.0%) |
| homs_24814_gapdh Step 7 subs | 191 | 259 | 137 | 115 | 137/137 (100.0%) | 137/137 (100.0%) | 135/137 (98.5%) |
| homs_24814_gapdh Step 11 localized | 44 | 259 | 36 | 30 | 31/36 (86.1%) | 36/36 (100.0%) | 36/36 (100.0%) |

## Top substitutions

### Slava GAPDH Step 7

| origin | destination | count |
|---|---|---:|
| S | N | 11 |
| G | D | 9 |
| S | G | 9 |
| T | G | 9 |
| M | I | 8 |
| C | S | 8 |
| N | G | 6 |
| M | T | 6 |
| V | H | 6 |
| N | A | 6 |
| V | P | 6 |
| T | P | 6 |

### ours homs_24814 Step 7

| origin | destination | count |
|---|---|---:|
| I | H | 9 |
| C | S | 8 |
| V | M | 7 |
| G | D | 7 |
| M | I | 7 |
| S | N | 7 |
| M | A | 5 |
| A | T | 5 |
| H | D | 5 |
| V | H | 5 |
| S | G | 5 |
| M | F | 4 |

### ours homs_24814_gapdh Step 7

| origin | destination | count |
|---|---|---:|
| I | H | 9 |
| C | S | 8 |
| G | D | 7 |
| M | I | 7 |
| V | M | 7 |
| S | N | 7 |
| H | D | 5 |
| V | H | 5 |
| M | A | 5 |
| A | T | 5 |
| S | G | 5 |
| V | P | 4 |

### ours homs_24814 localized

| origin | destination | count |
|---|---|---:|
| G | D | 5 |
| M | I/L | 4 |
| C | S | 4 |
| V | H | 4 |
| M | F | 3 |
| M | A | 2 |
| H | D | 2 |
| S | N | 2 |
| C | Y | 2 |
| A | T | 1 |
| V | K | 1 |
| N | M | 1 |

### ours homs_24814_gapdh localized

| origin | destination | count |
|---|---|---:|
| G | D | 5 |
| C | S | 4 |
| M | I/L | 4 |
| V | H | 4 |
| M | F | 3 |
| C | Y | 2 |
| S | N | 2 |
| M | A | 2 |
| H | D | 2 |
| V | M | 1 |
| D | G | 1 |
| A | T | 1 |

## QC verdict

- Good fit on substitution identity where the two pipelines share evidence: Step 7 has 100% origin/destination agreement on shared rows.
- Remaining mismatch is sensitivity and score-value completeness, not substitution identity.
- The key unresolved technical gap remains numeric `SpectralSim` and `RTScore` values in FragPipe 24.0 outputs.
