#!/usr/bin/env python3
"""Extraction des fiches « monstre » du SRD 5.2.1 (FR) vers un Markdown RAG.

Chaque monstre de la section « Monstres de A à Z » (pages 272 à 380 du PDF
FR_SRD_CC_v5.2.1.pdf) produit un fichier markdown autonome :

    <<<FICHE>>>
    id: monstres/<slug>
    nom: <Nom>
    type: monstre
    edition: SRD 5.2.1
    mots_cles: monstre
    <<<CONTENU>>>
    ## <Nom>
    <ligne d'identité>
    <CA / Initiative / Pv / Vitesse>
    <tableau des 6 caractéristiques : Score | Modificateur | Jet de sauvegarde>
    <Compétences / Sens / Langues / FP>
    <Traits / Actions / Actions Bonus / Réactions / Actions Légendaires>
    <<<FIN>>>

Le tableau des caractéristiques est reconstruit à partir des *mots* (et non
des lignes) car le PDF l'affiche en 3 colonnes de 2 caractéristiques : un
`get_text()` naïf intervertit MOD et JS.

Usage :
    python3 scripts/srd_monstres_to_fiches.py [pdf] [output] [--section monstres]
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pymupdf

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

PDF_DEFAULT = Path("dnd/FR_SRD_CC_v5.2.1.pdf")
OUT_DEFAULT = Path("DD/srd-5.2.1-md/monstres")

# Le PDF fait 380 pages ; la section monstres couvre les pages 272..380
# (index 271..379). Les monstres de la page 360 (Xorn, Zombi…) se
# prolongent au-delà de 360 : on lit donc jusqu'à la fin du PDF.
FIRST_PAGE = 271  # index 0-based de la page 272
LAST_PAGE = 380   # exclus

# Frontière de colonnes : gauche si x0 < 300, droite sinon (mesuré : gauche
# max ≈ 287, droite min ≈ 313 sur toute la section).
COL_SPLIT_X = 300.0

TYPE_RE = re.compile(
    r"^(?:Aberration|Artificiel|Bête|Céleste|Dragon|Élémentaire|Fée|Fiélon|"
    r"Géant|Humanoïde|Monstruosité|Mort-vivant|Plante)"
    r"(?:\s*\([^)]*\))?\s+de\s+taille\s+[A-ZÀ-Ü]+(?:\s+ou\s+[A-ZÀ-Ü]+)*"
    r"\s*,\s*[A-Za-zÀ-ÿ' ]+$"
)
PAGE_RE = re.compile(r"^\s*\d{1,3}\s*$")
HEADER_RE = re.compile(r"^\s*Document de Référence du Système(?: .*)?\s*$")
SECTION_HEADER = "Monstres de A à Z"

ABILITIES = ("For", "Dex", "Con", "Int", "Sag", "Cha")
ABILITY_FULL = {
    "For": "Force",
    "Dex": "Dextérité",
    "Con": "Constitution",
    "Int": "Intelligence",
    "Sag": "Sagesse",
    "Cha": "Charisme",
}

# Lignes de section du bloc de stats (utilisées pour couper les paragraphes).
SECTION_RE = re.compile(
    r"^(Compétences|Sens|Langues|FP|Traits|Actions Bonus|Actions Légendaires|"
    r"Actions|Réactions|Réaction|Légende)(?![A-Za-zÀ-ÿ])"
)

MINUS = "\u2212"  # U+2212 MINUS SIGN utilisé par le PDF


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def norm_sign(token: str) -> str:
    return token.replace(MINUS, "-").replace("+", "+")


def parse_signed(token: str) -> int | None:
    token = token.strip().replace(MINUS, "-")
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    return None


# --------------------------------------------------------------------------- #
# Découpage en lignes (par regroupement de mots sur un même y)
# --------------------------------------------------------------------------- #

def words_to_lines(words: list[tuple]) -> list[str]:
    """Regroupe les mots en lignes visuelles (même ordonnée y)."""
    lines: list[str] = []
    current: list[str] = []
    current_y: float | None = None
    for word in words:
        _x0, y0, _x1, _y1, token = word[0], word[1], word[2], word[3], word[4]
        if current_y is None or abs(y0 - current_y) <= 4.0:
            current.append(token)
            if current_y is None:
                current_y = y0
        else:
            lines.append(" ".join(current))
            current = [token]
            current_y = y0
    if current:
        lines.append(" ".join(current))
    return lines


# Zone à ignorer : bande de pied de page (y > 730), pour que le numéro de
# page et le titre du document ne se collent pas à la ligne de contenu
# voisine lors du regroupement par y. Le haut de page ne contient pas
# d'en-tête (le titre est en bas), on ne filtre donc pas en haut.
FOOTER_Y_MIN = 730.0


def column_words(page: pymupdf.Page, col: int) -> list[tuple]:
    words = page.get_text("words")
    out: list[tuple] = []
    for w in words:
        if w[1] > FOOTER_Y_MIN:
            continue
        if col == 0:
            if w[0] < COL_SPLIT_X:
                out.append(w)
        else:
            if w[0] >= COL_SPLIT_X:
                out.append(w)
    return out


# --------------------------------------------------------------------------- #
# Parsing d'un bloc de caractéristiques (le tableau MOD / JS)
# --------------------------------------------------------------------------- #

def parse_ability_table(lines: list[str]) -> list[tuple[str, int, int, int]]:
    """Retourne [(nom, score, modificateur, jet_de_sauvegarde), …] (6 entrées).

    Le PDF affiche 2 lignes de 3 caractéristiques (6 au total). On repère
    l'en-tête « MOD JS MOD JS MOD JS » puis on lit les 6 groupes de 4 tokens
    (nom, score, MOD, JS) qui suivent, avant la ligne « Compétences ».
    Le tableau peut se poursuivre sur la page suivante : on travaille sur les
    lignes du corps (déjà ordonnées), pas sur une seule page.
    """
    tokens: list[str] = []
    for line in lines:
        tokens.extend(line.split())
    # position de l'en-tête MOD
    start = None
    for i, tok in enumerate(tokens):
        if tok == "MOD":
            start = i
            break
    if start is None:
        return []

    abilities: list[tuple[str, int, int, int]] = []
    i = start
    # ignorer les 6 tokens d'en-tête (MOD JS MOD JS MOD JS)
    while i < len(tokens) and tokens[i] == "MOD":
        i += 1
        if i < len(tokens) and tokens[i] == "JS":
            i += 1
    while i + 3 < len(tokens):
        name = tokens[i]
        if name not in ABILITIES:
            break
        score = parse_signed(tokens[i + 1])
        mod = parse_signed(tokens[i + 2])
        js = parse_signed(tokens[i + 3])
        if score is None or mod is None:
            break
        if js is None:
            js = mod
        abilities.append((name, score, mod, js))
        i += 4
    return abilities


# --------------------------------------------------------------------------- #
# Parsing d'un monstre
# --------------------------------------------------------------------------- #

def parse_identity(type_line: str) -> tuple[str, str, str]:
    """« Aberration de taille G, Loyale Mauvaise » → (type, taille, alignement)."""
    m = re.match(r"^(?P<type>.*?)\s+de\s+taille\s+(?P<taille>[A-ZÀ-Ü]+)\s*,\s*(?P<align>.*?)\s*$", type_line)
    if not m:
        return (type_line.strip(), "", "")
    return (m.group("type").strip(), m.group("taille").strip(), m.group("align").strip())


def parse_monster(
    name: str,
    type_line: str,
    body_lines: list[str],
    page: pymupdf.Page,
    col: int,
    next_name: str = "",
) -> str:
    """Construit le markdown d'un monstre à partir de ses lignes de corps."""
    monster_type, taille, alignement = parse_identity(type_line)

    # --- Ligne d'identité ------------------------------------------------- #
    ident = f"**{monster_type}** de taille {taille}, {alignement}"

    # --- Retrait du paragraphe descriptif (lore) -------------------------- #
    # Le corps commence par le paragraphe descriptif, puis vient le bloc de
    # stats (CA …). Tout ce qui précède la ligne « CA » est de la lore et est
    # écarté (choix : fiche technique sans description narrative).
    start_stats = 0
    for idx, line in enumerate(body_lines):
        if re.search(r"\bCA\b", line):
            start_stats = idx
            break
    else:
        start_stats = 0
    body_lines = body_lines[start_stats:]

    # --- En-tête CA / Initiative / Pv / Vitesse --------------------------- #
    # Ces champs tiennent sur 1 à 2 lignes ; on les extrait par mot-clé.
    flat = " ".join(body_lines)
    flat = re.sub(r"\s+", " ", flat)

    def grab(pattern: str, text: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    ca = grab(r"\bCA\s+(\d+\s*(?:\([^)]*\))?)", flat)
    init = grab(r"Initiative\s+([+\u2212-]?\d+\s*(?:\(\d+\))?)", flat)
    pv = grab(r"\bPv\s+(\d+\s*\([^)]*\))", flat)
    vitesse = grab(r"Vitesse\s+(.*?)(?=\s+MOD\b|$)", flat)

    # --- Tableau des caractéristiques (depuis les lignes du corps) -------- #
    abilities = parse_ability_table(body_lines)

    # --- Lignes suivantes (Compétences → fin) ----------------------------- #
    # On retire les lignes déjà consommées (en-tête + tableau) du corps.
    prose: list[str] = []
    for line in body_lines:
        s = line.strip()
        if not s:
            continue
        if next_name and s == next_name.strip():
            continue  # nom du monstre suivant (fuite en fin de bloc)
        if re.match(r"^(?:CA|Initiative|Pv|Vitesse)\b", s):
            continue  # ligne CA / Initiative / Pv / Vitesse (déjà extraite)
        if s.startswith("MOD"):
            continue  # en-tête du tableau de caractéristiques
        if re.match(r"^(?:For|Dex|Con|Int|Sag|Cha)\b", s):
            continue  # ligne de caractéristique (déjà dans le tableau)
        if re.fullmatch(r"[+\u2212-]?\d+(\s+\(\d+\))?", s):
            continue  # jet de sauvegarde orphelin
        prose.append(s)

    # --- Reconstruction des paragraphes ----------------------------------- #
    TRAIT_RE = re.compile(r"^[A-ZÀÉ][a-zà-ÿ’]+(?:\s+[a-zà-ÿ’]+)*\.\s")
    paragraphs: list[str] = []
    current: list[str] = []
    for line in prose:
        if TRAIT_RE.match(line) and current:
            paragraphs.append(" ".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        paragraphs.append(" ".join(current))

    # --- Assemblage -------------------------------------------------------- #
    out: list[str] = []
    out.append(f"## {name}")
    out.append("")
    out.append(ident)
    out.append("")
    out.append(f"- **CA :** {ca}" if ca else "- **CA :** —")
    out.append(f"- **Initiative :** {init}" if init else "- **Initiative :** —")
    out.append(f"- **Pv :** {pv}" if pv else "- **Pv :** —")
    out.append(f"- **Vitesse :** {vitesse}" if vitesse else "- **Vitesse :** —")
    out.append("")
    out.append("| Caractéristique | Score | Modificateur | Jet de sauvegarde |")
    out.append("| --- | --- | --- | --- |")
    for ab_name, score, mod, js in abilities:
        label = ABILITY_FULL.get(ab_name, ab_name)
        out.append(f"| {label} | {score} | {mod:+d} | {js:+d} |")
    if not abilities:
        out.append("| — | — | — | — |")
    out.append("")

    # Lignes structurées Compétences / Sens / Langues / FP
    for line in prose:
        m = re.match(r"^(Compétences|Sens|Langues|FP)\s*[:\s]\s*(.*)$", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            out.append(f"**{key} :** {val}")
    # tout le reste = Traits / Actions / …
    rest: list[str] = []
    for line in prose:
        if re.match(r"^(Compétences|Sens|Langues|FP)\b", line):
            continue
        rest.append(line)

    # Découpe en sections Traits / Actions / Actions Bonus / Réactions / Actions Légendaires
    SECTION_TITLES = {
        "Traits": "Traits",
        "Actions": "Actions",
        "Actions Bonus": "Actions Bonus",
        "Réactions": "Réactions",
        "Réaction": "Réactions",
        "Actions Légendaires": "Actions Légendaires",
    }
    section_lines_map: dict[str, list[str]] = {}
    current_section = None
    for line in rest:
        if line in SECTION_TITLES:
            current_section = SECTION_TITLES[line]
            section_lines_map.setdefault(current_section, [])
        else:
            if current_section is None:
                current_section = "Traits"
                section_lines_map.setdefault(current_section, [])
            section_lines_map[current_section].append(line)

    if section_lines_map:
        for title in ("Traits", "Actions", "Actions Bonus", "Réactions", "Actions Légendaires"):
            lines = section_lines_map.get(title)
            if not lines:
                continue
            out.append(f"### {title}")
            out.append("")
            # paragraphes : nouvelle ligne = nouvelle puce si nom de trait
            para: list[str] = []
            for line in lines:
                if TRAIT_RE.match(line) and para:
                    out.append(" ".join(para))
                    out.append("")
                    para = [line]
                else:
                    para.append(line)
            if para:
                out.append(" ".join(para))
                out.append("")

    body = "\n".join(out).rstrip() + "\n"
    fiche = (
        "<<<FICHE>>>\n"
        f"id: monstres/{slugify(name)}\n"
        f"nom: {name}\n"
        "type: monstre\n"
        "edition: SRD 5.2.1\n"
        "mots_cles: monstre\n"
        "<<<CONTENU>>>\n"
        f"{body}"
        "<<<FIN>>>\n"
    )
    return fiche, bool(abilities)


# --------------------------------------------------------------------------- #
# Parcours de la section monstres
# --------------------------------------------------------------------------- #

def parse_monsters(pdf_path: Path) -> list[tuple[str, str, bool]]:
    doc = pymupdf.open(str(pdf_path))
    entries: list[tuple[str, str, bool]] = []

    # Lignes globales ordonnées (gauche puis droite, page à page).
    global_lines: list[tuple[str, int, int]] = []  # (texte, page, col)
    for pno in range(FIRST_PAGE, LAST_PAGE):
        page = doc[pno]
        for col in (0, 1):
            words = column_words(page, col)
            for line in words_to_lines(words):
                s = line.strip()
                if not s or PAGE_RE.match(s) or HEADER_RE.match(s) or s == SECTION_HEADER:
                    continue
                global_lines.append((s, pno, col))

    # repérer les lignes de type (= début de monstre)
    # ignorer les faux départs : si la ligne qui précède la ligne de type
    # contient une phrase de trait (« Changement d'aspect. … »), ce n'est pas
    # le nom du monstre suivant (le bloc précédent se poursuit sur la colonne)
    starts: list[int] = []
    for i, (text, _p, _c) in enumerate(global_lines):
        if TYPE_RE.match(text):
            if i > 0 and ". " in global_lines[i - 1][0]:
                continue
            starts.append(i)

    for k, start in enumerate(starts):
        name = global_lines[start - 1][0] if start > 0 else ""
        # le nom doit précéder la ligne de type ; s'il est vide, on tente +1
        if not name or TYPE_RE.match(name):
            # chercher le nom sur la ligne précédente non vide
            j = start - 1
            while j >= 0 and not global_lines[j][0]:
                j -= 1
            name = global_lines[j][0] if j >= 0 else ""
        # le corps s'arrête avant la ligne de nom du monstre suivant
        end = starts[k + 1] - 1 if k + 1 < len(starts) else len(global_lines)
        body = [global_lines[i][0] for i in range(start + 1, end)]
        next_name = global_lines[end][0] if end < len(global_lines) else ""
        _text, pno, col = global_lines[start]
        page = doc[pno]
        fiche, ok = parse_monster(name, global_lines[start][0], body, page, col, next_name)
        entries.append((name, fiche, ok))

    doc.close()
    return entries


# --------------------------------------------------------------------------- #
# Écriture
# --------------------------------------------------------------------------- #

def write_monster_fiches(
    entries: list[tuple[str, str, bool]], output_dir: Path
) -> tuple[int, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fiches: list[str] = []
    incomplete: list[str] = []
    seen: set[str] = set()
    for name, fiche, ok in entries:
        slug = slugify(name)
        if not ok:
            incomplete.append(f"monstres/{slug}")
        # gérer les homonymes
        target = output_dir / f"{slug}.md"
        if slug in seen:
            n = 2
            while (output_dir / f"{slug}-{n}.md").exists():
                n += 1
            slug = f"{slug}-{n}"
            target = output_dir / f"{slug}.md"
        seen.add(slug)
        target.write_text(fiche, encoding="utf-8")
        fiches.append(fiche)

    consolidated = "\n".join(fiches)
    bilan = ",".join(incomplete)
    (output_dir / "index.md").write_text(
        f"{consolidated}\n<<<BILAN>>> fiches_emises={len(fiches)} "
        f"| fiches_incompletes=[{bilan}]\n",
        encoding="utf-8",
    )
    return len(fiches), incomplete


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Fiches monstres SRD 5.2.1 → Markdown RAG")
    parser.add_argument("pdf", nargs="?", type=Path, default=PDF_DEFAULT)
    parser.add_argument("output", nargs="?", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--section", default="monstres", choices=("monstres",))
    args = parser.parse_args()

    entries = parse_monsters(args.pdf)
    count, incomplete = write_monster_fiches(entries, args.output)
    print(f"fiches_emises={count}")
    print(f"fiches_incompletes={incomplete}")
    print(f"sortie={args.output}")


if __name__ == "__main__":
    main()
