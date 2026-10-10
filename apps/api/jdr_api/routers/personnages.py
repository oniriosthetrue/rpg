"""Routes de gestion des personnages sauvegardés — contrat §5.

Les fiches vivent dans `extract.PERSO_DIR` (volume `data-perso/`), en
fichiers `<nom>.json` (+ `<nom>.md`) écrits par `dnd_perso.export`.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Header

from openui import mj

from jdr_api.commun import V, autorise, enveloppe

router = APIRouter()

# Nom de personnage : caractères autorisés uniquement (anti traversée de chemin).
_NOM_RE = re.compile(r"[\w éèêëàâäîïôöùûüçœ’'-]{1,64}", re.UNICODE)


def _valider_nom(nom: str) -> dict[str, Any] | None:
    """Valide un nom de personnage ; None si OK, sinon une enveloppe d'erreur."""
    nom = (nom or "").strip()
    if not nom or ".." in nom or not _NOM_RE.fullmatch(nom):
        return {"ok": False, "v": V, "type": "erreur", "erreur": "Nom de personnage invalide."}
    return None


@router.get("/api/personnages")
def lister_personnages(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Liste tous les personnages sauvegardés (nom, espece, classe, niveau…)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.lister_personnages())


@router.get("/api/personnages/{nom}")
def charger_personnage(
    nom: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Charge la fiche d'un personnage (markdown + dict + date de modification)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_nom(nom)) is not None:
        return err
    return enveloppe(mj.charger_personnage(nom))


@router.patch("/api/personnages/{nom}")
def modifier_personnage(
    nom: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Applique une liste d'actions closes (soigner, degats, gagner_xp…).

    Corps attendu : {"actions": [{"action": "soigner", "valeur": 5}, ...]}
    Toute action inconnue fait échouer la requête (contrat §5/§6).
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_nom(nom)) is not None:
        return err
    actions = body.get("actions")
    if not isinstance(actions, list):
        return enveloppe({
            "ok": False,
            "type": "erreur",
            "erreur": "Corps invalide : « actions » doit être une liste.",
        })
    return enveloppe(mj.modifier_personnage(nom, actions))


@router.delete("/api/personnages/{nom}")
def supprimer_personnage(
    nom: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Supprime la fiche d'un personnage (fichier .json + .md)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_nom(nom)) is not None:
        return err
    return enveloppe(mj.supprimer_personnage(nom))
