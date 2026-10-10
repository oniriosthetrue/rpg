#!/usr/bin/env python3
"""Extract autonomous Markdown fiches from the French SRD PDF."""

from __future__ import annotations

import argparse
import re
import textwrap
import unicodedata
from pathlib import Path

import pymupdf


LEVEL_RE = re.compile(
    r"^(?:Sort\s+mineur|(?:Abjuration|Conjuration|Divination|Enchantement|"
    r"Évocation|Illusion|Nécromancie|Transmutation)\s+du\s+"
    r"(?:[1-9]er|[2-9]e)\s+niveau)"
)
MONSTER_TYPE_RE = re.compile(
    r"^(?:Aberration|Artificiel|Bête|Céleste|Dragon|Élémentaire|Fée|Fiélon|"
    r"Géant|Humanoïde|Monstruosité|Mort-vivant|Plante) de taille\s+"
)
ITEM_TYPE_RE = re.compile(
    r"^(?:Anneau|Arme|Armure|Baguette|Bâton|Objet merveilleux|Parchemin|"
    r"Potion|Sceptre),"
)
CLASS_NAMES = {
    "Barbare", "Barde", "Clerc", "Druide", "Ensorceleur", "Guerrier",
    "Magicien", "Moine", "Occultiste", "Paladin", "Rôdeur", "Roublard",
}
PAGE_RE = re.compile(r"^\s*\d{1,3}\s*$")
HEADER_RE = re.compile(r"^\s*Document de Référence du Système(?: .*)?\s*$")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def page_columns(page: pymupdf.Page) -> list[str]:
    blocks = []
    for block in page.get_text("blocks"):
        x0, y0, x1, y1, text, *_ = block
        if y0 > page.rect.height - 42 or y1 < 18:
            continue
        blocks.append((x0, y0, x1, y1, text))

    if not blocks:
        return []
    midpoint = page.rect.width / 2
    columns = [[], []]
    for block in blocks:
        x0, y0, x1, y1, text = block
        column = 0 if (x0 + x1) / 2 < midpoint else 1
        columns[column].append(block)

    result = []
    for column in columns:
        column.sort(key=lambda block: (block[1], block[0]))
        for block in column:
            result.extend(block[4].splitlines())
    return result


def clean_lines(lines: list[str]) -> list[str]:
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line or HEADER_RE.match(line) or PAGE_RE.match(line):
            continue
        cleaned.append(line)
    return cleaned


BREAK_RE = re.compile(
    r"^(?:Temps d’incantation|Portée|Composantes|Durée|CA|Initiative|Pv|Vitesse|"
    r"MOD|JS|For|Dex|Con|Int|Sag|Cha|Compétences|Sens|Langues|FP|Traits|"
    r"Actions|Actions Bonus|Réactions|Actions Légendaires|Sorts|Aptitudes|"
    r"Niveau|Caractéristique|Dé de vie|Maîtrises|Formation|Équipement|"
    r"Prérequis|Répétable|Catégorie|Utilisations|\*\*\||•)(?![A-Za-zÀ-ÿ])"
 )


def format_body(lines: list[str]) -> str:
    paragraphs = []
    current = ""
    for line in lines:
        starts_metadata = bool(BREAK_RE.match(line) or LEVEL_RE.match(line))
        if starts_metadata and current:
            paragraphs.append(current)
            current = ""
        if current.endswith("-") and line[:1].islower():
            current = current[:-1] + line
        elif current:
            current += " " + line
        else:
            current = line
        if line.startswith("Durée"):
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return "\n\n".join(
        textwrap.fill(
            paragraph,
            width=72,
            break_long_words=False,
            break_on_hyphens=False,
        )
        for paragraph in paragraphs
    )


def section_lines(pdf_path: Path, first_page: int, last_page: int) -> list[str]:
    document = pymupdf.open(pdf_path)
    lines: list[str] = []
    for page_number in range(first_page, last_page):
        lines.extend(page_columns(document[page_number]))
    return clean_lines(lines)


def parse_spells(pdf_path: Path) -> list[tuple[str, list[str]]]:
    lines = section_lines(pdf_path, 113, 186)

    start = next(
        i
        for i, line in enumerate(lines)
        if line == "Description des sorts"
        or line.replace(" ", "") == "Descriptiondessorts"
    )
    lines = lines[start + 1 :]

    starts = []
    for index in range(len(lines) - 1):
        next_lines = " ".join(lines[index + 1 : index + 4])
        if LEVEL_RE.search(next_lines):
            starts.append(index)
    spells = []
    for position, start_index in enumerate(starts):
        end_index = starts[position + 1] if position + 1 < len(starts) else len(lines)
        name = lines[start_index]
        body = lines[start_index:end_index]
        spells.append((name, body))
    return spells


def parse_repeated_entries(
    pdf_path: Path, first_page: int, last_page: int, detail_pattern: re.Pattern[str]
) -> list[tuple[str, list[str]]]:
    lines = section_lines(pdf_path, first_page, last_page)
    starts = []
    for index in range(len(lines) - 2):
        if lines[index] == lines[index + 1] and detail_pattern.search(lines[index + 2]):
            starts.append(index)
    return [
        (
            lines[start_index],
            lines[start_index : starts[position + 1] if position + 1 < len(starts) else len(lines)],
        )
        for position, start_index in enumerate(starts)
    ]


