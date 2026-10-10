#!/usr/bin/env python3
"""Extraction des fiches « objet magique » du SRD 5.2.1 (FR) vers un Markdown RAG.

Chaque objet de la section « Objets magiques de A à Z » (pages 221 à 266 du
PDF FR_SRD_CC_v5.2.1.pdf) produit un fichier markdown autonome :

    <<<FICHE>>>
    id: objets/<slug>
    nom: <Nom>
    type: objet
    edition: SRD 5.2.1
    mots_cles: objet, <catégorie>
    <<<CONTENU>>>

    ## <Nom>

    <catégorie>, <rareté> (Harmonisation requise)

    <description>

    - <puce>
    <<<FIN>>>

Contrairement aux sorts, le titre d'un objet est en gras (flags & 16, ~12 pt)
et n'est PAS suivi d'une ligne d'école : c'est la ligne méta « Anneau, rare
(Harmonisation requise) » (10 pt, italique) qui suit directement le titre.
L'introduction de la section (p. 215-220 : catégories, règles, objets
intelligents/sensibles) est volontairement ignorée, de même que le chapitre
« Monstres » qui commence p. 267.

Les tableaux embarqués dans une fiche (ex. « Bâton de tonnerre et de foudre »)
sont absorbés dans le corps de la fiche : leurs cellules sont jointes au texte
courant, ce qui évite toute dépendance à find_tables (qui produit des faux
positifs sur les pages d'introduction).

Usage :
    python3 scripts/srd_objets_to_fiches.py [pdf] [output] [--first N] [--last N]
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
OUT_DEFAULT = Path("dnd/srd-5.2.1/03-objets-magiques")

# La section « Objets magiques » commence p. 215 (titre de chapitre) ; les
# fiches A à Z commencent p. 221, après l'introduction (p. 215-220), et
# s'arrêtent p. 266 : le chapitre « Monstres » commence p. 267.
FIRST_PAGE = 214  # index 0-based de la page 215
LAST_PAGE = 266   # exclus

# Frontière de colonnes : gauche si x0 < 300, droite sinon (mesuré : gauche
# max ≈ 287, droite min ≈ 313 sur toute la section).
COL_SPLIT_X = 300.0

# Tolérance de regroupement des spans en lignes visuelles (identique aux
# sorts : pas de ligne ≈ 11,5 pt).
LINE_TOL = 3.0

# Bande de pied de page à ignorer (titre du document + numéro de page).
FOOTER_Y_MIN = 730.0

# Ligne méta d'un objet : « <catégorie>, <rareté> (Harmonisation requise) ».
# Le suffixe « (Harmonisation requise) » est optionnel (mesuré p. 221 :
# « Anneau, rare » seul).
OBJ_META_RE = re.compile(
    r"^[^,]+,\s+(?:très |peu )?(?:courant|rare|inestimable|légendaire|artefat)"
    r"(?: \(Harmonisation requise\))?$"
)

MINUS = "\u2212"  # U+2212 MINUS SIGN
EXPOSANT_MAX_SIZE = 7.0


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
    """Retourne les spans de la section « Objets magiques », triés.

    Les tableaux embarqués (ex. « Bâton de tonnerre et de foudre ») ne sont
    pas isolés : leurs cellules sont jointes au corps de la fiche, ce qui
    préserve la lecture continue sans dépendre de find_tables.
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
                    x0, y0, x1, y1 = span["bbox"]
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
    # Ordre de lecture : page, puis colonne gauche, puis colonne droite.
    items.sort(key=lambda it: (it["page"], 0 if it["x0"] < COL_SPLIT_X else 1, it["y0"], it["x0"]))
    return items


# --------------------------------------------------------------------------- #
# Découpage en fiches
# --------------------------------------------------------------------------- #

def is_meta_line(it: dict) -> bool:
    """Ligne méta « Anneau, rare (Harmonisation requise) » : italique, ~10 pt."""
    if it["size"] < 8.5 or it["size"] > 12.0:
        return False
    if not (it["flags"] & 2):  # bit italic
        return False
    return bool(OBJ_META_RE.match(it["text"].strip()))


def is_object_start(lines: list[dict], i: int) -> bool:
    """Une ligne est le nom d'un objet si une ligne méta suit à courte distance.

    Le nom est en gras (flags & 16), non italique, taille ~12 ; la ligne méta
    est en italique (flags & 2), taille ~10. Elle n'est PAS toujours la ligne
    immédiatement suivante : mesuré p. 221, la première ligne de description
    (9,5 pt) a un y0 (~48,4) légèrement inférieur à celui de la méta (~52,4),
    donc le tri par y0 la fait remonter avant elle. On cherche donc la méta
    sur les trois lignes suivantes, en n'acceptant entre le titre et la méta
    que des lignes de description ou une seconde ligne de titre (wrap).
    """
    it = lines[i]
    if not (11.5 <= it["size"] <= 13.5):
        return False
    if it["y0"] < 30.0:
        return False
    if not it["text"].strip():
        return False
    if it["flags"] & 2:  # le nom n'est pas en italique
        return False
    if not (it["flags"] & 16):
        return False
    for j in range(i + 1, min(i + 4, len(lines))):
        nxt = lines[j]
        if is_meta_line(nxt):
            return True
        # Seconde ligne d'un titre qui wrappe.
        if (nxt["flags"] & 16) and not (nxt["flags"] & 2) and nxt["size"] >= 11.5:
            continue
        # Première ligne de description, remontée avant la méta par le tri.
        if not (nxt["flags"] & 2) and not (nxt["flags"] & 16) and 8.5 <= nxt["size"] <= 10.5:
            continue
        return False
    return False


