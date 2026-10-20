"""Orchestration headless de la création de personnage D&D 5.2.1 pour Open WebUI.

Couche d'adaptation au-dessus de `dnd_perso` (importé en **lecture seule**,
jamais modifié) :

- aucune entrée clavier (`input`) ni sortie console (`print`) ;
- le joueur répond en langage libre : la réponse est normalisée (`_norme`)
  puis confrontée aux options de l'étape ;
- si la réponse n'est pas comprise, un choix est tiré au hasard (avec un
  avertissement explicite dans la réponse JSON) ;
- la fiche finale est rendue en markdown, prête à être affichée dans le chat.

Chaque fonction retourne un dictionnaire sérialisable en JSON, destiné à être
relayé par le Maître du Jeu (la conversation est gérée par Open WebUI, pas ici).
"""

from __future__ import annotations

import json
import random
import re
from datetime import datetime
from typing import Any

from dnd_perso import dice, export, extract, models
from dnd_perso.io import _norme


def _phrase(texte: str) -> str:
    """Clé de comparaison pour les phrases-types (« au hasard », « continue »…) :
    minuscules, sans accents, sans ponctuation, espaces réduits.

    _norme conserve la ponctuation, donc « Au hasard ! » ne correspondait pas
    à « au hasard » et la réponse tombait dans la branche de saisie libre.
    """
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", _norme(texte))).strip()


# Paliers d'expérience (D&D 5.2.1) : PALIERS_XP[n] = XP minimum pour le niveau n+1.
PALIERS_XP = [0, 350, 1000, 2300, 3600, 6400, 10000, 15000, 23000, 36000]

# ---------------------------------------------------------------------------
# Données du corpus (chargées une seule fois)
# ---------------------------------------------------------------------------

_DONNEES: dict[str, Any] | None = None


def _charger() -> dict[str, Any]:
    """Charge (et met en cache) l'ensemble des données du corpus."""
    global _DONNEES
    if _DONNEES is None:
        _DONNEES = extract.charger_tout()
    return _DONNEES


# ---------------------------------------------------------------------------
# Sessions de création (une par chat Open WebUI)
# ---------------------------------------------------------------------------

_SESSIONS: dict[str, dict[str, Any]] = {}

# Alias de vocabulaire : nom courant (PHB 2024, mémoire du MJ) -> nom SRD 5.2.1.
_ALIAS_HISTORIQUE = {
    "Érudit": "Sage",
    "Savant": "Sage",
    "Charlatan": "Criminel",
    "Vagabond": "Criminel",
}

# Ordre des étapes de l'interview guidée.
ETAPES = [
    "classe",
    "espece",
    "genre",
    "historique",
    "competences",
    "langues",
    "caracteristiques",
    "alignement",
    "equipement",
    "nom",
    "sorts",
    "finalisation",
]

# Réponses signifiant « je ne sais pas, choisis pour moi » (tout au hasard).
_HASARD = (
    "au hasard",
    "j'ai pas",
    "jais pas",
    "je sais pas",
    "je ne sais pas",
    "jsais pas",
    "peu importe",
    "comme tu veux",
    "comme vous voulez",
    "decide",
    "decide pour moi",
    "decidez",
    "surprends moi",
    "surprenez moi",
    "fais moi confiance",
    "faites moi confiance",
    "nimporte quoi",
    "tout au hasard",
    "choisis",
    "choisissez",
    "va y",
    "vas y",
    "allez y",
)

# Réponses signifiant « j'arrête ».
_ABANDON = (
    "abandonne",
    "j'abandonne",
    "abandonner",
    "stop",
    "arrete",
    "arrete toi",
    "arretez",
    "arretez vous",
    "tant pis",
    "je renonce",
    "je laisse tomber",
    "annule",
    "annuler",
    "annule tout",
)

# Réponses vagues acceptées à l'étape « finalisation » (le MJ choisit tout).
_OUI = ("oui", "o", "vas y", "va y", "volontiers", "avec plaisir", "ok", "daccord", "oui vas y")
_NON = ("non", "n", "non merci", "pas besoin", "rien")

# Réponses signifiant « passe à la suite » ou « repose la question » : on ne
# remplit rien, on avance (la question courante est reposée si elle est due).
_CONTINUE = (
    "continue",
    "continuer",
    "continuez",
    "recommence",
    "recommencer",
    "recommencez",
    "reessaye",
    "reessayer",
    "reessaie",
    "retente",
    "retentez",
    "repose la question",
    "reposez la question",
)

# Réponses signifiant « je reviens à l'étape précédente ».
_RETOUR = (
    "retour",
    "retour en arriere",
    "en arriere",
    "revenir en arriere",
    "reviens en arriere",
    "revenir",
    "etape precedente",
    "precedent",
    "precedente",
    "annuler la derniere etape",
    "annuler derniere etape",
    "annuler la derniere",
)

# Questions posées au joueur (relaisées par le MJ, une étape à la fois).
_QUESTIONS = {
    "classe": "Commençons par la classe : qu'aimeriez-vous jouer ?",
    "espece": "Quelle espèce choisissez-vous ?",
    "genre": "Votre personnage est-il un homme ou une femme ?",
    "historique": "Quel antécédent (historique) a votre personnage ?",
    "competences": "Quelles compétences choisissez-vous ?",
    "langues": "Quelles langues votre personnage connaît-il ?",
    "caracteristiques": (
        "Comment générez-vous vos caractéristiques ? "
        "Choisissez « valeurs standard » ou « achat de points (27 pts) » en indiquant "
        "6 valeurs entre 8 et 15, par exemple : FOR 15, DEX 14, CON 13, INT 12, SAG 10, CHA 8."
    ),
    "alignement": "Quel est l'alignement de votre personnage ?",
    "equipement": "Quel équipement de départ choisissez-vous ?",
    "nom": "Quel nom donnez-vous à votre personnage ? (ou « au hasard »)",
    "sorts": (
        "Quels sorts connaissez-vous ? Choisissez parmi la liste (sorts mineurs "
        "puis sorts de 1er niveau), ou dites « au hasard »."
    ),
    "finalisation": "Tout est prêt, je génère votre fiche.",
}


# ---------------------------------------------------------------------------
# Aides : reconnaissance de la réponse libre du joueur
# ---------------------------------------------------------------------------


def _motif_option(opt: str) -> str:
    """Motif regex tolérant pour une option : insensible aux accents (via
    `_norme`) et à la marque du pluriel. « Acrobaties » est reconnu même écrit
    « acrobatie » (singulier), « Arcanes » même écrit « arcane », etc. — sinon
    une réponse au singulier n'était pas reconnue et la compétence était
    remplacée par un tirage au hasard. On rend le « s » final facultatif."""
    n = re.escape(_norme(opt))
    if n.endswith("s"):
        n = n[:-1] + "s?"
    return n


