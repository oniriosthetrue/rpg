"""Isolation des données par utilisateur + dépendance d'authentification API.

Le frontend (Next) vérifie le cookie de session puis relaie le jeton signé à
l'API via l'en-tête interne `X-Session`. L'API **re-vérifie la signature** du
jeton (elle reste autorité : elle ne fait pas aveuglément confiance à l'en-tête)
et, si elle est valide, fixe le sous-dossier d'utilisateur pour la requête
(`extract.definir_utilisateur`) : toutes les lectures/écritures de fiches,
campagnes et combats sont alors confinées au dossier du compte.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import Header, Request

from auth import security, store
from dnd_perso import extract

# Nom de l'en-tête interne transportant le jeton de session (relaisé par Next).
EN_TETE_SESSION = "X-Session"


@dataclass(frozen=True)
class Compte:
    id: str
    email: str
    verifie: bool


def _secret() -> str:
    from settings import settings

    return settings.auth_secret


def identifiant_session(jeton: str) -> str | None:
    """Retourne l'identifiant de compte porté par un jeton de session valide."""
    charge = security.verifier(jeton, _secret())
    return charge.get("uid") if charge else None


async def utilisateur_courant(
    request: Request,
    x_session: str | None = Header(default=None, alias=EN_TETE_SESSION),
) -> Iterator[Compte]:
    """Dépendance FastAPI : exige une session valide et isole les données du compte.

    Lève `HTTPException(401)` si le jeton est absent/invalide/expiré. En cas de
    succès, fixe le sous-dossier d'utilisateur pour la tâche courante et le
    rétablit en fin de requête (generator dependency → `finally`).
    """
    from fastapi import HTTPException

    if not x_session:
        raise HTTPException(status_code=401, detail="Authentification requise.")
    uid = identifiant_session(x_session)
    if not uid:
        raise HTTPException(status_code=401, detail="Session invalide ou expirée.")
    utilisateur = store.par_id(uid)
    if utilisateur is None:
        raise HTTPException(status_code=401, detail="Compte introuvable.")
    compte = Compte(id=utilisateur.id, email=utilisateur.email, verifie=utilisateur.verifie)
    token = extract.definir_utilisateur(compte.id)
    request.state.token_utilisateur = token
    try:
        yield compte
    finally:
        extract.restaurer_utilisateur(token)


def emettre_session(compte_id: str) -> str:
    """Fabrique un jeton de session signé pour un compte."""
    return security.signer({"uid": compte_id}, _secret(), _duree_session())


def _duree_session() -> int:
    from settings import settings

    return settings.session_duree_s
