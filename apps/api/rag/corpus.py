"""Analyse du corpus SRD en « chunks » prêts pour le RAG.

Le corpus (`packages/corpus/srd-5.2.1/`) est un ensemble de fiches markdown. Une
fiche = un chunk. Le format d'en-tête (contrat du corpus) :

    <<<FICHE>>>
    id: sorts/boule-de-feu
    nom: Boule de feu
    type: sort
    edition: SRD 5.2.1
    mots_cles: sort, Évocation
    source: FR_SRD_CC_v5.2.1.pdf p.170   (parfois absent)
    <<<CONTENU>>>
    <corps markdown>
    <<<FIN>>>

On extrait les métadonnées (pour le payload Qdrant et les citations) et le corps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dnd_perso import extract

# Clés d'en-tête à conserver dans le payload Qdrant (cf. ARCHITECTURE §3.3).
_CLES_META = ("id", "nom", "type", "edition", "mots_cles", "source")

# Longueur max du texte vectorisé (le reste reste dans le payload pour citations).
_MAX_EMBED_CAR = 4000


@dataclass
class Fiche:
    id: str
    nom: str
    type: str
    edition: str
    mots_cles: str
    source: str
    contenu: str
    chemin: str = ""

    def payload(self) -> dict:
        return {
            "id": self.id,
            "nom": self.nom,
            "type": self.type,
            "edition": self.edition,
            "mots_cles": self.mots_cles,
            "source": self.source,
            "contenu": self.contenu,
            "chemin": self.chemin,
        }

    def texte_a_embedder(self) -> str:
        """Le texte vectorisé : en-tête compact + corps (tronqué). Les mots-clés
        améliorent le rappel sémantique FR (« le gros poisson télépathe » → aboleth).

        On tronque le corps à `_MAX_EMBED_CAR` : le service embeddings est CPU-bound
        et certaines fiches (chapitres entiers) dépassent 200 000 caractères, ce qui
        bloque l'encodage. Le début suffit pour la recherche sémantique ; le texte
        COMPLET reste dans le payload Qdrant (cf. `payload()`) pour les citations.
        """
        entete = " | ".join(
            f"{k}: {v}" for k, v in (("nom", self.nom), ("type", self.type), ("mots_cles", self.mots_cles)) if v
        )
        corps = self.contenu[:_MAX_EMBED_CAR]
        return f"{entete}\n{corps}".strip()


def _parser_en_tete(bloc: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for ligne in bloc.splitlines():
        if ":" not in ligne:
            continue
        cle, _, val = ligne.partition(":")
        cle = cle.strip()
        if cle in _CLES_META:
            meta[cle] = val.strip()
    return meta


def iterer_fiches(racine: Path | None = None) -> list[Fiche]:
    """Parcourt tout le corpus et renvoie une Fiche par fichier markdown valide."""
    racine = racine or extract.CORPUS
    fiches: list[Fiche] = []
    for chemin in sorted(racine.rglob("*.md")):
        texte = chemin.read_text(encoding="utf-8")
        if "<<<CONTENU>>>" not in texte:
            continue  # index, README, fichiers sans structure de fiche
        avant, _, reste = texte.partition("<<<CONTENU>>>")
        corps, _, _ = reste.partition("<<<FIN>>>")
        meta = _parser_en_tete(avant.replace("<<<FICHE>>>", ""))
        if not meta.get("id"):
            continue
        fiches.append(
            Fiche(
                id=meta["id"],
                nom=meta.get("nom", meta["id"]),
                type=meta.get("type", ""),
                edition=meta.get("edition", ""),
                mots_cles=meta.get("mots_cles", ""),
                source=meta.get("source", ""),
                contenu=corps.strip(),
                chemin=str(chemin.relative_to(racine)),
            )
        )
    return fiches