def _trouver(r: str, options: list[str]) -> str | None:
    """Cherche une option dans la réponse : correspondance exacte, puis
    containment avec frontières de mot (tolérant aux accents et au pluriel)."""
    nr = _norme(r)
    if not nr:
        return None
    # Alias de vocabulaire : certains noms du PHB 2024 (« Érudit ») désignent
    # un historique du SRD sous un autre nom (« Sage »).
    for cle, cible in _ALIAS_HISTORIQUE.items():
        nc = _norme(cle)
        if cible in options and (nc == nr or re.search(r"\b" + re.escape(nc) + r"\b", nr)):
            return cible
    for opt in options:
        if _norme(opt) == nr:
            return opt
    for opt in options:
        if re.search(r"\b" + _motif_option(opt) + r"\b", nr):
            return opt
    return None


def _trouver_plusieurs(r: str, options: list[str]) -> list[str]:
    """Toutes les options mentionnées dans la réponse (compétences, sorts…)."""
    nr = _norme(r)
    trouvees: list[str] = []
    for opt in options:
        if re.search(r"\b" + _motif_option(opt) + r"\b", nr) and opt not in trouvees:
            trouvees.append(opt)
    return trouvees


# Motifs de reconnaissance des caractéristiques (abréviation ou nom complet),
# dans l'ordre FOR, DEX, CON, INT, SAG, CHA attendu par `Caracteristiques`.
_CARAC_MOTIFS = [
    r"force|for",
    r"dexterite|dex",
    r"constitution|con",
    r"intelligence|int",
    r"sagesse|sag",
    r"charisme|cha",
]


def _allouer_caracteristiques(r: str) -> tuple[list[int], bool] | None:
    """Répartition étiquetée des caractéristiques, dans l'ordre FOR/DEX/CON/INT/SAG/CHA.

    Chaque valeur est affectée à la caractéristique **nommée** (« CHA 15,
    FOR 8 » ou « Charisme 15, Force 8 ») et non placée positionnellement :
    l'ancien comportement, qui lisait les nombres dans l'ordre, inversait la
    fiche quand le joueur énonçait Charisme en premier (le Ensorceleur se
    retrouvait avec FOR 15 / CHA 8).

    Retourne `(valeurs, complete)` : `complete` vaut True si les six
    caractéristiques sont nommées, False si la réponse n'en nomme que
    certaines (les autres sont comblées avec les valeurs standard restantes).
    Retourne None si aucun libellé de caractéristique n'est présent.
    """
    t = _norme(r)
    t = re.split(r"\+\s*bonus", t)[0]
    allouees: dict[int, int] = {}
    # On découpe en segments (séparateurs ou conjonctions) pour qu'un libellé
    # ne capte pas le nombre de la proposition voisine (« 15 en Force et 8 en
    # Charisme » : sinon « Force » avalerait le 8 de la clause suivante).
    segments = re.split(r"[,;\n]| et | puis | puis-| alors | avec ", t)
    for seg in segments:
        mnum = re.search(r"\d{1,2}", seg)
        if not mnum:
            continue
        valeur = int(mnum.group(0))
        for idx, motif in enumerate(_CARAC_MOTIFS):
            if idx in allouees:
                continue
            if re.search(r"\b(?:" + motif + r")\b", seg):
                allouees[idx] = valeur
                break
    if not allouees:
        return None
    if len(allouees) == 6:
        return [allouees[i] for i in range(6)], True
    # Répartition partielle (« Charisme 15, le reste comme tu veux ») : on
    # complète avec les valeurs standard non encore employées.
    reste = list(extract.ARRAY_STANDARD)
    for v in allouees.values():
        if v in reste:
            reste.remove(v)
    resultat: list[int] = []
    for i in range(6):
        if i in allouees:
            resultat.append(allouees[i])
        else:
            resultat.append(reste.pop(0) if reste else 8)
    return resultat, False


def _extraire_valeurs(r: str) -> list[int] | None:
    """Extrait 6 valeurs d'achat de points (8-15, budget 27) d'une réponse.

    Les mentions de bonus racial (« + bonus d'elfe, Charisme 16 ») sont
    ignorées, et les valeurs standard (15 14 13 12 10 8) sont acceptées sans
    contrôle de budget : elles ne rentrent pas dans les 27 points d'achat.

    Les libellés (« CHA 15, FOR 8 ») sont honorés en priorité : chaque valeur
    est affectée à la caractéristique nommée. Sans libellé, on retombe sur
    l'ordre positionnel (FOR, DEX, CON, INT, SAG, CHA).
    """
    t = _norme(r)
    t = re.split(r"\+\s*bonus", t)[0]
    # 1) Répartition étiquetée : on respecte les libellés des caractéristiques.
    allouees = _allouer_caracteristiques(r)
    if allouees is not None:
        valeurs, complete = allouees
        if valeurs == list(extract.ARRAY_STANDARD):
            return valeurs
        if complete:
            # Répartition complète annoncée par le joueur : on lui fait
            # confiance (les valeurs peuvent inclure le bonus racial, donc
            # dépasser 15 ou le budget d'achat). On rejette seulement les
            # nombres absurdes hors plage D&D (3-20).
            if any(v < 3 or v > 20 for v in valeurs):
                return None
            return valeurs
        return valeurs
    # 2) Repli positionnel : six nombres, plage et budget 27.
    nums = [int(x) for x in re.findall(r"\d+", t)]
    if len(nums) == 6 and nums == list(extract.ARRAY_STANDARD):
        return nums
    if len(nums) != 6:
        return None
    if any(v < 8 or v > 15 for v in nums):
        return None
    if sum(extract.COUT_ACHAT.get(v, 99) for v in nums) > 27:
        return None
    return nums


# Index des caractéristiques dans l'ordre FOR, DEX, CON, INT, SAG, CHA (attendu
# par `Caracteristiques.depuis_liste`).
_CARAC_INDEX = {
    "force": 0, "dexterite": 1, "constitution": 2,
    "intelligence": 3, "sagesse": 4, "charisme": 5,
}


def _standard_pour_classe(classe: str, donnees: dict) -> list[int]:
    """Répartit le tableau standard (15 14 13 12 10 8) selon la classe.

    Quand le joueur choisit les « valeurs standard » sans préciser la
    répartition, on ne doit PAS les coller dans l'ordre FOR→CHA (cela laisse un
    Barde ou un Ensorceleur avec Charisme 8, la caractéristique la plus
    importante). On donne donc 15 à la caractéristique principale de la classe,
    14 à ses caractéristiques de sauvegarde, puis on complète dans l'ordre
    usuel. Résultat pour un Barde : CHA 15, DEX 14, FOR 13, CON 12, INT 10, SAG 8.
    """
    info = donnees.get("classes", {}).get(classe, {})
    ordre: list[int] = []

    def ajoute(nom: str) -> None:
        idx = _CARAC_INDEX.get(_norme(nom))
        if idx is not None and idx not in ordre:
            ordre.append(idx)

    # 1) Caractéristique(s) principale(s) de la classe (« Force et Charisme »…).
    for morceau in re.split(r"\s+(?:et|ou|/)\s+", info.get("carac", "") or ""):
        ajoute(morceau)
    # 2) Caractéristiques de sauvegarde (les autres aptitudes clés).
    for sauve in info.get("sauvegardes", []) or []:
        ajoute(sauve)
    # 3) Le reste dans l'ordre usuel FOR→CHA.
    for idx in range(6):
        if idx not in ordre:
            ordre.append(idx)

    valeurs = [0] * 6
    for rang, idx in enumerate(ordre):
        valeurs[idx] = extract.ARRAY_STANDARD[rang]
    return valeurs


