#!/usr/bin/env python3
"""Validation du corpus SRD 5.2.1 (fiches Markdown pour Open WebUI).

Vérifie, pour chaque fiche de chaque domaine :
  - fichier non vide
  - commence par « <<<FICHE>>> »
  - possède les champs id / nom / type / edition
  - contient « <<<CONTENU>>> » puis « <<<FIN>>> »

Affiche un comptage par domaine et la liste des anomalies.
Code de retour : 0 si aucune anomalie, 1 sinon.

Usage :
    python3 scripts/check_corpus.py [corpus_dir]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

CORPUS_DEFAULT = Path("dnd/srd-5.2.1")

# Domaines attendus, avec le nombre de fiches attendu (0 = non fourni volontairement).
DOMAINS = [
    ("01-chapitres", 9),
    ("02-sorts", 339),
    ("03-objets-magiques", 192),
    ("04-monstres", 305),
    ("05-lore", 0),
    ("06-tables-aleatoires", 8),
    ("07-appendices", 0),
]

REQUIRED_KEYS = ("id:", "nom:", "type:", "edition:")


def check_fiche(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"{path.name}: encodage UTF-8 invalide"]
    if not text.strip():
        return [f"{path.name}: fichier vide"]
    if not text.startswith("<<<FICHE>>>"):
        problems.append(f"{path.name}: en-tête <<<FICHE>>> manquant")
    header = text.split("<<<CONTENU>>>", 1)[0]
    for key in REQUIRED_KEYS:
        if f"\n{key}" not in header and not header.startswith(key):
            problems.append(f"{path.name}: champ {key} manquant")
    if "<<<CONTENU>>>" not in text:
        problems.append(f"{path.name}: <<<CONTENU>>> manquant")
    if "<<<FIN>>>" not in text:
        problems.append(f"{path.name}: <<<FIN>>> manquant")
    body = text.split("<<<CONTENU>>>", 1)
    if len(body) == 2:
        core = body[1].split("<<<FIN>>>")[0]
        if not core.strip():
            problems.append(f"{path.name}: corps de fiche vide")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Validation du corpus SRD 5.2.1")
    ap.add_argument("corpus", nargs="?", default=str(CORPUS_DEFAULT))
    args = ap.parse_args()

    root = Path(args.corpus)
    if not root.exists():
        print(f"Dossier introuvable : {root}", file=sys.stderr)
        return 2

    total = 0
    anomalies: list[str] = []
    for name, expected in DOMAINS:
        d = root / name
        if not d.exists():
            if expected:
                anomalies.append(f"{name}: dossier manquant")
            continue
        files = sorted(p for p in d.glob("*.md") if p.is_file())
        if len(files) != expected:
            anomalies.append(f"{name}: {len(files)} fiche(s) au lieu de {expected}")
        for f in files:
            total += 1
            anomalies.extend(check_fiche(f))
        print(f"{name}: {len(files)} fiche(s)")

    print(f"total: {total}")
    if anomalies:
        print("--- anomalies ---")
        for a in anomalies:
            print(f"- {a}")
        return 1
    print("corpus OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
