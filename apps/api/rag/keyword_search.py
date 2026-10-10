"""Recherche lexicale BM25 dans le corpus SRD."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from typing import Any

from rag.corpus import iterer_fiches

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_K1 = 1.5
_B = 0.75


def _tokeniser(texte: str) -> list[str]:
    texte = texte.replace("’", "'").replace("‘", "'").replace("ʼ", "'")
    normalise = unicodedata.normalize("NFKD", texte)
    ascii_texte = normalise.encode("ascii", "ignore").decode("ascii").lower()
    return [token for token in _TOKEN_RE.findall(ascii_texte) if len(token) > 1]


@lru_cache(maxsize=1)
def _indexer_corpus() -> tuple[list[dict[str, Any]], float, dict[str, int]]:
    documents: list[dict[str, Any]] = []
    frequences: Counter[str] = Counter()
    longueur_totale = 0

    for fiche in iterer_fiches():
        nom_tokens = _tokeniser(fiche.nom)
        # Le titre est répété pour donner plus de poids aux correspondances de nom.
        tokens = nom_tokens * 3 + _tokeniser(f"{fiche.mots_cles} {fiche.contenu}")
        frequences.update(set(tokens))
        longueur_totale += len(tokens)
        documents.append(
            {
                "payload": fiche.payload(),
                "frequences": Counter(tokens),
                "longueur": len(tokens),
                "tokens_nom": set(nom_tokens),
            }
        )

    longueur_moyenne = longueur_totale / len(documents) if documents else 0.0
    return documents, longueur_moyenne, dict(frequences)


def rechercher(question: str, limite: int) -> list[dict[str, Any]]:
    """Classe les fiches par score BM25, en donnant la priorité aux titres exacts."""
    tokens_question = set(_tokeniser(question))
    if not tokens_question or limite <= 0:
        return []

    documents, longueur_moyenne, frequences = _indexer_corpus()
    nombre_documents = len(documents)
    if not nombre_documents or not longueur_moyenne:
        return []

    resultats: list[dict[str, Any]] = []
    for document in documents:
        score = 0.0
        for token in tokens_question:
            tf = document["frequences"].get(token, 0)
            if not tf:
                continue
            df = frequences[token]
            idf = math.log(1 + (nombre_documents - df + 0.5) / (df + 0.5))
            normalisation = _K1 * (
                1 - _B + _B * document["longueur"] / longueur_moyenne
            )
            score += idf * (tf * (_K1 + 1)) / (tf + normalisation)

        if score <= 0:
            continue

        payload = dict(document["payload"])
        payload["_keyword_score"] = score
        payload["_keyword_exact_name"] = (
            len(document["tokens_nom"]) > 1
            and document["tokens_nom"].issubset(tokens_question)
        )
        resultats.append(payload)

    return sorted(
        resultats,
        key=lambda fiche: (
            fiche["_keyword_exact_name"],
            fiche["_keyword_score"],
        ),
        reverse=True,
    )[:limite]
