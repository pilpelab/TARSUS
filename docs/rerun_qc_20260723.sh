#!/usr/bin/env bash
set -euo pipefail

cd /home/labs/pilpel/barc/TARSUS_BC
source .venv/bin/activate

OUT_ROOT=/home/labs/pilpel/barc/TARSUS_BC/output/qc_20260723
ECOLI_FASTA=/home/labs/pilpel/barc/TARSUS_BC/data/protein.fasta
ECOLI_CDS=/home/labs/pilpel/barc/TARSUS_BC/data/ecoli_cds.fasta
HUMAN_FASTA=/home/labs/pilpel/slavat/tehilapaper/fasta/protein.fasta
HUMAN_CDS=/home/labs/pilpel/barc/TARSUS_BC/data/human_cds.fasta

mkdir -p "$OUT_ROOT"

# Preflight
make test-tools
pytest tests/unit tests/validation

# Local project runs
tarsus run \
  --fasta "$ECOLI_FASTA" \
  --cds "$ECOLI_CDS" \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/HouYM-25-G140-AstralDDA-AlaGGC-HS-1.raw \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/HouYM-25-G140-AstralDDA-AlaGGC-LS-1.raw \
  -o "$OUT_ROOT/alaggc"

tarsus run \
  --fasta "$ECOLI_FASTA" \
  --cds "$ECOLI_CDS" \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/control/HouYM-25-G140-AstralDDA-AlaGGCpar-LS-1.raw \
  -i /home/labs/pilpel/barc/TARSUS_BC/data/control/HouYM-25-G140-AstralDDA-AlaGCCpar-HS-1.raw \
  -o "$OUT_ROOT/alaggcpar"

# Slava coli tRNA panel available at /home/labs/pilpel/slavat/coli_trna/<sample>/*.raw
for sample in GluUUC GluUUCpar IleXCAU IleXCAUpar LeuUAG ProCGG ProCGGpar ProGGG ProGGGpar; do
  raw_dir="/home/labs/pilpel/slavat/coli_trna/${sample}"
  out_dir="$OUT_ROOT/${sample,,}"
  mapfile -t raws < <(find "$raw_dir" -maxdepth 1 -type f -iname '*.raw' | sort)

  if [[ "${#raws[@]}" -eq 0 ]]; then
    echo "ERROR: no RAW files found for $sample in $raw_dir" >&2
    exit 1
  fi

  args=(tarsus run --fasta "$ECOLI_FASTA" --cds "$ECOLI_CDS")
  for raw in "${raws[@]}"; do
    args+=(-i "$raw")
  done
  args+=(-o "$out_dir")

  "${args[@]}"
done

# hoMS full proteome rerun
homs_args=(tarsus run --fasta "$HUMAN_FASTA" --cds "$HUMAN_CDS")
for i in $(seq 1 15); do
  homs_args+=(-i "/home/labs/pilpel/slavat/tehilapaper/revisions/hoMS/raw/EX1_24814_Fraction-${i}_03092025.raw")
done
homs_args+=(-o "$OUT_ROOT/homs_24814")
"${homs_args[@]}"
