"""Orchestration de la création de personnage (SRD 5.2.1, niveau 1).

Suit les cinq étapes du SRD :

1. choix de la classe ;
2. origines (espèce, historique, langues) ;
3. caractéristiques ;
4. alignement ;
5. finalisation (sorts connus, babiole, nom).

Chaque étape est une fonction ``(etat, ctx) -> etat``. En mode ``auto``,
les choix sont tirés au hasard dans le corpus (générateur injecté,
reproductible via ``--seed``) ; sinon ``io`` présente des menus tolérants.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import extract
from . import io as ui
from . import models


@dataclass
class Contexte:
    """Contexte d'une création : données du corpus + hasard + mode."""

    donnees: dict[str, Any]
    rng: random.Random
    auto: bool = True


def _tirer_les(noms: list[str], nb: int, rng: random.Random) -> list[str]:
    """Tire ``nb`` noms distincts dans ``noms`` (sans doublons)."""
    if not noms or nb <= 0:
        return []
    return rng.sample(list(noms), min(nb, len(noms)))


def step_classe(etat: dict[str, Any], ctx: Contexte) -> dict[str, Any]:
    """Étape 1 — choix de la classe (et compétences de départ)."""
    classes = ctx.donnees["classes"]
    nom = ui.demander_classe(classes, ctx.rng, ctx.auto)
    etat["classe"] = nom
    info = classes[nom]
    options = list(info.get("competences") or [])
    nb = int(info.get("nb_competences") or 0)
    if options and nb > 0:
        etat["competences"] = ui.demander_competences(
            options, nb, ctx.rng, ctx.auto
        )
    # Équipement de départ : kit A (recommandé) ou kit B.
    kit_a = list(info.get("equip_A") or [])
    kit_b = list(info.get("equip_B") or [])
    etat["equipement"] = models.Equipement(
        ui.demander_equipement(kit_a, kit_b, ctx.rng, ctx.auto)
    )
    return etat


def step_origines(etat: dict[str, Any], ctx: Contexte) -> dict[str, Any]:
    """Étape 2 — origines : espèce, historique, langues."""
    etat["espece"] = ui.demander_espece(ctx.donnees["especes"], ctx.rng, ctx.auto)
    nom_hist = ui.demander_historique(
        ctx.donnees["historiques"], ctx.rng, ctx.auto
    )
    etat["historique"] = nom_hist
    # Bénéfices de l'historique (SRD 5.2.1) : don d'origines, maîtrise d'outil
    # et deux maîtrises de compétence (fusionnées avec celles de la classe).
    info_hist = ctx.donnees["historiques"].get(nom_hist, {})
    etat["don"] = info_hist.get("aptitude", "")
    etat["outils"] = info_hist.get("outils", "")
    competences = list(etat.get("competences") or [])
    for comp in info_hist.get("competences") or []:
        if comp not in competences:
            competences.append(comp)
    etat["competences"] = competences
    # Équipement de l'historique : kit A (recommandé) ou kit B (50 po).
    kit_a = list(info_hist.get("equip_A") or [])
    kit_b = list(info_hist.get("equip_B") or [])
    if kit_a or kit_b:
        objets = ui.demander_equipement(kit_a, kit_b, ctx.rng, ctx.auto)
        equip = list((etat.get("equipement") or models.Equipement()).objets)
        equip.extend(objets)
        etat["equipement"] = models.Equipement(equip)
    etat["langues"] = ui.demander_langues(ctx.donnees["langues"], ctx.rng, ctx.auto)
    return etat


def step_caracteristiques(etat: dict[str, Any], ctx: Contexte) -> dict[str, Any]:
    """Étape 3 — caractéristiques (valeur standard ou achat de points)."""
    # Valeurs par défaut optimisées pour la classe (table vérifiée).
    valeurs_defaut = extract.VALEURS_PAR_CLASSE.get(
        etat["classe"], list(extract.ARRAY_STANDARD)
    )
    valeurs = ui.demander_carac_valeurs(valeurs_defaut, ctx.rng, ctx.auto)
    etat["carac"] = models.Caracteristiques.depuis_liste(valeurs)
    return etat


