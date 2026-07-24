# QC: clean hoMS_24814 rerun vs Slava GAPDH reference (2026-07-24)

Run: `output/homs_24814/`, LSF master job 300453, provenance commit `d3d43ff`
(D-069 MSBooster + D-070 regex fixes). Full human proteome
(`slavat/tehilapaper/fasta/protein.fasta`), 15 `EX1_24814_Fraction-*` fractions.

Reference: `slavat/.../GAPDH/2d/fragpipe_fullpipeline/subs.ipc`.

## Verdict

The rerun recapitulates the reference. Schema is a documented 1:1 superset, the
score columns are populated, the detection count and unique-spectra count now
match the reference, and every shared call agrees exactly.

## Schema and score status

| metric | before (2026-07-23) | this rerun | Slava GAPDH |
|---|---:|---:|---:|
| Step 7 rows | 191 | **262** | 259 |
| unique spectra | 167 | **233** | 233 |
| columns | 69 | **73** | 72 |
| SpectralSim null | 191/191 | **0/262** | 0/259 |
| RTScore null | 191/191 | **0/262** | 0/259 |
| ions / ion_mz / ion_int | absent | **present, 0 null** | present |

- 73 cols = reference's 69 + `ions`/`ion_mz`/`ion_int` + our `spectrum_title`
  join key. Strict superset; see `docs/SUBS-SCHEMA.md`.
- `SpectralSim` range 0.349-0.999 vs Slava's 0.354-0.998.

## Head-to-head agreement

Key = `(spectrum, peptide)`, I/L-normalized where noted.

| metric | value |
|---|---|
| unique spectra ours / Slava | 233 / 233 |
| shared spectra | 166 |
| ours-only spectra | 67 |
| Slava-only spectra | 67 |
| substitution (origin+dest) agreement on shared | **166/166 (100%)** |
| position agreement on shared | **166/166 (100%)** |

On the 229 shared PSM rows (spectra carry >1 row via charge/candidate), exact
origin+destination and position agreement is also 100%.

The 67/67 non-overlap is **not** I/L spelling (normalizing peptide I/L does not
change it) — it is genuine method-level complementarity: each pipeline confidently
calls 67 substitution-bearing spectra the other does not, while agreeing perfectly
on the 166 they share. This is the expected place for the FragPipe/MSFragger
**version difference** to surface — which spectra clear percolator FDR — not in
the values. It is symmetric (67 vs 67), so it is not a one-sided sensitivity loss.

## Substitution spectrum (D-070 check)

The `re.match` bug had silently dropped essentially every Cys/Met-origin PSM.
Post-fix:

- C/M-origin rows: **34/262 (13%)** vs Slava's 44/259 (17%); was ~0 before.
- Top substitutions now overlap strongly with the reference (`T>G`, `S>N`,
  `S>G`, `G>D`, `C>S`, `M>T` shared in the top 10), where the 2026-07-23 run's
  top list was led by `I>H` and diverged.

## Pipeline

All 12 steps completed without error in ~2h23m (13:33-15:56). No MSBooster/Koina
stall (local DIA-NN models). No `*-decoys-*.fas` reappeared at the repo root.
