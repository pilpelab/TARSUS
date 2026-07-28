# TARSUS Apptainer/Singularity Environment Image - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the full TARSUS tool + runtime + code environment as a reproducible Apptainer/Singularity `.sif`, and make the repo publish-ready.

**Architecture:** One parametrized Apptainer definition (`container/tarsus.def`) built by a wrapper (`scripts/build_container.sh`) that assembles a build context and runs `singularity build --fakeroot` on `docker-gpu.wexac.weizmann.ac.il`. Internal builds copy the validated `tools/` tree into the image; public builds download the redistributable tools and consume a builder-supplied MSFragger ZIP + IonQuant JAR. A small additive provenance fallback bakes the commit SHA so it survives with no git repo. Execution stays exactly as today (a `bsub` master runs `tarsus run` inside the image); wiring child jobs through the container is a separate spec.

**Tech Stack:** Apptainer/Singularity (build with `--fakeroot`), Rocky Linux 9 base, `uv` (Python env), `make setup` (tool provisioning), pytest.

## Global Constraints

- **Build host:** only `docker-gpu.wexac.weizmann.ac.il` can build (`singularity build --fakeroot`). Other WEXAC nodes only run `.sif`. All build/validate steps run there.
- **Base image:** `rockylinux:9` (matches the RHEL9 host and vendored RHEL9 Xvfb libs).
- **License-gated tools (public mode):** MSFragger 4.4.1 (ZIP) and IonQuant 1.11.20 (JAR) have no public URL - the builder supplies them; never embed/redistribute them. Exact pinned checksums: MSFragger `d5268024c10f29317a20c4b5f42a2ec142dc282c0e8fc733ca286ff76537644a`, IonQuant `c38e3cc75dfb82f0b991d49397a49b6e8b98879f804018171d23db0fb3bbb8e3`.
- **Tool env contract:** `env.py` reads `TARSUS_TOOLS_DIR` (set it to `/opt/tarsus/tools` in-image); do not hardcode tool paths elsewhere.
- **The image never contains `data/`.** `dev.mzML` (18 MB) is validation-only and is dropped from both image and published repo.
- **In-image tests:** `pytest tests/unit tests/eval` only (validation tests need LSF + real tools and are never run in-image).
- **License:** TARSUS code is MIT; bundled third-party tools keep their own licenses.
- **Frequent commits**, one per task minimum.

---

## File Structure

- `src/tarsus/provenance.py` (modify) - add build-commit fallback to `git_sha()`.
- `tests/unit/test_provenance.py` (modify) - test the fallback.
- `tests/validation/conftest.py` (modify) - skip cleanly when `dev.mzML` absent.
- `.gitignore` (modify) - ignore `*.sif`, `container/build/`, `data/test-mock/dev.mzML`.
- `data/README.md` (modify) - document the removed `dev.mzML` fetch.
- `LICENSE` (create) - MIT.
- `README.md` (modify) - add "Container" section.
- `container/tarsus.def` (create) - the Apptainer recipe.
- `scripts/build_container.sh` (create) - the build wrapper (docker-gpu).

---

## Task 1: Provenance build-commit fallback

Bake the commit into the image so `tarsus` reports it with no git repo present.

**Files:**
- Modify: `src/tarsus/provenance.py` (function `git_sha`, around line 68-69)
- Test: `tests/unit/test_provenance.py`

**Interfaces:**
- Consumes: existing `_git`, `repo_root` in `provenance.py`.
- Produces: `git_sha(repo: Path | None = None) -> str | None` - unchanged signature; now falls back to `TARSUS_BUILD_COMMIT` env var, then a `BUILD_COMMIT` file at `repo_root()`, when git resolution returns `None`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_provenance.py`:

```python
def test_git_sha_falls_back_to_env(monkeypatch, tmp_path):
    """With no git repo, git_sha() uses TARSUS_BUILD_COMMIT (the baked commit)."""
    from tarsus import provenance
    # tmp_path is not a git repo -> _git returns None
    monkeypatch.setenv("TARSUS_BUILD_COMMIT", "abc1234deadbeef")
    assert provenance.git_sha(repo=tmp_path) == "abc1234deadbeef"


