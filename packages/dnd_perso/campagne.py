"""Moteur de campagne / scénario D&D 5.2.1 — pur, déterministe, sans dépendance externe.

Conçu pour être testable **hors stack** (aucun import FastAPI/HTTP), comme
`dnd_perso.combat` : le serveur `jdr-api` s'appuie sur ce module pour valider la
structure, persister et relire l'état d'une campagne.

Règle d'or (prolongement de celle du combat) :
**le LLM ne génère pas l'état, il le déclare ; le moteur ne crée pas l'histoire,
il la mémorise.**

Ce module ne crée donc **jamais** une intrigue : il ne fait que
- décrire la structure d'une campagne (dataclasses + sérialisation JSON),
- valider que la structure respecte le brief du MJ (>=2 crochets liés aux PJ,
  >=2 approches par défi, chaque PNJ complet, phase dans l'enum),
- appliquer des transitions déclarées (avancer la phase, résoudre un crochet,
  déplacer un bloc « Schrödinger », rencontrer un PNJ, …),
- relire fidèlement l'état (pour survivre à un reset de contexte),
- calculer une **advisory d'équilibrage** honnête (budget d'XP SRD 5.2.1) :
  le moteur *informe* de la dangerosité d'une rencontre, le scénario *décide*.

Le contenu narratif (prose des scènes, dialogues, descriptions) reste la
responsabilité du LLM ; le moteur n'en garde que des champs de texte opaques.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Enums / constantes
# ---------------------------------------------------------------------------

# Les 4 temps du rythme « montagne russe » du brief MJ.
PHASES = ["accroche", "montee", "climax", "conclusion"]

# Degrés de danger portés par la campagne (informatifs : le moteur ne modifie
# jamais les stats pour « équilibrer » — voir advisory_difficulte).
DANGERS = ["facile", "normale", "mortelle"]

# Statuts possibles d'un crochet narratif.
CROCHETS_STATUTS = ["ouverte", "resolvee", "abandonnee"]

# Les 3 piliers d'un scénario (Exploration / Interaction sociale / Combat).
PILIERS = ["exploration", "social", "combat"]

# Modes de création d'un scénario : « guide » (construit avec le MJ) ou
# « surprise » (le MJ l'invente en secret et ne révèle que l'accroche).
MODES = ["guide", "surprise"]

# Durées visées (orientent le nombre de scènes/blocs conseillé).
DUREES = ["one-shot", "courte", "moyenne", "longue"]

# Nombre de scènes/blocs conseillé selon la durée visée (advisory, jamais imposé).
_NB_SCENES_PAR_DUREE = {
    "one-shot": (3, 4),
    "courte": (5, 7),
    "moyenne": (8, 12),
    "longue": (12, 20),
}

# Alias de statuts de crochet que le LLM emploie parfois (normalisés vers CROCHETS_STATUTS).
_CROCHET_ALIAS = {
    "actif": "ouverte",
    "actives": "ouverte",
    "ouvert": "ouverte",
    "en cours": "ouverte",
    "verrouille": "ouverte",
    "verrouillé": "ouverte",
    "verrouillee": "resolvee",
    "verrouillée": "resolvee",
    "clos": "resolvee",
    "close": "resolvee",
    "fini": "resolvee",
    "abandonne": "abandonnee",
    "abandonnée": "abandonnee",
}


def _slug(texte: str) -> str:
    """Fabrique un identifiant ASCII à partir d'un titre (sans dépendance externe)."""
    t = unicodedata.normalize("NFKD", texte or "").encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "bloc"


def _entier(valeur: Any) -> int:
    """Convertit une valeur quelconque en entier (0 si invalide/absent)."""
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return 0


def conseil_cadrage(age_joueur: int, duree: str) -> dict[str, Any]:
    """Conseil de cadrage narratif selon l'âge du joueur et la durée visée.

    Le moteur **informe, il ne décide pas** : il suggère un registre de ton et
    un niveau de violence adaptés à l'âge, ainsi qu'un nombre de scènes indicatif
    selon la durée. Le MJ/LLM garde la main sur l'écriture.
    """
    conseil: dict[str, Any] = {}
    if age_joueur and age_joueur > 0:
        if age_joueur < 10:
            conseil["ton"] = (
                "Enfants : merveilleux et humoristique, violence implicite et "
                "sans gore, enjeux simples et optimistes."
            )
            conseil["violence"] = "implicite"
        elif age_joueur < 13:
            conseil["ton"] = (
                "Préados : aventure palpitante, tension sans horreur graphique, "
                "méchants menaçants mais combat reste « propre »."
            )
            conseil["violence"] = "moderee"
        elif age_joueur < 16:
            conseil["ton"] = (
                "Ados : enjeux moraux plus nuancés, tension et sacrifice "
                "possibles, violence sans sadisme gratuit."
            )
            conseil["violence"] = "assumee"
        else:
            conseil["ton"] = (
                "Adultes : tous registres permis (sombre, moralité grise, "
                "horreur, romance), violence et conséquences assumées."
            )
            conseil["violence"] = "sans_restriction"
    if duree in _NB_SCENES_PAR_DUREE:
        mini, maxi = _NB_SCENES_PAR_DUREE[duree]
        conseil["duree"] = duree
        conseil["scenes_conseillees"] = f"{mini}-{maxi}"
    return conseil


