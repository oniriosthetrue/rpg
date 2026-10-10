"""Lecture et extraction des données du corpus SRD 5.2.1 (lecture seule).

Stratégie :
- Les données « propres » (tables markdown) sont parsées à la volée depuis
  `dnd/srd-5.2.1/` et `dnd/classes/`, puis mises en cache dans `dnd_perso/data/`.
- Les données « dégradées » (prose collée, tableaux PDF sur 2 colonnes) sont
  fournies en constantes vérifiées ci-dessous (fallback), jamais réécrites
  dans le corpus.

Le corpus (`dnd/srd-5.2.1/`, `dnd/classes/`) n'est JAMAIS modifié.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------

# Racine des paquets = dossier contenant `dnd_perso/` et `corpus/`.
RACINE = Path(__file__).resolve().parent.parent
# Corpus SRD : override par env DND_CORPUS_DIR (conteneur), sinon packages/corpus.
CORPUS = Path(os.environ.get("DND_CORPUS_DIR") or (RACINE / "corpus" / "srd-5.2.1"))
CLASSES_DIR = CORPUS / "classes"
DATA_DIR = Path(__file__).resolve().parent / "data"
# Dossier des fiches personnage : configurable via l'env DND_PERSO_DIR
# (le conteneur jdr-api le monte en rw sur /app/data/perso) ; défaut conservé.
PERSO_DIR = Path(os.environ.get("DND_PERSO_DIR") or (Path(__file__).resolve().parent / "perso"))
# Dossier des rencontres de combat (état de combat persistant) : configurable via
# l'env DND_COMBAT_DIR (le conteneur jdr-api le monte en rw sur /app/data/combat).
COMBAT_DIR = Path(os.environ.get("DND_COMBAT_DIR") or (RACINE / "data-combat"))
# Dossier des campagnes / scénarios suivis (état canonique persistant) : configurable
# via l'env DND_CAMPAGNE_DIR (le conteneur jdr-api le monte en rw sur /app/data/campagne).
CAMPAGNE_DIR = Path(os.environ.get("DND_CAMPAGNE_DIR") or (RACINE / "data-campagne"))
# Dossier des scénarios importables (fichiers Markdown à front-matter, lecture seule).
SCENARIO_DIR = RACINE / "dnd" / "scenarios"

_FICHE_RE = re.compile(
    r"<<<FICHE>>>\n(?P<keys>.*?)<<<CONTENU>>>\n(?P<corps>.*?)<<<FIN>>>",
    re.DOTALL,
)


def _parse_fiche(texte: str) -> tuple[dict[str, str], str]:
    """Sépare l'en-tête `<<<FICHE>>>` du corps `<<<CONTENU>>>` d'une fiche."""
    m = _FICHE_RE.search(texte)
    if not m:
        return {}, texte
    keys: dict[str, str] = {}
    for ligne in m.group("keys").splitlines():
        if ":" in ligne:
            k, _, v = ligne.partition(":")
            keys[k.strip()] = v.strip()
    return keys, m.group("corps")


# ---------------------------------------------------------------------------
# Constantes vérifiées (fallback) — données que le markdown rend mal
# ---------------------------------------------------------------------------

# Valeurs standard (achat de points) : 27 points.
ARRAY_STANDARD = [15, 14, 13, 12, 10, 8]
COUT_ACHAT = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
MAX_CARAC = 20

# « Valeurs de caractéristique » : à la création, une caractéristique indiquée
# passe à 16, une autre à 14 (règle d'ajustement d'origine, SRD 5.2.1).
# Valeurs par défaut par classe (colonne « recommandée »), ordre
# [Force, Dextérité, Constitution, Intelligence, Sagesse, Charisme].
VALEURS_PAR_CLASSE: dict[str, list[int]] = {
    "Barbare": [15, 13, 14, 10, 12, 8],
    "Barde": [8, 14, 12, 13, 10, 15],
    "Clerc": [14, 8, 13, 10, 15, 12],
    "Druide": [8, 12, 14, 13, 15, 10],
    "Ensorceleur": [10, 13, 14, 8, 12, 15],
    "Guerrier": [15, 14, 13, 8, 10, 12],
    "Magicien": [8, 12, 13, 15, 14, 10],
    "Moine": [12, 15, 13, 10, 14, 8],
    "Occultiste": [8, 14, 13, 12, 10, 15],
    "Paladin": [15, 10, 13, 8, 12, 14],
    "Rôdeur": [12, 15, 13, 8, 14, 10],
    "Roublard": [12, 15, 13, 14, 10, 8],
}

# « Aperçu des classes » : domaine, caractéristique clé, complexité.
APERCU_CLASSES: dict[str, tuple[str, str, str]] = {
    "Barbare": ("Combat", "Force", "Moyenne"),
    "Barde": ("Représentation", "Charisme", "Élevée"),
    "Clerc": ("Dieux", "Sagesse", "Moyenne"),
    "Druide": ("Nature", "Sagesse", "Élevée"),
    "Ensorceleur": ("Pouvoirs", "Charisme", "Élevée"),
    "Guerrier": ("Armes", "Force ou Dextérité", "Basse"),
    "Magicien": ("Grimoires", "Intelligence", "Moyenne"),
    "Moine": ("Combat à mains nues", "Dextérité et Sagesse", "Élevée"),
    "Occultiste": ("Ésotérisme", "Charisme", "Élevée"),
    "Paladin": ("Défense", "Force et Charisme", "Moyenne"),
    "Rôdeur": ("Survie", "Dextérité et Sagesse", "Moyenne"),
    "Roublard": ("Discrétion", "Dextérité", "Basse"),
}

# Caractéristique d'incantation par classe lanceuse (SRD 5.2.1). Sert à calculer
# le **bonus d'attaque de sort** (bonus de maîtrise + mod de cette carac), que la
# fiche pré-calcule pour que le MJ l'annonce sans jamais le recalculer lui-même.
CARAC_INCANTATION: dict[str, str] = {
    "Barde": "Charisme",
    "Clerc": "Sagesse",
    "Druide": "Sagesse",
    "Ensorceleur": "Charisme",
    "Magicien": "Intelligence",
    "Occultiste": "Charisme",
    "Paladin": "Charisme",
    "Rôdeur": "Sagesse",
}

# Données complètes par classe (constantes vérifiées, markdown dégradé).
# nb_cantrips / nb_prepares : comptage confirmé sur les fiches `dnd/classes`.
#   - « sorts mineurs » (cantrips) : 2 ou 3 selon la classe.
    #   - « sorts préparés » du 1er niveau : 2 ou 4 selon la classe.
# Les classes martiales sans incantation ont nb_sorts_1 = 0.
# NB : le SRD 5.2.1 n'accorde PAS de sorts préparés au niveau 1 aux classes
# « préparistes » sans table dédiée ; on suit le décompte des fiches lues.
CLASSES: dict[str, dict[str, Any]] = {
    "Barbare": {
        "predilection": "Combat", "carac": "Force", "complexite": "Moyenne",
        "de_vie": 12, "sauvegardes": ["Force", "Constitution"],
        "competences": ["Athlétisme", "Dressage", "Intimidation", "Nature", "Perception", "Survie"],
        "nb_competences": 2, "armures": ["armures légères", "armures intermédiaires", "boucliers"],
        "armes": "armes courantes et armes de guerre",
        "equip_A": ["hache à deux mains", "4 hachettes", "paquetage d'explorateur", "15 po"],
        "equip_B": ["75 po"],
        "lanceur": False, "nb_cantrips": 0, "nb_sorts_1": 0,
    },
    "Barde": {
        "predilection": "Représentation", "carac": "Charisme", "complexite": "Élevée",
        "de_vie": 8, "sauvegardes": ["Dextérité", "Charisme"],
        "competences": ["Acrobaties", "Arcanes", "Athlétisme", "Discrétion", "Intuition", "Intimidation", "Investigation", "Nature", "Perception", "Persuasion", "Religion", "Survie", "Tromperie"], "nb_competences": 3,
        "armures": ["armures légères"], "armes": "armes courantes",
        "equip_A": ["armure de cuir", "2 dagues", "un instrument de musique", "paquetage d'artiste", "19 po"],
        "equip_B": ["90 po"],
        "lanceur": True, "nb_cantrips": 2, "nb_sorts_1": 4,
    },
    "Clerc": {
        "predilection": "Dieux", "carac": "Sagesse", "complexite": "Moyenne",
        "de_vie": 8, "sauvegardes": ["Sagesse", "Charisme"],
        "competences": ["Histoire", "Intuition", "Médecine", "Persuasion", "Religion"],
        "nb_competences": 2, "armures": ["armures légères", "armures intermédiaires", "boucliers"],
        "armes": "armes courantes",
        "equip_A": ["chemise de mailles", "bouclier", "masse d'armes", "symbole sacré", "paquetage d'ecclésiastique", "7 po"],
        "equip_B": ["110 po"],
        "lanceur": True, "nb_cantrips": 3, "nb_sorts_1": 4,
    },
    "Druide": {
        "predilection": "Nature", "carac": "Sagesse", "complexite": "Élevée",
        "de_vie": 8, "sauvegardes": ["Intelligence", "Sagesse"],
        "competences": ["Arcanes", "Dressage", "Intuition", "Médecine", "Nature", "Perception", "Religion", "Survie"],
        "nb_competences": 2, "armures": ["armures légères", "boucliers"],
        "armes": "armes courantes",
        "equip_A": ["armure de cuir", "bouclier", "serpe", "focaliseur druidique (bâton de combat)", "paquetage d'explorateur", "matériel d'herboriste", "9 po"],
        "equip_B": ["50 po"],
        "lanceur": True, "nb_cantrips": 2, "nb_sorts_1": 2,
    },
    "Ensorceleur": {
        "predilection": "Pouvoirs", "carac": "Charisme", "complexite": "Élevée",
        "de_vie": 6, "sauvegardes": ["Constitution", "Charisme"],
        "competences": ["Arcanes", "Intimidation", "Intuition", "Persuasion", "Religion", "Tromperie"],
        "nb_competences": 2, "armures": [], "armes": "armes courantes",
        "equip_A": ["lance", "2 dagues", "focaliseur arcanique (cristal)", "paquetage d'exploration souterraine", "28 po"],
        "equip_B": ["50 po"],
        "lanceur": True, "nb_cantrips": 4, "nb_sorts_1": 3,
    },
    "Guerrier": {
        "predilection": "Armes", "carac": "Force ou Dextérité", "complexite": "Basse",
        "de_vie": 10, "sauvegardes": ["Force", "Constitution"],
        "competences": ["Acrobaties", "Athlétisme", "Dressage", "Histoire", "Intuition", "Intimidation", "Perception", "Persuasion", "Survie"],
        "nb_competences": 2, "armures": ["toutes les armures", "boucliers"],
        "armes": "armes courantes et armes de guerre",
        "equip_A": ["cotte de mailles", "épée à deux mains", "fléau d'armes", "8 javelines", "paquetage d'exploration souterraine", "4 po"],
        "equip_B": ["armure de cuir clouté", "cimeterre", "épée courte", "arc long", "20 flèches", "carquois", "paquetage d'exploration souterraine", "11 po"],
        "equip_C": ["155 po"],
        "lanceur": False, "nb_cantrips": 0, "nb_sorts_1": 0,
    },
    "Magicien": {
        "predilection": "Grimoires", "carac": "Intelligence", "complexite": "Moyenne",
        "de_vie": 6, "sauvegardes": ["Intelligence", "Sagesse"],
        "competences": ["Arcanes", "Histoire", "Intuition", "Investigation", "Médecine", "Nature", "Religion"],
        "nb_competences": 2, "armures": [], "armes": "armes courantes",
        "equip_A": ["2 dagues", "focaliseur arcanique (bâton de combat)", "robe", "grimoire", "paquetage d'érudit", "5 po"],
        "equip_B": ["55 po"],
        "lanceur": True, "nb_cantrips": 3, "nb_sorts_1": 4,
    },
    "Moine": {
        "predilection": "Combat à mains nues", "carac": "Dextérité et Sagesse", "complexite": "Élevée",
        "de_vie": 8, "sauvegardes": ["Force", "Dextérité"],
        "competences": ["Acrobaties", "Athlétisme", "Discrétion", "Histoire", "Intuition", "Religion"],
        "nb_competences": 2, "armures": [], "armes": "armes courantes et armes de guerre «Légère»",
        "equip_A": ["lance", "5 dagues", "un outil d'artisan ou un instrument de musique", "paquetage d'explorateur", "11 po"],
        "equip_B": ["50 po"],
        "lanceur": False, "nb_cantrips": 0, "nb_sorts_1": 2,
    },
    "Occultiste": {
        "predilection": "Ésotérisme", "carac": "Charisme", "complexite": "Élevée",
        "de_vie": 8, "sauvegardes": ["Sagesse", "Charisme"],
        "competences": ["Arcanes", "Histoire", "Intimidation", "Investigation", "Nature", "Religion", "Tromperie"],
        "nb_competences": 2, "armures": ["armures légères"], "armes": "armes courantes",
        "equip_A": ["armure de cuir", "serpe", "2 dagues", "focaliseur arcanique (orbe)", "livre (savoir occulte)", "paquetage d'érudit", "15 po"],
        "equip_B": ["100 po"],
        "lanceur": True, "nb_cantrips": 2, "nb_sorts_1": 2,
    },
    "Paladin": {
        "predilection": "Défense", "carac": "Force et Charisme", "complexite": "Moyenne",
        "de_vie": 10, "sauvegardes": ["Sagesse", "Charisme"],
        "competences": ["Athlétisme", "Intimidation", "Intuition", "Médecine", "Persuasion", "Religion"],
        "nb_competences": 2, "armures": ["armures légères", "armures intermédiaires", "armures lourdes", "boucliers"],
        "armes": "armes courantes et armes de guerre",
        "equip_A": ["cotte de mailles", "bouclier", "épée longue", "6 javelines", "symbole sacré", "paquetage d'ecclésiastique", "9 po"],
        "equip_B": ["150 po"],
        "lanceur": False, "nb_cantrips": 0, "nb_sorts_1": 0,
    },
    "Rôdeur": {
        "predilection": "Survie", "carac": "Dextérité et Sagesse", "complexite": "Moyenne",
        "de_vie": 10, "sauvegardes": ["Force", "Dextérité"],
        "competences": ["Athlétisme", "Discrétion", "Dressage", "Intuition", "Investigation", "Nature", "Perception", "Survie"],
        "nb_competences": 3, "armures": ["armures légères", "armures intermédiaires", "boucliers"],
        "armes": "armes courantes et armes de guerre",
        "equip_A": ["armure de cuir clouté", "cimeterre", "épée courte", "arc long", "20 flèches", "carquois", "focaliseur druidique (branche de gui)", "paquetage d'explorateur", "7 po"],
        "equip_B": ["150 po"],
        "lanceur": True, "nb_cantrips": 2, "nb_sorts_1": 2,
    },
    "Roublard": {
        "predilection": "Discrétion", "carac": "Dextérité", "complexite": "Basse",
        "de_vie": 8, "sauvegardes": ["Dextérité", "Intelligence"],
        "competences": ["Acrobaties", "Athlétisme", "Discrétion", "Escamotage", "Intimidation", "Intuition", "Investigation", "Perception", "Persuasion", "Tromperie"],
        "nb_competences": 4, "armures": ["armures légères"],
        "armes": "armes courantes et armes de guerre «Finesse ou Légère»",
        "equip_A": ["armure de cuir", "2 dagues", "épée courte", "arc court", "20 flèches", "carquois", "outils de voleur", "paquetage de cambrioleur", "8 po"],
        "equip_B": ["100 po"],
        "lanceur": False, "nb_cantrips": 0, "nb_sorts_1": 0,
    },
}

# Historiques (antécédents) — données vérifiées, markdown dégradé.
HISTORIQUES: dict[str, dict[str, Any]] = {
    "Acolyte": {
        "caracs": ["Intelligence", "Sagesse", "Charisme"],
        "aptitude": "Initié à la magie (Clerc)",
        "competences": ["Intuition", "Religion"],
        "outils": "matériel de calligraphe",
        "equip_A": ["matériel de calligraphe", "livre (de prières)", "symbole sacré", "parchemin (10 feuilles)", "robe", "8 po"],
        "equip_B": ["50 po"],
    },
    "Criminel": {
        "caracs": ["Dextérité", "Constitution", "Intelligence"],
        "aptitude": "Vigilant",
        "competences": ["Discrétion", "Escamotage"],
        "outils": "outils de voleur",
        "equip_A": ["2 dagues", "outils de voleur", "2 bourses", "pied-de-biche", "tenue de voyage", "16 po"],
        "equip_B": ["50 po"],
    },
    "Sage": {
        "caracs": ["Constitution", "Intelligence", "Sagesse"],
        "aptitude": "Initié à la magie (Magicien)",
        "competences": ["Arcanes", "Histoire"],
        "outils": "matériel de calligraphe",
        "equip_A": ["bâton de combat", "matériel de calligraphe", "livre (d'histoire)", "parchemin (8 feuilles)", "robe", "8 po"],
        "equip_B": ["50 po"],
    },
    "Soldat": {
        "caracs": ["Force", "Dextérité", "Constitution"],
        "aptitude": "Sauvagerie martiale",
        "competences": ["Athlétisme", "Intimidation"],
        "outils": "un type de boîte de jeux",
        "equip_A": ["arc court", "20 flèches", "carquois", "lance", "boîte de jeux", "trousse de soins", "tenue de voyage", "14 po"],
        "equip_B": ["50 po"],
    },
}

# Langues : commun + table d12 (verifiable dans 02-origines.md).
# Les doublons de la table (Elfique, Halfelin, Nain) sont retirés pour
# l'affichage en menu : chaque langue n'est proposée qu'une seule fois.
LANGUES_D12 = [
    "Draconique", "Elfique", "Gigant", "Gnome", "Gobelin",
    "Halfelin", "Langue multiverselle des signes",
    "Nain", "Orc",
]
LANGUES_RARES = [
    "Abyssal", "Céleste", "Druidique", "Infernal", "Argot des voleurs",
    "Primordial", "Sylvestre", "Commun des profondeurs", "Profond",
]

# Alignements : 9 options, description parsée depuis 04-alignement.md.
ALIGNEMENTS = [
    "Loyal bon", "Neutre bon", "Chaotique bon",
    "Loyal neutre", "Neutre", "Chaotique neutre",
    "Loyal mauvais", "Neutre mauvais", "Chaotique mauvais",
]

# Descriptions courtes des options proposées dans les menus.
DESCRIPTIONS_ALIGNEMENTS: dict[str, str] = {
    "Loyal bon": "honnête et compatissant, respecte les lois",
    "Neutre bon": "bienveillant sans se soucier des règles",
    "Chaotique bon": "agit comme le lui dicte son cœur",
    "Loyal neutre": "suit la loi et la tradition sans partialité",
    "Neutre": "fait ce qui lui paraît juste, sans conviction",
    "Chaotique neutre": "liberté totale, refuse toute contrainte",
    "Loyal mauvais": "prend ce qu'il veut, avec méthode et sans pitié",
    "Neutre mauvais": "pense d'abord à lui, sans scrupules",
    "Chaotique mauvais": "capricieux et vindicatif, sème la destruction",
}

DESCRIPTIONS_ESPECES: dict[str, str] = {
    "Drakéide": "descendant de dragon, souffle destructeur",
    "Elfe": "peuple féerique des forêts, champion de la magie",
    "Gnome": "petit peuple ingénieur, illusionniste né",
    "Goliath": "géant des montagnes, robuste et endurant",
    "Halfelin": "petit peuple joyeux, discret et chanceux",
    "Humain": "ambitieux et polyvalent, partout chez lui",
    "Nain": "forgeron des montagnes, tenace et fier",
    "Orc": "guerrier puissant, issu des terres sauvages",
    "Tieffelin": "héritier du lignage infernal, vu avec méfiance",
}

DESCRIPTIONS_HISTORIQUES: dict[str, str] = {
    "Acolyte": "formé dans un temple, au service d'un dieu",
    "Criminel": "marqué par le crime, aux réseaux interlope",
    "Sage": "érudit dévoué au savoir et aux livres",
    "Soldat": "vétéran des champs de bataille, discipliné",
}

DESCRIPTIONS_LANGUES: dict[str, str] = {
    "Draconique": "langue ancienne des dragons et de leurs serviteurs",
    "Elfique": "langue mélodieuse des elfes, langue de la magie",
    "Gigant": "parlée par les géants des grottes et des cimes",
    "Gnome": "langue des gnomes, tournée vers l'ingénierie",
    "Gobelin": "parlée par les gobelins et les créatures sauvages",
    "Halfelin": "langue discrète des halfelins, souvent ignorée",
    "Langue multiverselle des signes": "langue gestuelle des sourds et muets",
    "Nain": "langue rude des nains, difficile à apprendre",
    "Orc": "langue gutturale des orcs et des demi-orcs",
    "Abyssal": "langue des démons des plans inférieurs",
    "Céleste": "langue des anges et des êtres célestes",
    "Druidique": "langue secrète des druides et des gardiens de la nature",
    "Infernal": "langue des diables des Neuf Enfers",
    "Argot des voleurs": "jargon secret des voleurs et des assassins",
    "Primordial": "langue élémentaire des plans de feu, d'eau, d'air et de terre",
    "Sylvestre": "langue des fées et des esprits de la nature",
    "Commun des profondeurs": "parlée dans l'Outreterre, sous la surface",
    "Profond": "langue des aboleths et des terreurs des profondeurs",
}

DESCRIPTIONS_COMPETENCES: dict[str, str] = {
    "Acrobaties": "sauts, équilibres et prouesses corporelles",
    "Arcanes": "connaissances des sorts, des symboles et des plans",
    "Athlétisme": "escalade, saut, natation, corps à corps",
    "Discrétion": "se cacher, surprendre, passer inaperçu",
    "Dressage": "dresser les montures et calmer les animaux",
    "Équitation": "monter, diriger et rester en selle",
    "Escamotage": "filer un objet, cacher, voler à la tire",
    "Histoire": "connaître les royaumes, les guerres et les ruines",
    "Intimidation": "inspirer la peur pour obtenir ce qu'on veut",
    "Intuition": "lire les intentions, deviner un mensonge",
    "Investigation": "relever des indices, mener une enquête",
    "Médecine": "soigner les blessures, diagnostiquer une maladie",
    "Nature": "connaître les bêtes, les plantes et les terrains",
    "Perception": "voir, entendre et sentir ce qui nous entoure",
    "Persuasion": "convaincre, négocier, se montrer courtois",
    "Religion": "connaître les dieux, les rites et les plans",
    "Survie": "s'orienter, traquer, survivre en milieu sauvage",
    "Tromperie": "mentir, duper, dissimuler ses intentions",
}


# Espèces : traits vérifiés (markdown dégradé → constantes).
# Chaque trait : (nom, description).
ESPECES: dict[str, dict[str, Any]] = {
    "Drakéide": {
        "taille": "M (1,50 à 2,10 m)", "vitesse": 9,
        "traits": [
            ("Ascendance draconique", "Vous choisissez une ascendance draconique (table). Le type de dégâts de votre souffle en dépend."),
            ("Résistance aux dégâts", "Résistance aux dégâts du type de votre ascendance."),
            ("Souffle du dragon", "Cône de 4,50 m ou ligne de 9 m sur 1,5 m : 1d10 dégâts, DD 8 + Con + maîtrise, demi-dégâts sur sauvegarde de Dextérité. +1d10 aux niveaux 5/11/17. Usage : bonus d'action, récupéré au repos long."),
            ("Vision dans le noir", "18 m."),
            ("Vol draconique", "Au niveau 5, vous gagnez un vol de 9 m."),
        ],
    },
    "Elfe": {
        "taille": "M (1,50 à 1,80 m)", "vitesse": 9,
        "traits": [
            ("Ascendance féerique", "Avantage aux jets de sauvegarde contre être Charmé."),
            ("Vision dans le noir", "18 m."),
            ("Lignage elfique", "Sort offert aux niveaux 1/3/5, toujours préparé, 1 lancement sans emplacement par repos long."),
            ("Incantation", "Intelligence, Sagesse ou Charisme (au choix) pour les sorts."),
        ],
    },
    "Gnome": {
        "taille": "P (90 à 120 cm)", "vitesse": 9,
        "traits": [
            ("Magie gnome", "Vous connaissez le sort illusion mineure."),
            ("Lignage gnome", "Forêts : communication avec les animaux. Roches : prestidigitation et réparation (10 minutes)."),
            ("Incantation", "Intelligence, Sagesse ou Charisme pour les sorts."),
        ],
    },
    "Goliath": {
        "taille": "M (2,10 à 2,40 m)", "vitesse": 10,
        "traits": [
            ("Ascendance gigante", "Brûlure ignée (1d10 feu sur coup) / Endurance de la pierre (1d12 + Con en Réaction) / Froid mordant (1d6 froid, vitesse -3 m). Usage : bonus d'action, récupéré au repos long."),
        ],
    },
    "Halfelin": {
        "taille": "P (60 à 90 cm)", "vitesse": 9,
        "traits": [
            ("Agilité halfeline", "Vous pouvez traverser une créature plus grande que vous."),
            ("Brave", "Avantage aux jets de sauvegarde contre être Effrayé."),
            ("Chance", "Relancez un 1 obtenu au d20."),
            ("Discrétion naturelle", "Vous pouvez vous cacher même partiellement caché."),
        ],
    },
    "Humain": {
        "taille": "M (1,20 à 2,10 m) ou P (60 à 120 cm)", "vitesse": 9,
        "traits": [
            ("Compétent", "Une compétence supplémentaire à votre choix."),
            ("Ingénieux", "Une Inspiration héroïque par repos long."),
            ("Polyvalent", "Un don supplémentaire («Doué» recommandé)."),
        ],
    },
    "Nain": {
        "taille": "M (1,20 à 1,50 m)", "vitesse": 9,
        "traits": [
            ("Connaissance de la pierre", "Perception des vibrations à 18 m pendant 10 minutes (action bonus, usage = bonus de maîtrise)."),
            ("Résistance naine", "Résistance aux dégâts de poison, avantage contre Empoisonné."),
            ("Ténacité naine", "+1 point de vie maximum par niveau."),
            ("Vision dans le noir", "36 m."),
        ],
    },
    "Orc": {
        "taille": "M (1,80 à 2,10 m)", "vitesse": 9,
        "traits": [
            ("Acharnement", "Réduit à 0 PV, vous récupérez 1 PV (1 fois par repos long)."),
            ("Poussée d'adrénaline", "Bonus d'action : PV temporaires = bonus de maîtrise. Usage = bonus de maîtrise, récupéré au repos court ou long."),
            ("Vision dans le noir", "36 m."),
        ],
    },
    "Tieffelin": {
        "taille": "M (1,20 à 2,10 m) ou P (90 à 120 cm)", "vitesse": 9,
        "traits": [
            ("Héritage fiélon", "Abyssal : résistance poison + bouffée de poison. Chtonien : résistance nécrotique + contact glacial. Infernal : résistance feu + trait de feu."),
            ("Sort fiélon", "Sort offert aux niveaux 1/3/5, récupéré au repos long."),
        ],
    },
}

# Tables de noms par espèce (le SRD ne fournit pas de tables de noms :
# listes embarquées, adaptées à chaque espèce).
NOMS_PAR_ESPECE = {
    "Drakéide": {
        "prenoms": [
            "Arjhan", "Sashalith", "Zaranda", "Mehenara", "Kriv", "Nerain",
            "Rasna", "Thuvrin", "Zaritha", "Kallindrax", "Meherra", "Rivenne",
        ],
        "noms": [
            "Aile d'Or", "Écaille d'Acier", "Croc de Feu", "Souffle d'Ambre",
            "Serre de Nuit", "Flamme Rouge", "Regard d'Or", "Sang de Braise",
            "Aile Nocturne", "Coeur de Cuivre",
        ],
    },
    "Elfe": {
        "prenoms": [
            "Aélis", "Caelia", "Elandri", "Thali", "Aerith", "Cael", "Ilyana",
            "Nael", "Sylane", "Ysolde", "Elwen", "Liriel",
        ],
        "noms": [
            "Clairelune", "Feuille d'Argent", "Vent du Soir", "Étoile du Matin",
            "Rosée du Matin", "Chantebois", "Laruelle", "Belarbre",
            "Sylvanel", "Aube Claire",
        ],
    },
    "Gnome": {
        "prenoms": [
            "Althéa", "Bip", "Coco", "Din", "Eulalie", "Filin", "Gribouille",
            "Mimi", "Nini", "Trotte", "Babette", "Puck",
        ],
        "noms": [
            "Bric-à-Brac", "Lunette", "Savoir-Vite", "Tournevis", "Astucieuse",
            "Babil", "Malice", "Fil-de-Fer", "Clochette", "Tinte-Lume",
        ],
    },
    "Goliath": {
        "prenoms": [
            "Abris", "Dael", "Kavrok", "Malag", "Thessa", "Yagrak", "Dossan",
            "Kaleena", "Tanin", "Ungrom", "Jakar", "Kalessa",
        ],
        "noms": [
            "Roc-Céleste", "Marche au Vent", "Fils des Cimes", "Briseroc",
            "Cime Éternelle", "Chute Libre", "Pied de Montagne",
            "Coeur de Pierre", "Tonnerre Haut", "Nuage Gris",
        ],
    },
    "Halfelin": {
        "prenoms": [
            "Milo", "Nella", "Pippa", "Filibert", "Luce", "Babette", "Fenwick",
            "Pru", "Tobie", "Coco", "Rosine", "Edouard",
        ],
        "noms": [
            "Sac à Dos", "Croque-Pain", "Trotte-menu", "Boisjoli", "Pied-Léger",
            "Croque-Pomme", "Bellemaison", "Douceur", "Petit-Appétit",
            "Sous-les-Feuilles",
        ],
    },
    "Humain": {
        "prenoms": [
            "Aaron", "Béatrice", "Camille", "Damien", "Élodie", "Florent",
            "Gaspard", "Hélène", "Isabeau", "Jules", "Karim", "Léa", "Marc",
            "Nathalie", "Olivier", "Pascale", "Quentin", "Rose", "Thibault",
            "Ursule", "Vincent", "Yves", "Zoé", "Agnès", "Bastien", "Claudine",
            "Didier", "Estelle", "Sébastien",
        ],
        "noms": [
            "du Val", "des Bois", "Lefèvre", "Moreau", "Grandet",
            "de la Fontaine", "Petitpas", "Renaud", "de Sable",
            "au Grand Coeur", "des Champs", "Lemoine",
        ],
    },
    "Nain": {
        "prenoms": [
            "Borin", "Durgin", "Kazim", "Morvan", "Thorek", "Hilda",
            "Grimhilde", "Ondrine", "Ragna", "Solveig", "Dorin", "Brunehaut",
        ],
        "noms": [
            "Barbe de Fer", "Poing d'Acier", "Forgelourde", "Pied Sûr",
            "Corne-Dure", "Rochefort", "Taille-Roche", "Grandmarteau",
            "Fougue du Roc", "Gros-Maraud",
        ],
    },
    "Orc": {
        "prenoms": [
            "Grom", "Moguk", "Uzrek", "Yagra", "Krag", "Droka", "Urzul",
            "Grisha", "Maugor", "Ogrisha", "Urgrog", "Kagh",
        ],
        "noms": [
            "Croc-Sanglant", "Mâchoire-Féroce", "Brise-Os", "Coeur-de-Sang",
            "Poing-Rouge", "Tranche-Nuit", "Hurlevent", "Oeil-de-Braise",
            "Morsure", "Tonnerre de Guerre",
        ],
    },
    "Tieffelin": {
        "prenoms": [
            "Alisara", "Kallista", "Malai", "Mistella", "Zara", "Drusilia",
            "Nymara", "Saphira", "Ysolde", "Vespera", "Cassia", "Lilith",
        ],
        "noms": [
            "Malfeu", "Cendre", "Nuit Écarlate", "Ombre Douce", "Braise",
            "Feu Follet", "Ame Sombre", "Serment Perdu", "Oeil de Corbeau",
            "Noir Désir",
        ],
    },
}

# ---------------------------------------------------------------------------
# Extraction à la volée + cache
# ---------------------------------------------------------------------------


def _charger_json_cache(nom: str) -> Any | None:
    p = DATA_DIR / nom
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _sauvegarder_json_cache(nom: str, donnees: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / nom).write_text(
        json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def charger_classes() -> dict[str, dict[str, Any]]:
    """Retourne les données par classe (constantes vérifiées — le markdown
    `dnd/classes/*.md` est dégradé et ne sert que de référence)."""
    return CLASSES


def charger_historiques() -> dict[str, dict[str, Any]]:
    """Historiques (antécédents) : constantes vérifiées."""
    return HISTORIQUES


def charger_especes() -> dict[str, dict[str, Any]]:
    """Espèces : constantes vérifiées (le chapitre est une prose collée)."""
    return ESPECES


def charger_alignements() -> list[str]:
    return list(ALIGNEMENTS)


def charger_langues() -> tuple[str, list[str], list[str]]:
    return ("Commun", list(LANGUES_D12), list(LANGUES_RARES))


def _extraire_sorts(modele: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Parsés depuis `02-sorts/*.md` : noms par classe + description courte.

    Retourne (noms par classe, descriptions par nom de sort). La description
    est le premier paragraphe de prose du corps (après la ligne «Durée : …»),
    mis sur une ligne et tronqué.
    """
    par_classe: dict[str, list[str]] = {}
    descriptions: dict[str, str] = {}
    for f in sorted((CORPUS / "02-sorts").glob("*.md")):
        texte = f.read_text(encoding="utf-8")
        keys, corps = _parse_fiche(texte)
        m = re.search(modele, texte, re.M)
        if not m:
            continue
        nom = keys.get("nom", f.stem.replace("-", " "))
        # Description : le premier paragraphe de prose après la ligne «Durée : …».
        # Les lignes qui suivent «Composantes : …» peuvent être coupées en fin de
        # ligne (retour à la ligne forcé) : on saute ces fragments (minuscules).
        lignes: list[str] = []
        apres_duree = False
        for ligne in corps.splitlines():
            if not apres_duree:
                if ligne.strip().lower().startswith("durée"):
                    apres_duree = True
                continue
            if not ligne.strip():
                if lignes:
                    break
                continue
            if lignes == [] and ligne.strip()[:1].islower():
                # fragment de la ligne « Composantes : … » (retour à la ligne
                # forcé) collé devant la description : on le retire pour
                # démarrer au premier mot commençant par une majuscule.
                m2 = re.search(r"[A-ZÀ-Ý][a-zà-ÿ]", ligne)
                if not m2:
                    continue
                ligne = ligne[m2.start():]
            lignes.append(ligne.strip())
        desc = " ".join(" ".join(lignes).split()).replace("**", "")
        if desc:
            descriptions[nom] = desc
        # Le groupe des classes est le dernier du patron (le 1er est l'école).
        classes = m.group(m.lastindex)
        for c in classes.split(","):
            par_classe.setdefault(c.strip(), []).append(nom)
    return par_classe, descriptions