def _est_kit_b(r: str) -> bool:
    """Le joueur réclame-t-il le kit B (pécule) plutôt que le kit A ?"""
    nr = _norme(r)
    return bool(re.search(r"\b(?:b|kit b|kitb|pécule|pecule|or|argent|sac)\b", nr))


# ---------------------------------------------------------------------------
# Remplissage des étapes
# ---------------------------------------------------------------------------


def _remplir(session: dict[str, Any], r: str) -> list[str]:
    """Remplit UNIQUEMENT l'étape en cours (celle qui vient d'être posée).

    On ne remplit qu'UNE étape par réponse : c'est le principe du tunnel « une
    question à la fois ». Auparavant la fonction remplissait tout ce qu'elle
    reconnaissait dans la réponse, ce qui faisait sauter des étapes (ex. répondre
    « Soldat » à l'historique remplissait aussi compétences + langues) et, pire,
    faisait déborder la réponse d'une étape sur l'étape « nom » (le joueur qui
    répond « chaotique bon » à l'alignement voyait son alignement enregistré
    comme nom, puis la fiche se finalisait d'un coup).

    L'étape à remplir est déterminée AVANT toute modification de l'état.
    Retourne la liste des avertissements (tirages au hasard, valeurs par défaut).
    """
    etat = session["etat"]
    rng = session["rng"]
    donnees = _charger()
    nr = _norme(r)
    avertis: list[str] = []
    etape = _premiere_non_remplie(etat)
    if etape is None or etape == "finalisation":
        return avertis

    # --- classe ---
    if etape == "classe":
        nom = _trouver(r, list(donnees["classes"]))
        if nom:
            etat["classe"] = nom

    # --- espèce ---
    elif etape == "espece":
        nom = _trouver(r, list(donnees["especes"]))
        if nom:
            etat["espece"] = nom

    # --- genre (homme / femme) ---
    elif etape == "genre":
        if re.search(r"\bfemme\b|\bféminin\b|\bf\b", nr):
            etat["genre"] = "Femme"
        elif re.search(r"\bhomme\b|\bmasculin\b|\bm\b", nr):
            etat["genre"] = "Homme"

    # --- historique ---
    elif etape == "historique":
        nom = _trouver(r, list(donnees["historiques"]))
        if nom:
            etat["historique"] = nom

    # --- alignement ---
    elif etape == "alignement":
        nom = _trouver(r, list(donnees["alignements"]))
        if nom:
            etat["alignement"] = nom

    # --- compétences (choix multiples, complément aléatoire) ---
    elif etape == "competences" and "classe" in etat:
        info = donnees["classes"].get(etat["classe"], {})
        options = list(info.get("competences") or [])
        nb = int(info.get("nb_competences") or 0)
        trouvees = _trouver_plusieurs(r, options)
        if len(trouvees) < nb and options:
            reste = [o for o in options if o not in trouvees]
            trouvees.extend(rng.sample(reste, min(nb - len(trouvees), len(reste))))
            avertis.append("Certaines compétences ont été tirées au hasard.")
        if trouvees:
            etat["competences"] = trouvees[:nb] if nb else trouvees

    # --- langues (commun + d12, variante rare facultative) ---
    elif etape == "langues":
        commun, d12, rares = donnees["langues"]
        trouvees = _trouver_plusieurs(r, d12)
        if not trouvees:
            trouvees = [rng.choice(d12)]
            avertis.append("Langue supplémentaire tirée au hasard.")
        langues = [commun] + trouvees[:1]
        if "rare" in nr:
            rares_ok = _trouver_plusieurs(r, rares)
            langues.append(rares_ok[0] if rares_ok else rng.choice(rares))
        etat["langues"] = langues

    # --- caractéristiques (standard par défaut, achat de points sur demande) ---
    elif etape == "caracteristiques":
        vals = _extraire_valeurs(r)
        veut_standard = bool(re.search(r"standard|valeur", nr))
        veut_points = bool(re.search(r"point|achat", nr))
        # Une phrase nommant une caractéristique (abréviation OU nom complet,
        # ex. « Charisme 15 ») ou contenant 6 nombres est une répartition, même
        # sans mot-clé « point »/« achat ». Sans ce large motif, une réponse
        # comme « je mets 15 en Charisme » ne remplissait rien et la question
        # était re-posée en boucle.
        semble_allocation = bool(
            re.search(
                r"\b(?:force|for|dexterite|dex|constitution|con|intelligence|int"
                r"|sagesse|sag|charisme|cha)\b",
                nr,
            )
            or len(re.findall(r"\d+", nr)) == 6
        )
        if vals is not None:
            etat["carac"] = models.Caracteristiques.depuis_liste(vals)
        elif veut_standard:
            std = _standard_pour_classe(etat.get("classe", ""), donnees)
            etat["carac"] = models.Caracteristiques.depuis_liste(std)
            avertis.append("Caractéristiques en valeurs standard (réparties pour ta classe).")
        elif veut_points or semble_allocation:
            # Réponse non comprise : plutôt que de reposer la même question en
            # boucle, on retient les valeurs standard et on en avertit le joueur.
            std = _standard_pour_classe(etat.get("classe", ""), donnees)
            etat["carac"] = models.Caracteristiques.depuis_liste(std)
            avertis.append(
                "Répartition non reconnue (6 valeurs entre 8 et 15, budget 27 pts) : "
                "j'ai retenu les valeurs standard réparties pour ta classe."
            )

    # --- équipement (kit A par défaut, kit B sur demande) ---
    elif etape == "equipement":
        info = donnees["classes"].get(etat.get("classe", ""), {})
        kit_a = list(info.get("equip_A") or [])
        kit_b = list(info.get("equip_B") or [])
        if kit_b and _est_kit_b(r):
            etat["equipement"] = models.Equipement(kit_b)
        else:
            etat["equipement"] = models.Equipement(kit_a or kit_b)

    # --- sorts (lanceurs uniquement, reconnaissance par nom) ---
    elif etape == "sorts" and "classe" in etat:
        info = donnees["classes"].get(etat["classe"], {})
        if info.get("lanceur"):
            nb_c = int(info.get("nb_cantrips") or 0) or 2
            nb_s = int(info.get("nb_sorts_1") or 0) or 2
            cantrips = list(donnees["cantrips"].get(etat["classe"], []))
            sorts_1 = list(donnees["sorts_1"].get(etat["classe"], []))
            choix_c = _trouver_plusieurs(r, cantrips)
            choix_s = _trouver_plusieurs(r, sorts_1)
            if len(choix_c) < nb_c and cantrips:
                reste = [o for o in cantrips if o not in choix_c]
                choix_c.extend(rng.sample(reste, min(nb_c - len(choix_c), len(reste))))
                avertis.append("Sorts mineurs tirés au hasard.")
            if len(choix_s) < nb_s and sorts_1:
                reste = [o for o in sorts_1 if o not in choix_s]
                choix_s.extend(rng.sample(reste, min(nb_s - len(choix_s), len(reste))))
                avertis.append("Sorts de 1er niveau tirés au hasard.")
            etat["sorts"] = choix_c[:nb_c] + choix_s[:nb_s]

    # --- nom (étape dédiée : réponse libre, sinon tiré dans la table) ---
    elif etape == "nom":
        est_meta = (
            any(m in nr for m in ("valeurs", "standard", "points", "caract"))
            or bool(re.search(r"\b(?:for|dex|con|int|sag|cha)\b", nr))
        )
        if nr not in _OUI and nr not in _NON and nr not in _HASARD and _phrase(r) not in _HASARD and not est_meta:
            nom = re.sub(
                r"^(?:je m appelle|je m appeller|moi c est|mon nom est|appelez moi|moi je m appelle)\s+",
                "",
                r,
            ).strip()
            etat["nom"] = nom if nom else r

    return avertis


