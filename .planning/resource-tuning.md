# Resource Tuning: Premature but Necessary

**Author:** agent (2026-07-01)
**Status:** draft — not implemented
**Depends on:** pipeline producing correct end-to-end results first (master job 994145 must complete)

## Preface

This plan is **premature**. Master job 994145 is still running (Step 5 of 11).
We have not yet validated Steps 6-11 produce correct results. Resource tuning
before the pipeline is proven is a risk: changed resource requests could mask
or introduce bugs. However, the waste is large enough that early documentation
is warranted — the actual implementation should wait until the first successful
end-to-end run is complete.

This plan supersedes `.planning/resource-distribution.md`, extending its scope
from Steps 3a/3b/3c to all pipeline steps.

## Baseline (from live jobs, master 994145)

### Step 1 — ThermoRawFileParser
- Requested: 7 GB LSF, 1 CPU
- Data: 6.0 GB + 8.3 GB mzML output (2 raw files)
- Actual: N/A (completed, no bjob data retained)
- Assessment: Need real max_mem data. 7 GB for a 7-11 GB raw file is reasonable.

### Step 2 — PepQuery Index (auto-scaled)
- _sub.mzML files: 3.1 GB each
- Auto-heap: max(8 GB, min(3.1×2×1024=6349, 24 GB)) = 8 GB
- LSF mem: 8 GB + 4 GB overhead = 12 GB
- Assessment: Auto-scaling is good. 12 GB per file × 2 files = good.

### Step 3a — FragPipe First Pass
- LSF: 30 GB, 10 slots
- JVM: **-Xmx125G** (way over LSF limit)
- Actual MAX MEM: unknown (no data from this run)
- Previous run #946232: **67.1 GB** MAX MEM

### Step 3c — FragPipe Second Pass
- LSF: 30 GB, 10 slots
- JVM: **-Xmx125G** (4× over LSF limit)
- Actual MAX MEM: **44.2 GB** (50% over 30 GB MEMLIMIT)
- CPU efficiency: 56.4%
- Wall time: 30.9 min

### Step 5 — PepQuery Validation (4568 chunk jobs)
- Requested LSF: **1500 MB** via `-R rusage[mem=1500]`
- MEMLIMIT: **1 GB** (1024 MB — queue default, no `-M` flag in code)
- JVM: **-Xmx4096m** (4× above MEMLIMIT, 8× above actual)
- Actual MAX MEM: **~500 MB** (across 4560 completed jobs)
- Job count: 4568 chunks from a ~15 KB PSM input file

### Step 6 — PDV / Step 7-11 — Python inline (no separate LSF jobs)
- Run on master: 4 GB requested, 43 MB actual utilization

### Master Job
- Requested: 4 GB, 1 CPU, queue gsla-cpu
- Actual: 43 MB RSS, ~0.74% CPU
- Run time so far: ~20 hours (mostly waiting on child jobs)

## Problems

### P1: `-M` flag missing from `submit_bsub()` (all steps)

`lsf.py:submit_bsub()` passes `-R rusage[mem=X]` but never passes `-M X`.
LSF's `-M` sets the per-process memory limit (MEMLIMIT). Without it, the
cluster applies a queue-level default (currently 1 GB for gsla-cpu).

**Impact:**
- PepQuery jobs get MEMLIMIT=1G despite requesting rusage=1500 MB
- Steps 3a/3c get whatever default applies (may not match rusage)
- Jobs that exceed the default MEMLIMIT get silently SIGKILL'd
- The user sees "exit code 137" with no clear cause

### P2: JVM heap >> LSF reservation >> Actual (Steps 3a/3c/5/9)

| Step | JVM -Xmx | LSF rusage | MEMLIMIT | Actual | Ratio |
|------|-----------|-----------|----------|--------|-------|
| 3a | 125 GB | 30 GB | ? | ? | ~4× LSF |
| 3c | 125 GB | 30 GB | ? | 44 GB | ~4× LSF, 1.5× actual |
| 5 | 4 GB | 1.5 GB | 1 GB | 0.5 GB | ~8× actual |
| 9 | 4 GB | 5 GB | ? | ? | ~? |

The `-Xmx` flag is what Java *commits* virtual address space for. The LSF
`rusage` is what the scheduler *reserves*. The MEMLIMIT is what the kernel
*enforces*. These three numbers should roughly agree. Currently they don't.

### P3: 10 slots, 9 threads (Steps 3a/3c)

Workflow template uses `num_threads=9`. LSF allocates `-n 10`. One core
always idle. Minor but systematic.

### P4: Master job 1% utilized

4 GB reserved, 43 MB used. 1 CPU, <1% utilized. Runs 20+ hours.

### P5: PepQuery job storm

4568 bsub jobs submitted in a tight Python loop with no throttling.
Each carries ~15s JVM startup overhead (cumulative ~19 CPU-hours).
Potential cluster backpressure.

### P6: Step 9 (PepQuery base rescoring) resources unknown

Defaults: 5 GB LSF, -Xmx4096m heap. No actual run data yet — may be
over- or under-provisioned.

## Proposed Changes

### Change 1: Add `-M` to `submit_bsub()` (fixes P1)

**File:** `src/tarsus/lsf.py`

In `submit_bsub()`, add `-M` flag with memory converted to KB (LSF
expects `-M` in kilobytes):

```python
bsub_cmd = [
    "bsub",
    "-J", job_name,
    "-q", queue,
    "-n", str(cpus),
    "-R", f"rusage[mem={memory_mb}] span[hosts=1]",
    "-M", str(memory_mb << 10),   # MB → KB
    "-oo", str(log_path),
] + cmd
```

