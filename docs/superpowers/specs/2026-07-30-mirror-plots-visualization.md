# Spec: Mirror Plots for Substitution Validation

**Status:** draft — idea from Leva, needs refinement.
**Date:** 2026-07-30
**Origin:** Garbled voice note from Leva (archived in `.memory/`)

## Context

Leva wants a per-substitution visualization that shows experimental vs predicted
spectra as a mirror plot, with multiple subplots covering different aspects of
the FragPipe output.

## Core Idea

For each repeated substitution found by the pipeline, generate a **mirror plot**
(a common mass spectrometry visualization where experimental and theoretical/
predicted spectra are plotted on mirrored y-axes, one pointing up, one down).

The plot should contain **12 subplots** total:
- One side showing the **experimental** spectrum
- The other side showing the **predicted / theoretical** spectrum
- Covering different charge states, ion series, or fragmentation dimensions

All necessary data is already in the FragPipe output (predicted intensities,
matched fragments, etc.) — the visualization just needs to extract and render it.

## Open Questions

- What exactly are the 12 subplots? (Charge states? Ion types? Scan windows?)
- Should this be integrated into Step 12 (`visualize`), or a standalone script?
- What format? (PDF report? Interactive HTML? Static PNG per substitution?)
- How to handle large numbers of substitutions — paginate? Summarize top-N?

## Next Steps

1. Clarify with Leva the exact layout of the 12 subplots
2. Decide integration point in the pipeline
3. Prototype on one substitution to validate the layout
4. Integrate into the pipeline's output

## Related

- Step 12 (`src/tarsus/steps/step12_visualize.py`) — existing visualization step
- FragPipe output tables contain predicted vs matched fragment data