def _remplir_etape_hasard(session: dict[str, Any], etape: str) -> None:
    """Tire au hasard la seule étape demandée (sans toucher aux suivantes).

    Utilisé quand le joueur dit « au hasard » en cours d'interview : on remplit
    uniquement l'étape courante et on poursuit le tunnel, au lieu de bâcler
    toute la création d'un coup.
    """
    etat = session["etat"]
    rng = session["rng"]
    donnees = _charger()
    if etape == "classe":
        if "classe" not in etat:
            etat["classe"] = rng.choice(list(donnees["classes"]))
    elif etape == "espece":
        if "espece" not in etat:
            etat["espece"] = rng.choice(list(donnees["especes"]))
    elif etape == "genre":
        if "genre" not in etat:
            etat["genre"] = rng.choice(["Homme", "Femme"])
    elif etape == "historique":
        if "historique" not in etat:
            etat["historique"] = rng.choice(list(donnees["historiques"]))
    elif etape == "competences":
        if "competences" not in etat:
            info = donnees["classes"].get(etat.get("classe", ""), {})
            options = list(info.get("competences") or [])
            nb = int(info.get("nb_competences") or 0)
            if options and nb > 0:
                etat["competences"] = rng.sample(options, min(nb, len(options)))
    elif etape == "langues":
        if "langues" not in etat:
            commun, d12, _rares = donnees["langues"]
            etat["langues"] = [commun, rng.choice(d12)]
    elif etape == "caracteristiques":
        if "carac" not in etat:
            std = _standard_pour_classe(etat.get("classe", ""), donnees)
            etat["carac"] = models.Caracteristiques.depuis_liste(std)
    elif etape == "alignement":
        if "alignement" not in etat:
            etat["alignement"] = rng.choice(list(donnees["alignements"]))
    elif etape == "equipement":
        if "equipement" not in etat:
            info = donnees["classes"].get(etat.get("classe", ""), {})
            kit_a = list(info.get("equip_A") or [])
            kit_b = list(info.get("equip_B") or [])
            etat["equipement"] = models.Equipement(kit_a or kit_b)
    elif etape == "nom":
        if not etat.get("nom"):
            etat["nom"] = _tirer_nom(etat, rng)
    elif etape == "sorts":
        if "sorts" not in etat:
            etat["sorts"] = _choisir_sorts(session)
    # « finalisation » : rien à tirer ici, les sorts sont gérés par _finaliser.


def _remplir_au_hasard(session: dict[str, Any]) -> None:
    """Complète tout ce qui manque par des tirages aléatoires (repli global)."""
    etat = session["etat"]
    for etape in ETAPES:
        cle = "carac" if etape == "caracteristiques" else etape
        if cle not in etat or (etape == "nom" and not etat.get("nom")):
            _remplir_etape_hasard(session, etape)


# ---------------------------------------------------------------------------
# Fonctions publiques (contrat Open WebUI : retour JSON, jamais de print)
# ---------------------------------------------------------------------------


def demarrer(chat_id: str, seed: int | None = None) -> dict[str, Any]:
    """Démarre une nouvelle création de personnage.

    Si une création est déjà en cours pour ce chat, on ne repart pas de zéro :
    on repose simplement la question courante. Sans cela, un rappel de la tool
    « au hasard » faisait recommencer l'interview depuis la « classe ».
    """
    existante = _SESSIONS.get(chat_id)
    if existante is not None and not existante.get("fini"):
        return _suivant(existante)
    _SESSIONS.pop(chat_id, None)
    session = {
        "chat_id": chat_id,
        "rng": random.Random(seed) if seed is not None else random.Random(),
        "etat": {},
        "fini": False,
    }
    _SESSIONS[chat_id] = session
    return _suivant(session)


def continuer(chat_id: str, reponse: str) -> dict[str, Any]:
    """Traite la réponse du joueur, puis pose la question suivante."""
    session = _SESSIONS.get(chat_id)
    if session is None or session.get("fini"):
        return {
            "ok": False,
            "type": "erreur",
            "erreur": "Aucune création en cours : utilisez /nouveau-perso pour commencer.",
        }
    r = (reponse or "").strip()
    nr = _norme(r)
    np_ = _phrase(r)
    if np_ in _ABANDON or "abandonn" in nr or "laisse tomber" in nr:
        _SESSIONS.pop(chat_id, None)
        return {
            "ok": True,
            "type": "abandon",
            "message": "Création abandonnée. Tapez /nouveau-perso pour recommencer quand vous voulez.",
        }
    if np_ in _HASARD:
        # « au hasard » en cours d'interview : on ne tire QUE l'étape courante,
        # puis on poursuit le tunnel. (Tirer toute la fiche d'un coup sautait
        # directement à la finalisation et perturbait la création.)
        etape = _premiere_non_remplie(session["etat"])
        if etape is not None and etape != "finalisation":
            _remplir_etape_hasard(session, etape)
        avertis = ["Ce choix a été tiré au hasard."]
    elif np_ in _CONTINUE:
        # « continue » / « réessaye » : on garde ce qui est déjà retenu et on
        # passe à la suite sans rien re-remplir.
        avertis = []
    elif np_ in _RETOUR or "en arriere" in nr or "etape precedente" in nr:
        return revenir(chat_id)
    else:
        avertis = _remplir(session, r)
    return _suivant(session, avertis)


