# External Tools

This directory contains third-party tools downloaded by `make setup` in the parent Makefile.

## Version Table

| Tool | Version | Source | License |
|------|---------|--------|---------|
| FragPipe | 24.0 | [Nesvilab/FragPipe](https://github.com/Nesvilab/FragPipe) | Academic free |
| MSFragger | 4.4.1 | https://msfragger.nesvilab.org | Academic free |
| IonQuant | 1.11.20 | https://ionquant.nesvilab.org | Academic free |
| Philosopher | 5.1.3-RC9 | (bundled with FragPipe) | Academic free |
| IonQuant | 1.11.18 | (bundled with FragPipe) | Academic free |
| Percolator | 3.7.1 | (bundled with FragPipe) | Academic free |
| MSBooster | 1.4.14 | (bundled with FragPipe) | Academic free |
| PepQuery | 2.0.2 | [pepquery.org](http://pepquery.org) | Academic free |
| PDV | 2.1.2 (JAR committed) + 2.2.3 (`lib/`, `resources/`) | [wenbostar/PDV](https://github.com/wenbostar/PDV) | GPL-3.0 |
| MSConvert | (ProteoWizard) | [proteowizard.sourceforge.io](http://proteowizard.sourceforge.io) | Apache 2.0 |

## MSFragger and IonQuant: each lab downloads them

MSFragger and IonQuant have an academic license, so they are not in the repo and `make setup` cannot download them. Accept the license, download these exact versions, and put them in `tools/_downloads/` with these exact names before `make setup`:

| File | Download | Pinned SHA256 (Makefile) |
|------|----------|--------------------------|
| `tools/_downloads/MSFragger-4.4.1.zip` | https://msfragger.nesvilab.org | `MF_SHA256` |
| `tools/_downloads/IonQuant-1.11.20.jar` | https://ionquant.nesvilab.org | `IQ_SHA256` |

```bash
mkdir -p tools/_downloads
# copy the two files in, then:
make setup
```

Files kept elsewhere work too: `make setup MF_SOURCE_ZIP=/path/to/MSFragger-4.4.1.zip IQ_SOURCE_JAR=/path/to/IonQuant-1.11.20.jar`. `make clean` keeps these two files.

## PDV layout

The pipeline runs PDV 2.1.2 (`src/tarsus/env.py` loads `tools/PDV-2.1.2/PDV-2.1.2.jar`). 2.1.2 has no public release, so its JAR is committed in the repo with a `NOTICE` (GPL-3.0, upstream source). The JAR needs `lib/` and `resources/` beside it; `make pdv` (part of `make setup`) downloads the public PDV 2.2.3 release, checks its SHA256, extracts it to `tools/PDV-2.2.3/` and links them in:

```
tools/PDV-2.1.2/
  PDV-2.1.2.jar                      committed, SHA256 checked by make pdv
  NOTICE                             committed
  lib -> ../PDV-2.2.3/lib            symlink made by make pdv
  resources -> ../PDV-2.2.3/resources
tools/PDV-2.2.3/                     downloaded by make pdv, not tracked
```

Verify with `make test-pdv-full`: it prints `PDV: OK (N figures generated)`.

## Runtimes (also bundled)

| Runtime | Version | Source |
|---------|---------|--------|
| JDK 21 | jdk-21.0.11+10 | [Eclipse Temurin](https://adoptium.net) |
| .NET 8 | 8.0.28 | [dotnet.microsoft.com](https://dotnet.microsoft.com) |

## Xvfb (self-contained virtual X11 display)

PDV requires a real X11 display even in "CLI mode" - its `PDVCLIMainClass`
constructor unconditionally creates a `JFrame`, and Java's headless mode
categorically forbids any `Window`/`Frame` construction (there is no flag to
bypass this - `-Djava.awt.headless=true` still throws `HeadlessException`).
So a real (virtual) X server is required to run PDV unattended on LSF.

**This is not part of the original reference pipeline** (`TARSUS_elizabev/aggregate_query.sh`
just calls `java -jar PDV....jar` directly, no display handling at all - the
original author must have run it interactively with a real/forwarded X11
session). We added Xvfb ourselves (D-020) to make Step 6 work inside a fully
unattended LSF batch job.

**Why it's vendored here instead of using the cluster's `module load Xvfb`:**
self-containment (D-004) - the pipeline should not depend on any particular
cluster's module system. `tools/xvfb/{bin,lib}/` bundles the `Xvfb` binary
plus its full closure of non-universal shared libraries (everything except
the baseline `libc`/`libm`/`libdl`/`libpthread`/`ld-linux`, which every glibc
Linux system already provides). At runtime we only set our own
`LD_LIBRARY_PATH` pointing at `tools/xvfb/lib/` - no `module load`, no Lmod,
no cluster-specific env vars.

**Options considered and rejected (see `.memory/decisions.md` D-037 for full
write-up):**
- `-Djava.awt.headless=true` - doesn't work, PDV still throws `HeadlessException`.
- `conda-forge`'s `xorg-x11-server-xvfb` packages (both the plain and the
  portable "cos7" baseline variant) - both are missing `libXfont2.so.2`,
  which conda-forge does not publish as a standalone package at all (a known
  gap in that feedstock). Dead end.

**Provenance of the bundled files:**
- `bin/Xvfb` + most of `lib/*.so*` - copied from this cluster's EasyBuild
  install (`Xvfb/21.1.9-GCCcore-13.2.0`, built against
  `X11/20231019-GCCcore-13.2.0`, `freetype/2.13.2`, `libpng/1.6.40`,
  `pixman/0.42.2` - all from the same GCCcore 13.2.0 toolchain, so they're
  mutually ABI-consistent).
- `lib/libbz2.so.1.0` - the one library missing from that EasyBuild build.
  Sourced separately from conda-forge's standalone `bzip2` package (public
  URL, pinned SHA256, `make xvfb` fetches it automatically). It only links
  against `libc`, so mixing it with the EasyBuild-toolchain libs is safe.
- Checksums for the full bundle are in `tools/xvfb/CHECKSUMS.sha256`
  (verified by `make xvfb` / `make test-xvfb`).

**Known limitation:** the EasyBuild-sourced files were extracted from *this*
cluster and are committed to the repo (not re-downloaded by `make setup`).
A lab deploying on a different cluster without an equivalent Xvfb build
would need to redo this extraction once (copy the `Xvfb` binary + its `ldd`
closure, minus the universal baseline libs, into `tools/xvfb/{bin,lib}/`) -
or simply export `$DISPLAY` from their own X11/VNC session, which
`XvfbDisplay` (see `src/tarsus/env.py`) honors automatically and skips the
bundled Xvfb entirely.

## Policy

- Tool binaries are gitignored, except the committed `tools/xvfb/` bundle and `tools/PDV-2.1.2/PDV-2.1.2.jar` (no public download for either)
- Run `make setup` from the repo root to download and verify all tools
- Each download is checksum-verified (SHA256)
- Versions are pinned explicitly - updates are intentional and recorded in git
