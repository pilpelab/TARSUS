# Resource Distribution: Steps 3a, 3b, 3c

**Author:** agent (2026-06-30)
**Status:** proposed — not implemented
**Depends on:** pipeline producing correct results first

## Motivation

The pipeline currently requests identical resources for steps 3a and 3c despite very
different workloads, requests JVM heap far exceeding LSF allocation (risk of OOM),
and runs step 3b on an undersized master node. Real job data from the trial run
documents the gaps.

## Baseline measurements (trial run, output/trial/)

```
                Wall time    MAX MEM    CPU eff.    Slots    LSF mem    JVM heap
Step 3a          8.5 min        ?          ?          10      30 GB      125 GB
Step 3b          inline       299 MB      master      1        4 GB       N/A
                                     (7.4M pep candidates)
Step 3c         30.9 min     44.2 GB     56.4%       10      30 GB      125 GB
Master (idle)   31 min idle   24 MB       0.74%       1        4 GB       N/A
```

## Problems

### 1. JVM heap >> LSF memory (critical)

`fragpipe_ram_gb=125` passes `-Xmx125G` to Java, while `memory_mb=30000` tells LSF to
reserve 30 GB (enforced at 29.2 GB MEMLIMIT). Step 3c hit 44.2 GB MAX MEM — 50% over
the limit. Earlier run #946232 hit 67.1 GB. The job is not killed only because LSF
measures RSS while Java commits virtual address space. This will break on a cluster
with stricter enforcement or under memory pressure.

**Danger signal:** When another user's job needs memory, the scheduler will see this
job exceeding its reservation and may SIGKILL it.

### 2. Step 3b runs on the wrong node

Step 3b generates 7.4M variant-peptide candidates (299 MB FASTA) using Polars. It runs
inline on the master node (1 CPU, 4 GB memory, D-012/D-017). The master is otherwise
idle (0.74% CPU, 24 MB) while waiting for child jobs. Step 3b is resource-constrained
and blocks the entire pipeline while running.

### 3. 10 slots, 9 threads — one wasted core

Fragger/Percolator/IonQuant all use `num_threads=9`. LSF allocates 10 slots. The 10th
slot is idle. Minor but unnecessary.

### 4. Identical resources for different workloads

Step 3a (tryptic, full proteome, 8.5 min) and step 3c (nocleavage, 14M variant
peptides, 30 min) request the same memory/CPU/JVM heap. 3c needs more memory for its
larger fragment index; 3a does not.

## Proposed changes

### Change 1: Align JVM heap with LSF memory

Edit: `src/tarsus/steps/step03a_first_pass.py`, `step03c_second_pass.py`

- Add a validation helper: if `fragpipe_ram_gb > memory_mb // 1024`, warn.
- Change step 3c defaults to `memory_mb=50000`, `fragpipe_ram_gb=45` (MAX MEM was 44 GB,
  45 GB gives headroom).
- Keep step 3a at `memory_mb=30000`, `fragpipe_ram_gb=28` (lighter workload).

In `orchestration.py`, pass different kwargs to each step instead of using defaults.

### Change 2: Move step 3b to its own LSF job

Edit: `src/tarsus/steps/step03b_make_peptides.py`, `orchestration.py`

- Add a `step03b_submit()` function that wraps `make_peptide_candidates()` in a bsub job.
- In `orchestration.py`, replace the inline call with the submitted version + `wait_for_jobs`.
- Resources: 2 CPUs, 16 GB memory (the 299 MB FASTA needs it), `queue=gsla-cpu`.

### Change 3: Align thread count with slot count

Edit: `step03a_first_pass.py`, `step03c_second_pass.py`

- Set `workflow.threads=10` (or `cpus-1`) in the workflow template patching.
- Or: request 9 slots instead of 10. Either way, align them.

### Change 4: Increase master job resources (alternative to Change 2)

Edit: `cli.py` line ~104

- Change master from `memory_mb=4000, cpus=1` to `memory_mb=8000, cpus=2`.
- Masters still mostly idle, but Python steps (3b, 4, 6, 7, 8, 11) have headroom.
- Simpler than Change 2 but wastes fewer resources than the status quo.

### Change 5: Centralize JVM memory constants

Edit: `src/tarsus/env.py`

- Add a `default_ram_gb(memory_mb)` method or a constant map.
- Ensures all tools use consistent `--ram` / `-Xmx` values.

## Order of implementation

1. **Change 1 + 5** (memory alignment) — highest priority, prevents potential OOM
2. **Change 2 or 4** (step 3b off master) — second priority
3. **Change 3** (thread/slot alignment) — minor but simple

## Verification

Re-run trial pipeline, then check:

```bash
bjobs -l <jobid> | grep -E "MAX MEM|CPU AVERAGE|CPU PEAK"
```

Expected:
- MAX MEM < MEMLIMIT (no over-allocation)
- CPU efficiency > 60% (less I/O wait, better thread utilization)
- Wall time for step 3c <= 30.9 min (baseline)
