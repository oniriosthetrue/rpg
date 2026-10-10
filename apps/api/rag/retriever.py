"""Retriever RAG : question du joueur → contexte SRD avec citations.

Le MJ ne doit jamais broder une règle hors corpus. On retrouve les fiches
pertinentes et on les injecte en contexte, chacune suivie de sa **source**
(ex. « SRD 5.2.1 p.170 ») pour que le MJ puisse citer et ne rien inventer.
"""

from __future__ import annotations

from rag import embeddings, qdrant_store


def _formater_source(payload: dict) -> str:
    source = (payload.get("source") or "").strip()
    edition = (payload.get("edition") or "").strip()
    if source:
        return source
    return edition or "SRD"


def recuperer_contexte(question: str, top_k: int | None = None) -> str:
    """Renvoie un bloc de contexte markdown (fiches + sources), ou "" si rien."""
    if not question or not question.strip():
        return ""
    try:
        vecteur = embeddings.embed_un(question)
        fiches = qdrant_store.rechercher(vecteur, top_k=top_k)
    except Exception:  # le RAG ne doit jamais bloquer une réponse du MJ
        return ""
    if not fiches:
        return ""
    blocs: list[str] = []
    for f in fiches:
        corps = (f.get("contenu") or "").strip()
        if not corps:
            continue
        titre = f.get("nom") or f.get("id") or ""
        blocs.append(
            f"### {titre}  \n_Source : {_formater_source(f)}_\n\n{corps}"
        )
    if not blocs:
        return ""
    return (
        "## Base de connaissances SRD (extraits pertinents — cite la source, "
        "n'invente rien hors de ces fiches)\n\n" + "\n\n---\n\n".join(blocs)
    )
