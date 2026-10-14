"""Routes de gestion des campagnes / scénarios — plan `dnd/PLAN-SCENARIO.md`.

Le router ne calcule rien et n'invente jamais une intrigue : il **traduit
HTTP <-> moteur** (`dnd_perso.campagne`) et **persiste** l'état canonique dans
`extract.CAMPAGNE_DIR` (un fichier JSON par campagne, relu à chaque appel — comme
les rencontres de combat). Toute la logique (validation de structure, transitions
de phase, advisory d'équilibrage, parseur Markdown) vit dans le moteur.

Règle d'or (prolongement du combat) : **le LLM ne génère pas l'état, il le
déclare ; le moteur ne crée pas l'histoire, il la mémorise.**

Le contenu narratif (prose des scènes) reste la responsabilité du MJ/LLM ; le
moteur n'en garde que des champs de texte opaques et la structure du brief.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Header

from dnd_perso import campagne as cp
from dnd_perso import extract
from dnd_perso import variete

from jdr_api.commun import V, autorise, enveloppe

router = APIRouter()

# Identifiant de campagne : alphanumérique + tirets/soulignés (anti traversée).
_ID_RE = re.compile(r"[\w-]{1,80}", re.UNICODE)


# Message d'ouverture canonique d'une campagne (relance d'une partie). C'est la
# MÊME amorce envoyée à la création (wizard) et à chaque « Rejouer » : le backend
# en est la source unique, pour qu'une partie recommencée s'ouvre exactement comme
# une partie neuve (le frontend ne le construit plus lui-même). Identique quel que
# soit le `mode` (guide ou surprise) — l'ouverture raconte toujours l'accroche.
_MESSAGE_OUVERTURE = (
    "Ouvre la campagne : raconte l'accroche en expliquant pourquoi le "
    "personnage est là et donne-lui une raison personnelle et concrète "
    "d'avancer dans la quête (un objectif immédiat, ce qu'il risque ou "
    "gagne, lié à son crochet personnel). Puis lance la partie."
)


def _message_ouverture(mode: str = "") -> str:
    """Amorce d'ouverture d'une campagne (identique pour tous les modes)."""
    return _MESSAGE_OUVERTURE


# ---------------------------------------------------------------------------
# Persistance (un fichier JSON par campagne, relu à chaque appel)
# ---------------------------------------------------------------------------

def _chemin(id_: str) -> Path:
    return extract.CAMPAGNE_DIR / f"campagne-{id_}.json"


def _valider_id(id_: str) -> dict[str, Any] | None:
    id_ = (id_ or "").strip()
    if not id_ or ".." in id_ or not _ID_RE.fullmatch(id_):
        return {"ok": False, "v": V, "type": "erreur", "erreur": "Identifiant de campagne invalide."}
    return None


def _charger(id_: str) -> tuple[cp.Campagne | None, dict[str, Any] | None]:
    """Relit une campagne. Retourne (campagne, None) ou (None, enveloppe d'erreur)."""
    chemin = _chemin(id_)
    if not chemin.exists():
        return None, {"ok": False, "v": V, "type": "erreur", "erreur": f"Campagne introuvable : {id_}"}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, {"ok": False, "v": V, "type": "erreur", "erreur": f"Campagne illisible : {exc}"}
    return cp.Campagne.depuis_dict(donnees), None


def _sauvegarder(c: cp.Campagne) -> None:
    extract.CAMPAGNE_DIR.mkdir(parents=True, exist_ok=True)
    _chemin(c.id).write_text(
        json.dumps(c.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/campagne/ouvrir")
def ouvrir(
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Ouvre une campagne depuis une structure JSON (celle du moteur).

    Corps : les champs d'une `Campagne` (`titre`, `pj`, `pnj`, `crochets`,
    `defis`, `lieux`, `blocs`, `danger`, …). `id` optionnel (défaut horodaté).
    L'état est persisté puis relu ; `etat()` inclut `structure_valide` et les
    `avertissements_structure` (la structure est *signalée*, jamais bloquante :
    le MJ peut ouvrir un scénario encore incomplet et le compléter ensuite).
    """
    if (err := autorise(x_api_key)) is not None:
        return err

    id_ = str(body.get("id") or datetime.now().strftime("%Y-%m-%d-%H%M%S"))
    if (err := _valider_id(id_)) is not None:
        return err
    if _chemin(id_).exists():
        return enveloppe({"ok": False, "type": "erreur", "erreur": f"Campagne déjà ouverte : {id_}"})

    corps = dict(body)
    corps["id"] = id_
    c = cp.Campagne.depuis_dict(corps)
    _sauvegarder(c)
    etat = c.etat()
    # Graines d'inspiration (variété) : 2 par dimension à l'ouverture, renvoyées au
    # client pour être injectées dans la consigne du MJ. Transitoires — NON persistées.
    etat["inspirations"] = variete.tirer_inspirations(nb=2)
    return enveloppe(etat)


@router.post("/api/campagne/importer")
def importer(
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Importe une campagne depuis le **Markdown à front-matter** d'un scénario.

    Corps : `{markdown, id?}`. L'en-tête YAML porte la structure, le corps est
    ignoré pour l'état canonique (il reste lisible dans le fichier source).
    """
    if (err := autorise(x_api_key)) is not None:
        return err

    markdown = body.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return enveloppe({"ok": False, "type": "erreur", "erreur": "« markdown » (texte du scénario) requis."})

    id_ = str(body.get("id") or "").strip()
    c = cp.campagne_depuis_markdown(markdown, id_fallback=id_)
    if not c.id:
        c.id = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    if (err := _valider_id(c.id)) is not None:
        return err
    if _chemin(c.id).exists():
        return enveloppe({"ok": False, "type": "erreur", "erreur": f"Campagne déjà ouverte : {c.id}"})

    _sauvegarder(c)
    return enveloppe(c.etat())


@router.get("/api/campagne")
def lister(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Liste les campagnes persistées (id, titre, phase, active)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    dossier = extract.CAMPAGNE_DIR
    campagne: list[dict[str, Any]] = []
    if dossier.exists():
        for chemin in sorted(dossier.glob("campagne-*.json")):
            try:
                d = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            campagne.append({
                "id": d.get("id", ""),
                "titre": d.get("titre", ""),
                "phase": d.get("phase", ""),
                "active": bool(d.get("active", True)),
            })
    return enveloppe({"ok": True, "type": "liste", "campagnes": campagne})


@router.get("/api/campagne/{id}")
def etat(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """État complet d'une campagne (pour relecture après reset de contexte)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err
    return enveloppe(c.etat())  # type: ignore[union-attr]


@router.post("/api/campagne/{id}/ecrire")
def ecrire(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Écrit / met à jour la **trame** d'une campagne déjà ouverte (le MJ conçoit,
    le moteur mémorise + valide).

    Corps : les champs de trame à poser (`titre`, `synopsis`, `accroche`, `enjeux`,
    `motivations`, `danger`, `pnj`, `defis`, `crochets`, `lieux`, `blocs`). Seuls
    les champs fournis sont écrits ; le cadrage et l'état de partie (`phase`,
    `indices`, chronologie, statuts déjà joués) sont **préservés**. Renvoie
    `etat()` avec `structure_valide` et `avertissements_structure` (signalés,
    jamais bloquants). C'est l'outil qui manquait pour persister le scénario que
    le MJ invente (sinon la campagne reste une coquille vide de cadrage).
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err
    res = c.ecrire_structure(body)  # type: ignore[union-attr]
    _sauvegarder(c)  # type: ignore[arg-type]
    return enveloppe(res)


@router.patch("/api/campagne/{id}")
def modifier(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Applique une mutation déclarée à la campagne (le MJ déclare, le moteur mémorise).

    Corps : `{action, ...}` où `action` est une des ACTIONS du moteur
    (`avancer_phase`, `resoudre_crochet`, `rencontrer_pnj`, `changer_attitude`,
    `deplacer_bloc`, `ajouter_indice`, `accorder_recompense`, `decouvrir_lieu`, …)
    et les paramètres associés (`id`, `nom`, `attitude`, `position`, `indice`, …).
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err

    action = str(body.get("action", "")).strip()
    kwargs = {k: v for k, v in body.items() if k != "action"}
    res = c.modifier(action, **kwargs)  # type: ignore[union-attr]
    if res.get("ok"):
        _sauvegarder(c)  # type: ignore[arg-type]
    return enveloppe(res)


@router.post("/api/campagne/{id}/advisory")
def advisory(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Advisory d'équilibrage d'une rencontre pour le groupe de la campagne.

    Corps : `{niveaux_pj?:[int], rencontre?:{monstres:[{nom,nb?,cr?}]} | monstres?:[...]}`.
    Sans `niveaux_pj`, on les déduit des fiches des PJ portés par la campagne (si
    elles existent). **Le moteur informe, il ne décide pas** : il ne modifie jamais
    stats ni effectifs — le scénario garde la main (ajouter/retirer des copies via
    `nb`, choisir des créatures de CR moindre).
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err

    # Niveaux du groupe : fournis, sinon déduits des fiches des PJ de la campagne.
    niveaux = body.get("niveaux_pj")
    if not isinstance(niveaux, list) or not niveaux:
        niveaux = _niveaux_des_pj(c.pj)  # type: ignore[union-attr]

    # Monstres de la rencontre : sous `rencontre.monstres` ou directement `monstres`.
    rencontre = body.get("rencontre")
    if isinstance(rencontre, dict) and "monstres" in rencontre:
        specs = rencontre.get("monstres", [])
    else:
        specs = body.get("monstres", [])
    if not isinstance(specs, list) or not specs:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Aucun monstre fourni pour l'advisory."})

    monstres = [cp.MonstreScenarise.depuis_dict(m) for m in specs if isinstance(m, dict)]
    res = cp.advisory_difficulte([int(n) for n in niveaux], monstres)
    return enveloppe(res)


@router.delete("/api/campagne/{id}")
def supprimer(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Supprime définitivement une campagne (son fichier JSON persisté)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    chemin = _chemin(id)
    if not chemin.exists():
        return {"ok": False, "v": V, "type": "erreur", "erreur": f"Campagne introuvable : {id}"}
    chemin.unlink(missing_ok=True)
    # Cascade : supprime aussi les rencontres de combat rattachées à cette campagne
    # (liaison via le champ `campagne_id` persisté à l'ouverture du combat).
    supprimes = _supprimer_combats_de_la_campagne(id)
    return {"ok": True, "v": V, "type": "supprime", "id": id, "combats_supprimes": supprimes}


def _supprimer_combats_de_la_campagne(id_: str) -> list[str]:
    """Supprime les fichiers de rencontre dont `campagne_id == id_`. Renvoie la
    liste des identifiants de combat supprimés (best-effort, ignore les illisibles)."""
    supprimes: list[str] = []
    dossier = extract.COMBAT_DIR
    if not dossier.exists():
        return supprimes
    for fichier in dossier.glob("rencontre-*.json"):
        try:
            donnees = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str(donnees.get("campagne_id", "")) == id_:
            fichier.unlink(missing_ok=True)
            supprimes.append(str(donnees.get("id", fichier.stem)))
    return supprimes


@router.post("/api/campagne/{id}/cloturer")
def cloturer(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Clôture une campagne (la rend inactive, journalise la clôture)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err
    res = c.cloturer()  # type: ignore[union-attr]
    _sauvegarder(c)  # type: ignore[arg-type]
    return enveloppe(res)


@router.post("/api/campagne/{id}/rejouer")
def rejouer(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Réinitialise la **partie** d'une campagne pour la rejouer depuis le début.

    La **trame** (synopsis, accroche, PNJ, défis, crochets, lieux, blocs) et le
    **personnage** sont conservés : seule l'état de jeu repart de zéro (phase
    `accroche`, campagne réactivée, indices/récompenses/chronologie vidés, crochets
    rouverts, lieux/PNJ non rencontrés, blocs repositionnés). Renvoie l'`etat()`
    réinitialisé, prêt à ouvrir une nouvelle conversation sur la même campagne.
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    c, err = _charger(id)
    if err:
        return err
    c.rejouer()  # type: ignore[union-attr]
    _sauvegarder(c)  # type: ignore[arg-type]
    etat = c.etat()  # type: ignore[union-attr]
    # Le backend fournit l'amorce d'ouverture (identique à celle de la création) :
    # le frontend n'a plus qu'à l'envoyer, sans la re-construire lui-même.
    etat["message"] = _message_ouverture(c.mode)  # type: ignore[union-attr]
    return enveloppe(etat)


def _niveaux_des_pj(noms_pj: list[str]) -> list[int]:
    """Déduit le niveau de chaque PJ depuis sa fiche (`extract.PERSO_DIR`). Silence
    sur les fiches absentes/illisible (l'advisory reste calculable sur le reste)."""
    niveaux: list[int] = []
    for nom in noms_pj:
        chemin = extract.PERSO_DIR / f"{nom}.json"
        if not chemin.exists():
            continue
        try:
            d = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        try:
            niveaux.append(int(d.get("niveau", 1)))
        except (TypeError, ValueError):
            niveaux.append(1)
    return niveaux

