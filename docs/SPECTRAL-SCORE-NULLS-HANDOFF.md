# Handoff: SpectralSim and RTScore are null

Status: acknowledged blocker.

The current TARSUS_BC reruns produce `SpectralSim` and `RTScore` columns in `subs.ipc`, but the values are all null.

Observed on completed hoMS QC outputs:

```text
homs_24814 Step 7:
  SpectralSim null 191/191
  RTScore     null 191/191

homs_24814_gapdh Step 7:
  SpectralSim null 191/191
  RTScore     null 191/191
```

Slava reference has numeric values:

```text
Slava GAPDH Step 7:
  SpectralSim null 0/259
  RTScore     null 0/259
```

This is a major unresolved bug. The schema is present, but the score values are missing. The next session should investigate why our FragPipe/MSBooster outputs do not provide these values, or where FragPipe 24.0 stores their equivalents.

No further debugging was done in this note.
