"""Retriever RAG : question du joueur → contexte SRD avec citations.

Le MJ ne doit jamais broder une règle hors corpus. On retrouve les fiches
pertinentes et on les injecte en contexte, chacune suivie de sa **source**
(ex. « SRD 5.2.1 p.170 ») pour que le MJ puisse citer et ne rien inventer.
"""

from __future__ import annotations

import logging
from typing import Any

from rag import embeddings, keyword_search, qdrant_store

_LOGGER = logging.getLogger(__name__)


def _cle_fiche(fiche: dict[str, Any]) -> str:
    return str(fiche.get("id") or fiche.get("nom") or "")


def _fusionner(
    semantiques: list[dict[str, Any]],
    lexicales: list[dict[str, Any]],
    limite: int,
) -> list[dict[str, Any]]:
    """Fusionne les rangs par RRF, avec priorité au nom exact trouvé par BM25."""
    fusion: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    noms_exacts: set[str] = set()
    rangs: tuple[tuple[list[dict[str, Any]], float], ...] = (
        (semantiques, 1.5),
        (lexicales, 1.0),
    )

    for fiches, poids in rangs:
        for rang, fiche in enumerate(fiches, start=1):
            cle = _cle_fiche(fiche)
            if not cle:
                continue
            fusion.setdefault(cle, {}).update(fiche)
            scores[cle] = scores.get(cle, 0.0) + poids / (60 + rang)
            if fiche.get("_keyword_exact_name"):
                noms_exacts.add(cle)

    classement = sorted(
        fusion,
        key=lambda cle: (cle in noms_exacts, scores[cle]),
        reverse=True,
    )
    return [fusion[cle] for cle in classement[:limite]]


def _formater_source(payload: dict) -> str:
    source = (payload.get("source") or "").strip()
    edition = (payload.get("edition") or "").strip()
    if source:
        return source
    return edition or "SRD"


def _meilleur_score(semantiques: list[dict[str, Any]]) -> float | None:
    """Plus haut score cosine parmi les fiches scorées, ou None si aucune."""
    scores = [
        f["_score"] for f in semantiques if isinstance(f.get("_score"), (int, float))
    ]
    return max(scores) if scores else None


def _filtrer_semantiques(semantiques: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Écarte les fiches vectorielles hors-sujet (bruit lexical/phonétique).

    On garde une fiche si son score cosine reste à portée du meilleur résultat
    (delta). Les scores cosine de ce modèle sont serrés (0,62–0,78), d'où le seuil
    relatif. Le BM25 (nom exact / mots-clés) est traité à part et n'est pas filtré
    ici — la pertinence globale de la requête est tranchée par la « porte » dans
    `_rechercher_fiches`.
    """
    if not semantiques:
        return []
    meilleur = _meilleur_score(semantiques)
    if meilleur is None:  # aucune fiche scorée (stub / source non vectorielle)
        return semantiques
    plancher = meilleur - qdrant_store.settings.rag_score_delta
    return [
        f
        for f in semantiques
        if not isinstance(f.get("_score"), (int, float))
        or f["_score"] >= plancher
    ]


def _rechercher_fiches(
    question: str, top_k: int | None
) -> list[dict[str, Any]]:
    """Retourne les fiches fusionnées (vectoriel + lexical), ou [] si rien."""
    if not question or not question.strip():
        return []
    limite = top_k or qdrant_store.settings.rag_top_k
    semantiques: list[dict[str, Any]] = []
    try:
        vecteur = embeddings.embed_un(question)
        semantiques = qdrant_store.rechercher(vecteur, top_k=limite)
        semantiques = _filtrer_semantiques(semantiques)
    except Exception:  # le RAG ne doit jamais bloquer une réponse du MJ
        _LOGGER.exception("Recherche vectorielle indisponible.")

    # « Porte » de pertinence : si rien dans le corpus ne ressemble vraiment à la
    # requête (meilleur score cosine sous le plancher), la question est hors-sujet
    # (méta-commande, narration, « que puis-je faire ? »…). On ne cite alors RIEN —
    # BM25 compris — plutôt que d'aligner des fiches SRD sans rapport.
    meilleur = _meilleur_score(semantiques)
    if meilleur is not None and meilleur < qdrant_store.settings.rag_min_score:
        return []

    try:
        lexicales = keyword_search.rechercher(question, limite)
    except Exception:
        _LOGGER.exception("Recherche BM25 indisponible.")
        lexicales = []

    return _fusionner(semantiques, lexicales, limite)


def _sources(fiches: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Dérive la liste de citations structurées des fiches retenues."""
    sources: list[dict[str, str]] = []
    for f in fiches:
        corps = (f.get("contenu") or "").strip()
        if not corps:
            continue
        sources.append(
            {
                "nom": str(f.get("nom") or f.get("id") or ""),
                "source": _formater_source(f),
                "edition": str((f.get("edition") or "").strip()),
            }
        )
    return sources


def recuperer_sources(
    question: str, top_k: int | None = None
) -> list[dict[str, str]]:
    """Retourne les citations structurées ({nom, source, edition}) pour une question."""
    return _sources(_rechercher_fiches(question, top_k))


def recuperer_contexte(question: str, top_k: int | None = None) -> str:
    """Renvoie un bloc de contexte markdown (fiches + sources), ou "" si rien."""
    fiches = _rechercher_fiches(question, top_k)
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
