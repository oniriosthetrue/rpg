"""Configuration centralisée de l'API (variables d'environnement).

Une seule source de vérité pour les réglages runtime. Les valeurs par défaut
correspondent au déploiement docker-compose (réseau `mynetwork`, services
`litellm`, `embedding`, `qdrant` de la stack existante).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(cle: str, defaut: str = "") -> str:
    return os.environ.get(cle, defaut).strip()


@dataclass(frozen=True)
class Settings:
    # LLM (OpenAI-compatible via litellm de la stack existante).
    litellm_base_url: str = _env("LITELLM_BASE_URL", "http://litellm:4000/v1")
    litellm_api_key: str = _env("LITELLM_API_KEY", "")
    mj_model: str = _env("MJ_MODEL", "VnimanieAI/Qwen3.8-Flash-Next-W4A16")

    # Embeddings (service embedding de la stack existante).
    embed_base_url: str = _env("EMBED_BASE_URL", "http://embedding:8080/v1")
    embed_model_name: str = _env("EMBED_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")

    # RAG / Qdrant.
    qdrant_url: str = _env("QDRANT_URL", "http://qdrant:6333")
    qdrant_collection: str = _env("QDRANT_COLLECTION", "srd_521")
    rag_top_k: int = int(_env("RAG_TOP_K", "3") or "3")
    # Plancher anti-bruit du retrieval : on écarte les fiches vectorielles dont le
    # score cosine est bas (seuil absolu) ou nettement sous le meilleur résultat
    # (seuil relatif). Les correspondances de nom exact (BM25) sont toujours gardées.
    rag_min_score: float = float(_env("RAG_MIN_SCORE", "0.66") or "0.66")
    rag_score_delta: float = float(_env("RAG_SCORE_DELTA", "0.05") or "0.05")

    # Clé interne (X-API-Key) — identique à celle que Traefik/Next injecte.
    dnd_api_key: str = _env("DND_API_KEY", "")


settings = Settings()
