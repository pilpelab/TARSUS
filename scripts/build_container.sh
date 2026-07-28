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

usage() { sed -n '2,7p' "$0"; exit "${1:-1}"; }
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

if [ "$MODE" = public ]; then
  [ -f "$MSF" ]  || { echo "error: --public needs --msfragger <MSFragger-4.4.1.zip>" >&2; exit 1; }
  [ -f "$IONQ" ] || { echo "error: --public needs --ionquant <IonQuant-1.11.20.jar>" >&2; exit 1; }
fi

BUILDER="$(command -v singularity || command -v apptainer || true)"
[ -n "$BUILDER" ] || { echo "error: no singularity/apptainer on PATH (run on docker-gpu; 'ml Singularity')" >&2; exit 1; }

CTX="$REPO/container/build/context"
rm -rf "$REPO/container/build"
mkdir -p "$CTX/opt-tarsus"

echo ">> assembling build context ($MODE)"
# Copy only what the image needs - an allowlist. A denylist is unsafe here: the
# repo root also holds a gitignored TARSUS_elizabev symlink into another user's
# home (which must never be shipped, and whose dangling symlinks break the copy)
# plus assorted caches and agent scratch. tools/ is handled per-mode below.
for p in src tests pyproject.toml uv.lock Makefile README.md LICENSE; do
    [ -e "$REPO/$p" ] || { echo "error: required repo path missing: $p" >&2; exit 1; }
    cp -a "$REPO/$p" "$CTX/opt-tarsus/"
done

# Vendored, redistributable, always-needed tool bits (small): Xvfb + PDV + README.
mkdir -p "$CTX/opt-tarsus/tools/_downloads"
cp -a "$REPO/tools/README.md" "$CTX/opt-tarsus/tools/" 2>/dev/null || true
cp -a "$REPO/tools/xvfb" "$CTX/opt-tarsus/tools/" 2>/dev/null || true
cp -a "$REPO/tools/PDV-2.1.2" "$CTX/opt-tarsus/tools/" 2>/dev/null || true

if [ "$MODE" = internal ]; then
  echo ">> internal: copying validated tools/ tree (~3.8 GB)"
  cp -a "$REPO/tools/." "$CTX/opt-tarsus/tools/"
else
  echo ">> public: staging builder-supplied MSFragger/IonQuant"
  cp -a "$MSF"  "$CTX/opt-tarsus/tools/_downloads/MSFragger-4.4.1.zip"
  cp -a "$IONQ" "$CTX/opt-tarsus/tools/_downloads/IonQuant-1.11.20.jar"
fi

# Baked commit (mark dirty tree).
SHA="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no 2>/dev/null)" ] || SHA="${SHA}-dirty"
printf '%s\n' "$SHA" > "$CTX/BUILD_COMMIT"
echo ">> baked commit: $SHA"

echo ">> building $OUT"
cd "$REPO"
"$BUILDER" build --fakeroot "$OUT" container/tarsus.def

echo ">> done: $OUT ($(du -h "$OUT" | cut -f1)), commit $SHA"
echo "   distribute: cp '$OUT' /home/labs/pilpel/<shared>/   (run: ml Singularity; singularity exec ... )"
