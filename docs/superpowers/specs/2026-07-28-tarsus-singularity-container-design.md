# Spec: TARSUS Apptainer/Singularity environment image + publish-readiness

**Status:** approved design, ready for an implementation plan.
**Date:** 2026-07-28
**Related:** supersedes the "No Docker in current scope" note in `.agents/project.md`
(that constraint is deliberately lifted for this work).

## Context

TARSUS_BC is a containerizable, configurable reimplementation of Slava's
TARSUS/FragPipe substitution pipeline, meant for cross-lab use on the institute's
LSF cluster. It currently runs from a working copy with a 3.8 GB `tools/` tree
provisioned by `make setup`, and is driven by `tarsus run`, which `bsub`-submits a
master job that fans heavy steps out to child `bsub` jobs and runs the pure-Python
steps (07, 11) inline.

We want to (a) make the repo publishable and (b) package the whole environment as
an Apptainer/Singularity image so the toolset + runtimes + code are reproducible.

## Goal & scope

Deliver a **reproducible environment image** - the hard, valuable part - plus the
repo cleanup needed to publish. The pipeline is driven exactly as today (a `bsub`
master runs `tarsus run` inside the image). A local/no-LSF execution backend and
the wiring of child jobs through the container are **explicitly deferred** to a
separate "execution" spec (see Non-goals).

**In scope:**
- One parametrized Apptainer definition (`container/tarsus.def`) that builds in two
  modes from a single source of truth.
- A build wrapper (`scripts/build_container.sh`) that drives public vs internal
  builds, stages the license-gated tools, and bakes provenance.
- A minimal, additive provenance change so the commit SHA survives into the image.
- Repo publish-readiness: `.gitignore` tightening, untracking non-essential
  artifacts, an MIT `LICENSE`, and a README "Container" section.
- In-image validation: tool presence + `pytest tests/unit tests/eval`.

**Out of scope (Non-goals):**
- Any change to how steps execute (no local backend, no `bsub singularity exec`
  child wrapping, no orchestration.py rework). The known child-job caveat below is
  documented, not solved.
- Publishing a prebuilt public image containing MSFragger/IonQuant (not licensed
  for redistribution).
- Docker/registry publishing, multi-arch, GPU.

## Audience & distribution (decided)

**Both** a public, build-it-yourself recipe and an internal prebuilt `.sif`:
- **Public:** the recipe is portable. Auto-fetchable tools download at build time;
  MSFragger and IonQuant are **supplied by the builder** (no public URL - see
  Constraints), who thereby accepts the nesvilab academic license.
- **Internal:** the same recipe copies the already-validated pinned `tools/` tree
  into the image (fast, no re-download, exact versions), producing a `.sif` for
  institute labs on the shared cluster.

## Constraints (ground truth - verified 2026-07-28)

1. **MSFragger 4.4.1 and IonQuant 1.11.20 have no public download URL.** `make
   setup` sources them from a colleague's directory. The public build MUST accept
   them as builder-supplied inputs (`--msfragger <zip>`, `--ionquant <jar>`); it
   must never embed or redistribute them, and must fail with a clear message if
   they are absent.
2. **Academic-free licenses** (FragPipe, MSFragger, IonQuant, Philosopher,
   MSBooster, Percolator): fine for internal academic use; not redistributable in a
   public image. Auto-downloadable and redistributable: ThermoRawFileParser
   (Apache), PDV (Apache), JDK 21 (Temurin/GPL+CE), .NET 8 (MIT), PepQuery.
3. **Provenance uses `git rev-parse` at runtime** (`provenance.py`). A container has
   no git repo, so the commit must be baked at build time.
4. **`env.py` already honours `TARSUS_TOOLS_DIR`** (default `<repo>/tools`). Setting
   it to the in-image tools path needs no code change. `env.py` also sets
   `JAVA_HOME`/`DOTNET_ROOT`/`PATH`/`LD_LIBRARY_PATH` and manages Xvfb for PDV; the
   vendored `tools/xvfb/` makes the X11 dependency self-contained inside the image.
5. **PDV needs a virtual X11 display** even in CLI mode; the image relies on the
   vendored Xvfb, not any `module load`.

## WEXAC container platform (authoritative - hpcwiki `home/lsf/container`, read 2026-07-28)

The institute cluster (WEXAC, RHEL9, IBM Spectrum LSF) constrains the workflow:

- **Building requires privileges** available only on
  `docker-gpu.wexac.weizmann.ac.il`. `ssh docker-gpu.wexac.weizmann.ac.il`, build
  there with `singularity build --fakeroot`, then distribute. Ordinary login/compute
  nodes can only *run* a `.sif`, not build one. `scripts/build_container.sh` is
  therefore a **docker-gpu** script.