def revenir(chat_id: str) -> dict[str, Any]:
    """Revient à l'étape précédente : efface la réponse de l'étape courante et
    de TOUTES les étapes suivantes (cascade), puis re-pose la question visée.

    La cascade est nécessaire car certaines réponses dépendent de choix
    antérieurs (compétences et sorts dépendent de la classe, etc.) : en
    remonter une invalide les suivantes. On peut enchaîner plusieurs retours.
    """
    session = _SESSIONS.get(chat_id)
    if session is None or session.get("fini"):
        return {
            "ok": False,
            "type": "erreur",
            "erreur": "Aucune création en cours : utilisez /nouveau-perso pour commencer.",
        }
    etat = session["etat"]
    courante = _premiere_non_remplie(etat)
    # L'étape « courante » n'a pas encore de réponse : on recule d'une étape
    # remplie. Sinon on efface la courante (cas où elle aurait une valeur).
    idx = ETAPES.index(courante) if courante in ETAPES else len(ETAPES)
    if courante == "finalisation" or courante is None:
        idx = len(ETAPES)
    # Index de la dernière étape réellement remplie, en sautant « sorts » si la
    # classe n'est pas lanceuse (cette étape n'a jamais été remplie).
    cible = None
    for i in range(idx - 1, -1, -1):
        et = ETAPES[i]
        if et == "finalisation":
            continue
        if et == "sorts" and not _classe_lanceuse(etat):
            continue
        cle = "carac" if et == "caracteristiques" else et
        if cle in etat:
            cible = et
            break
    if cible is None:
        return {
            "ok": True,
            "type": "question",
            "etape": _premiere_non_remplie(etat) or ETAPES[0],
            "question": "Nous sommes déjà au début de la création.",
            "options": _options(_premiere_non_remplie(etat) or "classe", etat),
            "limites": _limites(_premiere_non_remplie(etat) or "classe", etat),
            "progression": None,
            "avertissements": [],
        }
    # Cascade : on retire la clé cible et toutes celles des étapes suivantes.
    cle_cible = "carac" if cible == "caracteristiques" else cible
    for et in ETAPES[ETAPES.index(cible):]:
        cle = "carac" if et == "caracteristiques" else et
        etat.pop(cle, None)
    return _suivant(session, [f"Retour à l'étape « {cible} ». Les choix suivants ont été effacés."])


def abandonner(chat_id: str) -> dict[str, Any]:
    """Interrompt la création en cours."""
    if _SESSIONS.pop(chat_id, None) is None:
        return {"ok": False, "type": "erreur", "erreur": "Aucune création en cours."}
    return {
        "ok": True,
        "type": "abandon",
        "message": "Création interrompue. Tapez /nouveau-perso pour recommencer quand vous voulez.",
    }


def lister_options(etape: str, chat_id: str = "") -> dict[str, Any]:
    """Liste les options d'une étape (si le joueur demande « quelles classes ? »)."""
    if etape not in ETAPES:
        return {"ok": False, "type": "erreur", "erreur": f"Étape inconnue : {etape}"}
    etat = _SESSIONS.get(chat_id, {}).get("etat", {}) if chat_id else {}
    return {
        "ok": True,
        "type": "options",
        "etape": etape,
        "question": _question(etape, etat),
        "options": _options(etape, etat),
    }


def personnage_final(chat_id: str) -> dict[str, Any]:
    """Clôture la création : complète ce qui manque au hasard et rend la fiche."""
    session = _SESSIONS.get(chat_id)
    if session is None or session.get("fini"):
        return {
            "ok": False,
            "type": "erreur",
            "erreur": "Aucune création en cours : utilisez /nouveau-perso pour commencer.",
        }
    return _finaliser(session)


def etat_session(chat_id: str) -> dict[str, Any]:
    """Retourne l'état courant de la création (diagnostic)."""
    session = _SESSIONS.get(chat_id)
    if session is None:
        return {"ok": False, "type": "erreur", "erreur": "Aucune création en cours."}
    return {
        "ok": True,
        "type": "etat",
        "fini": session.get("fini", False),
        "etape": _premiere_non_remplie(session["etat"]),
        "etat": {k: v for k, v in session["etat"].items() if k != "carac"},
        "carac": session["etat"].get("carac").vers_dict() if session["etat"].get("carac") else None,
    }


# ---------------------------------------------------------------------------
# Logique interne
# ---------------------------------------------------------------------------


def _options(etape: str, etat: dict[str, Any]) -> list[str]:
    """Options d'une étape (dépendantes ou non des choix précédents)."""
    donnees = _charger()
    if etape == "classe":
        return sorted(donnees["classes"])
    if etape == "espece":
        return sorted(donnees["especes"])
    if etape == "genre":
        return ["Homme", "Femme"]
    if etape == "historique":
        # Enrichit chaque historique de ses bénéfices SRD (don, compétences,
        # outil) pour que le MJ puisse les annoncer au joueur.
        resultats = []
        for nom in sorted(donnees["historiques"]):
            info = donnees["historiques"][nom]
            details = []
            if info.get("aptitude"):
                details.append(f"don {info['aptitude']}")
            if info.get("competences"):
                details.append("comp. " + ", ".join(info["competences"]))
            if info.get("outils"):
                details.append(f"outil {info['outils']}")
            resultats.append(f"{nom} ({' ; '.join(details)})" if details else nom)
        return resultats
    if etape == "competences":
        info = donnees["classes"].get(etat.get("classe", ""), {})
        return list(info.get("competences") or [])
    if etape == "sorts":
        info = donnees["classes"].get(etat.get("classe", ""), {})
        cantrips = list(donnees["cantrips"].get(etat.get("classe", ""), []))
        sorts_1 = list(donnees["sorts_1"].get(etat.get("classe", ""), []))
        opts = [f"[mineur] {c}" for c in cantrips]
        opts += [f"[1er niveau] {s}" for s in sorts_1]
        return opts
    if etape == "langues":
        _commun, d12, _rares = donnees["langues"]
        return list(d12)
    if etape == "alignement":
        return list(donnees["alignements"])
    if etape == "caracteristiques":
        return ["Valeurs standard (15 14 13 12 10 8)", "Achat de points (27 pts)"]
    if etape == "equipement":
        return _options_equipement(etat)
    return []


def _options_equipement(etat: dict[str, Any]) -> list[str]:
    """Options d'équipement détaillées (contenu des kits A et B de la classe)."""
    info = _charger()["classes"].get(etat.get("classe", ""), {})
    kit_a = list(info.get("equip_A") or [])
    kit_b = list(info.get("equip_B") or [])
    opts: list[str] = []
    if kit_a:
        opts.append("Kit A : " + ", ".join(kit_a))
    if kit_b:
        opts.append("Kit B : " + ", ".join(kit_b))
    return opts or ["Kit A (recommandé)", "Kit B (pécule)"]


