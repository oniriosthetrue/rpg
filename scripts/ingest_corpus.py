"""Ingestion du corpus SRD dans Qdrant.

Usage (dans le conteneur api) :
    python -m scripts.ingest_corpus

Parcourt `packages/corpus/srd-5.2.1/`, embedde chaque fiche via le service
d'embeddings, et upsert le tout dans la collection Qdrant. Idempotent (upsert
par id dérivé) : relancer met à jour sans doublon.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Rendre `apps/api` importable quand on lance depuis la racine du dépôt.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from rag import embeddings, qdrant_store  # noqa: E402
from rag.corpus import iterer_fiches  # noqa: E402


def main() -> int:
    fiches = iterer_fiches()
    print(f"[ingest] {len(fiches)} fiches lues depuis le corpus")
    if not fiches:
        print("[ingest] ERREUR : aucune fiche trouvée (corpus vide ?)", file=sys.stderr)
        return 1

    total = 0
    taille = 8  # petits batchs : le service embeddings est CPU-bound sur les longues fiches
    for i in range(0, len(fiches), taille):
        paquet = fiches[i : i + taille]
        vecteurs = embeddings.embed([f.texte_a_embedder() for f in paquet])
        n = qdrant_store.upsert(paquet, vecteurs)
        total += n
        print(f"[ingest] {total}/{len(fiches)} upsertés")

    print(f"[ingest] terminé : {total} points dans la collection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
