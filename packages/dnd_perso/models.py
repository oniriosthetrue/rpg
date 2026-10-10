"""Modèles de données du personnage (dataclasses, stdlib uniquement)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Ordre canonique des six caractéristiques (SRD 5.2.1).
CARACTERISTIQUES = [
    "Force", "Dextérité", "Constitution", "Intelligence", "Sagesse", "Charisme",
]

# Compétences (liste SRD 5.2.1, ordre alphabétique).
LISTE_COMPETENCES = [
    "Acrobaties", "Arcanes", "Athlétisme", "Discrétion", "Dressage",
    "Escamotage", "Équitation", "Histoire", "Intimidation",
    "Intuition", "Investigation", "Médecine", "Nature", "Perception",
    "Persuasion", "Religion", "Survie", "Tromperie",
]

# Table des compétences : compétence -> caractéristique associée.
# (SRD 5.2.1, section « Utiliser les caractéristiques ».)
COMPETENCES: dict[str, str] = {
    "Acrobaties": "Dextérité",
    "Arcanes": "Intelligence",
    "Athlétisme": "Force",
    "Discrétion": "Dextérité",
    "Dressage": "Charisme",
    "Escamotage": "Dextérité",
    "Équitation": "Dextérité",
    "Histoire": "Intelligence",
    "Intimidation": "Charisme",
    "Intuition": "Sagesse",
    "Investigation": "Intelligence",
    "Médecine": "Sagesse",
    "Nature": "Intelligence",
    "Perception": "Sagesse",
    "Persuasion": "Charisme",
    "Religion": "Intelligence",
    "Survie": "Sagesse",
    "Tromperie": "Charisme",
}


# Table des armures : nom -> (CA de base, bonus de Dex applicable).
# (SRD 5.2.1, chapitre « Équipement » : les armures lourdes n'autorisent
# aucun bonus de Dextérité.)
ARMURES: dict[str, tuple[int, bool]] = {
    "armure de cuir": (11, True),
    "armure de cuir clouté": (12, True),
    "chemise de mailles": (13, True),
    "cotte de mailles": (16, False),
}

# Bonus d'un bouclier (SRD 5.2.1).
BONUS_BOUCLIER = 2


@dataclass
class Caracteristiques:
    """Les six caractéristiques, avec les modificateurs dérivés."""

    force: int = 8
    dexterite: int = 8
    constitution: int = 8
    intelligence: int = 8
    sagesse: int = 8
    charisme: int = 8

    def valeurs(self) -> list[int]:
        return [
            self.force, self.dexterite, self.constitution,
            self.intelligence, self.sagesse, self.charisme,
        ]

    @staticmethod
    def mod(valeur: int) -> int:
        """Modificateur de caractéristique : (valeur - 10) // 2."""
        return (valeur - 10) // 2

    def mod_for(self) -> int:
        return self.mod(self.force)

    def mod_dex(self) -> int:
        return self.mod(self.dexterite)

    def mod_con(self) -> int:
        return self.mod(self.constitution)

    def mod_int(self) -> int:
        return self.mod(self.intelligence)

    def mod_sag(self) -> int:
        return self.mod(self.sagesse)

    def mod_char(self) -> int:
        return self.mod(self.charisme)

    def mods(self) -> dict[str, int]:
        return {
            "Force": self.mod_for(),
            "Dextérité": self.mod_dex(),
            "Constitution": self.mod_con(),
            "Intelligence": self.mod_int(),
            "Sagesse": self.mod_sag(),
            "Charisme": self.mod_char(),
        }

    def vers_dict(self) -> dict[str, int]:
        return {
            "Force": self.force,
            "Dextérité": self.dexterite,
            "Constitution": self.constitution,
            "Intelligence": self.intelligence,
            "Sagesse": self.sagesse,
            "Charisme": self.charisme,
        }

    @classmethod
    def depuis_liste(cls, valeurs: list[int]) -> "Caracteristiques":
        if len(valeurs) != 6:
            raise ValueError("Il faut exactement six valeurs de caractéristique.")
        return cls(*valeurs)