def join_spans(spans: list[dict]) -> str:
    """Joint les spans d'une ligne en un texte fluide (exposants collés)."""
    parts: list[str] = []
    for it in spans:
        text = it["text"]
        if it["size"] < EXPOSANT_MAX_SIZE and parts:
            parts[-1] = parts[-1] + text
        else:
            parts.append(text)
    return " ".join(parts)


def group_lines(items: list[dict]) -> list[dict]:
    """Regroupe les spans en lignes visuelles (même ordonnée y)."""
    groups: list[list[dict]] = []
    cur: list[dict] = []
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
        text = join_spans(group)
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


def parse_objets(lines: list[dict]) -> list[dict]:
    """Découpe la séquence de lignes en fiches d'objet.

    Le corps = ligne méta + description (paragraphes joints, puces conservées).
    Les lignes de description qui précèdent la méta (tri par y0) sont conservées
    et rejetées après elle, pour que la fiche commence bien par la méta.
    """
    starts = [i for i in range(len(lines)) if is_object_start(lines, i)]
    # Un titre qui wrappe ne doit pas être pris pour le départ de la fiche
    # suivante : on élimine les déports consécutifs (i et i+1).
    starts = [i for n, i in enumerate(starts) if n == 0 or i != starts[n - 1] + 1]
    objets: list[dict] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        name = lines[start]["text"].strip()
        if not name:
            continue
        # Titre éventuellement suivi d'une seconde ligne de titre (wrap).
        j = start + 1
        while (
            j < end
            and lines[j]["size"] >= 11.5
            and (lines[j]["flags"] & 16)
            and not (lines[j]["flags"] & 2)
            and not is_meta_line(lines[j])
        ):
            name = f"{name} {lines[j]['text'].strip()}"
            j += 1
        # Ligne méta : peut être devancée par la première ligne de description.
        meta = ""
        desc: list[str] = []
        while j < end and not is_meta_line(lines[j]) and not (lines[j]["flags"] & 16):
            t = lines[j]["text"].strip()
            if t:
                desc.append(t)
            j += 1
        while j < end and is_meta_line(lines[j]):
            meta = lines[j]["text"].strip()
            j += 1
        while j < end:
            t = lines[j]["text"].strip()
            if t:
                desc.append(t)
            j += 1
        # Construire le corps : paragraphes joints, puces séparées.
        chunks: list[str] = []
        buf: list[str] = []
        for t in desc:
            if t.startswith("•"):
                if buf:
                    chunks.append(" ".join(buf))
                    buf = []
                chunks.append("- " + t.lstrip("•").strip())
            else:
                buf.append(t)
        if buf:
            chunks.append(" ".join(buf))
        corps = meta + "\n\n" + "\n\n".join(chunks) if meta else "\n\n".join(chunks)
        corps = clean_text(corps)
        categorie = meta.split(",")[0].strip() if meta else ""
        objets.append(
            {
                "nom": name,
                "meta": meta,
                "categorie": categorie,
                "corps": corps,
                "page": lines[start]["page"],
            }
        )
    return objets


# --------------------------------------------------------------------------- #
# Rendu markdown
# --------------------------------------------------------------------------- #

def render_objet(objet: dict) -> str:
    slug = slugify(objet["nom"])
    mots_cles = f"objet, {objet['categorie']}" if objet["categorie"] else "objet"
    lines: list[str] = []
    lines.append("<<<FICHE>>>")
    lines.append(f"id: objets/{slug}")
    lines.append(f"nom: {objet['nom']}")
    lines.append("type: objet")
    lines.append("edition: SRD 5.2.1")
    lines.append(f"mots_cles: {mots_cles}")
    lines.append("<<<CONTENU>>>")
    lines.append("")
    lines.append(f"## {objet['nom']}")
    lines.append("")
    lines.append(objet["corps"].strip())
    lines.append("<<<FIN>>>")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction des objets magiques du SRD 5.2.1")
    parser.add_argument("pdf", nargs="?", type=Path, default=PDF_DEFAULT)
    parser.add_argument("output", nargs="?", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--first", type=int, default=FIRST_PAGE,
                        help="index 0-based de la première page à lire")
    parser.add_argument("--last", type=int, default=LAST_PAGE,
                        help="index 0-based de la dernière page (exclus)")
    args = parser.parse_args(argv)

    if not args.pdf.exists():
        print(f"PDF introuvable : {args.pdf}", file=sys.stderr)
        return 1

    doc = pymupdf.open(args.pdf)
    items = collect_spans(doc, args.first, args.last)
    lines = group_lines(items)
    objets = parse_objets(lines)

    out_dir = args.output
    out_dir.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    written = 0
    for objet in objets:
        slug = slugify(objet["nom"])
        if slug in seen:
            print(f"  doublon ignoré : {objet['nom']}", file=sys.stderr)
            continue
        seen.add(slug)
        (out_dir / f"{slug}.md").write_text(render_objet(objet), encoding="utf-8")
        written += 1

    index_lines = [
        "---",
        "id: index/objets",
        "type: index",
        "---",
        "",
        "# Index des objets magiques",
        "",
    ]
    for objet in objets:
        slug = slugify(objet["nom"])
        index_lines.append(f"- {objet['nom']} → objets/{slug}.md")
    (out_dir.parent / "00-index" / "objets.md").parent.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / "00-index" / "objets.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )

    print(f"{written} fiches écrites dans {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
