"""Routes d'authentification par compte (email + mot de passe).

Montées sous `/api/auth/*`, elles sont les SEULES routes publiques de l'API
(pas de `X-Session` requis). L'API ne pose jamais de cookie : elle est interne
et ne voit que Next. Elle renvoie le jeton de session dans le corps JSON ;
c'est Next (`app/api/auth/[...chemin]/route.ts`) qui le place dans un cookie
httpOnly signé côté navigateur.

Endpoints :
- POST /register        — inscription (libre) ; envoie le lien de vérification.
- POST /verify          — active le compte via le jeton du lien.
- POST /login           — connexion ; renvoie le jeton de session.
- POST /logout          — no-op côté API (Next supprime le cookie).
- POST /forgot          — demande de réinitialisation (envoie le lien).
- POST /reset           — applique un nouveau mot de passe via le jeton.
- GET  /me              — renvoie le compte courant (session requise).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends

from auth import mailer, scope, security, store
from jdr_api.commun import V, enveloppe
from settings import settings

router = APIRouter()


def _erreur(message: str) -> dict[str, Any]:
    return {"ok": False, "v": V, "type": "erreur", "erreur": message}


@router.post("/api/auth/register")
def register(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    email = str(body.get("email", "")).strip().lower()
    mdp = str(body.get("mot_de_passe", ""))
    if not store.email_valide(email):
        return _erreur("Adresse email invalide.")
    if len(mdp) < 8:
        return _erreur("Le mot de passe doit faire au moins 8 caractères.")
    try:
        utilisateur = store.creer_utilisateur(email, mdp)
    except ValueError as exc:
        return _erreur(str(exc))
    jeton = security.signer({"uid": utilisateur.id, "but": "verify"}, settings.auth_secret, settings.lien_duree_s)
    store.definir_token_verify(utilisateur.id, jeton)
    envoye = mailer.envoyer_verification(email, jeton)
    return enveloppe(
        {
            "ok": True,
            "type": "inscrit",
            "email": email,
            "verifie": utilisateur.verifie,
            # En mode console (pas de SMTP), on renvoie le lien pour que l'UI
            # puisse le proposer directement — jamais présent quand un SMTP est actif.
            "lien_verification": None if envoye else mailer.lien_verification(jeton),
        }
    )


@router.post("/api/auth/verify")
def verify(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    jeton = str(body.get("token", ""))
    utilisateur = store.valider_par_token_verify(jeton)
    if utilisateur is None:
        return _erreur("Lien de vérification invalide ou expiré.")
    return enveloppe({"ok": True, "type": "verifie", "email": utilisateur.email})


@router.post("/api/auth/login")
def login(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    email = str(body.get("email", "")).strip().lower()
    mdp = str(body.get("mot_de_passe", ""))
    utilisateur = store.verifier_mot_de_passe(email, mdp)
    if utilisateur is None:
        return _erreur("Email ou mot de passe incorrect.")
    session = scope.emettre_session(utilisateur.id)
    return enveloppe(
        {
            "ok": True,
            "type": "connecte",
            "email": utilisateur.email,
            "verifie": utilisateur.verifie,
            "session": session,
        }
    )


@router.post("/api/auth/logout")
def logout() -> dict[str, Any]:
    # L'API est sans état : la déconnexion = suppression du cookie côté Next.
    return enveloppe({"ok": True, "type": "deconnecte"})


@router.post("/api/auth/forgot")
def forgot(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    email = str(body.get("email", "")).strip().lower()
    jeton = security.signer({"uid": email, "but": "reset"}, settings.auth_secret, settings.lien_duree_s)
    utilisateur = store.definir_token_reset(email, jeton)
    if utilisateur is not None:
        mailer.envoyer_reinitialisation(email, jeton)
    # Réponse identique que le compte existe ou non (pas d'énumération de comptes).
    return enveloppe({"ok": True, "type": "envoye"})


@router.post("/api/auth/reset")
def reset(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    jeton = str(body.get("token", ""))
    mdp = str(body.get("mot_de_passe", ""))
    if len(mdp) < 8:
        return _erreur("Le mot de passe doit faire au moins 8 caractères.")
    utilisateur = store.reinitialiser_mdp(jeton, mdp)
    if utilisateur is None:
        return _erreur("Lien de réinitialisation invalide ou expiré.")
    return enveloppe({"ok": True, "type": "reinitialise", "email": utilisateur.email})


@router.get("/api/auth/me")
def moi(compte: scope.Compte = Depends(scope.utilisateur_courant)) -> dict[str, Any]:
    return enveloppe({"ok": True, "type": "moi", "email": compte.email, "verifie": compte.verifie})


@router.post("/api/auth/delete")
def supprimer(
    body: dict[str, Any] = Body(...),
    compte: scope.Compte = Depends(scope.utilisateur_courant),
) -> dict[str, Any]:
    """Supprime définitivement le compte courant et toutes ses données.

    Exige le mot de passe (confirmation). Irréversible : la ligne SQLite et les
    dossiers perso/campagne/combat du compte sont effacés. Le frontend (Next)
    efface le cookie de session sur le type `supprime`.
    """
    import shutil

    from dnd_perso import extract

    mdp = str(body.get("mot_de_passe", ""))
    if not mdp:
        return _erreur("Le mot de passe est requis pour confirmer la suppression.")
    if not store.supprimer_utilisateur(compte.id, mdp):
        return _erreur("Mot de passe incorrect.")
    for dossier in extract.dossiers_utilisateur(compte.id):
        shutil.rmtree(dossier, ignore_errors=True)
    return enveloppe({"ok": True, "type": "supprime", "email": compte.email})
