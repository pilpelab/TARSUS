# TARSUS paper digest (Nature 2026)

What the published paper claims, how it defines its terms, and every caveat the authors or referees raised. Pipeline parameters and deviations from our code: `paper-methods-vs-tarsus.md`. Supplementary-table contents and gotchas: `paper-supplementary-tables.md`.

## Citation

Tretyachenko V, Leiman T, Morgenstern D, Levin Y, Asraf O, Dahan O, Dahary D, Pilpel Y. "Encoded and non-genetic protein variants expand the human functional proteome." Nature, online 2026-09-14. doi:10.1038/s41586-026-11124-z.

| Item | Value |
|---|---|
| Preprint | bioRxiv 10.1101/2025.02.17.638604; v1 2025-02-17, v2 2026-06-02 (post-revision), title "...alternative protein variants expand human functional proteome" |
| Code | https://github.com/treko90/tarsus (Nature and Reporting Summary; bioRxiv v2 text misspells it `treko090`) |
| New raw data | PRIDE PXD073135 (purified proteins, 18O/D2O HeLa, synthetic peptides; contents not itemized in the paper) |
| Public datasets | PXD010154 healthy tissues (Wang et al. 2019 MSB), PXD027328 Trulsson degradomics, PXD017276 Karayel RBC precursors, PXD043612 Arg starvation, PXD044085 Leu starvation, PXD028921 Trp/Tyr starvation, MSV000080679 BioPlex AP-MS |
| References DBs | Ensembl r112 GRCh38 pep + CDS (chosen over UniProt for codon mapping), gnomAD v4.1 exomes, AlphaMissense (zenodo 8208688), RNA-seq E-MTAB-2836 |
| Referees | #3 Stephen Fried (named); #2, #4 anonymous. Concurrent paper on the same topic: Tsour & Slavov, Nature 2026 |

## Sources read and their coverage

| Source | Coverage | Status |
|---|---|---|
| Nature article page | abstract, data/code availability, acknowledgements, Extended Data Fig. 1-10 legends | main text and Methods are paywalled from the cluster IP: NOT READ |
| bioRxiv v2 full text | all Results, Methods, figure legends | read via a fetch agent, paraphrased; references unread. Numbers below marked (v2) come from here and may differ in wording from the Nature final |
| Supplementary Information PDF | Supp. Notes 1-2, Supp. Figs. 1-15 | read in full |
| Reporting Summary | tool versions, data exclusions, replication | read in full |
| Peer Review File (92 pp) | all three review rounds and rebuttals | read in full |
| Supplementary Tables 1-18 | every sheet profiled numerically | `data/paper/tsv/` |
| github treko90/tarsus | 15 files, diffed against `TARSUS_elizabev/` | see `paper-methods-vs-tarsus.md` |

If someone obtains the Nature PDF, diff its Methods against this file and `paper-methods-vs-tarsus.md`; that is the one unread primary source.

## Headline numbers

| Quantity | Value | Source |
|---|---|---|
| Tissues in PXD010154 / analyzed | 29 / 27 (kidney, liver lacked clear RNA-seq) | Reporting Summary |
| Raw files analyzed | 942 of ~1,800 (trypsin-digested and with matched RNA-seq) | Peer review |
| Candidate substituted PSMs, second-pass MSFragger | 915,484 | SI Note 1 |
| Removed by PepQuery2 | 93% | SI Note 1 |
| After >=2 site-covering fragments and no N-terminal subs | 76,516 candidate peptides | SI Note 1 |
| Final, after labile-PTM rescoring + Ascore localization | 13,910 total / 7,215 unique (ST1) | SI Note 1, ST1 |
| Filtered (quantification) set | 10,121 total / 5,257 unique (ST4) | v2, ST4 |
| RNA-supported (genetic) | 5,358 | v2, peer review |
| No RNA support / with >=10 ref reads / after dropping 5 ambiguous classes | 8,552 / 6,510 / 5,216 | v2 |
| Mean log10 abundance ratio, non-genetic | -2.6 (~1/500) | v2 |
| Per-residue error rate stated | 1e-4 to 1e-3 (revised down from a 1e-2 per-molecule figure) | Peer review |
| MaxQuant DP / deTEL unique (both PepQuery2-revalidated) | 4,168 / 3,235; TARSUS-only 4,535, all three 916; 2,680 of 7,215 overlap either | Peer review Response Fig. 21 |
| MSBooster agreement, substituted vs reference | spectral similarity median 0.91 vs 0.96; RT Pearson 0.91 vs 0.94; 90% of substituted PSMs >= 0.75; <0.7 is ~6% | SI Note 1, Supp. Fig. 8 |