def step_alignement(etat: dict[str, Any], ctx: Contexte) -> dict[str, Any]:
    """Étape 4 — alignement (choix libre, 9 options)."""
    etat["alignement"] = ui.demander_alignement(
        ctx.donnees["alignements"], ctx.rng, ctx.auto
    )
    return etat


def step_finalisation(etat: dict[str, Any], ctx: Contexte) -> dict[str, Any]:
    """Étape 5 — finalisation : sorts connus, babiole, nom du personnage."""
    # Sorts connus (lanceurs de sorts uniquement).
    etat["sorts"] = _choisir_sorts(etat, ctx)
    # Babiole : tirage d100 dans la table du corpus.
    etat["babiole"] = ui.tirer_babiole(ctx.donnees["babioles"], ctx.rng)
    # Nom : saisi libre, sinon tiré dans la table de noms de l'espèce.
    etat["nom"] = ui.demander_nom(etat["espece"], ctx.rng, ctx.auto)
    return etat


def _choisir_sorts(etat: dict[str, Any], ctx: Contexte) -> list[str]:
    """Sorts mineurs + sorts du 1er niveau connus à la création."""
    classe = etat["classe"]
    info = ctx.donnees["classes"].get(classe, {})
    if not info.get("lanceur"):
        return []
    # Lancer un sort sans compteur déclaré : on applique le minimum SRD.
    nb_cantrips = int(info.get("nb_cantrips") or 0) or 2
    nb_sorts_1 = int(info.get("nb_sorts_1") or 0) or 2
    noms: list[str] = []
    cantrips = ctx.donnees["cantrips"].get(classe, [])
    if cantrips:
        noms.extend(ui.demander_sorts(cantrips, nb_cantrips, ctx.rng, ctx.auto))
    sorts_1 = ctx.donnees["sorts_1"].get(classe, [])
    if sorts_1:
        noms.extend(ui.demander_sorts(sorts_1, nb_sorts_1, ctx.rng, ctx.auto))
    return noms


def _vers_personnage(etat: dict[str, Any]) -> models.Personnage:
    """Convertit l'état accumulé en ``Personnage`` (modèles validés)."""
    competences = [models.Competence(nom=c) for c in etat.get("competences") or []]
    return models.Personnage(
        nom=etat.get("nom", ""),
        espece=etat.get("espece", ""),
        classe=etat.get("classe", ""),
        historique=etat.get("historique", ""),
        alignement=etat.get("alignement", "Neutre"),
        niveau=1,
        carac=etat.get("carac") or models.Caracteristiques(),
        competences=competences,
        langues=list(etat.get("langues") or ["Commun"]),
        equipement=etat.get("equipement") or models.Equipement(),
        sorts=list(etat.get("sorts") or []),
        babiole=etat.get("babiole", ""),
        don=etat.get("don", ""),
        outils=etat.get("outils", ""),
    )


def creer_personnage(
    donnees: dict[str, Any],
    rng: random.Random,
    auto: bool = True,
) -> models.Personnage:
    """Crée un personnage de niveau 1, de A à Z (les 5 étapes du SRD)."""
    etat: dict[str, Any] = {}
    etat = step_classe(etat, Contexte(donnees, rng, auto))
    etat = step_origines(etat, Contexte(donnees, rng, auto))
    etat = step_caracteristiques(etat, Contexte(donnees, rng, auto))
    etat = step_alignement(etat, Contexte(donnees, rng, auto))
    etat = step_finalisation(etat, Contexte(donnees, rng, auto))
    return _vers_personnage(etat)


def creer_automatiquement(
    rng: random.Random,
    donnees: dict[str, Any] | None = None,
) -> models.Personnage:
    """Raccourci : création 100 % automatique (tout au hasard)."""
    return creer_personnage(donnees or extract.charger_tout(), rng, auto=True)


__all__ = [
    "Contexte",
    "creer_personnage",
    "creer_automatiquement",
    "step_classe",
    "step_origines",
    "step_caracteristiques",
    "step_alignement",
    "step_finalisation",
]