def _question(etape: str, etat: dict[str, Any]) -> str:
    """Question d'une étape, enrichie du détail des kits pour l'équipement."""
    if etape == "equipement":
        info = _charger()["classes"].get(etat.get("classe", ""), {})
        kit_a = list(info.get("equip_A") or [])
        kit_b = list(info.get("equip_B") or [])
        lignes = ["Quel équipement de départ choisissez-vous ?"]
        if kit_a:
            lignes.append("— Kit A (matériel) : " + ", ".join(kit_a) + ".")
        if kit_b:
            lignes.append("— Kit B (pécule) : " + ", ".join(kit_b) + ".")
        return "\n".join(lignes)
    return _QUESTIONS[etape]


def _limites(etape: str, etat: dict[str, Any]) -> dict[str, int] | None:
    """Nombre max de choix autorisés pour une étape à sélection multiple.

    - « competences » : ``{"total": nb_competences}``.
    - « sorts » : ``{"mineur": nb_cantrips, "1er niveau": nb_sorts_1}`` (les
      options sont préfixées ``[mineur]`` / ``[1er niveau]`` ; la limite
      s'applique par groupe). ``None`` sinon (étape sans plafond).
    """
    donnees = _charger()
    info = donnees["classes"].get(etat.get("classe", ""), {})
    if etape == "competences":
        nb = int(info.get("nb_competences") or 0)
        return {"total": nb} if nb > 0 else None
    if etape == "sorts":
        return {
            "mineur": int(info.get("nb_cantrips") or 0) or 2,
            "1er niveau": int(info.get("nb_sorts_1") or 0) or 2,
        }
    return None


def _premiere_non_remplie(etat: dict[str, Any]) -> str | None:
    for etape in ETAPES:
        # L'étape « sorts » ne concerne que les lanceurs d'sorts : on la saute
        # pour les classes martiales (sinon le joueur resterait bloqué sur une
        # question que _remplir ne sait pas remplir pour lui).
        if etape == "sorts" and not _classe_lanceuse(etat):
            continue
        # Attention : l'étape « caracteristiques » est stockée sous la clé
        # « carac » (voir _remplir / _vers_personnage).
        cle = "carac" if etape == "caracteristiques" else etape
        if cle not in etat:
            return etape
    return None


def _suivant(session: dict[str, Any], avertis: list[str] | None = None) -> dict[str, Any]:
    """Pose la question de la première étape non remplie, sinon finalise."""
    etat = session["etat"]
    etape = _premiere_non_remplie(etat)
    # L'étape « finalisation » n'est qu'une question de clôture : une fois
    # toutes les autres étapes remplies, on termine (sinon on boucle à l'infini).
    if etape is None or etape == "finalisation":
        return _finaliser(session, avertis)
    if etape == "competences" and "classe" not in etat:
        # Le joueur n'a pas répondu sur la classe : on la tire au hasard.
        etat["classe"] = _tirer_classe(session)
        if avertis is None:
            avertis = []
        avertis.append("Classe tirée au hasard.")
    return {
        "ok": True,
        "type": "question",
        "etape": etape,
        "question": _question(etape, etat),
        "options": _options(etape, etat),
        "limites": _limites(etape, etat),
        "progression": f"{ETAPES.index(etape) + 1}/{len(ETAPES)}",
        "avertissements": avertis or [],
    }


def _tirer_classe(session: dict[str, Any]) -> str:
    return session["rng"].choice(sorted(_charger()["classes"]))


def _classe_lanceuse(etat: dict[str, Any]) -> bool:
    """Vrai si la classe choisie est lanceuse de sorts (peut donc choisir ses sorts)."""
    info = _charger()["classes"].get(etat.get("classe", ""), {})
    return bool(info.get("lanceur"))


def _tirer_nom(etat: dict[str, Any], rng: random.Random) -> str:
    """Tire un nom dans la table de l'espèce (repli : Humain)."""
    espece = etat.get("espece", "Humain")
    table = extract.NOMS_PAR_ESPECE.get(espece) or extract.NOMS_PAR_ESPECE["Humain"]
    return f"{rng.choice(table['prenoms'])} {rng.choice(table['noms'])}"


def _choisir_sorts(session: dict[str, Any]) -> list[str]:
    """Sorts connus à la création (lanceurs uniquement), tirés au hasard."""
    etat = session["etat"]
    rng = session["rng"]
    donnees = _charger()
    info = donnees["classes"].get(etat.get("classe", ""), {})
    if not info.get("lanceur"):
        return []
    nb_cantrips = int(info.get("nb_cantrips") or 0) or 2
    nb_sorts_1 = int(info.get("nb_sorts_1") or 0) or 2
    noms: list[str] = []
    cantrips = list(donnees["cantrips"].get(etat.get("classe", ""), []))
    if cantrips:
        noms.extend(rng.sample(cantrips, min(nb_cantrips, len(cantrips))))
    sorts_1 = list(donnees["sorts_1"].get(etat.get("classe", ""), []))
    if sorts_1:
        noms.extend(rng.sample(sorts_1, min(nb_sorts_1, len(sorts_1))))
    return noms


def _vers_personnage(etat: dict[str, Any]) -> models.Personnage:
    """Convertit l'état accumulé en `Personnage` (modèles validés)."""
    donnees = _charger()
    info_hist = donnees["historiques"].get(etat.get("historique", ""), {})
    # Bénéfices de l'historique (SRD 5.2.1) : don d'origines, maîtrise d'outil
    # et deux maîtrises de compétence, fusionnées avec celles de la classe.
    competences = list(etat.get("competences") or [])
    for comp in info_hist.get("competences") or []:
        if comp not in competences:
            competences.append(comp)
    # Équipement de l'historique (kit A recommandé), fusionné avec celui de la
    # classe, sans doublon.
    equip = list((etat.get("equipement") or models.Equipement()).objets)
    for objet in info_hist.get("equip_A") or []:
        if objet not in equip:
            equip.append(objet)
    return models.Personnage(
        nom=etat.get("nom", ""),
        espece=etat.get("espece", ""),
        genre=etat.get("genre", ""),
        classe=etat.get("classe", ""),
        historique=etat.get("historique", ""),
        alignement=etat.get("alignement", "Neutre"),
        niveau=1,
        carac=etat.get("carac") or models.Caracteristiques(),
        competences=[models.Competence(nom=c) for c in competences],
        langues=list(etat.get("langues") or ["commun"]),
        equipement=models.Equipement(equip),
        sorts=list(etat.get("sorts") or []),
        babiole=etat.get("babiole", ""),
        don=info_hist.get("aptitude", ""),
        outils=info_hist.get("outils", ""),
    )