- **Running under LSF**: load the module, bind data, exec. CPU example (TARSUS is
  CPU-only, no `--nv`):
  ```
  bsub -q gsla-cpu -R "rusage[mem=32GB]" -oo %J.out -eo %J.err \
    'ml Singularity; singularity exec --bind /home/labs/pilpel:/home/labs/pilpel \
       tarsus.sif tarsus run -i <raw> --fasta <fa> -o <out>'
  ```
  Apptainer auto-mounts `$HOME`, `/tmp`, cwd; the shared `/home/labs/...` tree
  (inputs, references, output) is bound explicitly.
- **Distribution**: either `scp tarsus.sif login1:~/`, or push to the internal
  registry `ops:5000` and `singularity pull tarsus.sif docker://ops:5000/tarsus`.
- **"edocker" = LSF native-docker path** (`-app docker-cpu` / `nvidia-gpu`,
  `-env LSB_CONTAINER_IMAGE=ops:5000/...`). Portable route for a self-built,
  self-contained tool is Singularity `.sif`; the docker path is noted as an
  alternative but not the primary target.
- Apptainer cache lives at `~/.apptainer/cache/`; `singularity cache clean` on
  docker-gpu after building.

## Design

### Component 1 - `container/tarsus.def` (single parametrized recipe)

Apptainer definition, `Bootstrap: docker`, `From: rockylinux:9` (RHEL9-compatible,
matching the WEXAC host and the vendored RHEL9 Xvfb/tool binaries - this materially
lowers the glibc-compatibility risk vs a Debian/Ubuntu base).

- `%files` - stage the repo into `/opt/tarsus` (source tree, `pyproject.toml`,
  `uv.lock`, `Makefile`, `src/`, `tests/`, `README.md`), and stage a build context
  directory `/build-tools` that the wrapper populates (see Component 2).
- `%post`:
  1. `dnf install` the minimal base (Rocky 9): `curl unzip ca-certificates git
     libgomp` (plus anything JDK/.NET/the vendored Xvfb closure need at runtime;
     the Xvfb libs came from RHEL9 EasyBuild, so a RHEL9 base is the natural fit).
  2. Install `uv` (pinned).
  3. **Provision tools** into `/opt/tarsus/tools`:
     - if `/build-tools/tools/` was staged (internal mode) → copy it verbatim;
     - else (public mode) → run the auto-download subset of `make setup`, and copy
       the builder-supplied MSFragger ZIP + IonQuant JAR from `/build-tools/` into
       the FragPipe layout the Makefile expects.
     Fail loudly if any required tool is missing at the end.
  4. `uv sync --frozen` to build `/opt/tarsus/.venv` with the `tarsus` package + deps.
  5. Write the baked commit SHA to `/opt/tarsus/BUILD_COMMIT` (from `/build-tools/
     BUILD_COMMIT`, written by the wrapper).
- `%environment` - export `TARSUS_TOOLS_DIR=/opt/tarsus/tools`, put
  `/opt/tarsus/.venv/bin` on `PATH`, and set `TARSUS_BUILD_COMMIT` from the baked
  file. Tool-specific env (`JAVA_HOME`, `DOTNET_ROOT`, `LD_LIBRARY_PATH`) continues
  to be set by `env.py` at call time via `ToolEnvironment`, so `%environment` stays
  thin and there is one source of truth for tool paths.
- `%test` - assert every tool resolves (reuse the `env.py`/`make verify` checks) and
  run `pytest tests/unit tests/eval -q` inside the image. A build that cannot pass
  the eval is not a valid environment.
- `%runscript` - `exec tarsus "$@"` (so `apptainer run tarsus.sif run -i ... -o ...`
  works), `%labels`/`%help` record version, commit, tool versions, and the license
  notice.

### Component 2 - `scripts/build_container.sh` (build wrapper)

One entry point, **run on `docker-gpu.wexac.weizmann.ac.il`** (the only host with
build privileges); the only place public vs internal differ.

```
build_container.sh --internal [--out tarsus.sif] [--push ops:5000/tarsus]
build_container.sh --public --msfragger <MSFragger-4.4.1.zip> \
                            --ionquant <IonQuant-1.11.20.jar> [--out tarsus.sif]
```

Responsibilities:
- Assemble a clean `/build-tools` staging dir: in `--internal`, symlink/copy the
  repo's validated `tools/`; in `--public`, place the two supplied license-gated
  files and let `%post` download the rest. Refuse `--public` without both files.
- Write `BUILD_COMMIT` (`git rev-parse HEAD`, plus a `-dirty` marker if the tree is
  dirty) into the staging dir so it is baked into the image.
