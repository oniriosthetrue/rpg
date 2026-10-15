"""Sécurité des comptes : hachage des mots de passe et jetons signés.

Tout est en bibliothèque standard (aucune dépendance externe) pour garantir un
build de l'image `api` (python:slim) sans compilation :

- `hacher_mot_de_passe` / `verifier_mot_de_passe` : PBKDF2-HMAC-SHA256 avec sel
  aléatoire (format auto-descriptif `$pbkdf2-sha256$itérations$sel$hash`) ;
- `signer` / `verifier` : jetons signés HMAC-SHA256 en base64url, avec charge
  JSON et expiration — utilisés pour les sessions (cookie) et les liens de
  vérification / réinitialisation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

# Paramètres PBKDF2 (OWASP 2023 : ≥ 600 000 itérations pour HMAC-SHA256).
# 310 000 reste très solide et garde un login < ~0,3 s sur un petit VPS.
_ITERATIONS = 310_000
_TAILLE_SEL = 16
_TAILLE_HASH = 32


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Hache un mot de passe (PBKDF2-HMAC-SHA256, sel aléatoire)."""
    sel = secrets.token_bytes(_TAILLE_SEL)
    dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, _ITERATIONS, _TAILLE_HASH)
    return "$pbkdf2-sha256${}${}${}".format(
        _ITERATIONS, _b64(sel), _b64(dk)
    )


def verifier_mot_de_passe(mot_de_passe: str, hache: str) -> bool:
    """Vérifie un mot de passe contre son hash (temps constant)."""
    try:
        algo, it_s, sel_b64, hash_b64 = hache.split("$")[1:]
        if algo != "pbkdf2-sha256":
            return False
        iterations = int(it_s)
        sel = _unb64(sel_b64)
        attendu = _unb64(hash_b64)
    except (ValueError, IndexError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", mot_de_passe.encode(), sel, iterations, len(attendu))
    return hmac.compare_digest(dk, attendu)


# ---------------------------------------------------------------------------
# Jetons signés (sessions + liens email)
# ---------------------------------------------------------------------------


def signer(charge: dict, secret: str, duree_s: int) -> str:
    """Produit un jeton signé `base64url(charge+exp).sig` expirant dans `duree_s`."""
    payload = dict(charge)
    payload["exp"] = int(time.time()) + duree_s
    corps = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(_hmac(corps.encode(), secret))
    return f"{corps}.{sig}"


def verifier(jeton: str, secret: str) -> dict | None:
    """Vérifie signature + expiration. Renvoie la charge (sans `exp`) ou None."""
    if not jeton or "." not in jeton:
        return None
    corps, _, sig = jeton.partition(".")
    attendu = _b64(_hmac(corps.encode(), secret))
    if not hmac.compare_digest(sig, attendu):
        return None
    try:
        payload = json.loads(_unb64(corps))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    payload.pop("exp", None)
    return payload


def jeton_aleatoire(n_octets: int = 32) -> str:
    """Jeton aléatoire opaque (base64url), ex. identifiant de session révoquable."""
    return _b64(secrets.token_bytes(n_octets))


# ---------------------------------------------------------------------------
# Aides base64url (sans `=` pour l'usage en cookie / URL)
# ---------------------------------------------------------------------------


def _b64(donnees: bytes) -> str:
    return base64.urlsafe_b64encode(donnees).decode().rstrip("=")


def _unb64(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def _hmac(corps: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode(), corps, hashlib.sha256).digest()
