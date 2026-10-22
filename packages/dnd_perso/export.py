"""Export du personnage : fiche markdown (format du corpus) et JSON.

Le fichier markdown suit la convention du corpus `dnd/srd-5.2.1/` :

    <<<FICHE>>>
    id: ...
    nom: ...
    type: personnage
    ...
    <<<CONTENU>>>
    ...corps de la fiche...
    <<<FIN>>>

Écriture dans `dnd_perso/perso/` uniquement (jamais dans le corpus).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import extract
from . import models


def _ligne(cle: str, valeur: str) -> str:
    return f"{cle}: {valeur}"


def en_markdown(p: models.Personnage) -> str:
    """Rend la fiche markdown complète d'un personnage (corps de fiche)."""
    c = p.carac
    lignes: list[str] = []
    lignes += [
        f"- Espèce : {p.espece}",
        *([f"- Genre : {p.genre}"] if p.genre else []),
        f"- Classe : {p.classe}",
        f"- Historique : {p.historique}",
        f"- Alignement : {p.alignement}",
        f"- Niveau : {p.niveau}",
        f"- Points de vie : {p.pv}",
        f"- Classe d'armure : {p.ca}",
        f"- Initiative : {p.initiative:+d}",
        f"- Bonus de maîtrise : +{p.bonus_maitrise}",
        "",
        "## Caractéristiques",
        "",
    ]
    for nom, val in zip(models.CARACTERISTIQUES, c.valeurs()):
        lignes.append(f"- {nom} : {val} ({c.mod(val):+d})")
    lignes += ["", "## Compétences", ""]
    if p.competences:
        for comp in p.competences:
            marque = "maîtrisée" if comp.maitrisee else "non maîtrisée"
            lignes.append(f"- {comp.nom} ({marque})")
    else:
        lignes.append("- Aucune compétence sélectionnée")
    # Table pré-calculée des bonus de jet : le MJ l'annonce telle quel
    # (« d20 + N ») et ne demande au joueur que le dé naturel.
    jets = p.table_des_jets()
    lignes += ["", "## Bonus des jets (d20 + total)", ""]
    lignes.append("**Compétences :**")
    for nom, total in jets["competences"].items():
        lignes.append(f"- {nom} : d20 {total:+d}")
    lignes += ["", "**Jets de sauvegarde :**"]
    for carac, total in jets["sauvegardes"].items():
        lignes.append(f"- Sauvegarde de {carac} : d20 {total:+d}")
    if jets.get("carac_incantation"):
        lignes += ["", "**Attaque de sort :**"]
        lignes.append(
            f"- Caractéristique d'incantation : {jets['carac_incantation']}"
        )
        lignes.append(f"- Bonus d'attaque de sort : {jets['attaque_sort']:+d}")
        lignes.append(f"- DD des sauvegardes contre tes sorts : {jets['dd_sort']}")
    lignes += ["", "## Langues", ""]
    lignes.append("- " + ", ".join(p.langues))
    if p.don:
        lignes += ["", "## Don d'origines", "", f"- {p.don}"]
    if p.outils:
        lignes += ["", "## Maîtrise d'outil", "", f"- {p.outils}"]
    lignes += ["", "## Sorts connus", ""]
    if p.sorts:
        for s in p.sorts:
            lignes.append(f"- {s}")
    else:
        lignes.append("- Aucun sort connu")
    emplacements = p.emplacements
    if emplacements:
        lignes += ["", "## Emplacements de sort", ""]
        for niveau_sort in sorted(emplacements):
            e = emplacements[niveau_sort]
            lignes.append(
                f"- {niveau_sort}e niveau : {e['restants']}/{e['max']} restants"
            )
        lignes.append("- Tours de magie : illimités (aucun emplacement consommé)")
    lignes += ["", "## Équipement", ""]
    objets = list(p.equipement.objets)
    if p.babiole:
        objets.append(p.babiole)
    if objets:
        for obj in objets:
            lignes.append(f"- {obj}")
    else:
        lignes.append("- Aucun équipement")
    return "\n".join(lignes)


def vers_fiche(p: models.Personnage, uid: str | None = None) -> str:
    """Fiche complète au format du corpus (FICHE / CONTENU / FIN)."""
    if uid is None:
        uid = f"perso-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    entete = "\n".join(
        [
            _ligne("id", uid),
            _ligne("nom", p.nom),
            _ligne("type", "personnage"),
            _ligne("edition", "srd-5.2.1"),
            _ligne("mots_cles", f"{p.espece}, {p.classe}, {p.historique}"),
        ]
    )
    corps = en_markdown(p)
    return f"<<<FICHE>>>\n{entete}\n<<<CONTENU>>>\n{corps}\n<<<FIN>>>\n"


def vers_json(p: models.Personnage) -> str:
    """Rend le personnage en JSON (dict complet, prêt à stocker)."""
    return json.dumps(p.vers_dict(), ensure_ascii=False, indent=2)


def sauvegarder(
    p: models.Personnage,
    dossier: Path | None = None,
    uid: str | None = None,
) -> tuple[Path, Path]:
    """Écrit `<nom>.md` et `<nom>.json` dans `dnd_perso/perso/`.

    Retourne les chemins (markdown, json).
    """
    dossier = dossier or extract.PERSO_DIR
    dossier.mkdir(parents=True, exist_ok=True)
    nom = p.nom.replace(" ", "_").replace("/", "_") or "sans_nom"
    md_path = dossier / f"{nom}.md"
    json_path = dossier / f"{nom}.json"
    md_path.write_text(vers_fiche(p, uid=uid), encoding="utf-8")
    json_path.write_text(vers_json(p), encoding="utf-8")
    return md_path, json_path


__all__ = ["vers_fiche", "vers_json", "sauvegarder"]