@dataclass
class Competence:
    """Une compétence maîtrisée (optionnelle à la création)."""

    nom: str
    maitrisee: bool = True

    def vers_dict(self) -> dict[str, Any]:
        return {"nom": self.nom, "maitrisee": self.maitrisee}


@dataclass
class Equipement:
    """L'équipement de départ (liste d'objets, dont l'or de départ)."""

    objets: list[str] = field(default_factory=list)

    def vers_dict(self) -> list[str]:
        return list(self.objets)


@dataclass
class Personnage:
    """Un personnage de niveau 1, complet (SRD 5.2.1)."""

    nom: str = ""
    espece: str = ""
    classe: str = ""
    historique: str = ""
    alignement: str = "Neutre"
    niveau: int = 1
    carac: Caracteristiques = field(default_factory=Caracteristiques)
    competences: list[Competence] = field(default_factory=list)
    langues: list[str] = field(default_factory=lambda: ["Commun"])
    equipement: Equipement = field(default_factory=Equipement)
    sorts: list[str] = field(default_factory=list)
    babiole: str = ""
    # Don d'origines accordé par l'historique (ex. « Initié à la magie (Magicien) »).
    don: str = ""
    # Maîtrise d'outil accordée par l'historique (ex. « matériel de calligraphe »).
    outils: str = ""
    xp: int = 0
    pv_actuels: int = -1
    # Dérivés (calculés, pas saisis) :
    bonus_maitrise: int = 2

    @property
    def pv(self) -> int:
        """Points de vie courants : valeur courante si connue, sinon le maximum
        (dé de vie + modificateur de Constitution)."""
        max_pv = self.de_vie + self.carac.mod_con()
        if self.pv_actuels < 0 or self.pv_actuels > max_pv:
            return max_pv
        return self.pv_actuels

    @property
    def initiative(self) -> int:
        """Initiative : modificateur de Dextérité."""
        return self.carac.mod_dex()

    @property
    def de_vie(self) -> int:
        """Dé de vie de la classe (chargé depuis CLASSES)."""
        return _DE_VIE.get(self.classe, 8)

    @property
    def ca(self) -> int:
        """Classe d'armure : armure portée + mod Dex, +2 si bouclier,
        sinon 10 + mod Dex (sans armure)."""
        ca = 10 + self.carac.mod_dex()
        for objet in self.equipement.objets:
            nom = objet.strip().lower()
            if nom in ARMURES:
                base, dex_ok = ARMURES[nom]
                ca = base + (self.carac.mod_dex() if dex_ok else 0)
                break
        if any(o.strip().lower() == "bouclier" for o in self.equipement.objets):
            ca += BONUS_BOUCLIER
        return ca

    def table_des_jets(self) -> dict[str, Any]:
        """Table **pré-calculée** des bonus de jet (le MJ la lit, ne calcule jamais).

        Pour chaque compétence : `total = modificateur de caractéristique`
        (+ `bonus_maitrise` si le personnage la maîtrise). Pour chaque jet de
        sauvegarde : `total = modificateur` (+ `bonus_maitrise` si la classe le
        confère — `extract.CLASSES[classe]["sauvegardes"]`). Le MJ annonce ainsi
        « d20 + N » tout fait et ne demande au joueur que le dé naturel.

        Import différé d'`extract` : `models` reste importable sans `extract`
        (aucune circularité, `extract` n'important jamais `models`).
        """
        from . import extract  # import différé (circulaire évitée)

        maitrisees = {c.nom for c in self.competences if c.maitrisee}
        mods = self.carac.mods()
        competences: dict[str, int] = {}
        for nom in LISTE_COMPETENCES:
            carac = COMPETENCES[nom]
            competences[nom] = mods[carac] + (
                self.bonus_maitrise if nom in maitrisees else 0
            )
        sauvegardes_pro = extract.CLASSES.get(self.classe, {}).get("sauvegardes", [])
        sauvegardes: dict[str, int] = {}
        for carac in CARACTERISTIQUES:
            sauvegardes[carac] = mods[carac] + (
                self.bonus_maitrise if carac in sauvegardes_pro else 0
            )
        return {
            "bonus_maitrise": self.bonus_maitrise,
            "competences": competences,
            "sauvegardes": sauvegardes,
        }

    def vers_dict(self) -> dict[str, Any]:
        equip = list(self.equipement.objets)
        if self.babiole:
            equip.append(self.babiole)
        d: dict[str, Any] = {
            "nom": self.nom,
            "espece": self.espece,
            "classe": self.classe,
            "historique": self.historique,
            "alignement": self.alignement,
            "niveau": self.niveau,
            "xp": self.xp,
            "carac": self.carac.vers_dict(),
            "mods": self.carac.mods(),
            "competences": [c.vers_dict() for c in self.competences],
            "langues": list(self.langues),
            "equipement": equip,
            "sorts": list(self.sorts),
            "bonus_maitrise": self.bonus_maitrise,
            "pv": self.pv,
            "initiative": self.initiative,
            "ca": self.ca,
            "jets": self.table_des_jets(),
        }
        if self.don:
            d["don"] = self.don
        if self.outils:
            d["outils"] = self.outils
        if self.pv_actuels >= 0:
            d["pv_actuels"] = self.pv_actuels
        return d

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> "Personnage":
        """Reconstruit un Personnage depuis le dict de `vers_dict()`.

        Accepte une fiche legacy contenant un champ `babiole` séparé : la babiole
        est alors fusionnée à la fin de `equipement` (contrat §8).
        """
        carac_d = d.get("carac", {}) or {}
        carac = Caracteristiques(
            force=int(carac_d.get("Force", 8)),
            dexterite=int(carac_d.get("Dextérité", 8)),
            constitution=int(carac_d.get("Constitution", 8)),
            intelligence=int(carac_d.get("Intelligence", 8)),
            sagesse=int(carac_d.get("Sagesse", 8)),
            charisme=int(carac_d.get("Charisme", 8)),
        )
        competences = [
            Competence(str(c.get("nom", "")), bool(c.get("maitrisee", True)))
            for c in d.get("competences", [])
            if isinstance(c, dict) and c.get("nom")
        ]
        equip = [str(o) for o in d.get("equipement", [])]
        babiole = str(d.get("babiole", "") or "")
        if babiole:
            equip.append(babiole)
        return cls(
            nom=str(d.get("nom", "sans_nom")),
            espece=str(d.get("espece", "")),
            classe=str(d.get("classe", "")),
            historique=str(d.get("historique", "")),
            alignement=str(d.get("alignement", "Neutre")),
            niveau=int(d.get("niveau", 1)),
            carac=carac,
            competences=competences,
            langues=list(d.get("langues", ["Commun"])),
            equipement=Equipement(objets=equip),
            sorts=[str(s) for s in d.get("sorts", [])],
            babiole="",
            don=str(d.get("don", "") or ""),
            outils=str(d.get("outils", "") or ""),
            xp=int(d.get("xp", 0)),
            pv_actuels=int(d.get("pv_actuels", -1)),
            bonus_maitrise=int(d.get("bonus_maitrise", 2)),
        )


# Table des dés de vie par classe (constante, dérivée de CLASSES).
_DE_VIE: dict[str, int] = {
    "Barbare": 12, "Barde": 8, "Clerc": 8, "Druide": 8, "Ensorceleur": 6,
    "Guerrier": 10, "Magicien": 6, "Moine": 8, "Occultiste": 8, "Paladin": 10,
    "Rôdeur": 10, "Roublard": 8,
}
