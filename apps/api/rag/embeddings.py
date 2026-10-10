"""Client d'embeddings (service OpenAI-compatible de la stack existante).

Le service `embedding` (scripts/embedding_server.py) expose `POST /v1/embeddings`
au format OpenAI. On l'appelle en HTTP interne via httpx.
"""

from __future__ import annotations

import time

import httpx

from settings import settings


def _post(textes: list[str], *, essais: int = 8, pause: float = 4.0) -> list[list[float]]:
    """POST /embeddings avec re-tentatives.

    Le service `embedding` peut repondre 503 (« model is loading ») apres un
    rechargement, ou couper la connexion sur un gros batch (CPU lent). On
    re-essaie jusqu'a `essais` fois avant de lever.
    """
    dernier: Exception | None = None
    for _ in range(essais):
        try:
            reponse = httpx.post(
                f"{settings.embed_base_url}/embeddings",
                json={"model": settings.embed_model_name, "input": textes},
                timeout=300.0,
            )
            if reponse.status_code == 200:
                donnees = sorted(
                    reponse.json()["data"], key=lambda d: d.get("index", 0)
                )
                return [d["embedding"] for d in donnees]
            dernier = RuntimeError(f"HTTP {reponse.status_code} : {reponse.text[:120]}")
        except (httpx.TransportError, httpx.HTTPError) as exc:
            dernier = exc
        time.sleep(pause)
    raise RuntimeError(f"service embeddings injoignable : {dernier}")


def embed(textes: list[str]) -> list[list[float]]:
    """Renvoie un vecteur par texte, dans l'ordre. Lève si le service est injoignable."""
    if not textes:
        return []
    return _post(textes)


def embed_un(texte: str) -> list[float]:
    return embed([texte])[0]
