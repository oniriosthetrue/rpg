"""Moteur de combat D&D 5.2.1 — pur, déterministe, sans dépendance externe.

Conçu pour être testable **hors stack** (aucun import FastAPI/HTTP) : le serveur
`jdr-api` et l'arène de test (`scripts/arena.py`) s'appuient tous deux sur ce
module. Règle d'or : **le LLM ne calcule rien** — toute l'arithmétique (jets,
PV, CA, critique) vit ici et renvoie des structures sérialisables en JSON.

Règles codées (SRD 5.2.1, chapitre « Règles de combat ») :
- **Initiative** : `d20 + bonus_d_initiative`, ordre décroissant.
- **Attaque** : `d20 + bonus_d_attaque` contre la CA. `nat 20` = critique
  (réussite auto), `nat 1` = échec auto.
- **Dégâts** : `NdM + modificateur`. Sur critique, on **double les dés**
  (on relance l'expression), **pas** le modificateur.
- **PV** : ne descendent jamais sous 0.

Les conditions (statuts) sont **stockées/affichées**, jamais simulées : leur
sémantique reste une règle textuelle du RAG que le MJ applique.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any

from dnd_perso import dice

# Un tour au-delà duquel une rencontre est considérée nulle (filet de sécurité
# de l'arène : évite les boucles infinies si deux combattants ne se touchent
# jamais).
PLAFOND_TOURS = 1000


# ---------------------------------------------------------------------------
# Combattant
# ---------------------------------------------------------------------------

@dataclass
class Combattant:
    """Un participant à une rencontre (PJ ou monstre), avec son état de combat.

    Les statistiques (CA, PV max, bonus d'attaque, dés de dégâts) sont
    **fournies** par l'appelant — fiche PJ (`dnd_perso.models`) ou fiche RAG du
    monstre. Le moteur ne les invente jamais.
    """

    cle: str
    nom: str
    camp: str  # "pj" | "monstre"
    pv: int
    pv_max: int
    ca: int
    bonus_attaque: int = 0
    des_degats: str = "1d6"
    mod_degats: int = 0
    bonus_initiative: int = 0
    initiative: int = 0
    conditions: list[str] = field(default_factory=list)

    @property
    def vivant(self) -> bool:
        return self.pv > 0

    def vers_dict(self) -> dict[str, Any]:
        return {
            "cle": self.cle,
            "nom": self.nom,
            "camp": self.camp,
            "pv": self.pv,
            "pv_max": self.pv_max,
            "ca": self.ca,
            "bonus_attaque": self.bonus_attaque,
            "des_degats": self.des_degats,
            "mod_degats": self.mod_degats,
            "bonus_initiative": self.bonus_initiative,
            "initiative": self.initiative,
            "conditions": list(self.conditions),
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Combattant":
        return cls(
            cle=str(d.get("cle", "")),
            nom=str(d.get("nom", "")),
            camp=str(d.get("camp", "monstre")),
            pv=int(d.get("pv", 0)),
            pv_max=int(d.get("pv_max", 0)),
            ca=int(d.get("ca", 10)),
            bonus_attaque=int(d.get("bonus_attaque", 0)),
            des_degats=str(d.get("des_degats", "1d6")),
            mod_degats=int(d.get("mod_degats", 0)),
            bonus_initiative=int(d.get("bonus_initiative", 0)),
            initiative=int(d.get("initiative", 0)),
            conditions=[str(c) for c in d.get("conditions", [])],
        )


# ---------------------------------------------------------------------------
# Jets
# ---------------------------------------------------------------------------

def roller_initiative(
    combattants: list[Combattant], rng: random.Random | None = None
) -> list[Combattant]:
    """Lance l'initiative de chaque combattant (`d20 + bonus`) et trie l'ordre.

    Tri : initiative décroissante ; égalité départagée par le bonus
    d'initiative (le plus rapide l'emporte), puis par nom pour rester
    déterministe.
    """
    rng = rng or random.Random()
    for c in combattants:
        c.initiative = dice.roll("1d20", rng) + c.bonus_initiative
    combattants.sort(
        key=lambda c: (-c.initiative, -c.bonus_initiative, c.nom)
    )
    return combattants


def resoudre_attaque(
    attaquant: Combattant,
    defenseur: Combattant,
    jet_d20: int,
    rng: random.Random | None = None,
    degats_fournis: int | None = None,
) -> dict[str, Any]:
    """Résout une attaque dont le **d20 est déjà connu**.

    Le d20 est fourni par l'appelant : pour un PJ c'est le **joueur** qui lance
    et communique son dé ; pour un monstre c'est le serveur qui l'a lancé. Le
    moteur ne relance jamais le d20 lui-même — il ne fait que trancher
    (touché/critique/échec) et calculer les dégâts.

    `degats_fournis` : si fourni (cas du **joueur** qui lance lui-même ses dés
    de dégâts), on applique cette valeur au lieu de lancer les dés du moteur.
    Le tranché (touché/critique) reste calculé par le moteur.

    Retourne un dict descriptif (aucun effet caché) ; **applique** les dégâts
    aux PV du défenseur.
    """
    rng = rng or random.Random()
    nat_critique = jet_d20 == 20
    nat_maladresse = jet_d20 == 1
    total = jet_d20 + attaquant.bonus_attaque
    if nat_maladresse:
        touche = False
    elif nat_critique:
        touche = True
    else:
        touche = total >= defenseur.ca

    des_lances: list[int] = []
    degats = 0
    if touche:
        if degats_fournis is not None:
            degats = max(0, int(degats_fournis))
        else:
            # Un critique double les DES, jamais le modificateur statique
            # intégré à l'expression (« 1d6+2 » -> 2×1d6 + 2, pas 2×(1d6+2)).
            des, stat = dice.decomposer(attaquant.des_degats)
            nb_fois = 2 if nat_critique else 1
            for _ in range(nb_fois):
                des_lances.append(dice.roll(des, rng))
            degats = sum(des_lances) + stat + attaquant.mod_degats
        defenseur.pv = max(0, defenseur.pv - degats)

    return {
        "ok": True,
        "type": "attaque",
        "attaquant": attaquant.cle,
        "defenseur": defenseur.cle,
        "jet_d20": jet_d20,
        "total": total,
        "ca_cible": defenseur.ca,
        "critique": nat_critique,
        "maladresse": nat_maladresse,
        "touche": touche,
        "degats": degats,
        "pv_restants": defenseur.pv,
        "hors_combat": not defenseur.vivant,
    }


def roller_attaque(
    attaquant: Combattant,
    defenseur: Combattant,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Lance le d20 d'attaque (cas du **monstre**, côté serveur) puis résout."""
    rng = rng or random.Random()
    jet = dice.roll("1d20", rng)
    return resoudre_attaque(attaquant, defenseur, jet, rng)


