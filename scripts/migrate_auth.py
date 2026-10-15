"""Migration des données globales existantes vers un compte administrateur.

Avant l'authentification, les fiches/campagnes/combats vivaient à la racine des
dossiers `data-perso/`, `data-campagne/`, `data-combat/`. Avec l'isolation par
compte, chaque utilisateur a son sous-dossier `data/<user_id>/`. Ce script :

1. crée (ou retrouve) le compte administrateur depuis `ADMIN_EMAIL` / `ADMIN_PASSWORD` ;
2. déplace les fichiers encore présents à la RACINE de chaque dossier de données
   dans le sous-dossier de ce compte.

Idempotent : les fichiers déjà rangés dans un sous-dossier sont ignorés ; un
second appel ne déplace rien de plus.

Usage (dans le conteneur api, ou avec PYTHONPATH=apps/api:packages) :
    ADMIN_EMAIL=moi@exemple.fr ADMIN_PASSWORD='motdepasse' \
    python3 scripts/migrate_auth.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "apps" / "api"))
sys.path.insert(0, str(RACINE / "packages"))

from auth import store  # noqa: E402


def _dossier(env: str, defaut: str) -> Path:
    return Path(os.environ.get(env) or (RACINE / defaut))


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    mdp = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not mdp:
        print("Définir ADMIN_EMAIL et ADMIN_PASSWORD.", file=sys.stderr)
        return 2
    if len(mdp) < 8:
        print("ADMIN_PASSWORD doit faire au moins 8 caractères.", file=sys.stderr)
        return 2

    store.initialiser()
    utilisateur = store.par_email(email)
    if utilisateur is None:
        utilisateur = store.creer_utilisateur(email, mdp, verifie=True)
        print(f"Compte administrateur créé : {email} ({utilisateur.id})")
    else:
        print(f"Compte administrateur existant : {email} ({utilisateur.id})")

    dossiers = {
        "perso": _dossier("DND_PERSO_DIR", "data-perso"),
        "campagne": _dossier("DND_CAMPAGNE_DIR", "data-campagne"),
        "combat": _dossier("DND_COMBAT_DIR", "data-combat"),
    }

    total = 0
    for nom, base in dossiers.items():
        if not base.exists():
            print(f"[{nom}] dossier absent ({base}) — ignoré")
            continue
        cible = base / utilisateur.id
        cible.mkdir(parents=True, exist_ok=True)
        deplaces = 0
        for entree in sorted(base.iterdir()):
            if not entree.is_file():
                continue  # sous-dossiers déjà migrés → ignorés
            destination = cible / entree.name
            if destination.exists():
                print(f"[{nom}] existe déjà, ignoré : {entree.name}")
                continue
            shutil.move(str(entree), str(destination))
            deplaces += 1
        print(f"[{nom}] {deplaces} fichier(s) déplacé(s) vers {cible}")
        total += deplaces

    print(f"Migration terminée : {total} fichier(s) rattaché(s) au compte {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