def charger_cantrips() -> dict[str, list[str]]:
    """Cantrips par classe, parsés depuis `02-sorts/*.md` (ligne
    «École mineure (…) »). Cache JSON dans `dnd_perso/data/sorts.json`."""
    cache = _charger_json_cache("sorts.json")
    if cache is not None:
        return cache
    if not CORPUS.is_dir():
        raise RuntimeError(
            f"Corpus introuvable : {CORPUS} — vérifiez que le dossier "
            "dnd/srd-5.2.1/ est présent."
        )
    par_classe, _desc = _extraire_sorts(r"^([A-Za-zÀ-ÿ]+) mineure \(([^)]*)\)\s*$")
    if not par_classe:
        raise RuntimeError(
            "Extraction des sorts mineurs impossible : aucune fiche "
            "comportant la ligne «École mineure (…) »."
        )
    _sauvegarder_json_cache("sorts.json", par_classe)
    return par_classe


def charger_sorts_1() -> dict[str, list[str]]:
    """Sorts de 1er niveau par classe, parsés depuis `02-sorts/*.md`
    (ligne «École du 1er niveau (…) »). Cache JSON dans
    `dnd_perso/data/sorts_1.json`."""
    cache = _charger_json_cache("sorts_1.json")
    if cache is not None:
        return cache
    if not CORPUS.is_dir():
        raise RuntimeError(
            f"Corpus introuvable : {CORPUS} — vérifiez que le dossier "
            "dnd/srd-5.2.1/ est présent."
        )
    par_classe, _desc = _extraire_sorts(
        r"^[A-Za-zÀ-ÿ]+ du 1[eè]re? niveau \(([^)]*)\)\s*$"
    )
    _sauvegarder_json_cache("sorts_1.json", par_classe)
    return par_classe


