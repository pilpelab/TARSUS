# Step-07/11 regression eval

A fast, committed, CI-style guard for the two deterministic steps that build the
deliverable tables:

- **Step 07** - `analyze_outputs(...)` -> `subs.ipc`
- **Step 11** - `localize(...)` -> `subs_localized.ipc` / `.csv`

Every correctness bug this project has hit lived in step 07 - D-069 (MSBooster
off -> null `SpectralSim`/`RTScore`), D-070 (`re.match` anchoring dropped every
Cys/Met substitution), and the `rev_` decoy leak (fixed in `7502692`). Each was
caught manually, late, by ad-hoc QC against Slava's references. This eval closes
that gap: it re-runs the two steps on frozen reference slices and fails if a
commit silently changes the output or breaks reproduction of Slava.

It calls the step functions **directly** - no orchestration, no LSF, no external
tools, no network. The whole thing runs in a couple of seconds.

## Run it

```bash
make eval            # == uv run pytest tests/eval -q
```

## What it checks (per fixture)

1. **Snapshot gate.** A fresh `analyze_outputs` / `localize` over the committed
   slice must equal the committed golden. Both sides are *canonicalized* first
   (`eval_lib.canonicalize`): rows sorted to a total order, floats rounded to 6
   dp - so row-order and float-representation noise never trip it, only a real
   value/schema change does.
2. **Invariant guards** (named, so a failure says *what* broke):
   - schema: every documented `subs.ipc` column present (docs/SUBS-SCHEMA.md);
   - `rev_` decoy count across `Protein`/`Protein_right` == 0 (guards `7502692`);
   - `SpectralSim` / `RTScore` null count == 0 (guards D-069);
   - `dpbp` all finite;
   - vs Slava's reference on shared spectra: substitution (origin+dest+position)
     identity == 100%, `dpbp` Pearson r >= 0.99 (I/L-normalized keys).

The pure helpers (`canonicalize`, the guards, `slava_compare`) have their own
unit tests in `test_eval_lib.py`.

## Layout

```
tests/eval/
  eval_lib.py              # canonicalize, invariant guards, slava_compare
  test_eval_lib.py         # unit tests for the pure helpers
  test_eval_step07_11.py   # the eval: run step07(+11) -> snapshot + invariants
  fixtures/<name>/
    inputs/                # the ~100-spectrum slice of every step-07/11 input
    golden/                # subs.ipc, subs_localized.ipc/.csv from current code
    reference/subs_ref.ipc # projection of Slava's subs.ipc for slava_compare
    README.md              # per-fixture lineage + provenance
scripts/build_eval_fixtures.py   # (re)build the slices and (re)bless goldens
```

## Fixtures

| name | organism | reference run |
|---|---|---|
| `gapdh` | human (GAPDH experiment) | `slavat/.../GAPDH/2d/fragpipe_fullpipeline` |
| `evcoli` | E. coli | `elizabev/tRNA/EVpar/tarsus_analysis` |

Each is a lineage-coherent ~100-spectrum slice, every spectrum drawn from that
run's Slava reference `subs.ipc`, deliberately covering Cys-/Met-origin
substitutions, I/L destinations, and multiple charges. `gapdh` additionally
carries one **synthetic `rev_` decoy row** so the `7502692` guard can actually
fire (neither reference run leaks a decoy naturally) - see
`fixtures/gapdh/README.md`.

## Blessing goldens (intentional changes only)

The snapshot fails on *any* behaviour or schema change - that is the point. When
the change is intentional and reviewed, regenerate the goldens:

```bash
TARSUS_EVAL_UPDATE=1 uv run pytest tests/eval -q   # rewrite goldens, skip snapshot asserts
uv run pytest tests/eval -q                        # confirm green
git add -p tests/eval/fixtures                      # review the golden diff, then commit
```

`TARSUS_EVAL_UPDATE=1` still runs the invariants and `slava_compare` - a bless
that violates them fails. **Blessing is a deliberate, reviewed commit; never do
it to make a red test green without understanding the diff.**

## Rebuilding fixtures from the reference dirs

Only needed if the reference runs change or the slice definition does (this reads
the cluster-only reference paths):

```bash
uv run python scripts/build_eval_fixtures.py --fixture all   # or gapdh|evcoli
```

The builder asserts, at build time, that each slice is non-empty, passes every
invariant, and still matches Slava - a silent empty result means the slice broke
lineage (D-047), not that the code is wrong.
