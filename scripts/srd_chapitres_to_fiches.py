#!/usr/bin/env python3
"""Extraction des chapitres de règles du SRD 5.2.1 (FR) vers des fiches Markdown.

Contrairement aux sorts ou aux objets magiques, la partie « règles générales »
du PDF n'est pas une suite de fiches A-à-Z : c'est un texte continu hiérarchisé
(un chapitre, des sections, des sous-sections, des sous-titres en tête de
paragraphe). On produit donc **une fiche par chapitre**, en respectant cette
hiérarchie :

    titre de chapitre  -> 26 pt gras   (certains wrappent sur 2 lignes)
    titre de section   -> 18 pt gras
    sous-section       -> 14 pt gras
    sous-titre run-in  -> 11 pt gras + 7,7 pt (petites capitales) -> **gras**
    corps de texte     -> 9 à 9,5 pt (0 = romain, 4 = italique)
    puces              -> « • » converti en « - »
    tableaux embarqués  -> absorbés dans le corps en texte joint

Chaque fiche produite :

    <<<FICHE>>>
    id: chapitres/<slug>
    nom: <Titre>
    type: chapitre
    edition: SRD 5.2.1
    mots_cles: chapitre, <slug>
    <<<CONTENU>>>

    # <Titre>

    ## <Section>
    ...
    <<<FIN>>>

La page 1 (« Informations légales ») et les pages 2-4 (« Contenu » = table des
matières, « Index des profils de jeu » = liste de monstres déjà couverte par
04-monstres) sont écartées : elles n'apportent aucune règle au RAG.

Usage :
    python3 scripts/srd_chapitres_to_fiches.py [pdf] [output] [--first N] [--last N]
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
OUT_DEFAULT = Path("dnd/srd-5.2.1/01-chapitres")

# Le corps du document commence à la page 5 (« Comment jouer ») : les pages
# 1-4 (mentions légales + table des matières) sont volontairement ignorées.
FIRST_PAGE = 4  # index 0-based de la page 5
# La section « Objets magiques » (p. 215) est traitée par
# srd_objets_to_fiches.py ; on s'arrête juste avant elle.
LAST_PAGE = 214  # exclus

# Frontière de colonnes : gauche si x0 < 300, droite sinon (mesuré : la
# colonne gauche s'arrète vers 290, la droite commence vers 313).
COL_SPLIT_X = 300.0

# Tolérance de regroupement des spans en lignes visuelles.
LINE_TOL = 3.0

# Bande de pied de page à ignorer (titre du document + numéro de page).
FOOTER_Y_MIN = 730.0

# Les exposants (« e » de « du 2e niveau », « 1er ») sont de très petite
# taille : ils doivent être collés au mot précédent, pas séparés par une espace.
EXPOSANT_MAX_SIZE = 8.0

# Tailles de titres mesurées dans ce PDF.
SIZE_CHAPITRE = 26.0
SIZE_SECTION = 18.0
SIZE_SOUS_SECTION = 14.0
SIZE_RUNIN = 11.0
SIZE_RUNIN_CAP = 7.7

# Tolérances de taille : les tailles fofluctuent légèrement d'une page à l'autre.
TOL_TITRE = 1.2
TOL_RUNIN = 1.0

# Saut vertical maximal entre deux lignes d'un même titre qui wrappe (mesuré :
# ~19 px pour un titre 18 pt, ~31 px pour un titre 26 pt). Au-delà, la ligne
# suivante en gras est un nouveau titre (le saut d'un nouveau bloc est plus grand).
SECTION_WRAP_GAP = 22.0
TITRE_WRAP_GAP = 34.0

MINUS = "\u2212"  # U+2212 MINUS SIGN

# Le chapitre « Sorts » contient la description des 339 sorts, déjà extraite
# par srd_sorts_to_fiches.py : on coupe le chapitre dès le titre
# « Description des sorts » (mesuré p. 114, y ≈ 33).
COUPE_DESCRIPTION_SORTS = re.compile(r"^Description des sorts\s*$")
PAGE_COUPE_SORTS = 114


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
    # « s'appli- » + « qu'ils » → « s'applique » : on supprime le hyphène de
    # césure suivi de l'espace de fin de ligne.
    text = re.sub(r"-\s+(?=[a-zà-ÿ])", "", text)
    return text


# --------------------------------------------------------------------------- #
# Collecte des spans
# --------------------------------------------------------------------------- #

def collect_spans(doc: pymupdf.Document, first: int, last: int) -> list[dict]:
    """Retourne les spans de la partie « règles », triés en ordre de lecture.

    Le PDF est en deux colonnes : on trie par page, puis colonne gauche, puis
    colonne droite, puis ordonnée. Les tableaux embarqués (caractéristiques,
    tables d'équipement, tables de classes) ne sont pas isolés : leurs cellules
    sont jointes au corps, ce qui préserve la lecture continue.
    """
    items: list[dict] = []
    for pno in range(first, min(last, doc.page_count)):
        page = doc[pno]
        dd = page.get_text("dict")
        for block in dd["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    x0, y0 = span["bbox"][0], span["bbox"][1]
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
    for it in items:
        if cur_y is None or abs(it["y0"] - cur_y) <= LINE_TOL:
            cur.append(it)
            if cur_y is None:
                cur_y = it["y0"]
        else:
            groups.append(cur)
            cur = [it]
            cur_y = it["y0"]
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
# Découpage en chapitres
# --------------------------------------------------------------------------- #

def is_chapter_title(it: dict) -> bool:
    """Un titre de chapitre : ~26 pt, gras, non italique, en haut de colonne."""
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


def is_subsection_title(it: dict) -> bool:
    if not (SIZE_SOUS_SECTION - TOL_RUNIN <= it["size"] <= SIZE_SOUS_SECTION + TOL_RUNIN):
        return False
    if not (it["flags"] & 16):
        return False
    if it["flags"] & 2:
        return False
    return bool(it["text"].strip())


def is_runin_head(lines: list[dict], i: int) -> bool:
    """Sous-titre en tête de paragraphe : 11 pt gras + 7,7 pt (petites capitales).

    Le PDF compose ces sous-titres en deux tailles : l'initiale en 11 pt gras et
    le reste en 7,7 pt (petites capitales). Le span 7,7 pt peut être suivi de
    blancs vides (le texte est en fait la suite du titre), puis la description
    commence en 9-9,5 pt non gras.
    """
    it = lines[i]
    if not (SIZE_RUNIN - TOL_RUNIN <= it["size"] <= SIZE_RUNIN + TOL_RUNIN):
        return False
    if not (it["flags"] & 16):
        return False
    if it["flags"] & 2:
        return False
    # Le span suivant doit être en petites capitales (7,7 pt) : c'est ce qui
    # distingue un sous-titre d'une ligne de corps ordinaire.
    for j in range(i + 1, min(i + 3, len(lines))):
        nxt = lines[j]
        if nxt["size"] <= 0:
            continue
        if abs(nxt["size"] - SIZE_RUNIN_CAP) <= 1.2 and (nxt["flags"] & 16):
            return True
        return False
    return False


def collect_runin(lines: list[dict], i: int) -> tuple[str, int]:
    """Reconstitue un sous-titre run-in (initiale 11 pt + suite 7,7 pt)."""
    pieces = [lines[i]["text"].strip()]
    j = i + 1
    while j < len(lines):
        nxt = lines[j]
        if abs(nxt["size"] - SIZE_RUNIN_CAP) <= 1.2 and (nxt["flags"] & 16):
            pieces.append(nxt["text"].strip())
            j += 1
        elif not nxt["text"].strip():
            j += 1
        else:
            break
    text = " ".join(p for p in pieces if p)
    return text.strip(), j


def parse_chapitres(lines: list[dict]) -> list[dict]:
    """Découpe la séquence de lignes en chapitres (titre + sections + corps)."""
    chapitres: list[dict] = []
    cur: dict | None = None
    # Corps en cours : une liste de segments (texte de corps ou titre).
    body: list[tuple[str, str]] = []

    def flush_body() -> None:
        nonlocal body
        if cur is None:
            body = []
            return
        cur["body"].extend(body)
        body = []

    # Les lignes antérieures au premier titre de chapitre sont ignorées
    # (bandeau de couverture, table des matières).
    first_title = next((i for i, it in enumerate(lines) if is_chapter_title(it)), None)
    if first_title is None:
        return []
    n = len(lines)
    i = first_title
    while i < n:
        it = lines[i]
        if is_chapter_title(it):
            if cur is not None:
                flush_body()
                chapitres.append(cur)
            # Titre de chapitre qui wrappe sur la ligne suivante : un titre de
            # chapitre est le seul texte en 26 pt gras, donc toute ligne
            # suivante en 26 pt gras non italique en est la suite.
            nom = it["text"].strip()
            j = i + 1
            while j < n:
                nxt = lines[j]
                if not nxt["text"].strip():
                    j += 1
                    continue
                if (
                    nxt["size"] >= SIZE_CHAPITRE - TOL_TITRE
                    and (nxt["flags"] & 16)
                    and not (nxt["flags"] & 2)
                    and (nxt["y0"] - lines[j - 1]["y0"]) <= TITRE_WRAP_GAP
                ):
                    nom = f"{nom} {nxt['text'].strip()}"
                    j += 1
                else:
                    break
            cur = {"nom": nom, "page": it["page"], "body": []}
            # Sauter les lignes absorbées dans le titre (sinon la ligne de
            # continuation serait re-traitée comme un nouveau titre).
            i = j
            continue
        if cur is None:
            i += 1
            continue
        if is_section_title(it):
            flush_body()
            # Section qui wrappe sur la ligne suivante : un titre de section est
            # le seul texte en 18 pt gras non italique, donc toute ligne
            # suivante en 18 pt gras non italique en est la suite (le saut
            # vertical doit rester celui d'une ligne, pas d'un nouveau bloc).
            text = it["text"].strip()
            j = i + 1
            while (
                j < n
                and not is_chapter_title(lines[j])
                and lines[j]["size"] >= SIZE_SECTION - TOL_RUNIN
                and (lines[j]["flags"] & 16)
                and not (lines[j]["flags"] & 2)
                and (lines[j]["y0"] - lines[j - 1]["y0"]) <= SECTION_WRAP_GAP
            ):
                text = f"{text} {lines[j]['text'].strip()}"
                j += 1
            body.append(("section", text))
            i = j
            continue
        if is_subsection_title(it):
            flush_body()
            body.append(("sous-section", it["text"].strip()))
            i += 1
            continue
        if it["flags"] & 2:
            # Ligne de corps en italique : texte normal, pas un titre.
            body.append(("texte", it["text"]))
            i += 1
            continue
        if is_runin_head(lines, i):
            flush_body()
            text, j = collect_runin(lines, i)
            body.append(("runin", text))
            # Sauter les spans 7,7 pt absorbés dans le sous-titre, sinon ils
            # seraient réémis en tant que lignes de corps (texte dupliqué).
            i = j
            continue
        body.append(("texte", it["text"]))
        i += 1
    if cur is not None:
        flush_body()
        chapitres.append(cur)
    return chapitres


# --------------------------------------------------------------------------- #
# Rendu markdown
# --------------------------------------------------------------------------- #

def render_chapitre(chap: dict) -> str:
    slug = slugify(chap["nom"])
    parts: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            parts.append(" ".join(buf).strip())
            buf.clear()

    for kind, text in chap["body"]:
        text = text.strip()
        if not text:
            continue
        if kind == "section":
            flush()
            parts.append(f"## {text}")
        elif kind == "sous-section":
            flush()
            parts.append(f"### {text}")
        elif kind == "runin":
            flush()
            parts.append(f"**{text}**")
        else:
            if text.startswith("•"):
                flush()
                parts.append("- " + text.lstrip("•").strip())
            else:
                buf.append(text)
    flush()

    corps = "\n\n".join(parts)
    corps = clean_text(corps)

    lines: list[str] = []
    lines.append("<<<FICHE>>>")
    lines.append(f"id: chapitres/{slug}")
    lines.append(f"nom: {chap['nom']}")
    lines.append("type: chapitre")
    lines.append("edition: SRD 5.2.1")
    lines.append(f"mots_cles: chapitre, {slug}")
    lines.append("<<<CONTENU>>>")
    lines.append("")
    lines.append(f"# {chap['nom']}")
    lines.append("")
    lines.append(corps)
    lines.append("<<<FIN>>>")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Extraire les chapitres du SRD 5.2.1 (FR).")
    parser.add_argument("pdf", nargs="?", default=str(PDF_DEFAULT))
    parser.add_argument("output", nargs="?", default=str(OUT_DEFAULT))
    parser.add_argument("--first", type=int, default=FIRST_PAGE, help="index 0-based de la 1re page")
    parser.add_argument("--last", type=int, default=LAST_PAGE, help="index 0-based de la dernière page (exclu)")
    args = parser.parse_args(argv)

    pdf_path = Path(args.pdf)
    out_dir = Path(args.output)
    if not pdf_path.exists():
        print(f"PDF introuvable : {pdf_path}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(str(pdf_path))
    items = collect_spans(doc, args.first, args.last)
    lines = group_lines(items)
    chapitres = parse_chapitres(lines)

    # Le chapitre « Sorts » contient la description des sorts, déjà extraite
    # ailleurs : on coupe dès le titre « Description des sorts ».
    for chap in chapitres:
        if chap["nom"] == "Sorts":
            cut = next(
                (
                    n
                    for n, (kind, text) in enumerate(chap["body"])
                    if kind == "section" and COUPE_DESCRIPTION_SORTS.match(text.strip())
                ),
                None,
            )
            if cut is not None:
                chap["body"] = chap["body"][:cut]

    # Les chapitres « Informations légales » et « Contenu » (table des
    # matières) ne portent aucune règle : ils sont écartés.
    skip = {"informations-legales", "contenu", "index-des-profils-de-jeu"}
    written = 0
    empty = 0
    for chap in chapitres:
        slug = slugify(chap["nom"])
        if slug in skip:
            continue
        body = [seg for seg in chap["body"] if seg[1].strip()]
        if not body:
            empty += 1
            print(f"  ! chapitre vide ignoré : {chap['nom']} (p.{chap['page']})")
            continue
        chap["body"] = body
        content = render_chapitre(chap)
        dest = out_dir / f"{slug}.md"
        dest.write_text(content, encoding="utf-8")
        written += 1
        print(f"  ✓ {slug}.md ({len(content)} o)")

    print(f"\n{written} chapitres écrits dans {out_dir} ({empty} vides ignorés)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
