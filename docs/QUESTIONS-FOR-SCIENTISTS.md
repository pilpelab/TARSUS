# Questions for the experimentalists — `AlaGGC`

**Status:** blocking. The pipeline is finished and mechanically faithful to the reference
implementation. The biology does not validate, and we cannot tell whether that is an experimental
result or a remaining error, because **no one has stated what this experiment should produce.**

---

## What we assumed

`HouYM-25-G140-AstralDDA-**AlaGGC**-{LS,HS}-1` — E. coli, tRNA lab. `GGC` is a **glycine codon**;
`Ala` is alanine. So we read this as an engineered tRNA charged with Ala but decoding GGC, which
should misincorporate **alanine at glycine codons** and produce **Gly→Ala (G→A)** substitutions.

We could find this written down **nowhere** — not in the code, not in the reference implementation,
and not in the reference run's own `sdrf.tsv` (every biological field reads "not available").

## What we get

Comparing our `AlaGGC` run against the reference `EVpar` run (same instrument, same pipeline):

| | AlaGGC (ours) | EVpar (reference) | |
|---|---|---|---|
| **G→A** | 8 / 2,556 — **0.31%** | 101 / 3,922 — **2.58%** | **8× depleted** |
| A→G (reverse direction) | 0.31% | 0.38% | flat |

**G→A is not just absent — it is eight times rarer than in the reference dataset.**

The substitutions that *are* enriched look like mass-spectrometry artifacts rather than biology:

| Substitution | Δmass | AlaGGC | EVpar | Interpretation |
|---|---|---|---|---|
| F→M | −16.03 Da | 109 | **0** | oxidation-related (Met+O ≈ Phe) |
| L→N | +0.96 Da | 84 | **0** | ≈ +1 Da — C13 isotope / deamidation |
| I→N | +0.96 Da | 70 | **0** | same |
| L→D | +1.94 Da | 53 | **0** | ≈ +2 Da — double C13 |
| Q→K | +0.036 Da | 99 | 107 | near-isobaric — barely separable at 20 ppm |

They cluster at ±1, ±2 and ±16 Da — the classic isotope-peak and oxidation misassignment signature.
Several are **completely absent** from the reference dataset run through the same pipeline.

---

## The questions

1. **What substitution should `AlaGGC` produce?** Is it Gly→Ala, or do we have the direction
   backwards? This is the single most important question — everything else follows from it.

2. **What is `EVpar`?** Is it the control (empty-vector parental)? If so, why does the *control*
   show more Gly→Ala than the mistranslation strain?

3. **Was the mistranslation validated independently** — western blot, fluorescent reporter, targeted
   MS? If the strain was never confirmed to mistranslate, then the absence of signal is an
   **experimental result, not a pipeline bug**, and we should report it as such.

4. **Are F→M and L→N expected?** They dominate our results and are entirely absent from the
   reference's.

5. **What Gly→Ala rate did the paper report?** A number — even an order of magnitude — gives us
   something to validate against.

---

## Why we are not just "fixing" it

Tuning search parameters until Gly→Ala appears would be fitting to a target nobody supplied. If the
signal genuinely is not there, the honest conclusions are: *the experiment did not work*, *the method
cannot detect it at this level*, or *we misunderstood the design*. Which of those is true is a
scientific call, not an engineering one.

**With answers to (1) and (5), the pipeline can be validated or falsified within minutes.**