def parse_items(pdf_path: Path) -> list[tuple[str, list[str]]]:
    lines = section_lines(pdf_path, 220, 267)
    starts = [
        index
        for index in range(len(lines) - 1)
        if ITEM_TYPE_RE.search(lines[index + 1])
    ]
    return [
        (
            lines[start_index],
            lines[start_index : starts[position + 1] if position + 1 < len(starts) else len(lines)],
        )
        for position, start_index in enumerate(starts)
    ]


def parse_classes(pdf_path: Path) -> list[tuple[str, list[str]]]:
    lines = section_lines(pdf_path, 29, 87)
    starts = [
        index
        for index, line in enumerate(lines)
        if line in CLASS_NAMES
        and any(
            lines[index + offset] in {
                f"Traits de base du {line}",
                f"Traits de base de l’{line}",
            }
            for offset in range(1, 5)
            if index + offset < len(lines)
        )
    ]
    return [
        (
            lines[start_index],
            lines[start_index : starts[position + 1] if position + 1 < len(starts) else len(lines)],
        )
        for position, start_index in enumerate(starts)
    ]


def parse_equipment_tables(pdf_path: Path) -> list[tuple[str, list[str]]]:
    document = pymupdf.open(pdf_path)
    tables = []
    for page_number in range(94, 110):
        page = document[page_number]
        for table_number, table in enumerate(page.find_tables(strategy="lines").tables, 1):
            rows = table.extract()
            if not rows:
                continue
            preceding = [
                block[4].splitlines()[-1].strip()
                for block in page.get_text("blocks")
                if block[3] <= table.bbox[1] and block[4].strip()
            ]
            title = preceding[-1] if preceding else f"Tableau {page_number + 1}-{table_number}"
            tables.append((title, rows))
    return tables


def write_fiches(
    entries: list[tuple[str, list[str]]], output_dir: Path, entry_type: str, prefix: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_fiches = []
    for name, body in entries:
        identifier = f"{prefix}/{slugify(name)}"
        content = format_body(body)
        fiche = (
            "<<<FICHE>>>\n"
            f"id: {identifier}\n"
            f"nom: {name}\n"
            f"type: {entry_type}\n"
            "edition: SRD 5.2.1\n"
            f"mots_cles: {entry_type}\n"
            "<<<CONTENU>>>\n"
            f"## {name}\n\n{content}\n"
            "<<<FIN>>>\n"
        )
        (output_dir / f"{slugify(name)}.md").write_text(fiche, encoding="utf-8")
        all_fiches.append(fiche)

    incomplete = [
        f"{prefix}/{slugify(name)}"
        for name, body in entries
        if "[NON PRÉCISÉ]" in "\n".join(body)
    ]
    bilan = ",".join(incomplete)
    consolidated = "\n".join(all_fiches)
    (output_dir / "index.md").write_text(
        f"{consolidated}\n<<<BILAN>>> fiches_emises={len(entries)} "
        f"| fiches_incompletes=[{bilan}]\n",
        encoding="utf-8",
    )


def write_table_fiches(tables: list[tuple[str, list[str]]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fiches = []
    for name, rows in tables:
        safe_rows = [[cell or "[NON PRÉCISÉ]" for cell in row] for row in rows]
        header = safe_rows[0]
        markdown = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        markdown.extend("| " + " | ".join(row) + " |" for row in safe_rows[1:])
        identifier = f"equipement/{slugify(name)}"
        fiche = (
            "<<<FICHE>>>\n"
            f"id: {identifier}\n"
            f"nom: {name}\n"
            "type: table\n"
            "edition: SRD 5.2.1\n"
            "mots_cles: equipement, table\n"
            "<<<CONTENU>>>\n"
            f"## {name}\n\n" + "\n".join(markdown) + "\n<<<FIN>>>\n"
        )
        (output_dir / f"{slugify(name)}.md").write_text(fiche, encoding="utf-8")
        fiches.append(fiche)
    (output_dir / "index.md").write_text(
        "\n".join(fiches)
        + f"\n<<<BILAN>>> fiches_emises={len(fiches)} | fiches_incompletes=[]\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--section",
        choices=("sorts", "monstres", "objets", "classes", "equipement"),
        default="sorts",
    )
    args = parser.parse_args()
    if args.section == "sorts":
        entries, entry_type, prefix = parse_spells(args.pdf), "sort", "sorts"
    elif args.section == "monstres":
        entries = parse_repeated_entries(args.pdf, 271, 380, MONSTER_TYPE_RE)
        entry_type, prefix = "monstre", "monstres"
    elif args.section == "objets":
        entries = parse_items(args.pdf)
        entry_type, prefix = "objet", "objets"
    elif args.section == "classes":
        entries = parse_classes(args.pdf)
        entry_type, prefix = "classe", "classes"
    else:
        write_table_fiches(parse_equipment_tables(args.pdf), args.output)
        return
    write_fiches(entries, args.output, entry_type, prefix)
    incomplete = [
        f"{prefix}/{slugify(name)}"
        for name, body in entries
        if "[NON PRÉCISÉ]" in "\n".join(body)
    ]
    print(f"fiches_emises={len(entries)}")
    print(f"fiches_incompletes={incomplete}")


if __name__ == "__main__":
    main()