## Definitions

- **Unique substitution** = distinct substituted peptide sequence (`alt_peptide`). **Total** = sum of its observations across tissue samples. ST1: 7,215 unique `alt_peptide` vs 7,544 unique (protein, position, origin, destination). The paper itself switches unit for ST4: its "5,257 unique" equals the protein-site count, not `alt_peptide` (4,978). Our QC Venn (D-072) keys on protein-site, so its counts are not comparable to the paper's 7,215.
- **Abundance ratio** = log10(MS1 intensity substituted / MS1 intensity reference). This is our `dpbp` column (`docs/SUBS-SCHEMA.md`); the string "dpbp" never appears in the paper. For quantification (v2 Methods): max intensity per peptide per charge state, ratio per charge state, median across charge states. The authors call it semi-quantitative: ionization efficiency differs between the two peptides (synthetic pairs: alternative was more detectable in 4 of 7, ED Fig. 4).
- **Mutational distance** = minimum nucleotide changes from the reference codon (Ensembl r112 CDS) to any codon of the destination amino acid. 1 = near-cognate, 2-3 = non-cognate. RNA-supported subs are distance 1 in 5,001 of 5,130; non-genetic are distance 2 in 30% and 3 in ~2% (v2).
- **Genetic vs non-genetic**: RNA-seq reads aligned with BWA to Ensembl r112 CDS, codon counts per site summed per tissue. One-sided binomial P(X >= k | n, p = eps/3) with eps = 0.001, Benjamini-Hochberg; FDR < 0.05 means RNA-supported (genetic). MS evidence is deliberately not part of the test. Non-genetic **broad** set: >=1 reference read and 0 alternative reads (aggregate analyses). **Conservative** set: >=10 reference reads and 0 alternative reads (allele-frequency and AlphaMissense analyses).
- **Heterozygous / somatic** (RNA log10 alt/ref ratio): heterozygous within +-0.33 (Results) or +-0.3 (Methods), coverage >= 10; somatic -1.5 to -3 (Results, Fig. 3) or -1.5 to -3.5 (Methods).
- **Extended set** = ST1. **Filtered set** = ST4, for MS1 quantification: no K/R origin or destination, <=1 missed cleavage, away from peptide termini (rule reconstructed in `paper-supplementary-tables.md`).
- **Ambiguous classes** = C>A, C>S, H>D, M>D, W>D, flagged `ambiguous=1` in ST1/ST4/ST9/ST11 and excluded from downstream analyses (section below).
- **Immunoglobulin** = GO:0019814 "immunoglobulin complex" or GO:0003823 "antigen binding", manually curated to bona fide antibody chains (not the Ig superfamily). Flag column `immunoglobulin` in ST1/ST4.
- **Functional site** = UniProt "site", "binding site", "active site" annotation.
- **Substitution fraction** (removed from the paper) = substituted origin residues / all origin residues in identified peptides of the same search. Still used in ED Fig. 5-7 legends.

## Claims by Results section (v2 numbers)

