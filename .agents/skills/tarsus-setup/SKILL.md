---
name: tarsus-setup
description: Setting up TARSUS from a fresh clone and running it on an LSF cluster. Use when asked to set up or install TARSUS, run it on Thermo .raw files, or check whether a run finished.
---

# TARSUS setup

Takes a fresh clone to a passing tool check and a first pipeline run. TARSUS runs on LSF: every step is a `bsub` job, and the compute nodes read the repo, its `.venv` and `tools/` from shared storage.

Work from the repo root. The human owns every install and every license: before each command marked **ask**, say what it does and wait for a yes.

## Stop rules

Stop, tell the human, and wait when:

- **No `bsub`.** Say: "TARSUS needs an LSF cluster today: it submits every step with `bsub`, and this machine has no `bsub`. Setup stops here. Run it from a login node of an LSF cluster whose compute nodes share storage with it."
- **A checksum fails** (`sha256sum -c` prints `FAILED`). The SHA256 values in the `Makefile` are pinned: they stay exactly as written. Report the file name; the human fetches the right file.
- **A preflight row fails.** Report the command and its output.
- **A step needs a password, a login or a license click.** That step is the human's.

## 1. Preflight

Run each row in order; each must meet its pass condition before the next.

| Check | Command | Pass condition |
|---|---|---|
| CPU | `uname -m` | `x86_64` |
| LSF | `command -v bsub` | prints a path. Empty output: the no-`bsub` stop rule |
| Queue | `bqueues -u "$USER"` | the human picks one `Open:Active` CPU queue. It is `<queue>` below |
| Shared storage | `bsub -K -q <queue> -J tarsus-fs-check -o /dev/null test -f "$PWD/pyproject.toml"` | ends with `<<Job is finished>>` and exit code 0 |
| uv | `uv --version` | prints a version |
| Python | `uv python find '>=3.11'` | prints a path. No path: `uv sync` will download Python 3.11, so name that when asking in step 3 |

Done when every row passes.

## 2. MSFragger and IonQuant (human only)

Each lab accepts the academic license for MSFragger and IonQuant itself, so the repo does not ship them. Ask the human to:

1. Accept the academic license at https://msfragger.nesvilab.org.
2. Download exactly MSFragger 4.4.1 (zip) and IonQuant 1.11.20 (jar).
3. Run `mkdir -p tools/_downloads` and put the files at `tools/_downloads/MSFragger-4.4.1.zip` and `tools/_downloads/IonQuant-1.11.20.jar`.

Done when `ls tools/_downloads/MSFragger-4.4.1.zip tools/_downloads/IonQuant-1.11.20.jar` lists both.

## 3. Install

1. **ask** `uv sync --frozen`: the Python dependencies into `.venv`, exactly as `uv.lock` pins them. `--frozen` keeps `uv.lock` unchanged, and `tarsus run` refuses to start while a tracked file is modified.
2. **ask** `make setup`: downloads the pinned tools into `tools/`, checks each SHA256, and unpacks MSFragger and IonQuant from `tools/_downloads/`. Run it on the login node: compute nodes often have no internet. Done when it ends with `All tools installed.`

## 4. Verify

`make test-tools`. Done when no line says `MISSING` or `FAILED` and the output ends like this (lines with `...` print the tool's own version text):

```
  JDK: openjdk version "21.0.11" ...
  .NET: ...
  FragPipe: ...
  MSFragger: OK (4.4.1)
  IonQuant: OK (1.11.20)
  PepQuery: ...
  PepQuery: OK (JAR loads)
  PDV: OK (JAR verified, 2.1.2, SHA256 matches)
  ThermoRawFileParser: OK
  Xvfb: OK (self-contained, display ready)

All tool checks complete.
```

`make test-pdv-full`. Done when it prints `  PDV: OK (N figures generated)` with N above 0.

## 5. First run

Ask the human for a proteome FASTA, one or more Thermo `.raw` files, and an output directory. `output/<name>` inside the repo works: it is git-ignored.

Check whether compute nodes reach the MSBooster model server:

```bash
bsub -K -q <queue> -J tarsus-koina-check -o /dev/null curl -s -o /dev/null --max-time 20 https://koina.wilhelmlab.org
```

Exit code 0: they do, keep the default. Anything else: add `--msbooster-models dia-nn`, which uses the local DIA-NN models offline.

```bash
uv run tarsus run --fasta <proteome.fasta> -i <run.raw> -o <outdir> --queue <queue>
```

Repeat `-i` for each `.raw` file. `--queue` defaults to `gsla-cpu`, a Weizmann queue, so always pass it. `uv run tarsus run --help` lists the other options (`--cds`, `--localize-tol`, `--base-rescore-tol`, `--memory`); add one only when the human asks for it.

Done when it prints `Submitted master job <ID> to queue '<queue>'.`

## 6. Monitor

A run takes hours. Check with:

- `bjobs`: the master job `tarsus_master` and the step jobs it submits.
- `tail -n 20 <outdir>/master.log`: one timestamped line per step event.

Done when `grep 'DONE: Pipeline complete.' <outdir>/master.log` prints the line. LSF then appends its job summary to the same file, ending in `Successfully completed.` If `tarsus_master` leaves `bjobs` without the DONE line, show the human the last 40 lines of `master.log`.

## 7. Result

- `<outdir>/11_localized/subs_localized.csv` is the result: one row per substitution spectrum match, with `origin` and `destination` amino acids, `Gene` and `misProt`.
- Show the human `<outdir>/12_visualize/protein_burden.png` first: substitutions per protein. The other Step 12 figures sit beside it.
