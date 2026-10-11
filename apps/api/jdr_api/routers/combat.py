"""Routes de gestion des rencontres de combat — plan `dnd/PLAN-COMBAT.md` §4.

Le router ne calcule rien : il **traduit HTTP <-> moteur** (`dnd_perso.combat`)
et **persiste** l'état de rencontre dans `extract.COMBAT_DIR` (un fichier JSON
par rencontre, relus à chaque appel — comme les fiches perso). Toute
l'arithmétique (initiative, attaque vs CA, critique, dégâts) vit dans le moteur.

Règle d'or : **le LLM ne calcule rien**. Le serveur lance les d20 des monstres ;
pour les PJ, il enregistre les dés annoncés par le joueur.

Cohérence PJ : dès qu'un PJ encaisse des dégâts (ou se soigne) en combat, la
valeur est **répercutée** sur sa fiche (`mj.modifier_personnage`) pour que
`data-perso/<nom>.json` reste la vérité des PV hors combat. Un seul chemin
d'écriture des PV d'un PJ.
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Header

from dnd_perso import combat, extract, models
from openui import mj

from jdr_api.commun import V, autorise, enveloppe

router = APIRouter()

# Identifiant de rencontre : alphanumérique + tirets/soulignés (anti traversée).
_ID_RE = re.compile(r"[\w-]{1,80}", re.UNICODE)


# ---------------------------------------------------------------------------
# Persistance (un fichier JSON par rencontre, relu à chaque appel)
# ---------------------------------------------------------------------------

def _chemin(id_: str) -> Path:
    return extract.COMBAT_DIR / f"rencontre-{id_}.json"


def _valider_id(id_: str) -> dict[str, Any] | None:
    id_ = (id_ or "").strip()
    if not id_ or ".." in id_ or not _ID_RE.fullmatch(id_):
        return {"ok": False, "v": V, "type": "erreur", "erreur": "Identifiant de rencontre invalide."}
    return None


def _charger(id_: str) -> tuple[combat.Rencontre | None, dict[str, Any] | None]:
    """Relit une rencontre. Retourne (rencontre, None) ou (None, enveloppe d'erreur)."""
    chemin = _chemin(id_)
    if not chemin.exists():
        return None, {"ok": False, "v": V, "type": "erreur", "erreur": f"Rencontre introuvable : {id_}"}
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, {"ok": False, "v": V, "type": "erreur", "erreur": f"Rencontre illisible : {exc}"}
    return combat.Rencontre.depuis_dict(donnees), None


def _sauvegarder(r: combat.Rencontre) -> None:
    extract.COMBAT_DIR.mkdir(parents=True, exist_ok=True)
    _chemin(r.id).write_text(
        json.dumps(r.vers_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Construction des combattants
# ---------------------------------------------------------------------------

def _pj_depuis_fiche(nom: str) -> tuple[combat.Combattant | None, str | None]:
    """Construit un Combattant « PJ » depuis sa fiche. Renvoie (combattant, erreur)."""
    chemin = extract.PERSO_DIR / f"{nom}.json"
    if not chemin.exists():
        return None, f"Personnage introuvable : {nom}"
    try:
        p = models.Personnage.depuis_dict(json.loads(chemin.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        return None, f"Fiche illisible : {exc}"
    pv = p.pv
    c = combat.Combattant(
        cle=f"pj:{p.nom}",
        nom=p.nom,
        camp="pj",
        pv=pv,
        pv_max=p.de_vie + p.carac.mod_con(),
        ca=p.ca,
        bonus_attaque=p.carac.mod_for() + p.bonus_maitrise,
        des_degats="1d8",
        mod_degats=p.carac.mod_for(),
        bonus_initiative=p.initiative,
    )
    return c, None


def _monstres_depuis_saisie(spec: dict[str, Any], index: int) -> list[combat.Combattant]:
    """Construit un ou plusieurs Combattants « monstre » depuis les stats **fournies**
    par le MJ (lus dans la fiche RAG). Le serveur ne les invente jamais.

    `nb` (défaut 1) crée plusieurs exemplaires numérotés.
    """
    nom = str(spec.get("nom", "monstre")).strip() or "monstre"
    pv = int(spec.get("pv", 1))
    ca = int(spec.get("ca", 10))
    bba = int(spec.get("attaque", 0))
    des = str(spec.get("degats", "1d6"))
    mod = int(spec.get("mod_degats", 0))
    binit = int(spec.get("init_bonus", 0))
    nb = max(1, int(spec.get("nb", 1)))
    sortie: list[combat.Combattant] = []
    for k in range(nb):
        suffixe = f" {k + 1}" if nb > 1 else ""
        sortie.append(combat.Combattant(
            cle=f"mon:{index + k}:{nom}{suffixe}".replace(" ", "_"),
            nom=f"{nom}{suffixe}",
            camp="monstre",
            pv=pv,
            pv_max=pv,
            ca=ca,
            bonus_attaque=bba,
            des_degats=des,
            mod_degats=mod,
            bonus_initiative=binit,
        ))
    return sortie


def _repercuter_pj(nom_pj: str, action: str, valeur: int, critique: bool = False) -> None:
    """Répercute dégâts/soins d'un PJ sur sa fiche (vérité hors combat)."""
    acte: dict[str, Any] = {"action": action, "valeur": valeur}
    if critique:
        acte["critique"] = True
    mj.modifier_personnage(nom_pj, [acte])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/api/combat/ouvrir")
def ouvrir(
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Ouvre une rencontre : construit les combattants et lance les initiatives.

    Corps : `{id?, titre?, combattants:[{type:"pj",nom} |
    {type:"monstre",nom,pv,ca,attaque,degats,mod_degats?,init_bonus?,nb?}]}`.
    """
    if (err := autorise(x_api_key)) is not None:
        return err

    id_ = str(body.get("id") or datetime.now().strftime("combat-%Y-%m-%d-%H%M%S"))
    if (err := _valider_id(id_)) is not None:
        return err
    if _chemin(id_).exists():
        return enveloppe({"ok": False, "type": "erreur", "erreur": f"Rencontre déjà ouverte : {id_}"})

    specs = body.get("combattants")
    if not isinstance(specs, list) or not specs:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "« combattants » doit être une liste non vide."})

    combattants: list[combat.Combattant] = []
    index_mon = 0
    for spec in specs:
        if not isinstance(spec, dict):
            return enveloppe({"ok": False, "type": "erreur", "erreur": f"Combattant invalide : {spec!r}"})
        type_ = str(spec.get("type", "")).strip().lower()
        if type_ == "pj":
            c, err = _pj_depuis_fiche(str(spec.get("nom", "")).strip())
            if err:
                return enveloppe({"ok": False, "type": "erreur", "erreur": err})
            combattants.append(c)  # type: ignore[arg-type]
        elif type_ == "monstre":
            nouveaux = _monstres_depuis_saisie(spec, index_mon)
            combattants.extend(nouveaux)
            index_mon += len(nouveaux)
        else:
            return enveloppe({"ok": False, "type": "erreur", "erreur": f"Type de combattant inconnu : {type_!r}"})

    if len(combattants) < 2:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Une rencontre exige au moins deux combattants."})

    rng = random.Random(body.get("seed")) if body.get("seed") is not None else random.Random()
    r = combat.Rencontre.ouvrir(
        id_, combattants,
        titre=str(body.get("titre", "")),
        rng=rng,
        campagne_id=str(body.get("campagne_id", "")).strip(),
    )
    _sauvegarder(r)
    return enveloppe(r.etat())


@router.get("/api/combat")
def lister(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Liste les rencontres persistées (id, titre, actif, tour, nb_combattants)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    dossier = extract.COMBAT_DIR
    rencontres: list[dict[str, Any]] = []
    if dossier.exists():
        for chemin in sorted(dossier.glob("rencontre-*.json")):
            try:
                d = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rencontres.append({
                "id": d.get("id", ""),
                "titre": d.get("titre", ""),
                "active": bool(d.get("active", True)),
                "tour": d.get("tour", 0),
                "nb_combattants": len(d.get("ordre", [])),
            })
    return enveloppe({"ok": True, "type": "liste", "rencontres": rencontres})


@router.get("/api/combat/{id}")
def etat(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """État complet d'une rencontre (ordre, tour, qui joue)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    return enveloppe(r.etat())  # type: ignore[union-attr]


@router.post("/api/combat/{id}/jet-monstre")
def jet_monstre(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Le serveur lance attaque + dégâts d'un monstre contre une cible."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    attaquant = r.combattant(str(body.get("attaquant", "")))  # type: ignore[union-attr]
    defenseur = r.combattant(str(body.get("cible", "")))  # type: ignore[union-attr]
    if attaquant is None or defenseur is None:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Attaquant ou cible inconnu."})
    if attaquant.camp != "monstre":
        return enveloppe({"ok": False, "type": "erreur", "erreur": "jet-monstre réservé aux monstres (le joueur annonce ses propres dés)."})

    rng = random.Random()
    res = combat.roller_attaque(attaquant, defenseur, rng)
    if defenseur.camp == "pj" and res["degats"] > 0:
        _repercuter_pj(defenseur.nom, "degats", res["degats"], critique=res["critique"])
    _sauvegarder(r)  # type: ignore[arg-type]
    return enveloppe(res)


@router.post("/api/combat/{id}/jet-joueur")
def jet_joueur(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Enregistre le jet annoncé par le joueur (le serveur ne lance pas le d20).

    Corps : `{attaquant, cible, de_attaque, de_degats?}`. `de_attaque` = le d20
    naturel du joueur ; `de_degats` = total de dégâts annoncé (optionnel : sinon
    le moteur lance les dés du PJ).
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    attaquant = r.combattant(str(body.get("attaquant", "")))  # type: ignore[union-attr]
    defenseur = r.combattant(str(body.get("cible", "")))  # type: ignore[union-attr]
    if attaquant is None or defenseur is None:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Attaquant ou cible inconnu."})

    try:
        jet = int(body.get("de_attaque"))
    except (TypeError, ValueError):
        return enveloppe({"ok": False, "type": "erreur", "erreur": "« de_attaque » (d20 du joueur) requis."})
    if not 1 <= jet <= 20:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Le d20 doit être entre 1 et 20."})

    degats_fournis = None
    if body.get("de_degats") is not None:
        try:
            degats_fournis = int(body.get("de_degats"))
        except (TypeError, ValueError):
            return enveloppe({"ok": False, "type": "erreur", "erreur": "« de_degats » invalide."})

    res = combat.resoudre_attaque(attaquant, defenseur, jet, random.Random(), degats_fournis=degats_fournis)
    if defenseur.camp == "pj" and res["degats"] > 0:
        _repercuter_pj(defenseur.nom, "degats", res["degats"], critique=res["critique"])
    _sauvegarder(r)  # type: ignore[arg-type]
    return enveloppe(res)


@router.post("/api/combat/{id}/tour-suivant")
def tour_suivant(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Avance d'une case dans l'ordre d'initiative (saute les morts)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    res = r.tour_suivant()  # type: ignore[union-attr]
    if res.get("ok"):
        _sauvegarder(r)  # type: ignore[arg-type]
    return enveloppe(res)


@router.patch("/api/combat/{id}")
def modifier(
    id: str,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Dégâts / soins / condition sur un combattant.

    Corps : `{cle, action:"degats"|"soigner"|"condition", valeur}`.
    Pour un PJ, l'effet est aussi répercuté sur sa fiche.
    """
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    c = r.combattant(str(body.get("cle", "")))  # type: ignore[union-attr]
    if c is None:
        return enveloppe({"ok": False, "type": "erreur", "erreur": "Combattant inconnu."})
    action = str(body.get("action", "")).strip().lower()
    valeur = body.get("valeur")

    if action == "degats":
        try:
            v = int(valeur)
        except (TypeError, ValueError):
            return enveloppe({"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"})
        res = combat.appliquer_degats(c, v)
        if res.get("ok") and c.camp == "pj":
            _repercuter_pj(c.nom, "degats", v)
    elif action in ("soigner", "soins"):
        try:
            v = int(valeur)
        except (TypeError, ValueError):
            return enveloppe({"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"})
        res = combat.appliquer_soins(c, v)
        if res.get("ok") and c.camp == "pj":
            _repercuter_pj(c.nom, "soigner", v)
    elif action == "condition":
        res = combat.ajouter_condition(c, str(valeur or ""))
    else:
        return enveloppe({"ok": False, "type": "erreur", "erreur": f"Action inconnue : {action!r}"})

    if res.get("ok"):
        _sauvegarder(r)  # type: ignore[arg-type]
    return enveloppe(res)


@router.post("/api/combat/{id}/cloturer")
def cloturer(
    id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Clôture une rencontre (les PV des PJ sont déjà persistés sur leur fiche)."""
    if (err := autorise(x_api_key)) is not None:
        return err
    if (err := _valider_id(id)) is not None:
        return err
    r, err = _charger(id)
    if err:
        return err
    res = r.cloturer()  # type: ignore[union-attr]
    _sauvegarder(r)  # type: ignore[arg-type]
    return enveloppe(res)