- Invoke `singularity build --fakeroot tarsus.sif container/tarsus.def` (fall back
  to `apptainer build --fakeroot`), passing the mode.
- Print the resulting `.sif` path, size, and the baked commit; guidance to
  `scp tarsus.sif login1:~/` (and, with `--push`, publish to the `ops:5000`
  registry for institute-wide `singularity pull`).

### Component 3 - provenance fallback (the one code touch)

`provenance.py::git_sha()` returns `None` when git is unavailable. Add: if git
resolution fails, fall back to `TARSUS_BUILD_COMMIT` / the `/opt/tarsus/BUILD_COMMIT`
file. Additive only - existing behaviour on a normal working copy is unchanged.
Covered by a unit test that monkeypatches the env var and asserts the fallback.

### Component 4 - repo publish-readiness

- **`.gitignore`**: add `*.sif`, `container/build/`, and any wrapper staging dir.
- **Untrack non-essential artifacts** (keep on disk, remove from the published
  tree): `docs/qc-history/subs/*.ipc` (~8 MB of historical QC evidence). Decide
  `data/test-mock/dev.mzML` (18 MB): keep only if a tracked test needs it, else move
  behind a fetch step. List each removal in the plan with its justification.
- **`LICENSE`**: add MIT for the TARSUS code. A `NOTICE`/README section makes clear
  the bundled third-party tools retain their own licenses and are not covered by MIT.
- **README**: add a "Container" section - build on `docker-gpu` (both modes),
  distribute (`scp` or `ops:5000`), and run on LSF today
  (`bsub -q gsla-cpu '... ml Singularity; singularity exec --bind /home/labs/pilpel:/home/labs/pilpel tarsus.sif tarsus run ...'`),
  plus the child-job caveat below.

### Known limitation - the deferred-execution boundary (documented, not solved)

Running the master inside the image still submits child `bsub` jobs whose tool
paths (`/opt/tarsus/tools/...`) exist only *inside* the container, so those child
jobs must themselves run under `ml Singularity; singularity exec ... tarsus.sif`
(with the same `--bind`). Wiring that (and/or a no-LSF local backend) is the
separate execution spec. This deliverable therefore validates the
image **as a reproducible environment** - tools resolve, unit + eval tests pass
inside it - and documents the LSF driving model rather than claiming a full
end-to-end cluster run.

## Risks

1. **glibc vs the vendored Xvfb/tool binaries.** The Xvfb closure was copied from
   this cluster's RHEL9 EasyBuild, so the `rockylinux:9` base is chosen precisely to
   match it (same glibc family as build+run host). Mitigation still stands: the
   `%test` stage exercises `env.py`'s Xvfb start; if any vendored lib is unsatisfied,
   add it in `%post` via `dnf`. Validate before declaring the image good.
2. **`uv sync --frozen` needs `uv.lock` current.** If the lock drifts from
   `pyproject.toml` the build fails fast - fix the lock, do not `--no-frozen`.
3. **Image size** (~4-5 GB with tools baked). Acceptable for HPC `.sif`; documented.
4. **Untracking tracked artifacts** changes the published history's working tree.
   Use `git rm --cached` (keep files on disk); never delete the source data.

## Acceptance criteria

- `scripts/build_container.sh --internal` (run on `docker-gpu.wexac.weizmann.ac.il`)
  produces a `.sif` whose `%test` passes: every tool resolves and
  `pytest tests/unit tests/eval` is green inside the image.
- On a WEXAC node, `ml Singularity; singularity run tarsus.sif --help` and
  `... run --help` work; `singularity inspect` shows the baked commit and tool
  versions.
- `scripts/build_container.sh --public` fails clearly without `--msfragger`/
  `--ionquant`, and succeeds when both are supplied.
- Inside the image, `tarsus` reports the baked commit via the provenance fallback
  (no git repo present).
- `LICENSE` (MIT) present; `docs/qc-history/subs/*.ipc` untracked; `.gitignore`
  ignores `*.sif`; README documents build + run + the child-job caveat.
- No change to step execution semantics; `git grep` shows orchestration.py untouched.

## Suggested build order

1. Provenance fallback + its unit test (smallest, unblocks in-image commit reporting).
2. `container/tarsus.def` skeleton + `build_container.sh --internal`; iterate until
   `%test` is green on the internal build (this is where risk 1 gets settled).
3. `--public` mode (staging + fail-loud on missing MSFragger/IonQuant).
4. Repo cleanup: `.gitignore`, `git rm --cached` the QC artifacts, `LICENSE`, README.
5. Final: build both modes, confirm acceptance criteria, document sizes/commit.
