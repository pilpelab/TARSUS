"""Resource sizing for JVM-backed LSF steps.

Two jobs:

1. **Never let a JVM heap exceed its LSF reservation.** ``-Xmx`` is a *ceiling*,
   not a reservation: the JVM happily accepts ``-Xmx4096m`` inside a 1500 MB
   cgroup and only dies — with ``TERM_MEMLIMIT``, no Java stack trace — once the
   heap actually grows past the limit. That makes it a *latent* bug: it works on
   small inputs and detonates on big ones. It has already cost us once (D-049,
   defect 1: PDV shards ran a 4096 MB heap inside a 4000 MB reservation and every
   shard was killed the moment targeted mode made them render real data).

2. **Scale PepQuery's memory with the reference proteome.** PepQuery loads the
   ``-db`` FASTA to compete each candidate against reference peptides, so its
   footprint tracks FASTA size. A default tuned for E. coli silently OOMs on a
   human proteome ~60x larger.

Both are overridable per-lab via environment variables — no code change needed.
"""

import math
import os
from pathlib import Path

_MB = 1024 * 1024

#: MB the shard needs *beyond* the JVM heap: JVM non-heap (metaspace, thread
#: stacks, code cache, native buffers) plus the Python parent process.
NON_HEAP_HEADROOM_MB = 768

# ── PepQuery memory model ────────────────────────────────────────────
#
# Fitted to two measurements, and it predicts both:
#
#   E. coli   1.8 MB FASTA -> 279 MB peak RSS   (measured: LSF `Max Memory`
#                                                across 3,869 Step 9 jobs;
#                                                median 249, p95 262, max 279)
#   Human   106.0 MB FASTA -> ~4 GB             (reported requirement)
#
#   peak_mb ~= BASE_MB + PER_FASTA_MB * fasta_mb
#            = 220 + 36 * 1.8   = 285   (vs 279 measured)
#            = 220 + 36 * 106.0 = 4036  (vs ~4 GB reported)
#
# The JVM heap is then set to SAFETY_FACTOR x the predicted peak, because a heap
# sized exactly at the live-set forces constant GC and can still OOM.
PEPQUERY_BASE_MB = 220
PEPQUERY_PER_FASTA_MB = 36
PEPQUERY_SAFETY_FACTOR = 1.5
PEPQUERY_MIN_HEAP_MB = 1024


class ResourceConfigError(ValueError):
    """A JVM heap cannot fit inside its LSF memory reservation."""


def check_heap_fits(java_heap_mb: int, memory_mb: int, what: str = "job") -> None:
    """Fail loudly when a JVM heap does not fit inside its LSF reservation.

    Raises:
        ResourceConfigError: *memory_mb* leaves less than
            :data:`NON_HEAP_HEADROOM_MB` above *java_heap_mb*.
    """
    if memory_mb - java_heap_mb < NON_HEAP_HEADROOM_MB:
        raise ResourceConfigError(
            f"{what}: JVM heap ({java_heap_mb} MB) does not fit inside the LSF "
            f"memory reservation ({memory_mb} MB). The reservation must exceed "
            f"the heap by at least {NON_HEAP_HEADROOM_MB} MB to cover JVM "
            f"non-heap memory and the Python parent, or the job is killed with "
            f"TERM_MEMLIMIT once the heap fills. Note -Xmx is a ceiling, not a "
            f"reservation: an oversized heap looks fine on small inputs and only "
            f"fails on large ones."
        )


def estimate_pepquery_memory(fasta_path: Path) -> tuple[int, int]:
    """Size a PepQuery job from the reference proteome it will load.

    Returns ``(memory_mb, java_heap_mb)`` — the LSF reservation and the JVM heap,
    guaranteed to satisfy :func:`check_heap_fits`.

    Override per-lab with ``TARSUS_PEPQUERY_MEM_MB`` and
    ``TARSUS_PEPQUERY_HEAP_MB``. Setting only the heap sizes the reservation
    around it; setting only the reservation leaves the heap to the model (and is
    still validated, so an impossible pair fails immediately rather than at the
    first big input).
    """
    env_heap = os.environ.get("TARSUS_PEPQUERY_HEAP_MB")
    env_mem = os.environ.get("TARSUS_PEPQUERY_MEM_MB")

    if env_heap:
        java_heap_mb = int(env_heap)
    else:
        fasta_mb = fasta_path.stat().st_size / _MB if fasta_path.is_file() else 0.0
        predicted_peak = PEPQUERY_BASE_MB + PEPQUERY_PER_FASTA_MB * fasta_mb
        java_heap_mb = max(
            PEPQUERY_MIN_HEAP_MB,
            int(math.ceil(predicted_peak * PEPQUERY_SAFETY_FACTOR)),
        )

    memory_mb = int(env_mem) if env_mem else java_heap_mb + NON_HEAP_HEADROOM_MB

    check_heap_fits(java_heap_mb, memory_mb, what=f"PepQuery ({fasta_path.name})")
    return memory_mb, java_heap_mb
