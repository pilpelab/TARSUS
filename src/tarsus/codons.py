"""Map a detected substitution back to the **codon** that encoded its origin residue.

The pipeline works in amino-acid space, but mistranslation happens in *codon* space:
an engineered tRNA reads one specific codon, not an amino acid. `AlaGGC` inserts Ala
at **GGC** — and Gly has four codons, so an amino-acid-level ``G->A`` count dilutes the
signal across three codons the tRNA never touches.

This module recovers the codon so Step 12 can draw the lab's canonical **61x19**
heatmap (``SubsToSixtyTwentyWithMask.py``): 61 sense codons by 19 amino-acid classes.

**19, not 20** — the lab's own axis merges Ile and Leu into ``I/L``:

    ALL_AA = ['A','Q','Y','W','N','S','R','G','M','H','C','V','K','F','T','E','D','I/L','P']

That is independent confirmation of D-064: this heatmap cannot be drawn without the
isobaric collapse. Our Step 11 already emits ``I/L``, so its output drops straight in.

The mapping follows the reference's ``subsUtils.fetch_codon``: search the **translated
CDS** for the base peptide, then read the codon at the substituted offset. It needs no
protein accession — which matters, because our ``Protein`` column holds the candidate
FASTA header (``PEPTIDE_T5S``), not a real protein ID.
"""

from collections import Counter
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

#: Cells to grey out on the 61x19 heatmap — chiefly each codon's cognate (self) cell.
#: Indexed by **RNA** codon (``UUU``).
SIXTY_TWENTY_MASK_CSV = _ASSETS_DIR / "SixtyTwentyMask.csv"

#: Near-Cognate Error cells — substitutions reachable by a single nucleotide change.
#: Indexed by **DNA** codon (``ATA``), unlike :data:`SIXTY_TWENTY_MASK_CSV`.
NECE_MASK_CSV = _ASSETS_DIR / "NeCEMask.csv"

# These two live here, not in `tarsus.assets`, on purpose.
#
# `orchestration` imports step modules **lazily**, so a master job that has been
# running for hours already holds `tarsus.assets` in `sys.modules` — the version
# that existed when Step 3b first imported it. Adding a new constant to that module
# mid-run is invisible to the live process, so a freshly-read Step 12 doing
# `from ..assets import NECE_MASK_CSV` raises ImportError and kills an otherwise
# finished pipeline at the very last step. That is exactly what happened to
# `hoMS_24814` on 2026-07-14 (the D-063 mid-run-edit hazard, in the flesh).
#
# This module is the home of the 61x19 domain (GENCODE, ALL_CODONS, ALL_AA), so the
# masks belong here anyway — and being a *new* module it can never be stale-cached.

#: The standard genetic code (DNA codons). Verbatim from the lab's script.
GENCODE: dict[str, str] = {
    "ATA": "I", "ATC": "I", "ATT": "I", "ATG": "M",
    "ACA": "T", "ACC": "T", "ACG": "T", "ACT": "T",
    "AAC": "N", "AAT": "N", "AAA": "K", "AAG": "K",
    "AGC": "S", "AGT": "S", "AGA": "R", "AGG": "R",
    "CTA": "L", "CTC": "L", "CTG": "L", "CTT": "L",
    "CCA": "P", "CCC": "P", "CCG": "P", "CCT": "P",
    "CAC": "H", "CAT": "H", "CAA": "Q", "CAG": "Q",
    "CGA": "R", "CGC": "R", "CGG": "R", "CGT": "R",
    "GTA": "V", "GTC": "V", "GTG": "V", "GTT": "V",
    "GCA": "A", "GCC": "A", "GCG": "A", "GCT": "A",
    "GAC": "D", "GAT": "D", "GAA": "E", "GAG": "E",
    "GGA": "G", "GGC": "G", "GGG": "G", "GGT": "G",
    "TCA": "S", "TCC": "S", "TCG": "S", "TCT": "S",
    "TTC": "F", "TTT": "F", "TTA": "L", "TTG": "L",
    "TAC": "Y", "TAT": "Y", "TAA": "_", "TAG": "_",
    "TGC": "C", "TGT": "C", "TGA": "_", "TGG": "W",
}

#: The 61 sense codons, in the lab's row order (stops excluded).
ALL_CODONS: list[str] = [
    "ATA", "ATC", "ATT", "ATG", "ACA", "ACC", "ACG", "ACT", "AAC", "AAT", "AAA", "AAG",
    "AGC", "AGT", "AGA", "AGG", "CTA", "CTC", "CTG", "CTT", "CCA", "CCC", "CCG", "CCT",
    "CAC", "CAT", "CAA", "CAG", "CGA", "CGC", "CGG", "CGT", "GTA", "GTC", "GTG", "GTT",
    "GCA", "GCC", "GCG", "GCT", "GAC", "GAT", "GAA", "GAG", "GGA", "GGC", "GGG", "GGT",
    "TCA", "TCC", "TCG", "TCT", "TTC", "TTT", "TTA", "TTG", "TAC", "TAT", "TGC", "TGT",
    "TGG",
]

