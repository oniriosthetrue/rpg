"""Accès Qdrant : création de la collection, upsert des fiches, recherche.

On utilise le client officiel `qdrant-client`. La collection porte des vecteurs
cosine de la dimension du modèle d'embedding (auto-détectée au premier upsert),
et un payload = les métadonnées de la fiche (id, nom, type, source, contenu…).
"""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from rag.corpus import Fiche
from settings import settings

_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.qdrant_url, timeout=30)
    return _client


def _id_point(id_fiche: str) -> str:
    """Qdrant exige un id UUID ou entier : on dérive un UUID stable de l'id fiche."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, id_fiche))


def s_assurer_collection(dim: int) -> None:
    c = client()
    if not c.collection_exists(settings.qdrant_collection):
        c.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        # Index de filtrage (par type de fiche : sort, monstre, objet…).
        c.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name="type",
            field_schema="keyword",
        )


def upsert(fiches: list[Fiche], vecteurs: list[list[float]]) -> int:
    assert len(fiches) == len(vecteurs)
    s_assurer_collection(len(vecteurs[0]))
    points = [
        PointStruct(id=_id_point(f.id), vector=v, payload=f.payload())
        for f, v in zip(fiches, vecteurs)
    ]
    # Upsert par paquets pour ne pas saturer une seule requête.
    taille = 64
    for i in range(0, len(points), taille):
        client().upsert(
            collection_name=settings.qdrant_collection, points=points[i : i + taille]
        )
    return len(points)


def rechercher(
    vecteur: list[float], top_k: int | None = None, type_: str | None = None
) -> list[dict[str, Any]]:
    """Recherche les `top_k` fiches les plus proches. Renvoie des dicts payload + score."""
    top_k = top_k or settings.rag_top_k
    reponse = client().query_points(
        collection_name=settings.qdrant_collection,
        query=vecteur,
        limit=top_k,
        with_payload=True,
    )
    sortie: list[dict[str, Any]] = []
    for pt in reponse.points:
        payload = dict(pt.payload or {})
        payload["_score"] = pt.score
        sortie.append(payload)
    return sortie