def _finaliser(session: dict[str, Any], avertis: list[str] | None = None) -> dict[str, Any]:
    """Finalise la création : sorts, babiole, nom, puis fiche markdown."""
    etat = session["etat"]
    rng = session["rng"]
    donnees = _charger()
    avertis = list(avertis or [])

    # Sorts connus (lanceurs) : reconnaissance dans la réponse, sinon au hasard.
    if "sorts" not in etat:
        etat["sorts"] = _choisir_sorts(session)
        if etat["sorts"]:
            avertis.append("Sorts tirés au hasard.")

    # Babiole : tirage d100 dans la table du corpus.
    if "babiole" not in etat:
        table = list(donnees["babioles"])
        if table:
            tirage, nom = dice.roll_d100(table, rng)
            etat["babiole"] = nom

    # Nom : saisi libre, sinon tiré dans la table de l'espèce.
    if "nom" not in etat or not etat.get("nom"):
        etat["nom"] = _tirer_nom(etat, rng)

    p = _vers_personnage(etat)
    try:
        md_path, json_path = export.sauvegarder(p)
    except OSError as exc:
        return {
            "ok": False,
            "type": "erreur",
            "erreur": f"La sauvegarde a échoué : {exc}",
        }
    session["fini"] = True
    return {
        "ok": True,
        "type": "fiche",
        "message": "La fiche est prête. Vous pouvez encore demander des modifications.",
        "fiche": export.en_markdown(p),
        "personnage": p.vers_dict(),
        "sauvegarde": True,
        "fichier": str(json_path),
        "avertissements": avertis,
    }


# ---------------------------------------------------------------------------
# Gestion des personnages sauvegardés (contrat §5)
# ---------------------------------------------------------------------------


def _valide_nom(nom: str) -> bool:
    """Refuse les noms pouvant sortir du dossier de données (injection de chemin)."""
    return bool(nom) and "/" not in nom and "\\" not in nom and ".." not in nom


def _nom_fichier(nom: str) -> str:
    """Raccourcit un nom de personnage à sa forme « fichier » sur disque.

    `export.sauvegarder` écrit `<nom>.json` en remplaçant les espaces et les
    « / » par des tirets bas. Les requêtes peuvent arriver avec le nom tel
    qu'affiché (« Mistella Nuit Écarlate », avec espaces) : on applique la
    même transformation pour retrouver le bon fichier quel que soit le format
    reçu.
    """
    return str(nom or "").strip().replace(" ", "_").replace("/", "_") or "sans_nom"


def lister_personnages() -> dict[str, Any]:
    """Liste tous les personnages sauvegardés dans `extract.PERSO_DIR`."""
    dossier = extract.PERSO_DIR
    fichiers = sorted(dossier.glob("*.json")) if dossier.exists() else []
    personnages: list[dict[str, Any]] = []
    for fichier in fichiers:
        try:
            d = json.loads(fichier.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        personnages.append(
            {
                "nom": fichier.stem,
                "espece": str(d.get("espece", "")),
                "classe": str(d.get("classe", "")),
                "niveau": int(d.get("niveau", 1)),
                "modifie_le": datetime.fromtimestamp(fichier.stat().st_mtime).isoformat(
                    sep=" ", timespec="seconds"
                ),
            }
        )
    return {
        "ok": True,
        "type": "liste",
        "message": f"{len(personnages)} personnage(s) disponible(s).",
        "personnages": personnages,
    }


def charger_personnage(nom: str) -> dict[str, Any]:
    """Charge un personnage sauvegardé : fiche markdown + dict complet."""
    if not _valide_nom(nom):
        return {"ok": False, "type": "erreur", "erreur": f"Nom invalide : {nom}"}
    chemin = extract.PERSO_DIR / f"{_nom_fichier(nom)}.json"
    if not chemin.exists():
        return {"ok": False, "type": "erreur", "erreur": f"Personnage introuvable : {nom}"}
    try:
        d = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "type": "erreur", "erreur": f"Fiche illisible : {exc}"}
    p = models.Personnage.depuis_dict(d)
    return {
        "ok": True,
        "type": "personnage",
        "message": f"Personnage chargé : {p.nom}.",
        "fiche": export.en_markdown(p),
        "personnage": p.vers_dict(),
        "modifie_le": datetime.fromtimestamp(chemin.stat().st_mtime).isoformat(
            sep=" ", timespec="seconds"
        ),
    }


def _retirer_objet(
    p: models.Personnage, objet: str, quantite: int | None = None
) -> str | None:
    """Retire de l'inventaire l'objet désigné par `objet` (tolérant aux accents,
    à la casse et aux formulations partielles). Renvoie une phrase décrivant le
    changement, ou None si aucun objet ne correspond (ou ambiguïté).

    Le joueur nomme souvent un objet par un surnom ou un fragment (« le bocal »,
    « la graisse de griffon ») alors que l'inventaire porte un libellé long
    (« Bocal en verre renfermant du lard, avec l'étiquette « Graisse de
    griffon » »). On apparie donc par : égalité exacte, puis mot-à-mot, puis
    sous-chaîne (dans un sens ou l'autre). Si plusieurs objets se disputent la
    même correspondance, on ne devine pas : on renvoie None (le MJ précise).

    `quantite` (optionnel) : pour une **pile comptée** (« 20 flèches »), on
    décrémente le compteur au lieu de supprimer l'entrée (« 20 flèches » →
    « 15 flèches » pour 5 retirés) ; si la quantité atteint le total, l'entrée
    disparaît. Sans `quantite`, on retire l'entrée entière. Le nom peut être
    préfixé d'un nombre (« 5 flèches ») : il est alors lu comme la quantité.
    """
    objets = p.equipement.objets
    # Le MJ/joueur peut préfixer le nom d'une quantité (« 5 flèches ») : on la
    # sépare pour apparier sur le seul nom, et on l'emploie comme quantité si
    # `quantite` n'est pas fourni séparément.
    demande = objet
    m = re.match(r"^\s*(\d+)\s+(.*)$", objet)
    if m:
        demande = m.group(2)
        if quantite is None:
            quantite = int(m.group(1))
    demande = _norme(demande)
    if not demande:
        return None

    def score(entree: str) -> int:
        e = _norme(entree)
        # On apparie aussi sur le nom sans son compteur (« 20 flèches » -> « fleches »).
        e_nom = re.sub(r"^\s*\d+\s+", "", e)
        if e == demande or e_nom == demande:
            return 3
        if re.search(r"\b" + re.escape(demande) + r"\b", e) or re.search(
            r"\b" + re.escape(demande) + r"\b", e_nom
        ):
            return 2
        if demande in e or e in demande or demande in e_nom or e_nom in demande:
            return 1
        return 0

    meilleurs = [(score(o), i) for i, o in enumerate(objets)]
    meilleurs = [(s, i) for (s, i) in meilleurs if s > 0]
    if not meilleurs:
        return None
    meilleur = max(s for s, _ in meilleurs)
    candidats = [i for s, i in meilleurs if s == meilleur]
    if len(candidats) > 1:
        # Plusieurs objets correspondent aussi bien : on refuse de trancher.
        return None
    idx = candidats[0]
    entree = objets[idx]

    if quantite is not None:
        em = re.match(r"^\s*(\d+)\s+(.*)$", entree)
        if em:  # pile comptée (« 20 flèches ») : on décrémente le compteur.
            total = int(em.group(1))
            libelle = em.group(2)
            if quantite >= total:
                objets.pop(idx)
                return f"{entree} retiré en totalité (0 restant)"
            reste = total - quantite
            objets[idx] = f"{reste} {libelle}"
            return f"{quantite} {libelle} retirés → {reste} restants"
        # Objet non compté : impossible d'en retirer une partie → on retire tout.
    objets.pop(idx)
    return f"objet retiré : {entree}"