#: The three stop codons (``GENCODE`` maps them to ``_``).
STOP_CODONS: list[str] = ["TAA", "TAG", "TGA"]

#: All **64** codons — the 61 sense codons plus the 3 stops. The heatmap draws the
#: complete table: a stop codon carries no substitution in a translated peptide, so
#: its row is always empty, but it is shown (never dropped) so every pipeline's codon
#: heatmap is the same fixed 64 x 19 grid and is comparable cell-for-cell.
ALL_CODONS_64: list[str] = ALL_CODONS + STOP_CODONS

#: The 19 **destination** classes — Ile and Leu merged (`I/L`), exactly as Step 11
#: emits them. A misincorporated residue is seen only by mass, so I and L are one.
ALL_AA: list[str] = [
    "A", "Q", "Y", "W", "N", "S", "R", "G", "M", "H",
    "C", "V", "K", "F", "T", "E", "D", "I/L", "P",
]

#: The 20 **origin** amino acids — Ile and Leu **separate**. The origin residue is
#: read from the genome (the codon spells out I vs L), so it is never ambiguous
#: (D-065). Same order as :data:`ALL_AA` with the merged `I/L` split back into `I`,
#: `L`, so the two heatmap axes stay column-aligned.
ALL_ORIGIN_AA: list[str] = [
    "A", "Q", "Y", "W", "N", "S", "R", "G", "M", "H",
    "C", "V", "K", "F", "T", "E", "D", "I", "L", "P",
]

#: Sentinel for a substitution whose codon could not be resolved. Counted and
#: **reported** — never silently dropped (that is the D-057 failure mode).
UNRESOLVED = "_"


def translate(nt: str) -> str:
    """Translate a DNA sequence to protein. Unknown codons become ``X``."""
    return "".join(
        GENCODE.get(nt[i:i + 3], "X") for i in range(0, len(nt) - 2, 3)
    )


def rna_to_dna(codon: str) -> str:
    """``UUU`` -> ``TTT``. The two mask files disagree on alphabet; this reconciles them."""
    return codon.replace("U", "T")


def load_cds(cds_fasta: Path) -> list[tuple[str, str]]:
    """Load a CDS FASTA as ``[(nucleotide_seq, translated_seq), ...]``.

    Records whose length is not a multiple of 3 are skipped — they cannot be
    codonized, and a partial read would silently shift every downstream codon.
    """
    seqs: list[str] = []
    buf: list[str] = []
    started = False
    with cds_fasta.open() as fh:
        for line in fh:
            if line.startswith(">"):
                if started and buf:
                    seqs.append("".join(buf))
                started, buf = True, []
            else:
                buf.append(line.strip())
    if buf:
        seqs.append("".join(buf))

    return [
        (nt, translate(nt).rstrip("_"))
        for nt in (s.upper() for s in seqs)
        if len(nt) % 3 == 0
    ]


def fetch_codon(base_peptide: str, offset: int, cds: list[tuple[str, str]]) -> str:
    """The codon encoding *base_peptide*[*offset*], or :data:`UNRESOLVED`.

    Mirrors the reference's ``subsUtils.fetch_codon``: find the peptide in a
    translated CDS, then read the codon at the substituted offset.

    When the peptide maps to several proteins that disagree on the codon, the
    substitution is genuinely ambiguous — we return :data:`UNRESOLVED` rather than
    silently picking one. (On the AlaGGC trial this affected 2 of 358.)
    """
    found: set[str] = set()
    for nt, aa in cds:
        i = aa.find(base_peptide)
        if i < 0:
            continue
        start = 3 * (i + offset)
        codon = nt[start:start + 3]
        if len(codon) == 3:
            found.add(codon)
    if len(found) == 1:
        return found.pop()
    return UNRESOLVED


def codon_counts(
    rows: list[tuple[str, int, str]], cds: list[tuple[str, str]],
) -> tuple[Counter[tuple[str, str]], int]:
    """Count ``(codon, destination)`` pairs for substitutions.

    Args:
        rows: ``(base_peptide, offset, destination)`` per localized substitution.
        cds: from :func:`load_cds`.

    Returns:
        ``(counts, n_unresolved)`` — the caller **must** surface *n_unresolved*.
    """
    counts: Counter[tuple[str, str]] = Counter()
    unresolved = 0
    cache: dict[tuple[str, int], str] = {}
    for base, offset, dest in rows:
        key = (base, offset)
        if key not in cache:
            cache[key] = fetch_codon(base, offset, cds)
        codon = cache[key]
        if codon == UNRESOLVED or codon not in GENCODE:
            unresolved += 1
            continue
        counts[(codon, dest)] += 1
    return counts, unresolved
