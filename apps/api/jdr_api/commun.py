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
    """Contrôle d'accès déprécié : l'authentification passe désormais par la
    session par compte (`scope.utilisateur_courant`, en-tête `X-Session`),
    appliquée au niveau des routers dans `main.py`. Cette fonction ne bloque
    donc plus rien et n'est conservée que pour ne pas casser d'éventuels
    appels résiduels ; elle retournera `None` (accès libre) dans tous les cas.
    """
    return None