def modifier_personnage(nom: str, actions: list[dict]) -> dict[str, Any]:
    """Applique une liste d'actions closes à un personnage sauvegardé (contrat §5).

    Actions acceptées : soigner, degats, ajouter_or, ajouter_objet, retirer_objet,
    apprendre_sort, gagner_xp, changer_alignement.
    Toute action inconnue fait échouer la requête (aucune modification partielle).
    """
    if not _valide_nom(nom):
        return {"ok": False, "type": "erreur", "erreur": f"Nom invalide : {nom}"}
    chemin = extract.PERSO_DIR / f"{_nom_fichier(nom)}.json"
    if not chemin.exists():
        return {"ok": False, "type": "erreur", "erreur": f"Personnage introuvable : {nom}"}
    try:
        d = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"ok": False, "type": "erreur", "erreur": f"Fiche illisible : {exc}"}
    p = models.Personnage.depuis_dict(d)
    modifications: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            return {"ok": False, "type": "erreur", "erreur": f"Action invalide : {action!r}"}
        nom_action = str(action.get("action", ""))
        valeur = action.get("valeur")
        if nom_action == "soigner":
            try:
                v = int(valeur)
            except (TypeError, ValueError):
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            if v <= 0:
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            max_pv = p.de_vie + p.carac.mod_con()
            avant = p.pv
            p.pv_actuels = min(avant + v, max_pv)
            modifications.append(f"soigné de {p.pv - avant} PV ({p.pv}/{max_pv})")
        elif nom_action == "degats":
            try:
                v = int(valeur)
            except (TypeError, ValueError):
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            if v <= 0:
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            critique = bool(action.get("critique", False))
            degat = v * 2 if critique else v
            avant = p.pv
            p.pv_actuels = max(avant - degat, 0)
            modifications.append(f"{degat} dégâts encaissés ({p.pv} PV restants)")
            if p.pv == 0:
                modifications.append("Le personnage est à la mort (0 PV).")
        elif nom_action == "ajouter_or":
            try:
                v = int(valeur)
            except (TypeError, ValueError):
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            if v <= 0:
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            for i, obj in enumerate(p.equipement.objets):
                m = re.match(r"^(\d+)\s*po$", obj.strip())
                if m:
                    total = int(m.group(1)) + v
                    p.equipement.objets[i] = f"{total} po"
                    modifications.append(f"or porté à {total} po")
                    break
            else:
                p.equipement.objets.append(f"{v} po")
                modifications.append(f"{v} po ajoutés")
        elif nom_action == "ajouter_objet":
            objet = str(valeur or "").strip()
            if not objet:
                return {"ok": False, "type": "erreur", "erreur": "Valeur invalide : objet manquant."}
            p.equipement.objets.append(objet)
            modifications.append(f"objet ajouté : {objet}")
        elif nom_action == "retirer_objet":
            objet = str(valeur or "").strip()
            if not objet:
                return {"ok": False, "type": "erreur", "erreur": "Valeur invalide : objet manquant."}
            quantite = action.get("quantite")
            if quantite is not None:
                try:
                    quantite = int(quantite)
                except (TypeError, ValueError):
                    return {"ok": False, "type": "erreur", "erreur": f"Quantité invalide : {quantite}"}
                if quantite <= 0:
                    return {"ok": False, "type": "erreur", "erreur": f"Quantité invalide : {quantite}"}
            retire = _retirer_objet(p, objet, quantite)
            if retire is None:
                inventaire = ", ".join(p.equipement.objets) or "(inventaire vide)"
                return {
                    "ok": False,
                    "type": "erreur",
                    "erreur": f"Objet introuvable dans l'inventaire : « {objet} ». "
                    f"Inventaire actuel : {inventaire}.",
                }
            modifications.append(retire)
        elif nom_action == "apprendre_sort":
            sort = str(valeur or "").strip()
            if not sort:
                return {"ok": False, "type": "erreur", "erreur": "Valeur invalide : sort manquant."}
            p.sorts.append(sort)
            modifications.append(f"sort appris : {sort}")
        elif nom_action == "gagner_xp":
            try:
                v = int(valeur)
            except (TypeError, ValueError):
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            if v <= 0:
                return {"ok": False, "type": "erreur", "erreur": f"Valeur invalide : {valeur}"}
            p.xp += v
            modifications.append(f"{v} XP gagnés (total : {p.xp})")
            while p.niveau < len(PALIERS_XP) and p.xp >= PALIERS_XP[p.niveau]:
                p.niveau += 1
                modifications.append(f"niveau atteint : {p.niveau}")
        elif nom_action == "changer_alignement":
            alignement = str(valeur or "").strip()
            if not alignement:
                return {"ok": False, "type": "erreur", "erreur": "Valeur invalide : alignement manquant."}
            p.alignement = alignement
            modifications.append(f"alignement changé : {alignement}")
        else:
            return {"ok": False, "type": "erreur", "erreur": f"Action inconnue : {nom_action}"}
    export.sauvegarder(p)
    return {
        "ok": True,
        "type": "personnage",
        "message": "Personnage mis à jour.",
        "fiche": export.en_markdown(p),
        "personnage": p.vers_dict(),
        "modifications": modifications,
    }


def supprimer_personnage(nom: str) -> dict[str, Any]:
    """Supprime un personnage sauvegardé (fichiers .json et .md)."""
    if not _valide_nom(nom):
        return {"ok": False, "type": "erreur", "erreur": f"Nom invalide : {nom}"}
    nom_fichier = _nom_fichier(nom)
    json_path = extract.PERSO_DIR / f"{nom_fichier}.json"
    if not json_path.exists():
        return {"ok": False, "type": "erreur", "erreur": f"Personnage introuvable : {nom}"}
    json_path.unlink()
    (extract.PERSO_DIR / f"{nom_fichier}.md").unlink(missing_ok=True)
    return {"ok": True, "type": "supprime", "message": f"Personnage supprimé : {nom}"}


__all__ = [
    "demarrer",
    "continuer",
    "abandonner",
    "personnage_final",
    "lister_options",
    "etat_session",
    "lister_personnages",
    "charger_personnage",
    "modifier_personnage",
    "supprimer_personnage",
]