def charger_descriptions_sorts() -> dict[str, str]:
    """Descriptions courtes des sorts (cantrips + 1er niveau), extraites
    du corps des fiches. Cache JSON dans `dnd_perso/data/sorts_desc.json`."""
    cache = _charger_json_cache("sorts_desc.json")
    if cache is not None:
        return cache
    if not CORPUS.is_dir():
        raise RuntimeError(
            f"Corpus introuvable : {CORPUS} — vérifiez que le dossier "
            "dnd/srd-5.2.1/ est présent."
        )
    _par_classe, descriptions = _extraire_sorts(
        r"^[A-Za-zÀ-ÿ]+ (?:mineure|du 1[eè]re? niveau) \(([^)]*)\)\s*$"
    )
    _sauvegarder_json_cache("sorts_desc.json", descriptions)
    return descriptions


def charger_babioles() -> list[tuple[int, str]]:
    """Table d100 des babioles, parsée depuis
    `06-equipement-et-babioles.md`. Cache JSON."""
    cache = _charger_json_cache("babioles.json")
    if cache is not None:
        return [tuple(x) for x in cache]
    p = CORPUS / "creer_personnage" / "06-equipement-et-babioles.md"
    if not p.is_file():
        return []
    texte = p.read_text(encoding="utf-8")
    table: list[tuple[int, str]] = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        m = re.match(r"^\|?\s*(\d{1,3})\s*\|\s*(.+?)\s*\|?\s*$", ligne)
        if m and "d100" not in ligne.lower():
            table.append((int(m.group(1)), m.group(2).strip()))
    if table:
        _sauvegarder_json_cache("babioles.json", table)
    return table


def charger_tout() -> dict[str, Any]:
    """Charge l'ensemble des données nécessaires à la création."""
    return {
        "classes": charger_classes(),
        "historiques": charger_historiques(),
        "especes": charger_especes(),
        "alignements": charger_alignements(),
        "langues": charger_langues(),
        "cantrips": charger_cantrips(),
        "sorts_1": charger_sorts_1(),
        "babioles": charger_babioles(),
    }