def resoudre_sauvegarde(
    combattant: Combattant,
    bonus_sauvegarde: int,
    dd: int,
    jet_d20: int,
) -> dict[str, Any]:
    """Résout un jet de sauvegarde dont le d20 est connu (réussite si `>= dd`)."""
    total = jet_d20 + bonus_sauvegarde
    return {
        "ok": True,
        "type": "sauvegarde",
        "combattant": combattant.cle,
        "jet_d20": jet_d20,
        "total": total,
        "dd": dd,
        "reussie": jet_d20 == 20 or (jet_d20 != 1 and total >= dd),
    }


# ---------------------------------------------------------------------------
# Modification d'état (dégâts / soins / conditions)
# ---------------------------------------------------------------------------

def appliquer_degats(combattant: Combattant, valeur: int) -> dict[str, Any]:
    if valeur <= 0:
        return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
    avant = combattant.pv
    combattant.pv = max(0, combattant.pv - valeur)
    return {
        "ok": True,
        "type": "degats",
        "cle": combattant.cle,
        "degats": avant - combattant.pv,
        "pv_restants": combattant.pv,
        "hors_combat": not combattant.vivant,
    }


def appliquer_soins(combattant: Combattant, valeur: int) -> dict[str, Any]:
    if valeur <= 0:
        return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
    avant = combattant.pv
    combattant.pv = min(combattant.pv_max, combattant.pv + valeur)
    return {
        "ok": True,
        "type": "soins",
        "cle": combattant.cle,
        "soigne": combattant.pv - avant,
        "pv_restants": combattant.pv,
    }


def ajouter_condition(combattant: Combattant, condition: str) -> dict[str, Any]:
    cond = str(condition or "").strip()
    if not cond:
        return {"ok": False, "type": "erreur", "erreur": "Condition manquante."}
    if cond not in combattant.conditions:
        combattant.conditions.append(cond)
    return {
        "ok": True,
        "type": "condition",
        "cle": combattant.cle,
        "conditions": list(combattant.conditions),
    }


