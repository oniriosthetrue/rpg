#!/usr/bin/env python3
"""Extraction des fiches « sort » du SRD 5.2.1 (FR) vers un Markdown RAG.

Chaque sort de la section « Description des sorts » (pages 114 à 186 du PDF
FR_SRD_CC_v5.2.1.pdf) produit un fichier markdown autonome :

    <<<FICHE>>>
    id: sorts/<slug>
    nom: <Nom>
    type: sort
    edition: SRD 5.2.1
    mots_cles: sort, <école>
    <<<CONTENU>>>

    ## <Nom>

    <école> du <n>e niveau (<classes>)

    Temps d'incantation : ...
    Portée : ...
    Composantes : ...
    Durée : ...

    <description>
    <<<FIN>>>

Le PDF est en deux colonnes ; les spans sont donc triés par colonne puis par
ordonnée, ce qui respecte l'ordre de lecture et évite de coller le corps d'un
sort au `Durée :` du précédent (défaut de `get_text("text")`).

Usage :
    python3 scripts/srd_sorts_to_fiches.py [pdf] [output] [--first N] [--last N]
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
OUT_DEFAULT = Path("dnd/srd-5.2.1/02-sorts")

# La section « Description des sorts » commence à la page 114 (le header est à
# y=220, le premier sort « Agrandissement/rapetissement » juste en dessous) et
# se termine à la page 186 ; le Glossaire occupe la page 187.
FIRST_PAGE = 113  # index 0-based de la page 114
LAST_PAGE = 186   # exclus

# Frontière de colonnes : gauche si x0 < 300, droite sinon (mesuré : gauche
# max ≈ 287, droite min ≈ 313 sur toute la section).
COL_SPLIT_X = 300.0

# Tolérance de regroupement des spans en lignes visuelles. Mesuré : le pas de
# ligne est ≈ 11,5 pt ; le décalage de métrique entre la ligne « Durée »
# (Cambria-Italic) et la première ligne de description (Cambria) est ≈ 2,8 pt,
# alors que l'exposant « e » de « du 2e niveau » ne dépasse pas ≈ 1,0 pt. Une
# tolérance de 2,0 sépare « Durée : » du corps tout en conservant l'exposant.
LINE_TOL = 2.0

# Écart horizontal maximal entre deux spans d'une même ligne : au-delà, on
# change de colonne (évite de coller un titre de section au corps de texte).
GAP_H_MAX = 20.0

# Chute de taille de police maximale entre deux spans d'une même ligne : au-delà,
# un titre (12 pt) précède le corps de texte (9,5 pt).
SIZE_DROP_MAX = 3.0

# En-tête de paragraphe « À plus haut niveau » : à isoler du corps de texte.
RUNIN_RE = re.compile(r"^(?:À plus haut niveau|Emplacement de niveau supérieur)\s*\.?$")

# Sous-titre de paragraphe en italique au milieu d'une ligne de description
# (ex. « Alarme mentale. ») : court, sans ponctuation interne, terminé par un point.
RUNIN_BODY_RE = re.compile(r"^[A-ZÀ-Ü][^:;.!?]*\.$")

# Largeur maximale d'un sous-titre de paragraphe (mesuré : « Alarme mentale. »
# fait 74 pt ; une ligne de description pleine fait ~227 pt).
RUNIN_MAX_WIDTH = 140.0

# Décalage de métrique des spans en italique (sous-titres de paragraphe) : leur
# bbox est rapportée ~20 pt trop bas, ce qui les fait trier APRÈS le texte qui
# les suit. On corrige le y0 de cette valeur avant le tri.
ITALIC_Y_BIAS = 20.0

# Bande de pied de page à ignorer (titre du document + numéro de page).
FOOTER_Y_MIN = 730.0

# Les pages d'introduction (112-113) ne contiennent pas de fiche : elles sont
# écartées d'office, et tout span antérieur au premier nom de sort est ignoré.

SCHOOL_RE = re.compile(
    r"^(Abjuration|Appel|Conjuration|Divination|Enchantement|Invocation|Évocation|"
    r"Illusion|Nécromancie|Transmutation)\b"
)

# Écoles acceptées pour le champ `école` (le PDF écrit « Invocation »).
SCHOOLS = (
    "Abjuration",
    "Appel",
    "Conjuration",
    "Divination",
    "Enchantement",
    "Invocation",
    "Évocation",
    "Illusion",
    "Nécromancie",
    "Transmutation",
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
    # « s'appli- » + « qu'ils » → « s'applique » : on supprime le hyphène de
    # césure suivi de l'espace de fin de ligne.
    text = re.sub(r"-\s+(?=[a-zà-ÿ])", "", text)
    # Ordinaux fragmentés par l'exposant : « du 2 . e » → « du 2e »,
    # « du 1 . er » → « du 1er ».
    text = re.sub(r"(\d+)\s+\.\s+(e|er)\b", r"\1\2", text)
    return text


def is_runin_header(it: dict) -> bool:
    """Vrai si le span est un sous-titre de paragraphe (« Alarme mentale. »).

    Le PDF ne marque PAS ces spans en italique (flags = 16, gras) : la détection
    se fait sur le motif (majuscule, court, sans ponctuation interne, point
    final), complétée par la garde de largeur et de style. Ne pas tester
    `flags & 2` : le bit italique est absent sur ces spans.
    """
    text = it["text"].strip()
    if not (it["flags"] & 2 or it["flags"] & 16):
        return False
    if it["x1"] - it["x0"] > RUNIN_MAX_WIDTH:
        return False
    return bool(RUNIN_BODY_RE.match(text))


# --------------------------------------------------------------------------- #
# Collecte des spans
# --------------------------------------------------------------------------- #

def collect_spans(doc: pymupdf.Document, first: int, last: int) -> list[dict]:
    """Retourne les spans de la zone « Description des sorts », triés."""
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
                    it = {
                        "page": pno + 1,
                        "x0": x0,
                        "y0": y0,
                        "x1": x1,
                        "text": text,
                        "font": span.get("font", ""),
                        "flags": span.get("flags", 0),
                        "size": span.get("size", 0.0),
                    }
                    if is_runin_header(it):
                        # Sous-titre de paragraphe : sa bbox est rapportée ~20 pt
                        # trop bas, ce qui le ferait trier après le texte qu'il
                        # introduit. On corrige le y0 avant le tri.
                        it["y0"] -= ITALIC_Y_BIAS
                    items.append(it)
    # Ordre de lecture : page, puis colonne gauche, puis colonne droite.
    # Le tie-breaker x0 est indispensable : l'exposant « e » de « du 2e niveau »
    # a un y0 légèrement supérieur à celui du reste de la ligne, et un tri
    # strictement par y0 le rejetterait en fin de ligne.
    items.sort(key=lambda it: (it["page"], 0 if it["x0"] < COL_SPLIT_X else 1, it["y0"], it["x0"]))
    return items


# --------------------------------------------------------------------------- #
# Découpage en fiches
# --------------------------------------------------------------------------- #

META_RE = re.compile(r"^(?:Temps d['’]incantation|Portée|Composantes|Durée)\s*:")


def is_school_line(it: dict) -> bool:
    """Ligne « École du Xe niveau (classes) » : italique, taille ~10."""
    if it["size"] < 8.5 or it["size"] > 12.0:
        return False
    if not (it["flags"] & 2):  # bit italic
        return False
    return bool(SCHOOL_RE.match(it["text"].lstrip()))


def is_spell_start(lines: list[dict], i: int) -> bool:
    """Une ligne est le nom d'un sort si la suivante est la ligne école.

    Le nom est en SemiBold (flags & 16), non italique, taille ~12 ; la ligne
    école qui suit est en italique (flags & 2), taille ~10. On ne teste pas
    le span suivant span par span : la ligne école est fragmentée par
    l'exposant « e » de « du 2e niveau ».
    """
    it = lines[i]
    if not (10.0 <= it["size"] <= 13.5):
        return False
    if it["y0"] < 30.0:
        return False
    if not it["text"].strip():
        return False
    if it["flags"] & 2:  # le nom n'est pas en italique
        return False
    nxt = lines[i + 1] if i + 1 < len(lines) else None
    return nxt is not None and is_school_line(nxt)


def join_spans(spans: list[dict]) -> str:
    """Joint les spans d'une ligne en un texte fluide.

    Les spans d'exposant (taille < EXPOSANT_MAX_SIZE, ex. le « e » de
    « du 2e niveau ») sont collés au span précédent sans espace.
    """
    parts: list[str] = []
    for it in spans:
        text = it["text"].lstrip()
        if it["size"] < EXPOSANT_MAX_SIZE and parts:
            parts[-1] = parts[-1] + text  # exposant : collé au mot précédent
        elif is_runin_header(it):
            # Sous-titre de paragraphe (« Alarme mentale. ») : à isoler en gras,
            # sinon il se colle au milieu de la phrase.
            parts.append(f"\n\n**{text.strip().rstrip('. ')}**\n\n")
        else:
            parts.append(text)
    # Le « \n\n » d'un sous-titre ne doit pas être encadré par les espaces
    # ajoutés par la jointure : on les retire avant de rendre la ligne.
    return re.sub(r" *\n\n *", "\n\n", " ".join(parts))


def group_lines(items: list[dict]) -> list[dict]:
    """Regroupe les spans en lignes visuelles (même ordonnée y).

    Indispensable : le PDF fragmente la ligne école à cause de l'exposant
    « e » de « du 2e niveau », et les lignes de description ont un y0
    légèrement inférieur à celui de la ligne « Durée : » (métriques de
    police). Raisonner en lignes évite de mélanger les blocs.
    """
    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_y: float | None = None
    for it in items:
        if not cur:
            cur = [it]
            cur_y = it["y0"]
            continue
        prev = cur[-1]
        # Un span d'exposant (le « e » de « du 2e niveau ») a une taille très
        # inférieure au reste de la ligne : il doit être joint sans égard à la
        # garde de taille, sinon la ligne école est fragmentée.
        is_exposant = it["size"] < EXPOSANT_MAX_SIZE
        same_line = (
            abs(it["y0"] - cur_y) <= LINE_TOL
            and it["x0"] - prev["x1"] <= GAP_H_MAX
            and (is_exposant or abs(prev["size"] - it["size"]) <= SIZE_DROP_MAX)
        )
        if same_line:
            cur.append(it)
        else:
            groups.append(cur)
            cur = [it]
            cur_y = it["y0"]
    if cur:
        groups.append(cur)
    lines: list[dict] = []
    for group in groups:
        # À l'intérieur d'une ligne, on lit de gauche à droite : l'exposant
        # « e » de « du 2e niveau » a un y0 plus grand que le reste de la ligne
        # et serait mal placé si l'on conservait l'ordre du tri global.
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


def extract_school(text: str) -> str:
    m = re.search(
        r"(Abjuration|Appel|Conjuration|Divination|Enchantement|Invocation|Évocation|"
        r"Illusion|Nécromancie|Transmutation)",
        text,
    )
    return m.group(1) if m else ""


def parse_spells(lines: list[dict]) -> list[dict]:
    """Découpe la séquence de lignes en fiches de sort.

    Le corps est construit en deux passes : les lignes méta (identifiées par
    leur étiquette) sont émises avant la description, ce qui rend le découpage
    insensible au recouvrement de y0 entre « Durée : » et la description.
    """
    starts = [i for i in range(len(lines)) if is_spell_start(lines, i)]
    spells: list[dict] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(lines)
        name = lines[start]["text"].strip()
        if not name:
            continue
        j = start + 1
        parts: list[str] = []
        # La ligne école peut wrapper (liste de classes longue, ou nom en bas
        # de colonne) : on consomme toutes les lignes qui précèdent la
        # première ligne méta « Temps d'incantation : », en les joignant par
        # des espaces pour reformer une seule ligne logique.
        while j < end and not META_RE.match(lines[j]["text"].lstrip()):
            t = lines[j]["text"].strip()
            if t:
                parts.append(t)
            j += 1
        school_line = " ".join(parts)
        meta: list[str] = []
        desc: list[str] = []
        for k in range(j, end):
            t = lines[k]["text"].strip()
            if not t:
                continue
            if META_RE.match(t):
                meta.append(t)
            elif RUNIN_RE.match(t):
                # En-tête de paragraphe « Emplacement de niveau supérieur. » ou
                # « À plus haut niveau » : isolé, en gras, avant la suite.
                desc.append(f"\n\n**{t.rstrip('. ')}**\n\n")
            else:
                desc.append(t)
        body = f"{school_line}\n" + "\n".join(meta) if school_line else "\n".join(meta)
        if desc:
            body = f"{body}\n\n" + "\n".join(desc)
        body = clean_text(body)
        school = extract_school(body)
        spells.append(
            {
                "nom": name,
                "ecole": school,
                "corps": body,
                "page": lines[start]["page"],
            }
        )
    return spells


# --------------------------------------------------------------------------- #
# Rendu markdown
# --------------------------------------------------------------------------- #

def render_spell(spell: dict) -> str:
    slug = slugify(spell["nom"])
    ecole = spell["ecole"]
    mots_cles = f"sort, {ecole}" if ecole else "sort"
    lines: list[str] = []
    lines.append("<<<FICHE>>>")
    lines.append(f"id: sorts/{slug}")
    lines.append(f"nom: {spell['nom']}")
    lines.append("type: sort")
    lines.append("edition: SRD 5.2.1")
    lines.append(f"mots_cles: {mots_cles}")
    lines.append("<<<CONTENU>>>")
    lines.append("")
    lines.append(f"## {spell['nom']}")
    lines.append("")
    lines.append(spell["corps"].strip())
    lines.append("<<<FIN>>>")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction des sorts du SRD 5.2.1")
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
    doc.close()

    lines = group_lines(items)
    spells = parse_spells(lines)
    if not spells:
        print("Aucun sort détecté — vérifiez les bornes de pages.", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    written = 0
    seen: set[str] = set()
    for spell in spells:
        slug = slugify(spell["nom"])
        if slug in seen:
            print(f"  doublon ignoré : {spell['nom']}")
            continue
        seen.add(slug)
        (args.output / f"{slug}.md").write_text(
            render_spell(spell), encoding="utf-8"
        )
        written += 1

    # Index alphabétique (utile pour l'aliasing FR côté OWUI).
    index_lines = [
        "---",
        "id: index/sorts",
        "nom: Index des sorts",
        "type: index",
        "edition: SRD 5.2.1",
        "mots_cles: index, sorts",
        "---",
        "",
        "# Index des sorts",
        "",
    ]
    for spell in sorted(spells, key=lambda s: s["nom"]):
        index_lines.append(f"- {spell['nom']} → sorts/{slugify(spell['nom'])}.md")
    (args.output.parent / "00-index" / "sorts.md").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8"
    )

    print(f"{written} sorts écrits dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
