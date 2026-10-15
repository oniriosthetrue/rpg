"""Persistance des comptes dans un fichier SQLite (volume dédié).

Une seule table `utilisateurs`. L'accès est volontairement minimal (stdlib
`sqlite3`) : l'app est mono-process (uvicorn), les écritures sont rares
(inscription, vérification, réinitialisation).

Le chemin de la base vient de l'env `DND_AUTH_DB` (défaut : `data/auth.db`).
"""

from __future__ import annotations

import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from auth import security

# Email : validation simple (le lien de vérification fait le vrai contrôle).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_valide(email: str) -> bool:
    return bool(_EMAIL_RE.fullmatch((email or "").strip().lower()))


def _chemin_db() -> Path:
    return Path(os.environ.get("DND_AUTH_DB") or (Path(__file__).resolve().parent / "data" / "auth.db"))


@dataclass(frozen=True)
class Utilisateur:
    id: str
    email: str
    verifie: bool

    @property
    def email_normalise(self) -> str:
        return self.email.strip().lower()


@contextmanager
def _connexion() -> Iterator[sqlite3.Connection]:
    chemin = _chemin_db()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def initialiser() -> None:
    """Crée la table si absente (idempotent — appelé au démarrage de l'API)."""
    with _connexion() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id           TEXT PRIMARY KEY,
                email        TEXT NOT NULL UNIQUE,
                hash_mdp     TEXT NOT NULL,
                verifie      INTEGER NOT NULL DEFAULT 0,
                token_verify TEXT,
                token_reset  TEXT,
                cree_le      TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


def creer_utilisateur(email: str, mot_de_passe: str, *, verifie: bool = False) -> Utilisateur:
    """Insère un compte. Lève `ValueError` si l'email existe déjà."""
    email = email.strip().lower()
    uid = uuid.uuid4().hex
    with _connexion() as conn:
        try:
            conn.execute(
                "INSERT INTO utilisateurs (id, email, hash_mdp, verifie) VALUES (?, ?, ?, ?)",
                (uid, email, security.hacher_mot_de_passe(mot_de_passe), 1 if verifie else 0),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Un compte existe déjà avec cet email.") from exc
    return Utilisateur(id=uid, email=email, verifie=verifie)


def par_email(email: str) -> Utilisateur | None:
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, email, verifie FROM utilisateurs WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    return _vers_utilisateur(ligne) if ligne else None


def par_id(uid: str) -> Utilisateur | None:
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, email, verifie FROM utilisateurs WHERE id = ?", (uid,)
        ).fetchone()
    return _vers_utilisateur(ligne) if ligne else None


def verifier_mot_de_passe(email: str, mot_de_passe: str) -> Utilisateur | None:
    """Retourne l'utilisateur si l'email + mot de passe correspondent, sinon None."""
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, email, verifie, hash_mdp FROM utilisateurs WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    if not ligne or not security.verifier_mot_de_passe(mot_de_passe, ligne["hash_mdp"]):
        return None
    return Utilisateur(id=ligne["id"], email=ligne["email"], verifie=bool(ligne["verifie"]))


def definir_token_verify(uid: str, token: str) -> None:
    with _connexion() as conn:
        conn.execute("UPDATE utilisateurs SET token_verify = ? WHERE id = ?", (token, uid))


def valider_par_token_verify(token: str) -> Utilisateur | None:
    """Active le compte portant ce jeton de vérification et retourne l'utilisateur."""
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, email, verifie FROM utilisateurs WHERE token_verify = ?", (token,)
        ).fetchone()
        if not ligne:
            return None
        conn.execute(
            "UPDATE utilisateurs SET verifie = 1, token_verify = NULL WHERE id = ?",
            (ligne["id"],),
        )
    return Utilisateur(id=ligne["id"], email=ligne["email"], verifie=True)


def definir_token_reset(email: str, token: str) -> Utilisateur | None:
    """Mémorise un jeton de réinitialisation et retourne l'utilisateur (si l'email existe)."""
    utilisateur = par_email(email)
    if utilisateur is None:
        return None
    with _connexion() as conn:
        conn.execute("UPDATE utilisateurs SET token_reset = ? WHERE id = ?", (token, utilisateur.id))
    return utilisateur


def reinitialiser_mdp(token: str, nouveau_mdp: str) -> Utilisateur | None:
    """Applique le nouveau mot de passe au compte portant ce jeton de réinitialisation."""
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, email, verifie FROM utilisateurs WHERE token_reset = ?", (token,)
        ).fetchone()
        if not ligne:
            return None
        conn.execute(
            "UPDATE utilisateurs SET hash_mdp = ?, token_reset = NULL WHERE id = ?",
            (security.hacher_mot_de_passe(nouveau_mdp), ligne["id"]),
        )
    return Utilisateur(id=ligne["id"], email=ligne["email"], verifie=bool(ligne["verifie"]))


def supprimer_utilisateur(uid: str, mot_de_passe: str) -> bool:
    """Supprime définitivement le compte si le mot de passe est correct.

    Retourne True si le compte a été supprimé, False sinon (compte inexistant
    ou mot de passe erroné). Ne supprime PAS les données de jeu : c'est à
    l'appelant de le faire (via `extract.dossiers_utilisateur`).
    """
    with _connexion() as conn:
        ligne = conn.execute(
            "SELECT id, hash_mdp FROM utilisateurs WHERE id = ?", (uid,)
        ).fetchone()
        if not ligne or not security.verifier_mot_de_passe(mot_de_passe, ligne["hash_mdp"]):
            return False
        conn.execute("DELETE FROM utilisateurs WHERE id = ?", (uid,))
    return True


def _vers_utilisateur(ligne: sqlite3.Row) -> Utilisateur:
    return Utilisateur(id=ligne["id"], email=ligne["email"], verifie=bool(ligne["verifie"]))