# Actions déclaratives acceptées par `Campagne.modifier` (le PATCH du routeur).
ACTIONS = [
    "avancer_phase",
    "resoudre_crochet",
    "ouvrir_crochet",
    "abandonner_crochet",
    "rencontrer_pnj",
    "changer_attitude",
    "deplacer_bloc",
    "ajouter_indice",
    "accorder_recompense",
    "decouvrir_lieu",
]


# ---------------------------------------------------------------------------
# Sous-objets de la campagne
# ---------------------------------------------------------------------------

@dataclass
class PNJ:
    """Un PNJ « rapide » du brief : Objectif / Faille / Attitude de départ."""

    nom: str
    objectif: str = ""
    faille: str = ""
    attitude: str = ""
    rencontre: bool = False  # déjà croisé par le groupe ?

    def vers_dict(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "objectif": self.objectif,
            "faille": self.faille,
            "attitude": self.attitude,
            "rencontre": self.rencontre,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "PNJ":
        return cls(
            nom=str(d.get("nom", "")),
            objectif=str(d.get("objectif", "")),
            faille=str(d.get("faille", "")),
            attitude=str(d.get("attitude", "")),
            rencontre=bool(d.get("rencontre", False)),
        )

    def complet(self) -> bool:
        """Un PNJ est « complet » s'il a objectif + faille + attitude (règle du brief)."""
        return bool(self.objectif and self.faille and self.attitude)


@dataclass
class MonstreScenarise:
    """Un monstre tel que le scénario le *curle* pour une rencontre précise.

    Le moteur ne lit pas les stats ici (elles viennent de la fiche RAG au moment
    d'ouvrir le combat) : le scénario porte le **« quoi » tactique** — la tactique
    attendue et les pouvoirs à utiliser — que le MJ déclare au moteur de combat
    (`lancer_le_jet_d_un_monstre`). Voir `dnd/CONTRAT-API-JDR.md` §12.
    """

    nom: str
    nb: int = 1
    cr: str = ""  # facteur de puissance, fourni par la fiche RAG (jamais inventé)
    comportement: str = ""  # tactique : « attaque le PJ isolé, fuit si <5 PV »
    pouvoirs_a_utiliser: list[str] = field(default_factory=list)

    def vers_dict(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "nb": self.nb,
            "cr": self.cr,
            "comportement": self.comportement,
            "pouvoirs_a_utiliser": list(self.pouvoirs_a_utiliser),
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "MonstreScenarise":
        return cls(
            nom=str(d.get("nom", "")),
            nb=max(1, int(d.get("nb", 1))),
            cr=str(d.get("cr", "")),
            comportement=str(d.get("comportement", "")),
            pouvoirs_a_utiliser=[str(p) for p in d.get("pouvoirs_a_utiliser", [])],
        )


@dataclass
class Rencontre:
    """Une rencontre portée par un lieu : monstres scénarisés + intention."""

    titre: str = ""
    monstres: list[MonstreScenarise] = field(default_factory=list)
    terrain: str = ""  # terrain dynamique / avantage tactique narratif

    def vers_dict(self) -> dict[str, Any]:
        return {
            "titre": self.titre,
            "monstres": [m.vers_dict() for m in self.monstres],
            "terrain": self.terrain,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Rencontre":
        return cls(
            titre=str(d.get("titre", "")),
            monstres=[MonstreScenarise.depuis_dict(m) for m in d.get("monstres", [])],
            terrain=str(d.get("terrain", "")),
        )


@dataclass
class Lieu:
    """Un lieu clé : description, obstacles, piliers représentés, rencontre.

    `zone` qualifie explicitement le lieu pour le moteur de combat :
    - `"dangereuse"` : un affrontement y est possible (une `rencontre` y est
      planifiée, ou le MJ l'a déclarée comme telle) ;
    - `"sure"` : aucun combat ne doit y éclore — le MJ y raconte sans arme.
    Par défaut, un lieu est dangereux s'il porte une `rencontre`, sûr sinon.
    """

    nom: str
    description: str = ""
    obstacles: str = ""
    piliers: list[str] = field(default_factory=list)
    rencontre: Rencontre | None = None
    decouvert: bool = False
    zone: str = ""  # "sure" | "dangereuse" (vide = déduit de la rencontre)

    @property
    def est_dangereuse(self) -> bool:
        """Le combat est-il licite dans ce lieu ?"""
        z = (self.zone or "").strip().lower()
        if z in ("dangereuse", "dangereux", "danger"):
            return True
        if z in ("sure", "sur", "safe", "paix"):
            return False
        return self.rencontre is not None  # défaut : déduit de la rencontre planifiée

    def vers_dict(self) -> dict[str, Any]:
        return {
            "nom": self.nom,
            "description": self.description,
            "obstacles": self.obstacles,
            "piliers": list(self.piliers),
            "rencontre": self.rencontre.vers_dict() if self.rencontre else None,
            "decouvert": self.decouvert,
            "zone": self.zone or ("dangereuse" if self.est_dangereuse else "sure"),
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Lieu":
        ren = d.get("rencontre")
        # Tolérance : le LLM écrit parfois « note » au lieu de « description ».
        description = d.get("description") or d.get("note") or ""
        return cls(
            nom=str(d.get("nom", "")),
            description=str(description),
            obstacles=str(d.get("obstacles", "")),
            piliers=[str(p) for p in d.get("piliers", [])],
            rencontre=Rencontre.depuis_dict(ren) if isinstance(ren, dict) else None,
            decouvert=bool(d.get("decouvert", False)),
            zone=str(d.get("zone", "")).strip().lower(),
        )


@dataclass
class Defi:
    """Un défi / obstacle non-linéaire : jamais une seule solution (>=2 approches)."""

    nom: str
    approches: list[str] = field(default_factory=list)

    def vers_dict(self) -> dict[str, Any]:
        return {"nom": self.nom, "approches": list(self.approches)}

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Defi":
        return cls(
            nom=str(d.get("nom", "")),
            approches=[str(a) for a in d.get("approches", [])],
        )


@dataclass
class Crochet:
    """Un crochet narratif lié au background d'un PJ (moteur de l'implication)."""

    id: str
    titre: str = ""
    lie_a_pj: str = ""
    statut: str = "ouverte"

    def vers_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titre": self.titre,
            "lie_a_pj": self.lie_a_pj,
            "statut": self.statut,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Crochet":
        statut = str(d.get("statut", "ouverte")).strip().lower()
        if statut not in CROCHETS_STATUTS:
            statut = _CROCHET_ALIAS.get(statut, "ouverte")
        return cls(
            id=str(d.get("id", "")),
            titre=str(d.get("titre", "")),
            lie_a_pj=str(d.get("lie_a_pj", "")),
            statut=statut,
        )


@dataclass
class Bloc:
    """Un bloc d'événement modulaire (« Schrödinger's Dungeon »).

    Le MJ peut le déplacer (le *relocaliser* ailleurs) si les joueurs sortent du
    chemin prévu : `position` = actif|reserve, `deplace` = déjà relocalisé.
    """

    id: str
    titre: str = ""
    contenu: str = ""
    position: str = "actif"
    deplace: bool = False

    def vers_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "titre": self.titre,
            "contenu": self.contenu,
            "position": self.position,
            "deplace": self.deplace,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Bloc":
        # Tolérance : le LLM écrit parfois « nom »/« note » au lieu de « titre »/
        # « contenu », et omet l'« id ». On normalise et on auto-génère un id.
        titre = str(d.get("titre") or d.get("nom") or "")
        contenu = str(d.get("contenu") or d.get("note") or "")
        id_ = str(d.get("id") or "").strip() or _slug(titre)
        return cls(
            id=id_,
            titre=titre,
            contenu=contenu,
            position=str(d.get("position", "actif")),
            deplace=bool(d.get("deplace", False)),
        )


# ---------------------------------------------------------------------------
# Campagne
# ---------------------------------------------------------------------------

@dataclass
class Campagne:
    """L'état canonique d'un scénario suivi par le MJ (persisté en JSON)."""

    id: str
    titre: str = ""
    synopsis: str = ""
    pj: list[str] = field(default_factory=list)
    phase: str = "accroche"
    danger: str = "normale"
    active: bool = True
    accroche: str = ""
    enjeux: str = ""
    motivations: str = ""
    lieux: list[Lieu] = field(default_factory=list)
    pnj: list[PNJ] = field(default_factory=list)
    defis: list[Defi] = field(default_factory=list)
    crochets: list[Crochet] = field(default_factory=list)
    blocs: list[Bloc] = field(default_factory=list)
    indices: list[str] = field(default_factory=list)
    recompenses: list[str] = field(default_factory=list)
    chronologie: list[str] = field(default_factory=list)
    # -- cadrage de la création (renseigné par le joueur, exploité par le MJ) --
    mode: str = "guide"  # "guide" | "surprise"
    age_joueur: int = 0  # âge du joueur (0 = non renseigné) — oriente le ton
    duree: str = ""  # "one-shot" | "courte" | "moyenne" | "longue"
    nb_joueurs: int = 0  # effectif du groupe (0 = non renseigné)
    niveaux: list[int] = field(default_factory=list)  # niveau de chaque PJ
    piliers: list[str] = field(default_factory=list)  # piliers préférés
    ton: str = ""  # ton souhaité (sombre, épique, humoristique…)
    theme: str = ""  # thème / point de départ libre

    # -- accès ---------------------------------------------------------------

    def pnj_par_nom(self, nom: str) -> PNJ | None:
        for p in self.pnj:
            if p.nom == nom:
                return p
        return None

    def crochet_par_id(self, id_: str) -> Crochet | None:
        for c in self.crochets:
            if c.id == id_:
                return c
        return None

    def bloc_par_id(self, id_: str) -> Bloc | None:
        for b in self.blocs:
            if b.id == id_:
                return b
        return None

    def lieu_par_nom(self, nom: str) -> Lieu | None:
        for l in self.lieux:
            if l.nom == nom:
                return l
        return None

    # -- validation de structure (le brief du MJ) ----------------------------

    def valider_structure(self) -> list[str]:
        """Retourne la liste des manquements à la structure attendue (vide = OK).

        Le moteur valide la **structure** (le squelette du brief), jamais la
        qualité créative — c'est le rôle du prompt, pas du moteur.
        """
        problemes: list[str] = []
        if not self.titre:
            problemes.append("Le scénario n'a pas de titre.")
        if self.phase not in PHASES:
            problemes.append(f"Phase inconnue : {self.phase!r} (attendu : {PHASES}).")
        if self.danger not in DANGERS:
            problemes.append(f"Danger inconnu : {self.danger!r} (attendu : {DANGERS}).")
        # >=2 crochets liés aux PJ (moteur de l'implication).
        lies = [c for c in self.crochets if c.lie_a_pj]
        if len(lies) < 2:
            problemes.append("Il faut au moins 2 crochets liés au background d'un PJ.")
        # Chaque défi doit offrir >=2 approches (jamais une seule solution).
        for d in self.defis:
            if len(d.approches) < 2:
                problemes.append(f"Défi « {d.nom} » : au moins 2 approches requises.")
        # Chaque PNJ doit être « complet » (objectif + faille + attitude).
        for p in self.pnj:
            if not p.complet():
                problemes.append(
                    f"PNJ « {p.nom} » incomplet : objectif, faille et attitude requis."
                )
        # Cohérence zone / rencontre : le combat n'est licite que dans une zone
        # dangereuse, qui doit donc porter une rencontre planifiée (et l'inverse :
        # une zone sûre ne doit pas en porter).
        for l in self.lieux:
            if l.est_dangereuse and not l.rencontre:
                problemes.append(
                    f"Lieu « {l.nom} » est une zone dangereuse mais n'a aucune "
                    "`rencontre` planifiée : le combat y serait refusé. Soit y "
                    "déclarer une rencontre, soit le passer en zone « sure »."
                )
            if not l.est_dangereuse and l.rencontre:
                problemes.append(
                    f"Lieu « {l.nom} » est une zone sûre mais porte une `rencontre` : "
                    "le combat y serait refusé par le moteur. Passe-le en zone "
                    "« dangereuse » (et la rencontre devient exploitable)."
                )
        return problemes

    # -- transitions déclarées ----------------------------------------------

    def avancer_phase(self) -> dict[str, Any]:
        """Passe à la phase suivante du rythme (accroche -> montee -> climax -> conclusion)."""
        if self.phase not in PHASES:
            return {"ok": False, "type": "erreur", "erreur": f"Phase inconnue : {self.phase}"}
        i = PHASES.index(self.phase)
        if i >= len(PHASES) - 1:
            return {
                "ok": False,
                "type": "erreur",
                "erreur": "La campagne est déjà à sa phase finale (conclusion).",
            }
        self.phase = PHASES[i + 1]
        self._journal(f"Phase -> {self.phase}")
        return {"ok": True, "type": "phase", "phase": self.phase}

    def resoudre_crochet(self, id_: str, statut: str = "resolvee") -> dict[str, Any]:
        if statut not in CROCHETS_STATUTS:
            return {"ok": False, "type": "erreur", "erreur": f"Statut inconnu : {statut}"}
        c = self.crochet_par_id(id_)
        if c is None:
            return {"ok": False, "type": "erreur", "erreur": f"Crochet inconnu : {id_}"}
        c.statut = statut
        self._journal(f"Crochet {id_} -> {statut}")
        return {"ok": True, "type": "crochet", "id": c.id, "statut": c.statut}

    def rencontrer_pnj(self, nom: str) -> dict[str, Any]:
        p = self.pnj_par_nom(nom)
        if p is None:
            return {"ok": False, "type": "erreur", "erreur": f"PNJ inconnu : {nom}"}
        p.rencontre = True
        self._journal(f"PNJ rencontré : {nom}")
        return {"ok": True, "type": "pnj", "nom": p.nom, "rencontre": True}

    def changer_attitude(self, nom: str, attitude: str) -> dict[str, Any]:
        p = self.pnj_par_nom(nom)
        if p is None:
            return {"ok": False, "type": "erreur", "erreur": f"PNJ inconnu : {nom}"}
        p.attitude = attitude
        self._journal(f"Attitude de {nom} -> {attitude}")
        return {"ok": True, "type": "pnj", "nom": p.nom, "attitude": p.attitude}

    def deplacer_bloc(self, id_: str, position: str = "reserve") -> dict[str, Any]:
        """Relocalise un bloc modulaire (Schrödinger) : actif <-> reserve."""
        if position not in ("actif", "reserve"):
            return {"ok": False, "type": "erreur", "erreur": f"Position inconnue : {position}"}
        b = self.bloc_par_id(id_)
        if b is None:
            return {"ok": False, "type": "erreur", "erreur": f"Bloc inconnu : {id_}"}
        b.position = position
        b.deplace = True
        self._journal(f"Bloc {id_} -> {position}")
        return {"ok": True, "type": "bloc", "id": b.id, "position": b.position}

    def ajouter_indice(self, indice: str) -> dict[str, Any]:
        if not indice:
            return {"ok": False, "type": "erreur", "erreur": "Indice vide."}
        self.indices.append(indice)
        self._journal(f"Indice découvert : {indice}")
        return {"ok": True, "type": "indice", "indices": list(self.indices)}

    def accorder_recompense(self, recompense: str) -> dict[str, Any]:
        if not recompense:
            return {"ok": False, "type": "erreur", "erreur": "Récompense vide."}
        self.recompenses.append(recompense)
        self._journal(f"Récompense accordée : {recompense}")
        return {"ok": True, "type": "recompense", "recompenses": list(self.recompenses)}

    def decouvrir_lieu(self, nom: str) -> dict[str, Any]:
        l = self.lieu_par_nom(nom)
        if l is None:
            return {"ok": False, "type": "erreur", "erreur": f"Lieu inconnu : {nom}"}
        l.decouvert = True
        self._journal(f"Lieu découvert : {nom}")
        return {"ok": True, "type": "lieu", "nom": l.nom, "decouvert": True}

    def modifier(self, action: str, **kwargs: Any) -> dict[str, Any]:
        """Point d'entrée unique des mutations déclarées (le PATCH du routeur).

        Un seul chemin, une `action` de l'enum ACTIONS — calqué sur
        `appliquer_au_combat`. Retourne l'enveloppe du moteur (jamème HTTP).
        """
        action = (action or "").strip()
        if action == "avancer_phase":
            return self.avancer_phase()
        if action in ("resoudre_crochet", "ouvrir_crochet", "abandonner_crochet"):
            statut = {"resoudre_crochet": "resolvee",
                      "ouvrir_crochet": "ouverte",
                      "abandonner_crochet": "abandonnee"}[action]
            return self.resoudre_crochet(str(kwargs.get("id", "")), statut)
        if action == "rencontrer_pnj":
            return self.rencontrer_pnj(str(kwargs.get("nom", "")))
        if action == "changer_attitude":
            return self.changer_attitude(str(kwargs.get("nom", "")), str(kwargs.get("attitude", "")))
        if action == "deplacer_bloc":
            return self.deplacer_bloc(str(kwargs.get("id", "")), str(kwargs.get("position", "reserve")))
        if action == "ajouter_indice":
            return self.ajouter_indice(str(kwargs.get("indice", "")))
        if action == "accorder_recompense":
            return self.accorder_recompense(str(kwargs.get("recompense", "")))
        if action == "decouvrir_lieu":
            return self.decouvrir_lieu(str(kwargs.get("nom", "")))
        return {"ok": False, "type": "erreur", "erreur": f"Action inconnue : {action!r}"}

    # -- écriture de la trame (le MJ conçoit, le moteur mémorise + valide) ----

    def ecrire_structure(self, champs: dict[str, Any]) -> dict[str, Any]:
        """Écrit la **trame** du scénario dans la campagne existante.

        Le MJ (LLM) conçoit le scénario en secret ou avec le joueur, puis le
        **déclare** ici : le moteur le mémorise et le valide. Sans cet outil, la
        trame conçue par le LLM reste dans le contexte de conversation et se perd
        au premier reset — la campagne reste une coquille vide de cadrage.

        N'écrase **que les champs fournis et reconnus** (titre, synopsis, accroche,
        enjeux, motivations, danger, pnj, defis, crochets, lieux, blocs) :
        le cadrage (`mode`, `age_joueur`, `duree`, `piliers`, `ton`, `theme`, …)
        et l'état de partie (`phase`, `indices`, `recompenses`, `chronologie`,
        statuts des crochets/PNJ/lieux déjà joués) sont **préservés**. Retourne
        l'état + les avertissements de structure (signalés, jamais bloquants).
        """
        for cle in ("titre", "synopsis", "accroche", "enjeux", "motivations"):
            if cle in champs:
                setattr(self, cle, str(champs[cle]))
        if str(champs.get("danger", "")) in DANGERS:
            self.danger = str(champs["danger"])
        if isinstance(champs.get("pnj"), list):
            self.pnj = [PNJ.depuis_dict(p) for p in champs["pnj"] if isinstance(p, dict)]
        if isinstance(champs.get("defis"), list):
            self.defis = [Defi.depuis_dict(d) for d in champs["defis"] if isinstance(d, dict)]
        if isinstance(champs.get("crochets"), list):
            self.crochets = [
                Crochet.depuis_dict(c) for c in champs["crochets"] if isinstance(c, dict)
            ]
        if isinstance(champs.get("lieux"), list):
            self.lieux = [Lieu.depuis_dict(l) for l in champs["lieux"] if isinstance(l, dict)]
        if isinstance(champs.get("blocs"), list):
            self.blocs = [Bloc.depuis_dict(b) for b in champs["blocs"] if isinstance(b, dict)]
        self._journal("Trame du scénario écrite / mise à jour.")
        return self.etat()

    def cloturer(self) -> dict[str, Any]:
        self.active = False
        self._journal("Campagne clôturée.")
        return {"ok": True, "type": "cloture", "id": self.id}

    def rejouer(self) -> dict[str, Any]:
        """Remet la **partie** à zéro sans toucher à la **trame** ni au PJ.

        Le scénario (titre, synopsis, accroche, enjeux, PNJ, défis, crochets,
        lieux, blocs) et le cadrage sont **conservés** : on peut rejouer la même
        aventure avec le même personnage. Seule l'état de jeu est réinitialisé :
        phase → `accroche`, campagne réactivée, indices/récompenses/chronologie
        vidés, crochets rouverts, lieux/PNJ non rencontrés, blocs repositionnés.
        """
        self.phase = "accroche"
        self.active = True
        self.indices = []
        self.recompenses = []
        self.chronologie = []
        for c in self.crochets:
            c.statut = "ouverte"
        for l in self.lieux:
            l.decouvert = False
        for p in self.pnj:
            p.rencontre = False
        for b in self.blocs:
            b.position = "actif"
            b.deplace = False
        self._journal("Campagne réinitialisée (rejouée depuis l'accroche).")
        return {"ok": True, "type": "rejouee", "id": self.id, "phase": self.phase}

    def _journal(self, entree: str) -> None:
        self.chronologie.append(entree)

    # -- sérialisation -------------------------------------------------------

    def vers_dict(self) -> dict[str, Any]:
        return {
            "v": 1,
            "id": self.id,
            "titre": self.titre,
            "synopsis": self.synopsis,
            "pj": list(self.pj),
            "phase": self.phase,
            "danger": self.danger,
            "active": self.active,
            "accroche": self.accroche,
            "enjeux": self.enjeux,
            "motivations": self.motivations,
            "lieux": [l.vers_dict() for l in self.lieux],
            "pnj": [p.vers_dict() for p in self.pnj],
            "defis": [d.vers_dict() for d in self.defis],
            "crochets": [c.vers_dict() for c in self.crochets],
            "blocs": [b.vers_dict() for b in self.blocs],
            "indices": list(self.indices),
            "recompenses": list(self.recompenses),
            "chronologie": list(self.chronologie),
            "mode": self.mode,
            "age_joueur": self.age_joueur,
            "duree": self.duree,
            "nb_joueurs": self.nb_joueurs,
            "niveaux": list(self.niveaux),
            "piliers": list(self.piliers),
            "ton": self.ton,
            "theme": self.theme,
        }

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Campagne":
        return cls(
            id=str(d.get("id", "")),
            titre=str(d.get("titre", "")),
            synopsis=str(d.get("synopsis", "")),
            pj=[str(p) for p in d.get("pj", [])],
            phase=str(d.get("phase", "accroche")),
            danger=str(d.get("danger", "normale")),
            active=bool(d.get("active", True)),
            accroche=str(d.get("accroche", "")),
            enjeux=str(d.get("enjeux", "")),
            motivations=str(d.get("motivations", "")),
            lieux=[Lieu.depuis_dict(x) for x in d.get("lieux", [])],
            pnj=[PNJ.depuis_dict(x) for x in d.get("pnj", [])],
            defis=[Defi.depuis_dict(x) for x in d.get("defis", [])],
            crochets=[Crochet.depuis_dict(x) for x in d.get("crochets", [])],
            blocs=[Bloc.depuis_dict(x) for x in d.get("blocs", [])],
            indices=[str(x) for x in d.get("indices", [])],
            recompenses=[str(x) for x in d.get("recompenses", [])],
            chronologie=[str(x) for x in d.get("chronologie", [])],
            mode=str(d.get("mode", "guide")),
            age_joueur=_entier(d.get("age_joueur", 0)),
            duree=str(d.get("duree", "")),
            nb_joueurs=_entier(d.get("nb_joueurs", 0)),
            niveaux=[_entier(n) for n in d.get("niveaux", [])],
            piliers=[str(x) for x in d.get("piliers", [])],
            ton=str(d.get("ton", "")),
            theme=str(d.get("theme", "")),
        )

    # -- rendu ---------------------------------------------------------------

    def etat(self) -> dict[str, Any]:
        """Vue d'ensemble sérialisable (pour l'API / l'outil / la relecture)."""
        return {
            "ok": True,
            "type": "campagne",
            "id": self.id,
            "titre": self.titre,
            "synopsis": self.synopsis,
            "pj": list(self.pj),
            "phase": self.phase,
            "danger": self.danger,
            "active": self.active,
            "structure_valide": not self.valider_structure(),
            "avertissements_structure": self.valider_structure(),
            "accroche": self.accroche,
            "enjeux": self.enjeux,
            "motivations": self.motivations,
            "lieux": [l.vers_dict() for l in self.lieux],
            "pnj": [p.vers_dict() for p in self.pnj],
            "defis": [d.vers_dict() for d in self.defis],
            "crochets": [c.vers_dict() for c in self.crochets],
            "blocs": [b.vers_dict() for b in self.blocs],
            "indices": list(self.indices),
            "recompenses": list(self.recompenses),
            "chronologie": list(self.chronologie),
            "mode": self.mode,
            "age_joueur": self.age_joueur,
            "duree": self.duree,
            "nb_joueurs": self.nb_joueurs,
            "niveaux": list(self.niveaux),
            "piliers": list(self.piliers),
            "ton": self.ton,
            "theme": self.theme,
            "conseil_cadrage": conseil_cadrage(self.age_joueur, self.duree),
        }


# ---------------------------------------------------------------------------
# Advisory d'équilibrage (budget d'XP SRD 5.2.1) — le moteur INFORME, le scénario DÉCIDE
# ---------------------------------------------------------------------------

# Seuils d'XP par personnage selon son niveau (SRD 5.2.1, « Construire une
# rencontre ») : (facile, moyenne, difficile, mortelle).
_SEUILS_XP: dict[int, tuple[int, int, int, int]] = {
    1: (50, 100, 150, 200),
    2: (100, 200, 300, 400),
    3: (150, 300, 450, 600),
    4: (250, 500, 750, 1100),
    5: (500, 1100, 1600, 2000),
    6: (900, 1400, 2300, 3400),
    7: (1400, 2300, 3400, 4800),
    8: (2300, 3400, 4800, 7200),
    9: (2900, 4400, 5900, 8800),
    10: (3900, 5900, 8800, 11700),
    11: (5000, 7400, 11700, 15700),
    12: (5900, 9400, 14100, 18500),
    13: (7400, 11700, 17600, 23200),
    14: (9400, 14100, 21100, 28100),
    15: (11700, 17600, 26300, 35100),
    16: (14100, 21100, 31600, 42200),
    17: (17600, 26300, 39400, 52600),
    18: (21100, 31600, 47300, 63400),
    19: (26300, 39400, 59100, 79000),
    20: (31600, 47300, 71000, 94000),
}

# XP par facteur de puissance (CR) — SRD 5.2.1. Les CR fractionnaires sont
# acceptés en chaîne ("1/8", "1/4", "1/2") comme en nombre.
_XP_PAR_CR: dict[str, int] = {
    "0": 0, "1/8": 50, "0.125": 50, "1/4": 100, "0.25": 100,
    "1/2": 200, "0.5": 200, "1": 400, "2": 450, "3": 700, "4": 1100,
    "5": 1800, "6": 2300, "7": 2900, "8": 3900, "9": 5000, "10": 5900,
    "11": 7200, "12": 8400, "13": 10000, "14": 11500, "15": 13000,
    "16": 15000, "17": 18000, "18": 20000, "19": 22000, "20": 25000,
    "21": 33000, "22": 41500, "23": 50000, "24": 62000, "25": 75000,
    "26": 90000, "27": 105000, "28": 120000, "29": 135000, "30": 155000,
}


def _xp_d_un_cr(cr: Any) -> int | None:
    """Convertit un CR (chaîne ou nombre, fractionnaire accepté) en XP. None si inconnu."""
    if cr is None or str(cr).strip() == "":
        return None
    cle = str(cr).strip().lower()
    if cle in _XP_PAR_CR:
        return _XP_PAR_CR[cle]
    # Normalise les floats ("1.0" -> "1").
    try:
        f = float(cle)
        if f.is_integer():
            return _XP_PAR_CR.get(str(int(f)))
    except ValueError:
        return None
    return None


def advisory_difficulte(
    niveaux_pj: list[int], rencontre: Rencontre | list[MonstreScenarise]
) -> dict[str, Any]:
    """Estime la dangerosité d'une rencontre pour le groupe (budget d'XP SRD 5.2.1).

    **Le moteur informe, il ne décide pas** : il ne modifie jamais les stats ni les
    effectifs. Il compare l'XP cumulée des monstres (CR * effectif) aux seuils du
    groupe, et renvoie un degré + un conseil. Le scénario garde la main (ajouter /
    retirer des copies via `nb`, choisir d'autres créatures).

    `niveaux_pj` : niveau de chaque PJ du groupe (solo = liste de 1).
    `rencontre` : une `Rencontre` ou une liste de `MonstreScenarise`.
    """
    monstres = rencontre.monstres if isinstance(rencontre, Rencontre) else list(rencontre)
    niveaux = [max(1, int(n)) for n in niveaux_pj if isinstance(n, (int, float)) or str(n).isdigit()]
    if not niveaux:
        return {"ok": False, "type": "erreur", "erreur": "Aucun niveau de PJ fourni pour l'advisory."}

    # XP cumulée des monstres (CR inconnu -> ignoré, signalé).
    xp_monstres = 0
    cr_inconnus: list[str] = []
    for m in monstres:
        xp = _xp_d_un_cr(m.cr)
        if xp is None:
            cr_inconnus.append(m.nom)
            continue
        xp_monstres += xp * max(1, m.nb)

    # Budget du groupe : somme des seuils par personnage.
    def seuil(index: int) -> int:
        total = 0
        for n in niveaux:
            bornes = _SEUILS_XP.get(min(n, 20), _SEUILS_XP[20])
            total += bornes[index]
        return total

    facile, moyenne, difficile, mortelle = seuil(0), seuil(1), seuil(2), seuil(3)

    if xp_monstres >= mortelle:
        degre = "mortelle"
    elif xp_monstres >= difficile:
        degre = "difficile"
    elif xp_monstres >= moyenne:
        degre = "moyenne"
    elif xp_monstres >= facile:
        degre = "facile"
    else:
        degre = "tres_facile"

    conseil = {
        "tres_facile": "Rencontre triviale pour ce groupe : envisager plus d'effectif ou une créature plus forte.",
        "facile": "Rencontre facile : le groupe devrait s'en sortir sans ressource notable.",
        "moyenne": "Rencontre équilibrée : tension raisonnable pour ce niveau.",
        "difficile": "Rencontre difficile : prévoir une issue de secours ou un avantage tactique.",
        "mortelle": "Rencontre potentiellement mortelle pour ce niveau : le MJ peut réduire l'effectif (nb) ou choisir des créatures de CR moindre.",
    }[degre]

    return {
        "ok": True,
        "type": "advisory",
        "groupe": {"effectif": len(niveaux), "niveaux": niveaux},
        "xp_monstres": xp_monstres,
        "seuils": {"facile": facile, "moyenne": moyenne, "difficile": difficile, "mortelle": mortelle},
        "degre": degre,
        "conseil": conseil,
        "cr_inconnus": cr_inconnus,
    }


# ---------------------------------------------------------------------------
# Parseur Markdown -> front-matter (stdlib uniquement, sans pyyaml)
# ---------------------------------------------------------------------------
#
# Un scénario importé est un fichier Markdown à front-matter, dans le même
# esprit que les fiches RAG : un bloc d'en-tête YAML délimité par `---` porte la
# STRUCTURE (id, titre, pj, pnj, crochets, …), le corps `## …` porte la prose
# lisible par le MJ. Le moteur ne parse que l'en-tête (la structure canonique) ;
# le corps est conservé tel quel dans `synopsis`/champs de texte si besoin.
#
# Sous-ensemble YAML supporté (volontairement borné, sans dépendance) :
#   cle: valeur            (scalaire : str / int / bool)
#   cle: [a, b, c]         (liste en ligne)
#   cle:                   (liste ou mapping en bloc, lignes suivantes indentées)
#     - champ: valeur      (liste de mappings)
#     - valeur             (liste de scalaires)

_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)


def _valeur_scalaire(texte: str) -> Any:
    """Convertit une valeur scalaire YAML simple (str/int/bool) sans pyyaml."""
    t = texte.strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        return t[1:-1]
    bas = t.lower()
    if bas in ("true", "oui", "yes", "vrai"):
        return True
    if bas in ("false", "non", "no", "faux"):
        return False
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    return t


def _liste_en_ligne(texte: str) -> list[Any]:
    """Parse `[a, b, c]` (scalaires uniquement)."""
    interieur = texte.strip()[1:-1].strip()
    if not interieur:
        return []
    return [_valeur_scalaire(x) for x in interieur.split(",")]


def _indent(ligne: str) -> int:
    return len(ligne) - len(ligne.lstrip(" "))


def _parser_bloc(lignes: list[str], i: int, indent: int) -> tuple[Any, int]:
    """Parse un bloc YAML (mapping ou liste) à partir de la ligne `i` (>=indent)."""
    # Liste ?
    contenu = lignes[i].strip()
    if contenu.startswith("- "):
        return _parser_liste(lignes, i, indent)
    return _parser_mapping(lignes, i, indent)


def _parser_mapping(lignes: list[str], i: int, indent: int) -> tuple[dict[str, Any], int]:
    resultat: dict[str, Any] = {}
    while i < len(lignes):
        ligne = lignes[i]
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            i += 1
            continue
        ind = _indent(ligne)
        if ind < indent:
            break
        if ind > indent:  # héritage inattendu : on s'arrête proprement
            break
        texte = ligne.strip()
        if ":" not in texte:
            i += 1
            continue
        cle, _, reste = texte.partition(":")
        cle = cle.strip()
        reste = reste.strip()
        if reste:
            if reste.startswith("["):
                resultat[cle] = _liste_en_ligne(reste)
            else:
                resultat[cle] = _valeur_scalaire(reste)
            i += 1
        else:
            # Valeur en bloc : regarder l'indentation de la ligne suivante.
            j = i + 1
            while j < len(lignes) and not lignes[j].strip():
                j += 1
            if j < len(lignes) and _indent(lignes[j]) > indent:
                sous, i = _parser_bloc(lignes, j, _indent(lignes[j]))
                resultat[cle] = sous
            else:
                resultat[cle] = ""
                i += 1
    return resultat, i


def _parser_liste(lignes: list[str], i: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while i < len(lignes):
        ligne = lignes[i]
        if not ligne.strip():
            i += 1
            continue
        ind = _indent(ligne)
        if ind < indent or not ligne.strip().startswith("- "):
            break
        apres = ligne.strip()[2:]  # retire "- "
        if ":" in apres:
            # Item = mapping : le premier champ est sur la ligne "- cle: val",
            # les suivants sont indentés de 2 de plus que le tiret.
            item_indent = ind + 2
            # On réécrit la ligne courante sans le "- " pour la parser comme mapping.
            lignes[i] = " " * item_indent + apres
            mapping, i = _parser_mapping(lignes, i, item_indent)
            items.append(mapping)
        else:
            items.append(_valeur_scalaire(apres))
            i += 1
    return items, i


def parser_front_matter(texte: str) -> tuple[dict[str, Any], str]:
    """Sépare le front-matter YAML du corps Markdown. Retourne (en_tete, corps)."""
    m = _FRONT_RE.match(texte.lstrip("\ufeff\n"))
    if not m:
        return {}, texte
    en_tete_texte = m.group(1)
    corps = texte[m.end():]
    lignes = en_tete_texte.splitlines()
    en_tete, _ = _parser_bloc(lignes, 0, 0)
    if not isinstance(en_tete, dict):
        en_tete = {}
    return en_tete, corps


def campagne_depuis_markdown(texte: str, id_fallback: str = "") -> Campagne:
    """Construit une `Campagne` depuis le texte Markdown d'un scénario importé.

    L'en-tête YAML porte la structure ; le corps est ignoré pour l'état canonique
    (il reste lisible par le MJ dans le fichier source). Aucune validation de
    structure ici : appeler `campagne.valider_structure()` après.
    """
    en_tete, _corps = parser_front_matter(texte)
    en_tete.setdefault("id", id_fallback)
    return Campagne.depuis_dict(en_tete)
