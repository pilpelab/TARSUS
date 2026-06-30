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

## Policy

- All tool binaries are gitignored — only this README and the Makefile are tracked
- Run `make setup` from the repo root to download and verify all tools
- Each download is checksum-verified (SHA256)
- Versions are pinned explicitly — updates are intentional and recorded in git