1. **Pipeline.** Three stages: reference search and write unidentified spectra; in silico mutagenize identified reference peptides and search the remainder (MSFragger + IonQuant); PepQuery2 validation + Ascore localization. PepQuery2 competes each PSM against 10,000 shuffles of itself, reference peptides, PTM-modified reference peptides (including labile), and SAAVs of other reference peptides; it must beat all of them. Stated experimentally estimated FDR ~2%.
2. **Prevalence.** 13,910 / 7,215 unique; ~40% more than prior methods on the same data. Detection is biased toward tryptic-peptide N-termini, also in RNA-supported "ground truth" (ED Fig. 3). 539 non-genetic subs have abundance ratio > 0 (text says 2.3%; it is 3.9%); 68 non-Ig subs with >=100 RNA reads and no RNA support keep log10 ratio > 0. Authors estimate ionization/chromatography/noise may inflate non-genetic abundance 100-1,000x; true levels may still be single-digit percent.
3. **Genetic variants mirror population frequency.** Heterozygous: 630 unique, 498 in gnomAD, Pearson 0.24 (p = 8.1e-11). Somatic: 868 unique in 363 proteins (432 Ig), 363 in gnomAD, Pearson 0.23 (p = 2.58e-10). gnomAD supports 66% (3,544 of 5,358) of RNA-supported variants (ST5).
4. **Non-genetic look like mistranslation.** After dropping ambiguous classes: frequent A>S, A>N, V>I/L, H>N, A>V, E>T, Y>F, A>T, S>G; directional (R>K vs K>R, G>A vs A>G, Y>F vs F>Y, T>S vs S>T are not reciprocal). Non-genetic subs (coverage >= 10) correlate with minor allele frequency, Pearson 0.55 (p = 1.88e-20). BLOSUM62 shifts negative. Starvation (ST7, ED Fig. 5-7): Trp-dep W>F, Tyr-dep Y>F, Arg-dep R>K/R>C/R>H/R>S, Leu-dep L>F/L>V and M>T (all Leu-starved replicates, no controls).
5. **Function.** AlphaMissense pathogenicity anti-correlates with abundance (genetic R = -0.44, non-genetic R = -0.25; called weak). Proteasome inhibition (Trulsson U2OS +-MG132) raises substituted/reference ratios (Mann-Whitney p = 3.9e-8; only the relative shift is interpretable). Active-site proximity enrichment p = 5e-5 (randomization, 20,000 sims, C/H/M/W excluded); binding sites p = 0.06. Recurrence: 163 proteins / 392 unique subs in >=5 tissues. Hemoglobin: 227 unique non-ambiguous, 27 exact clinical variants (20 raise, 7 lower O2 affinity, ST15), 73 position-level candidates (ST16); 19 subs seen in tissue, purified Hb and RBC precursors.
6. **Purified-protein validation** (in-house, PXD073135): unique subs healthy / purified / overlap, Fisher on a 19 x L universe (L = MS-covered residues): GAPDH 44/31/5 (p 7.7e-6), PRDX6 13/27/4 (1.5e-6), PARK7 5/27/3 (1.1e-4), Hb 278/60/37 (4.2e-33). BioPlex 121 AP-MS: 2,748 unique, 54 overlap tissue (2.53x, p = 4.28e-10). Recombinant R1 antibody in HEK293: 45 variants, ~1/100 to 1/5,000 of reference, some distance > 1.

## Ambiguous and artifact classes

Mass shifts are relative to the unmodified residue; in the search Cys carries carbamidomethyl (+57.02146), so C>A is -88.99 Da relative to CAM-Cys.

| Class | dM (Da) | Proposed artifact | What was tested | Status in paper |
|---|---|---|---|---|
| C>A | -31.972 | TCEP desulfurization: CAM-Cys beta-elimination to dehydroalanine, reduction to Ala | D2O digest of HeLa (Wang 2010 protocol): zero C>A labelled or unlabelled; HEK293 and E. coli proteomes: zero C>A; 3 events in purified proteins | "vast majority" artifact; excluded from every analysis |
| C>S | -15.977 | dehydroalanine hydration to Ser | none specific; 181 genetic and 555 non-genetic C>S | flagged, excluded |
| H>D | -22.032 | His oxidation (blood storage) | none specific | flagged, excluded |
| M>D | -16.014 | oxidation (Hb Bristol mechanism) | none specific | flagged, excluded |
| W>D | -71.052 | Trp oxidation / ring opening | 18O water throughout lysis, reduction, alkylation, digestion: 38 W>D in 5,546 W-peptides, none with 18O on the Asp; D-peptides elute 12.9 min earlier (0/38 co-elute within 60 s, Wilcoxon p ~3e-14) so not in-source; 14/38 recur in tissues, 8/38 in starvation; rises under W/Y starvation | real molecular species, mechanism open (in-vivo O2 oxidation not excluded); flagged, excluded from key claims |
| W>A | -115.042 | unknown | largely removed by the revision filters | referee #4 reads this as pipeline bias |
| M>T | -29.993 | iodoacetamide alkylation artifact candidate | appears only in Leu-starved replicates | kept as biology, with caveat |

Isotope misassignment is a further artifact source the paper does not flag per class: MSFragger runs with `isotope_error=0/1/2/3`, and spectral similarity of substituted PSMs drops with isotope offset (non-genetic PSMs by offset 0/1/2/3: 5,590 / 2,242 / 716 / 239, i.e. ~32% have offset >= 1; Peer review Response Fig. 6). In ST7 the Arg and Leu starvation controls are led by L>N and I>N (+0.959 Da), the near-1 Da signature `.memory/lessons.md` already warns about.