def test_git_sha_falls_back_to_build_commit_file(monkeypatch, tmp_path):
    """With no git and no env var, git_sha() reads repo_root()/BUILD_COMMIT."""
    from tarsus import provenance
    monkeypatch.delenv("TARSUS_BUILD_COMMIT", raising=False)
    monkeypatch.setattr(provenance, "repo_root", lambda: tmp_path)
    (tmp_path / "BUILD_COMMIT").write_text("feedface99\n")
    assert provenance.git_sha(repo=tmp_path) == "feedface99"


def test_git_sha_none_when_no_source(monkeypatch, tmp_path):
    """No git, no env, no file -> None (unchanged behaviour)."""
    from tarsus import provenance
    monkeypatch.delenv("TARSUS_BUILD_COMMIT", raising=False)
    monkeypatch.setattr(provenance, "repo_root", lambda: tmp_path)
    assert provenance.git_sha(repo=tmp_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_provenance.py::test_git_sha_falls_back_to_env -v`
Expected: FAIL (git_sha returns None, not the env value).

- [ ] **Step 3: Implement the fallback**

In `src/tarsus/provenance.py`, add `import os` to the imports (line 23-26 block) and replace `git_sha`:

```python
def git_sha(repo: Path | None = None) -> str | None:
    """Commit that produced this code.

    In a working tree this is ``git rev-parse HEAD``. In a container there is no
    git repo, so fall back to the commit baked at build time: the
    ``TARSUS_BUILD_COMMIT`` env var (set by the image's ``%environment``), then a
    ``BUILD_COMMIT`` file written next to the package. Returns ``None`` only when
    none of the three is available.
    """
    sha = _git("rev-parse", "HEAD", repo=repo or repo_root())
    if sha:
        return sha
    env = os.environ.get("TARSUS_BUILD_COMMIT")
    if env:
        return env.strip() or None
    try:
        text = (repo_root() / "BUILD_COMMIT").read_text().strip()
    except OSError:
        return None
    return text or None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/unit/test_provenance.py -v`
Expected: PASS (all, including the three new tests).

- [ ] **Step 5: Commit**

```bash
git add src/tarsus/provenance.py tests/unit/test_provenance.py
git commit -m "feat(provenance): fall back to baked commit when git is absent

In a container there is no git repo; git_sha() now falls back to
TARSUS_BUILD_COMMIT / a BUILD_COMMIT file so tarsus still reports the commit
that produced the image. Additive - working-tree behaviour is unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Repo publish-readiness

Untrack non-essential artifacts, add MIT LICENSE, keep validation tests skippable without `dev.mzML`.

**Files:**
- Modify: `tests/validation/conftest.py` (the `mock_data` fixture, ~line 51-56)
- Modify: `.gitignore`
- Modify: `data/README.md`
- Create: `LICENSE`
- Untrack: `data/test-mock/dev.mzML`, `docs/qc-history/subs/*.ipc` (10 files)

- [ ] **Step 1: Make the validation fixture skip when `dev.mzML` is absent**

In `tests/validation/conftest.py`, replace the `mock_data` fixture body:

```python
@pytest.fixture(scope="session")
def mock_data() -> dict:
    """Paths to mock test data (50 spectra, fast).

    dev.mzML is not published (18 MB, validation-only); skip if it is absent.
    """
    mzml = MOCK_DATA_DIR / "dev.mzML"
    if not mzml.exists():
        pytest.skip(f"mock mzML not present at {mzml} (see data/README.md)")
    return {
        "fasta": DATA_DIR / "protein.fasta",
        "mzml": mzml,
    }
```

- [ ] **Step 2: Verify the skip works even with the file still on disk**

The file is still present now, so the fixture must NOT skip yet. Confirm collection is clean:

Run: `.venv/bin/python -m pytest tests/validation --collect-only -q 2>&1 | tail -3`
Expected: collects without error (no import/collection failure).

- [ ] **Step 3: Untrack the non-essential artifacts (keep on disk)**

```bash
git rm --cached data/test-mock/dev.mzML docs/qc-history/subs/*.ipc
```

Expected: 11 files staged for deletion from the index; still present on disk (`ls data/test-mock/dev.mzML` succeeds).

- [ ] **Step 4: Ignore them and container build outputs**

Append to `.gitignore` (under a new heading):

```
# Container build artifacts
*.sif
container/build/

# Validation-only mock spectra (18 MB, not published; fetch per data/README.md)
data/test-mock/dev.mzML

# Historical QC subs artifacts (evidence, not shipped)
docs/qc-history/subs/*.ipc
```

- [ ] **Step 5: Document the removed fixture in `data/README.md`**

Append:

```markdown

## Validation mock spectra (`test-mock/dev.mzML`)

`dev.mzML` (50 spectra, ~18 MB) is used only by `tests/validation` and is **not**
tracked in git or shipped in the container. The validation suite `pytest.skip`s
cleanly when it is absent. To run validation locally, place a `dev.mzML` at
`data/test-mock/dev.mzML` (any small mzML with a handful of MS2 spectra works).
```

- [ ] **Step 6: Add the MIT LICENSE**

Create `LICENSE` (fill the year and holder as the institute prefers; default shown):

```
MIT License

Copyright (c) 2026 Weizmann Institute of Science (Pilpel Lab)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 7: Verify unit + eval still green (untracking touched nothing they need)**

Run: `.venv/bin/python -m pytest tests/unit tests/eval -q 2>&1 | tail -3`
Expected: PASS (all green - the untracked files are not used by unit/eval).

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore(repo): publish-readiness - MIT LICENSE, drop 18MB+8MB artifacts

- Add MIT LICENSE (bundled tools keep their own licenses).
- Untrack data/test-mock/dev.mzML (validation-only) and docs/qc-history/subs/*.ipc;
  gitignore them. Validation conftest now pytest.skip's when dev.mzML is absent.
- Document the mock-spectra fetch in data/README.md.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `container/tarsus.def` (Apptainer recipe)

The recipe: base, tool provisioning (internal copy vs public download+BYO), Python env, baked commit, in-image tests, runscript.

**Files:**
- Create: `container/tarsus.def`

**Interfaces:**
- Consumes: a build context the wrapper assembles at `container/build/context/` (Task 4): `opt-tarsus/` (repo minus `data/`, with or without a full `tools/` tree) and `BUILD_COMMIT`.
- Produces: an image whose `%post` leaves tools under `/opt/tarsus/tools`, the venv at `/opt/tarsus/.venv`, and `/opt/tarsus/BUILD_COMMIT`; `%runscript` = `tarsus`.

- [ ] **Step 1: Write the definition file**

Create `container/tarsus.def`:

```
Bootstrap: docker
From: rockylinux:9

# Build context is assembled by scripts/build_container.sh at
# container/build/context/. Internal builds put the full validated tools/ tree
# under opt-tarsus/tools/; public builds put only the redistributable tools plus
# the builder-supplied MSFragger ZIP / IonQuant JAR under
# opt-tarsus/tools/_downloads/, and %post downloads the rest via `make setup`.

%files
    container/build/context/opt-tarsus /opt/tarsus
    container/build/context/BUILD_COMMIT /opt/tarsus/BUILD_COMMIT

%post
    set -eux
    dnf -y install curl unzip tar gzip which procps-ng ca-certificates git \
        libgomp gcc gcc-c++ make
    dnf clean all

    # uv (pinned installer dir on PATH); uv fetches its own Python 3.11.
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

    cd /opt/tarsus
    export TARSUS_TOOLS_DIR=/opt/tarsus/tools

    # Provision tools. Internal mode: FragPipe+MSFragger already staged -> nothing
    # to download. Public mode: fetch redistributable tools and consume the
    # builder-supplied license-gated files staged under tools/_downloads/.
    if [ -f tools/fragpipe-24.0/tools/MSFragger-4.4.1/MSFragger-4.4.1.jar ]; then
        echo "internal mode: tools staged, verifying"
        make verify
    else
        echo "public mode: downloading redistributable tools + consuming BYO MSFragger/IonQuant"
        make setup \
            MF_SOURCE_ZIP=/opt/tarsus/tools/_downloads/MSFragger-4.4.1.zip \
            IQ_SOURCE_JAR=/opt/tarsus/tools/_downloads/IonQuant-1.11.20.jar
    fi

    # Python environment (frozen lock -> reproducible).
    uv sync --frozen

    # Sanity: the console script exists.
    test -x /opt/tarsus/.venv/bin/tarsus

%environment
    export TARSUS_TOOLS_DIR=/opt/tarsus/tools
    export PATH=/opt/tarsus/.venv/bin:$PATH
    export TARSUS_BUILD_COMMIT="$(cat /opt/tarsus/BUILD_COMMIT 2>/dev/null || echo unknown)"

%test
    set -eux
    export TARSUS_TOOLS_DIR=/opt/tarsus/tools
    cd /opt/tarsus
    # Every external tool must resolve.
    .venv/bin/python -c "import sys; from tarsus.env import ToolEnvironment; \
v = ToolEnvironment.from_env().verify(); \
[print(k, ok, m) for k,(ok,m) in v.items()]; \
sys.exit(0 if all(ok for ok,_ in v.values()) else 1)"
    # Fast, tool-free correctness gates.
    .venv/bin/python -m pytest tests/unit tests/eval -q

%runscript
    exec tarsus "$@"

%labels
    org.tarsus.name TARSUS_BC
    org.tarsus.version 0.1.0

%help
    TARSUS substitution pipeline - self-contained environment image.
    Run:  singularity run tarsus.sif run -i <raw> --fasta <fasta> -o <outdir>
    Tools live at /opt/tarsus/tools (TARSUS_TOOLS_DIR); commit is in /opt/tarsus/BUILD_COMMIT.
    Build only on docker-gpu.wexac.weizmann.ac.il (see scripts/build_container.sh).
```

- [ ] **Step 2: Sanity-check the file exists and is non-empty**

Run: `test -s container/tarsus.def && head -3 container/tarsus.def`
Expected: prints the `Bootstrap: docker` header (full build is Task 5, on docker-gpu).

- [ ] **Step 3: Commit**

```bash
git add container/tarsus.def
git commit -m "feat(container): Apptainer recipe (rockylinux:9, internal+public tools)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `scripts/build_container.sh` (build wrapper)

Assembles the build context and runs the fakeroot build; the only place public vs internal differ.

**Files:**
- Create: `scripts/build_container.sh` (executable)

**Interfaces:**
- Consumes: `container/tarsus.def`; the repo working tree; `--msfragger`/`--ionquant` files in public mode.
- Produces: `container/build/context/{opt-tarsus/,BUILD_COMMIT}` and the output `.sif`.

- [ ] **Step 1: Write the wrapper**

Create `scripts/build_container.sh`:

```bash
#!/usr/bin/env bash
# Build the TARSUS Apptainer image. RUN ON docker-gpu.wexac.weizmann.ac.il only
# (the sole host with `singularity build --fakeroot` privileges).
#
#   build_container.sh --internal [--out tarsus.sif]
#   build_container.sh --public --msfragger <MSFragger-4.4.1.zip> \
#                               --ionquant <IonQuant-1.11.20.jar> [--out tarsus.sif]
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
MODE="" OUT="$REPO/tarsus.sif" MSF="" IONQ=""

usage() { sed -n '2,10p' "$0"; exit "${1:-1}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --internal) MODE=internal ;;
    --public)   MODE=public ;;
    --msfragger) MSF="$2"; shift ;;
    --ionquant)  IONQ="$2"; shift ;;
    --out)       OUT="$2"; shift ;;
    -h|--help)   usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
  shift
done
[ -n "$MODE" ] || { echo "error: pass --internal or --public" >&2; usage 1; }

BUILDER="$(command -v singularity || command -v apptainer || true)"
[ -n "$BUILDER" ] || { echo "error: no singularity/apptainer on PATH (run on docker-gpu; 'ml Singularity')" >&2; exit 1; }

CTX="$REPO/container/build/context"
rm -rf "$REPO/container/build"
mkdir -p "$CTX/opt-tarsus"

echo ">> assembling build context ($MODE)"
# Repo minus heavy/irrelevant paths. tools/ handled per-mode below.
tar -C "$REPO" \
    --exclude=./.git --exclude=./.venv --exclude=./data --exclude=./output \
    --exclude=./tools --exclude=./container/build --exclude='*.sif' \
    -cf - . | tar -C "$CTX/opt-tarsus" -xf -

# Vendored, redistributable, always-needed tool bits (small): Xvfb + PDV + README.
mkdir -p "$CTX/opt-tarsus/tools/_downloads"
cp -a "$REPO/tools/README.md" "$CTX/opt-tarsus/tools/" 2>/dev/null || true
cp -a "$REPO/tools/xvfb" "$CTX/opt-tarsus/tools/" 2>/dev/null || true
cp -a "$REPO/tools/PDV-2.1.2" "$CTX/opt-tarsus/tools/" 2>/dev/null || true

if [ "$MODE" = internal ]; then
  echo ">> internal: copying validated tools/ tree (~3.8 GB)"
  cp -a "$REPO/tools/." "$CTX/opt-tarsus/tools/"
else
  [ -f "$MSF" ]  || { echo "error: --public needs --msfragger <MSFragger-4.4.1.zip>" >&2; exit 1; }
  [ -f "$IONQ" ] || { echo "error: --public needs --ionquant <IonQuant-1.11.20.jar>" >&2; exit 1; }
  echo ">> public: staging builder-supplied MSFragger/IonQuant"
  cp -a "$MSF"  "$CTX/opt-tarsus/tools/_downloads/MSFragger-4.4.1.zip"
  cp -a "$IONQ" "$CTX/opt-tarsus/tools/_downloads/IonQuant-1.11.20.jar"
fi

# Baked commit (mark dirty tree).
SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
git -C "$REPO" diff --quiet 2>/dev/null || SHA="${SHA}-dirty"
printf '%s\n' "$SHA" > "$CTX/BUILD_COMMIT"
echo ">> baked commit: $SHA"

echo ">> building $OUT"
cd "$REPO"
"$BUILDER" build --fakeroot "$OUT" container/tarsus.def

echo ">> done: $OUT ($(du -h "$OUT" | cut -f1)), commit $SHA"
echo "   distribute: cp '$OUT' /home/labs/pilpel/<shared>/   (run: ml Singularity; singularity exec ... )"
```

- [ ] **Step 2: Make it executable and lint it**

```bash
chmod +x scripts/build_container.sh
bash -n scripts/build_container.sh   # syntax check
```
Expected: no output (syntax OK).

- [ ] **Step 3: Verify public-mode argument guards (no build triggered)**

Run: `scripts/build_container.sh --public 2>&1 | tail -2`
Expected: prints `error: --public needs --msfragger ...` (exits non-zero before any build).

Run: `scripts/build_container.sh 2>&1 | tail -2`
Expected: prints `error: pass --internal or --public`.

- [ ] **Step 4: Commit**

```bash
git add scripts/build_container.sh
git commit -m "feat(container): build_container.sh wrapper (internal/public, fakeroot)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Build + validate on docker-gpu, and document (acceptance)

The only task that runs on `docker-gpu.wexac.weizmann.ac.il`. Produces a validated `.sif` and the README section.

**Files:**
- Modify: `README.md` (add "Container" section)

- [ ] **Step 1: Build the internal image on docker-gpu**

On `docker-gpu.wexac.weizmann.ac.il` (e.g. `! ssh docker-gpu.wexac.weizmann.ac.il`), from the repo root:

Run: `ml Singularity 2>/dev/null; scripts/build_container.sh --internal --out /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif`
Expected: build completes; final line prints the `.sif` path, size (~4-5 GB), and baked commit. `%test` must pass inside the build (every tool `ok`, then `pytest tests/unit tests/eval` green). If the build fails in `%test` on an Xvfb/lib error, add the missing `.so` package to the `%post` `dnf install` line (risk 1) and rebuild.

- [ ] **Step 2: Verify the built image runs and reports the baked commit**

```bash
ml Singularity
singularity inspect /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif | grep -i version
singularity run /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif --help
singularity exec /home/labs/pilpel/barc/TARSUS_BC/tarsus.sif \
  python -c "from tarsus.provenance import git_sha; print('commit', git_sha())"
```
Expected: `--help` lists the `tarsus` commands; the commit line prints the baked SHA (not "unknown"), confirming the provenance fallback (no git repo in-image).

- [ ] **Step 3: Verify a public-mode build guards and builds**

```bash
# guard (no files) - must fail fast:
scripts/build_container.sh --public ; echo "exit=$?"
# real public build (supply the license-gated files you obtained under the nesvilab license):
scripts/build_container.sh --public \
  --msfragger /path/to/MSFragger-4.4.1.zip \
  --ionquant  /path/to/IonQuant-1.11.20.jar \
  --out /home/labs/pilpel/barc/TARSUS_BC/tarsus-public.sif
```
Expected: the guard prints the `--msfragger` error and exits non-zero; the real build completes with `%test` green.

- [ ] **Step 4: Add the README "Container" section**

Append to `README.md`:

````markdown
## Container (Apptainer/Singularity)

TARSUS ships as a self-contained Apptainer image bundling all tools + runtimes +
code. **Build only on `docker-gpu.wexac.weizmann.ac.il`** (the sole host with
`--fakeroot` privileges); every other WEXAC node can run the `.sif`.

Build (internal - bakes the already-validated `tools/` tree):

```bash
ssh docker-gpu.wexac.weizmann.ac.il
cd /path/to/TARSUS_BC
ml Singularity
scripts/build_container.sh --internal --out tarsus.sif
```

Build (public/portable - you supply MSFragger + IonQuant under the nesvilab
academic license; the rest download automatically):

```bash
scripts/build_container.sh --public \
  --msfragger MSFragger-4.4.1.zip --ionquant IonQuant-1.11.20.jar --out tarsus.sif
```

Distribute: copy `tarsus.sif` to a shared `/home/labs/...` path (run it in place),
or `scp tarsus.sif login1:~/`, or push to the internal `ops:5000` registry.

Run on LSF today (CPU; bind the shared tree that holds inputs/outputs/references):

```bash
bsub -q gsla-cpu -R "rusage[mem=32GB]" -oo %J.out -eo %J.err \
  'ml Singularity; singularity exec --bind /home/labs/pilpel:/home/labs/pilpel \
     /home/labs/pilpel/<shared>/tarsus.sif tarsus run -i <raw> --fasta <fasta> -o <outdir>'
```

**Known limitation (deferred):** the master submits child `bsub` jobs whose tool
paths exist only inside the image, so those child jobs must also run via
`ml Singularity; singularity exec ... tarsus.sif`. Wiring that (or a no-LSF local
backend) is a separate spec; this image is validated as a reproducible environment
(tools resolve; `pytest tests/unit tests/eval` green inside it).
````

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs(container): README build/run/distribute section + child-job caveat

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review notes (author)

- **Spec coverage:** Component 1 def → Task 3; Component 2 wrapper → Task 4; provenance → Task 1; repo cleanup (LICENSE, untrack, gitignore, data/README, validation-skip, no `data/` in image) → Task 2 + wrapper `--exclude`; WEXAC build-host / `ml Singularity` / bind / distribution → Tasks 4-5 + README; acceptance criteria → Task 5. All spec sections map to a task.
- **`data/` never in image:** enforced by the wrapper `tar --exclude=./data` (Task 4, Step 1).
- **Deferred execution:** documented in README (Task 5) and not implemented - orchestration.py is untouched (verify: `git grep` shows no change).
- **`--push ops:5000` intentionally deferred:** the spec listed it as *optional*; distribution default is a shared-filesystem `.sif` copy (Task 5 README). Pushing a `.sif` to `ops:5000` needs registry auth (ORAS/docker) and buys little over the shared-fs copy, so it is left as a documented manual step rather than a wrapper flag. Add it later if institute demand appears.
- **Minor image bloat accepted:** the context `tar` excludes `data/`, `.git`, `.venv`, `tools/`, `output/`, `*.sif`; the ~8 MB `docs/qc-history/subs/*.ipc` (untracked but on disk) may still be copied. Negligible in a ~4-5 GB image; not worth a special exclude.
```