# ---------------------------------------------------------------------------
# Rencontre
# ---------------------------------------------------------------------------

@dataclass
class Rencontre:
    """Une rencontre active : ordre d'initiative + tour courant."""

    id: str
    titre: str = ""
    active: bool = True
    tour: int = 1
    ordre: list[Combattant] = field(default_factory=list)
    index_actif: int = 0

    # -- accès ---------------------------------------------------------------

    def combattant(self, cle: str) -> Combattant | None:
        for c in self.ordre:
            if c.cle == cle:
                return c
        return None

    @property
    def actif(self) -> Combattant | None:
        if 0 <= self.index_actif < len(self.ordre):
            return self.ordre[self.index_actif]
        return None

    @property
    def camps_en_jeu(self) -> set[str]:
        return {c.camp for c in self.ordre if c.vivant}

    @property
    def finie(self) -> bool:
        return len(self.camps_en_jeu) <= 1

    # -- ouverture -----------------------------------------------------------

    @classmethod
    def ouvrir(
        cls,
        id: str,
        combattants: list[Combattant],
        titre: str = "",
        rng: random.Random | None = None,
    ) -> "Rencontre":
        """Ouvre une rencontre : lance les initiatives et place le 1er tour."""
        rng = rng or random.Random()
        ordre = roller_initiative(list(combattants), rng)
        rencontre = cls(id=id, titre=titre, ordre=ordre, index_actif=0, tour=1)
        rencontre._aligner_sur_vivant()
        return rencontre

    # -- tour ----------------------------------------------------------------

    def tour_suivant(self) -> dict[str, Any]:
        """Avance au prochain combattant **vivant** ; incrémente le tour au
        passage en bout de liste. Refuse si la rencontre est finie."""
        if not self.active:
            return {"ok": False, "type": "erreur", "erreur": "Rencontre clôturée."}
        if self.finie:
            return {
                "ok": False,
                "type": "erreur",
                "erreur": "Rencontre terminée : il ne reste qu'un camp en vie.",
            }
        n = len(self.ordre)
        pas = self.index_actif
        for _ in range(n):
            pas = (pas + 1) % n
            if pas == 0:
                self.tour += 1
            if self.ordre[pas].vivant:
                self.index_actif = pas
                break
        return {
            "ok": True,
            "type": "tour",
            "tour": self.tour,
            "actif": self.actif.cle if self.actif else None,
        }

    def _aligner_sur_vivant(self) -> None:
        """Place `index_actif` sur le premier combattant vivant (après ouverture)."""
        for i, c in enumerate(self.ordre):
            if c.vivant:
                self.index_actif = i
                return

    # -- clôture -------------------------------------------------------------

    def cloturer(self) -> dict[str, Any]:
        self.active = False
        vainqueurs = sorted(self.camps_en_jeu)
        return {
            "ok": True,
            "type": "cloture",
            "id": self.id,
            "tour": self.tour,
            "vainqueurs": vainqueurs,
        }

    # -- sérialisation -------------------------------------------------------

    def vers_dict(self) -> dict[str, Any]:
        return {
            "v": 1,
            "id": self.id,
            "titre": self.titre,
            "active": self.active,
            "tour": self.tour,
            "index_actif": self.index_actif,
            "ordre": [c.vers_dict() for c in self.ordre],
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Rencontre":
        return cls(
            id=str(d.get("id", "")),
            titre=str(d.get("titre", "")),
            active=bool(d.get("active", True)),
            tour=int(d.get("tour", 1)),
            index_actif=int(d.get("index_actif", 0)),
            ordre=[Combattant.depuis_dict(c) for c in d.get("ordre", [])],
        )

    # -- rendu ---------------------------------------------------------------

    def etat(self) -> dict[str, Any]:
        """Vue d'ensemble sérialisable (pour l'API / l'outil)."""
        return {
            "ok": True,
            "type": "rencontre",
            "id": self.id,
            "titre": self.titre,
            "active": self.active,
            "tour": self.tour,
            "finie": self.finie,
            "actif": self.actif.cle if self.actif else None,
            "ordre": [
                {
                    "cle": c.cle,
                    "nom": c.nom,
                    "camp": c.camp,
                    "initiative": c.initiative,
                    "pv": c.pv,
                    "pv_max": c.pv_max,
                    "ca": c.ca,
                    "conditions": list(c.conditions),
                    "vivant": c.vivant,
                }
                for c in self.ordre
            ],
        }
