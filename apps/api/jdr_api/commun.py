"""Aides partagées par les routers : enveloppe JSON et contrôle d'accès.

Voir `dnd/CONTRAT-API-JDR.md` §1 (enveloppe) et §7 (authentification).
"""

from __future__ import annotations

import os
from typing import Any

# Version du contrat (contrat §1 : ne jamais changer sans concertation).
V = 1


def enveloppe(d: dict[str, Any]) -> dict[str, Any]:
    """Ajoute le champ de version `v` à une réponse produite par `mj`."""
    if "v" not in d:
        d = dict(d)
        d["v"] = V
    return d


def autorise(x_api_key: str | None) -> dict[str, Any] | None:
    """Vérifie l'en-tête `X-API-Key` quand `DND_API_KEY` est configuré.

    Renvoie None si l'accès est libre ou autorisé, sinon une enveloppe
    `type: "erreur"` que le router doit renvoyer telle quelle.
    """
    attendue = os.environ.get("DND_API_KEY", "").strip()
    if not attendue:
        return None
    if (x_api_key or "").strip() == attendue:
        return None
    return {
        "ok": False,
        "v": V,
        "type": "erreur",
        "erreur": "Accès refusné : clé d'API manquante ou invalide.",
    }
