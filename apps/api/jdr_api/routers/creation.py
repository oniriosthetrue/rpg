"""Routes de création guidée de personnage — contrat §4.

Le router ne fait que traduire HTTP <-> appels à `openui.mj` ; tout le
métier (questions, choix, jets, tables) reste dans `mj.py`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Header, Query

from openui import mj

from jdr_api.commun import autorise, enveloppe

router = APIRouter()


@router.post("/api/creation")
def demarrer_creation(
    body: dict[str, Any] = Body(default={}),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Démarre une création : renvoie la première question + les options."""
    if (err := autorise(x_api_key)) is not None:
        return err
    chat_id = str(body.get("chat_id") or "defaut")
    seed = body.get("seed")
    return enveloppe(mj.demarrer(chat_id, seed))


@router.post("/api/creation/{chat_id}/reponse")
def repondre(
    chat_id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Transmet la réponse du joueur (mot pour mot) et pose la suite."""
    if (err := autorise(x_api_key)) is not None:
        return err
    reponse = str(body.get("reponse", "") or "")
    return enveloppe(mj.continuer(chat_id, reponse))


@router.post("/api/creation/{chat_id}/retour")
def revenir(
    chat_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Revient à l'étape précédente (efface cette étape et les suivantes)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.revenir(chat_id))


@router.post("/api/creation/{chat_id}/abandon")
def abandonner(
    chat_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Interrompt proprement la création en cours."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.abandonner(chat_id))


@router.post("/api/creation/{chat_id}/finaliser")
def finaliser(
    chat_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Force la finalisation : renvoie la fiche complète (type: « fiche »)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.personnage_final(chat_id))


@router.get("/api/creation/{chat_id}/etat")
def etat(
    chat_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Retourne l'état de la session (etape, answers, avertissements)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.etat_session(chat_id))


@router.get("/api/creation/{chat_id}/options")
def options(
    chat_id: str,
    etape: str = Query(..., description="Nom de l'étape, ex. « classe »."),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Liste les options d'une étape (« quelles classes ? »…)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    return enveloppe(mj.lister_options(etape, chat_id))
