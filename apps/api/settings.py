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
    # « Porte » de pertinence du retrieval : si le MEILLEUR score cosine d'une
    # requête est sous ce plancher, la question est hors-sujet (méta-commande,
    # narration, « que puis-je faire ? ») et on ne cite aucune fiche SRD. Les
    # questions réelles (« détection de la magie » 0,77 ; « traces de pas » 0,65)
    # dépassent ce seuil ; les méta-commandes restent sous 0,50.
    rag_min_score: float = float(_env("RAG_MIN_SCORE", "0.60") or "0.60")
    # Seuil relatif : on écarte les fiches nettement sous le meilleur résultat.
    rag_score_delta: float = float(_env("RAG_SCORE_DELTA", "0.02") or "0.02")

    # Clé interne (X-API-Key) — identique à celle que Traefik/Next injecte.
    dnd_api_key: str = _env("DND_API_KEY", "")

    # ─── Authentification par compte (email + mot de passe) ────────────────
    # Secret de signature des jetons (sessions + liens email). OBLIGATOIRE en prod.
    auth_secret: str = _env("AUTH_SECRET", "")
    # Durée de vie d'une session (cookie), en secondes. Défaut : 30 jours.
    session_duree_s: int = int(_env("SESSION_DUREE_S", "2592000") or "2592000")
    # Durée de validité des liens de vérification / réinitialisation (1 h).
    lien_duree_s: int = int(_env("LIEN_DUREE_S", "3600") or "3600")
    # URL publique de l'app (pour les liens des emails).
    base_url: str = _env("BASE_URL", "https://rpg.minervia.fr").rstrip("/")

    # SMTP (optionnel). Sans `SMTP_HOST`, l'envoi passe en mode console (loggé).
    smtp_host: str = _env("SMTP_HOST", "")
    smtp_port: int = int(_env("SMTP_PORT", "587") or "587")
    smtp_user: str = _env("SMTP_USER", "")
    smtp_pass: str = _env("SMTP_PASS", "")
    smtp_from: str = _env("SMTP_FROM", "")
    smtp_starttls: bool = _env("SMTP_STARTTLS", "1") not in ("0", "false", "no", "")


settings = Settings()