## Claims removed during review (do not cite as paper results)

- Substitution abundance vs source-protein expression: Met-oxidation control showed the same negative trend, so it is MS1 detection/quantification bias.
- tRNA abundance vs substitution frequency, and the inference that low tRNA(Trp)/tRNA(Cys) avoids STOP readthrough: not robust once C/W/H ambiguous classes are removed.
- Protein-specific functional examples built on ambiguous classes (GAPDH C152A active-site Cys, PRDX6, DJ-1). Purified GAPDH showed C152G, not C152A.
- The section claiming translation errors diversify antibodies (R1 antibody kept only in the supplement).
- The substitution-fraction metric (replaced by counts).

## Caveats and limitations (authors and referees)

- Abundance ratio is semi-quantitative; MS1 detectability and missingness bias low-abundance proteins.
- Genetic origin not fully excluded: RNA coverage, unsampled somatic clones, circulating immunoglobulins produced elsewhere.
- Overlap between tissue and purified/enriched samples is statistically significant but small in absolute terms (referee #2 required a cautionary sentence).
- Cross-dataset recurrence of W>D can reflect detectability of abundant proteins; authors claim only reproducible existence, not site selectivity.
- Trulsson degradomics has no matched sequencing and is ubiquitin-enriched, so absolute ratios there are not interpretable.
- Correlations (AlphaMissense, allele frequency) are weak and correlational.
- deTEL is pip-installable; TARSUS is "a complicated recipe" (referee #3). Combining TARSUS, MaxQuant DP and deTEL gives ~30% more unique detections than TARSUS alone.

## Structural blind spots of the TARSUS design

- Only variants of first-pass-identified reference peptides are searched. A protein that is (near) fully edited or variant never yields its reference peptide, so its variant is never searched (authors, RNA-editing answer).
- Substituted PSMs with no MS1 intensity are excluded so every hit is quantifiable; including them would add ~40% unique detections (planned for a future release).
- Substitutions at the peptide N-terminal residue are excluded (poor b1 detectability).
- The second-pass search space is large and target-decoy FDR is weak there (metaproteomics analogy); PepQuery2 is the independent validation layer. A re-search of remainder spectra against reference + substituted peptides reassigned >85% to the substituted peptide, 129 (~1.5%) to the reference (with worse scores), ~1,900 (~15%) to neither.
- Strict Ascore localization is applied only to substitutions without RNA support; without RNA-seq the pipeline cannot reproduce that leniency.

## Inconsistencies inside the paper

Check the primary source before aligning code or reports to either side.

| Topic | Version A | Version B |
|---|---|---|
| FragPipe version | 22.1.07 (v2 Methods; public script path `fragpipe-22.1-build07`, a pre-release with custom modifications from the Nesvizhskii lab per Acknowledgements) | 23.1 (Reporting Summary, public README, `TARSUS_elizabev/`) |
| MSBooster models | v2 Methods: DIA-NN RT + AlphaPept MS2 generic | Slava's GAPDH second pass ran `AlphaPept_rt_generic` + `AlphaPept_ms2_generic` |
| Terminal exclusion for filtered set | >=3 positions (Results) | within 4 residues (Methods); ST4 data fit 3 from N-term, 2 from C-term |
| Heterozygous RNA window | +-0.33 (Results) | +-0.3 (Methods) |
| Somatic RNA window | -1.5 to -3 (Results) | -1.5 to -3.5 (Methods) |
| Somatic Ig count | 630 of 1,238 | 432 of 868 |
| Ratio > 0 share | "2.3%" | 539 / 13,910 = 3.9% |
| PXD028921 | Trp/Tyr starvation (Results, ED Fig. 7) | Trp/Phe (Data availability, Methods) |
| Tool overlap wording | ">60% and >40%" | 56% (deTEL) and 42% (MaxQuant) |
| Tissues | 29 (abstract) | 27 analyzed (Reporting Summary, ST1) |
| Purified GAPDH unique subs | 31 (text, ST14 overlaps sheet) | 38 unique `alt_peptide` in ST14 |
| Recurrent subs | 392 unique in >=5 tissues (text) | ST12 has 223 rows with n_tissues 4 to 18 |
| ED Fig. 4 legend | synthetic peptides (Nature) | duplicate of ED Fig. 3 (bioRxiv v2) |