This single change ensures MEMLIMIT always matches the reservation for
every step, eliminating the silent-SIGKILL risk.

### Change 2: Align JVM heap with LSF memory (fixes P2 — Steps 3a/3c)

**Files:** `src/tarsus/steps/step03a_first_pass.py`, `step03c_second_pass.py`,
`src/tarsus/orchestration.py`

- Step 3a: `memory_mb=30000`, `fragpipe_ram_gb=28`
  - (28 GB JVM heap ≤ 30 GB LSF limit, previous run unknown but 3a is lighter)
- Step 3c: `memory_mb=50000`, `fragpipe_ram_gb=45`
  - (45 GB matches actual 44.2 GB MAX MEM with headroom)
- Add validation: warn if `fragpipe_ram_gb > memory_mb // 1024`
- In `orchestration.py`, pass explicit kwargs instead of relying on defaults

### Change 3: Align PepQuery JVM with actual usage (fixes P2 — Step 5)

**File:** `src/tarsus/steps/step05_query_psm.py`

- Reduce `java_heap_mb` default from 4096 to **1024**
- Reduce `memory_mb` default from 1500 to **1024** (matches actual ~500 MB
  with 2× headroom)
- Or keep at 1500 with `-M 1500000` once Change 1 is in place
- Principle: `-Xmx` should be ≤ `memory_mb` ≤ MEMLIMIT

**But:** Wait for Step 9 data before making the same change there.

### Change 4: Align thread/slot count (fixes P3 — Steps 3a/3c)

**File:** `src/tarsus/assets/` (workflow template patching)

Two options:
- **4a**: Change `num_threads=9` → `num_threads=10` in the FragPipe workflow
  template patching
- **4b**: Reduce LSF slots from 10 to 9

4a is better (more parallelism, same cost). However, FragPipe's performance
may not scale linearly beyond 9 threads (Amdahl's law on I/O-bound MS
search). 4b saves one slot for other users. Decide based on actual CPU
utilization data from the completed run.

### Change 5: PepQuery submission rate-limit (fixes P5 — Step 5)

**File:** `src/tarsus/steps/step05_query_psm.py`

Add a small delay or batch-throttle in the chunk submission loop:
```python
import time
BATCH_SIZE = 500  # submit 500, then wait
for idx, chunk in enumerate(chunks):
    ...
    if idx > 0 and idx % BATCH_SIZE == 0:
        time.sleep(5)  # let scheduler catch up
```

No change to correctness — `wait_for_jobs` already blocks. This just
prevents the submission loop from flooding the scheduler.

### Change 6: Right-size the master job (fixes P4 — cli.py)

**File:** `src/tarsus/cli.py`

Drop master from `memory_mb=4000, cpus=1` to `memory_mb=1024, cpus=1`.
The master uses 43 MB and is >99% idle. 1 GB is generous.
(If Change 7 is implemented, bump to 2 GB instead.)

### Change 7: Move Step 3b to its own LSF job (from existing plan)

**File:** `src/tarsus/steps/step03b_make_peptides.py`, `orchestration.py`

Wrap `make_peptide_candidates()` in a bsub job (2 CPUs, 16 GB). Replace
inline call with submit+wait. This offloads the 299 MB FASTA generation
from the undersized master.

**Tradeoff:** Adds scheduling overhead for a ~2-minute Python job.
The existing plan's Change 4 (bump master to 8 GB / 2 CPU) is simpler.
Decide after seeing actual Step 3b runtime from the completed run.

## Implementation Order

```
Phase 0: Wait for master 994145 to complete
  → Collect actual MAX MEM/cpu_util for Steps 6-11
  → Adjust tuning parameters based on real data
  → Do NOT implement before this

Phase 1 (safety — prevents SIGKILL):
  Change 1: Add -M to submit_bsub()
  Change 2: Align JVM heap (3a/3c)
  Change 3: Align PepQuery heap (Step 5)

Phase 2 (efficiency — reduces waste):
  Change 4: Thread/slot alignment
  Change 5: Rate-limit PepQuery submission
  Change 6: Right-size master

Phase 3 (pipeline structure — optional):
  Change 7: Step 3b offload OR master bump

Phase 4 (extend to remaining steps):
  Update Step 9 (and Step 1 if data warrants) with Phase 1 patterns
```

## Verification

```bash
# After implementation, re-run trial and check:
bjobs -l <jobid> | grep -E "MAX MEM|MEMLIMIT|CPU"

# Expected:
# Step 3a: MAX MEM < 30000 MB, MEMLIMIT ≈ 30000 MB
# Step 3c: MAX MEM < 50000 MB, MEMLIMIT ≈ 50000 MB
# Step 5:  MAX MEM < 1500 MB,  MEMLIMIT ≈ 1500 MB
# Master:  MAX MEM < 1024 MB,  MEMLIMIT ≈ 1024 MB
```

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Reducing 3a/3c -Xmx causes OOM during FragPipe | Low (reduction to 28/45 GB, previous used 44/67) | Job failure, restart | Check against actual; leave headroom |
| -M kills a legitimately memory-hungry job | Medium | Job failure | Set -M = rusage (same as current intent) |
| Rate limiting slows pipeline | Low (5s every 500 jobs = ~45s total on 4568) | Negligible | Tune BATCH_SIZE if needed |
| Step 9 unknown resource profile | Medium | Phase 4 deferred | Collect data from first run |
