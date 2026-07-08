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
| PDV | 2.2.3 | [wenbostar/PDV](https://github.com/wenbostar/PDV) | Apache 2.0 |
| MSConvert | (ProteoWizard) | [proteowizard.sourceforge.io](http://proteowizard.sourceforge.io) | Apache 2.0 |

## Runtimes (also bundled)

| Runtime | Version | Source |
|---------|---------|--------|
| JDK 21 | jdk-21.0.11+10 | [Eclipse Temurin](https://adoptium.net) |
| .NET 8 | 8.0.28 | [dotnet.microsoft.com](https://dotnet.microsoft.com) |

## Xvfb (self-contained virtual X11 display)

PDV requires a real X11 display even in "CLI mode" — its `PDVCLIMainClass`
constructor unconditionally creates a `JFrame`, and Java's headless mode
categorically forbids any `Window`/`Frame` construction (there is no flag to
bypass this — `-Djava.awt.headless=true` still throws `HeadlessException`).
So a real (virtual) X server is required to run PDV unattended on LSF.

**This is not part of the original reference pipeline** (`TARSUS_elizabev/aggregate_query.sh`
just calls `java -jar PDV....jar` directly, no display handling at all — the
original author must have run it interactively with a real/forwarded X11
session). We added Xvfb ourselves (D-020) to make Step 6 work inside a fully
unattended LSF batch job.

**Why it's vendored here instead of using the cluster's `module load Xvfb`:**
self-containment (D-004) — the pipeline should not depend on any particular
cluster's module system. `tools/xvfb/{bin,lib}/` bundles the `Xvfb` binary
plus its full closure of non-universal shared libraries (everything except
the baseline `libc`/`libm`/`libdl`/`libpthread`/`ld-linux`, which every glibc
Linux system already provides). At runtime we only set our own
`LD_LIBRARY_PATH` pointing at `tools/xvfb/lib/` — no `module load`, no Lmod,
no cluster-specific env vars.

**Options considered and rejected (see `.memory/decisions.md` D-037 for full
write-up):**
- `-Djava.awt.headless=true` — doesn't work, PDV still throws `HeadlessException`.
- `conda-forge`'s `xorg-x11-server-xvfb` packages (both the plain and the
  portable "cos7" baseline variant) — both are missing `libXfont2.so.2`,
  which conda-forge does not publish as a standalone package at all (a known
  gap in that feedstock). Dead end.

**Provenance of the bundled files:**
- `bin/Xvfb` + most of `lib/*.so*` — copied from this cluster's EasyBuild
  install (`Xvfb/21.1.9-GCCcore-13.2.0`, built against
  `X11/20231019-GCCcore-13.2.0`, `freetype/2.13.2`, `libpng/1.6.40`,
  `pixman/0.42.2` — all from the same GCCcore 13.2.0 toolchain, so they're
  mutually ABI-consistent).
- `lib/libbz2.so.1.0` — the one library missing from that EasyBuild build.
  Sourced separately from conda-forge's standalone `bzip2` package (public
  URL, pinned SHA256, `make xvfb` fetches it automatically). It only links
  against `libc`, so mixing it with the EasyBuild-toolchain libs is safe.
- Checksums for the full bundle are in `tools/xvfb/CHECKSUMS.sha256`
  (verified by `make xvfb` / `make test-xvfb`).

**Known limitation:** the EasyBuild-sourced files were extracted from *this*
cluster and are committed to the repo (not re-downloaded by `make setup`).
A lab deploying on a different cluster without an equivalent Xvfb build
would need to redo this extraction once (copy the `Xvfb` binary + its `ldd`
closure, minus the universal baseline libs, into `tools/xvfb/{bin,lib}/`) —
or simply export `$DISPLAY` from their own X11/VNC session, which
`XvfbDisplay` (see `src/tarsus/env.py`) honors automatically and skips the
bundled Xvfb entirely.

## Policy

- All tool binaries are gitignored — only this README and the Makefile are tracked
- Run `make setup` from the repo root to download and verify all tools
- Each download is checksum-verified (SHA256)
- Versions are pinned explicitly — updates are intentional and recorded in git
