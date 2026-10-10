#!/usr/bin/env python3
"""Extraction des tables aléatoires (d100) du SRD 5.2.1 (FR) vers des fiches Markdown.

Les tables aléatoires se trouvent dans le chapitre « Boîte à outils ludique »
(p. 203-214) : Allure de voyage, Conception d'historique, Malédictions et
contagions magiques, Effets environnementaux, Terreur et grand stress, Poison,
Pièges, Rencontres de combat.

Chaque section du chapitre devient une fiche. Les lignes de tableau (« 01–05
  … ») sont regroupées en tableau Markdown « | d100 | Résultat | » ; les
sous-titres (12 pt gras) deviennent des « ### » ; le reste est rendu en prose.

NOTE : le chapitre « Lore » n'existe pas dans cette édition du PDF (le lore est
fondu dans « Comment jouer » / « Origines des personnages ») ; les « Animaux »
sont couverts par 04-monstres. Ces deux domaines sont donc volontairement vides.

Usage :
    python3 scripts/srd_tables_to_fiches.py [pdf] [output]
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

PDF_DEFAULT = Path("dnd/FR_SRD_CC_v5.2.1.pdf")
OUT_DEFAULT = Path("dnd/srd-5.2.1/06-tables-aleatoires")

# Le chapitre « Boîte à outils ludique » commence p. 203 (index 202) et se
# termine avant « Objets magiques » (p. 215).
FIRST_PAGE = 202
LAST_PAGE = 214  # exclus

# Frontière de colonnes : gauche si x0 < 300, droite sinon.
COL_SPLIT_X = 300.0

# Tolérance de regroupement des spans en lignes visuelles. Un peu plus large
# qu'ailleurs (6 px) pour que la colonne « d100 » et la colonne « Résultat »
# d'une même ligne de tableau soient jointes.
LINE_TOL = 6.0

# Écart horizontal maximal entre deux spans d'une même ligne : au-delà, on
# considère qu'on change de colonne (évite de coller un titre de section au
# premier paragraphe, ou deux colonnes de texte entre elles).
GAP_H_MAX = 20.0

# Chute de taille de police maximale entre deux spans d'une même ligne : au-delà,
# on considère qu'un titre (18 pt) précède le corps de texte (9,5 pt).
SIZE_DROP_MAX = 3.0

# Bande de pied de page à ignorer.
FOOTER_Y_MIN = 730.0

# Exposants (« e », « 1er ») : coller au mot précédent.
EXPOSANT_MAX_SIZE = 8.0

# Tailles de titres mesurées dans ce PDF.
SIZE_CHAPITRE = 26.0
SIZE_SECTION = 18.0
SIZE_SOUS_SECTION = 14.0
SIZE_RUNIN = 12.0
TOL_TITRE = 1.2
TOL_RUNIN = 1.0

# Saut vertical maximal entre deux lignes d'un titre de section qui wrappe.
SECTION_WRAP_GAP = 22.0

# Ligne de tableau d100 : plage « 01–05 » puis le résultat.
ROW_RE = re.compile(r"^\s*(\d{2}\s*[-\u2013\u2212]\s*\d{2})\s+(.*\S)\s*$")
# Ligne d'en-tête de tableau (« d100 … ») : à jeter, on émet notre propre en-tête.
HEADER_RE = re.compile(r"^\s*d\s*100\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def clean_text(text: str) -> str:
    """Normalise les espaces et répare les césures de fin de ligne."""
    text = text.replace("\u00ad", "").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"-\s+(?=[a-zà-ÿ])", "", text)
    return text


# --------------------------------------------------------------------------- #
# Collecte des spans
# --------------------------------------------------------------------------- #

def collect_spans(doc: pymupdf.Document, first: int, last: int) -> list[dict]:
    """Retourne les spans du chapitre « Boîte à outils ludique », triés en ordre
    de lecture (gauche puis droite, puis ordonnée). Tous les spans sont gardés :
    aucune filtre de taille ni de position horizontale."""
    items: list[dict] = []
    for pno in range(first, min(last, doc.page_count)):
        page = doc[pno]
        dd = page.get_text("dict")
        for block in dd["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    x0, y0, x1, _y1 = span["bbox"]
                    if y0 > FOOTER_Y_MIN:
                        continue
                    text = span["text"]
                    if not text.strip():
                        continue
                    items.append(
                        {
                            "page": pno + 1,
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "text": text,
                            "font": span.get("font", ""),
                            "flags": span.get("flags", 0),
                            "size": span.get("size", 0.0),
                        }
                    )
    items.sort(key=lambda it: (it["page"], 0 if it["x0"] < COL_SPLIT_X else 1, it["y0"], it["x0"]))
    return items


def group_lines(items: list[dict]) -> list[dict]:
    """Regroupe les spans en lignes visuelles (même ordonnée y)."""
    groups: list[list[dict]] = []
    cur: list[list[dict]] = []
    cur_y: float | None = None
    prev_x1: float | None = None
    prev_size: float | None = None
    for it in items:
        if not cur:
            cur.append(it)
            cur_y = it["y0"]
        elif (
            abs(it["y0"] - cur_y) <= LINE_TOL
            and (it["x0"] < COL_SPLIT_X) == (cur[-1]["x0"] < COL_SPLIT_X)
            and abs(prev_size - it["size"]) <= SIZE_DROP_MAX
        ):
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
            cur_y = it["y0"]
        prev_x1 = it["x1"]
        prev_size = it["size"]
    if cur:
        groups.append(cur)

    lines: list[dict] = []
    for group in groups:
        group.sort(key=lambda it: it["x0"])
        parts: list[str] = []
        for it in group:
            text = it["text"]
            if it["size"] < EXPOSANT_MAX_SIZE and parts:
                parts[-1] = parts[-1] + text
            else:
                parts.append(text)
        text = " ".join(parts)
        if not text.strip():
            continue
        first = group[0]
        lines.append(
            {
                "page": first["page"],
                "x0": first["x0"],
                "y0": first["y0"],
                "text": text,
                "size": first["size"],
                "flags": first["flags"],
            }
        )
    return lines


# --------------------------------------------------------------------------- #
# Découpage en sections
# --------------------------------------------------------------------------- #

def is_chapter_title(it: dict) -> bool:
    if it["size"] < SIZE_CHAPITRE - TOL_TITRE:
        return False
    if not (it["flags"] & 16):
        return False
    if it["flags"] & 2:
        return False
    return bool(it["text"].strip())


def is_section_title(it: dict) -> bool:
    if not (SIZE_SECTION - TOL_RUNIN <= it["size"] <= SIZE_SECTION + TOL_TITRE):
        return False
    if not (it["flags"] & 16):
        return False
    if it["flags"] & 2:
        return False
    return bool(it["text"].strip())


def is_subhead(it: dict) -> bool:
    """Sous-titre de tableau (poison, piège, étape…) : 12 pt gras non italique."""
    if not (SIZE_RUNIN - TOL_RUNIN <= it["size"] <= SIZE_RUNIN + TOL_TITRE):
        return False
    if not (it["flags"] & 16):
        return False
    if it["flags"] & 2:
        return False
    return bool(it["text"].strip())


def parse_tables(doc: pymupdf.Document) -> list[tuple[str, list[dict]]]:
    """Retourne [(titre de section, lignes du corps), …] pour le chapitre
    « Boîte à outils ludique »."""
    items = collect_spans(doc, FIRST_PAGE, LAST_PAGE)
    lines = group_lines(items)
    n = len(lines)

    # Le titre du chapitre (26 pt) et l'éventuelle intro sont ignorés : ils sont
    # déjà dans 01-chapitres.
    i = 0
    while i < n and not is_section_title(lines[i]):
        i += 1

    tables: list[tuple[str, list[dict]]] = []
    while i < n:
        it = lines[i]
        if not is_section_title(it):
            i += 1
            continue
        title = it["text"].strip()
        j = i + 1
        # Titre qui wrappe sur 2 lignes : même taille, saut vertical court.
        while (
            j < n
            and is_section_title(lines[j])
            and (lines[j]["y0"] - lines[j - 1]["y0"]) <= SECTION_WRAP_GAP
        ):
            title = title + " " + lines[j]["text"].strip()
            j += 1
        body: list[dict] = []
        k = j
        while k < n and not is_section_title(lines[k]) and not is_chapter_title(lines[k]):
            body.append(lines[k])
            k += 1
        tables.append((title, body))
        i = j
    return tables


# --------------------------------------------------------------------------- #
# Rendu
# --------------------------------------------------------------------------- #

def render_table(title: str, body: list[dict]) -> str:
    parts: list[str] = [f"# {title}", ""]
    prose: list[str] = []
    rows: list[str] = []

    def flush_prose() -> None:
        if prose:
            parts.append(" ".join(prose).strip())
            parts.append("")
            prose.clear()

    def flush_rows() -> None:
        if rows:
            parts.append("| d100 | Résultat |")
            parts.append("| --- | --- |")
            for row in rows:
                parts.append(f"| {row} |")
            parts.append("")
            rows.clear()

    for it in body:
        text = clean_text(it["text"])
        if not text.strip():
            continue
        if HEADER_RE.match(text):
            continue
        m = ROW_RE.match(text)
        if m:
            flush_prose()
            plage = re.sub(r"\s*[-\u2013\u2212]\s*", "–", m.group(1))
            rows.append(f"{plage} | {m.group(2).strip()}")
            continue
        if is_subhead(it):
            flush_prose()
            flush_rows()
            parts.append(f"### {text.strip()}")
            parts.append("")
            continue
        prose.append(text.strip())

    flush_prose()
    flush_rows()
    return "\n".join(parts).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Tables aléatoires SRD 5.2.1 -> fiches Markdown")
    ap.add_argument("pdf", nargs="?", default=str(PDF_DEFAULT))
    ap.add_argument("out", nargs="?", default=str(OUT_DEFAULT))
    args = ap.parse_args()

    pdf = Path(args.pdf)
    out = Path(args.out)
    if not pdf.exists():
        print(f"PDF introuvable : {pdf}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(str(pdf))
    tables = parse_tables(doc)
    doc.close()

    n = 0
    for title, body in tables:
        if not body:
            continue
        slug = slugify(title)
        if not slug:
            continue
        content = render_table(title, body)
        fiche = (
            "<<<FICHE>>>\n"
            f"id: tables/{slug}\n"
            f"nom: {title}\n"
            "type: table-aléatoire\n"
            "edition: SRD 5.2.1\n"
            f"mots_cles: table, d100, {slug}\n"
            "<<<CONTENU>>>\n\n"
            f"{content}\n"
            "<<<FIN>>>\n"
        )
        (out / f"{slug}.md").write_text(fiche, encoding="utf-8")
        n += 1

    print(f"tables écrites : {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
