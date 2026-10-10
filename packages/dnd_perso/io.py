"""Menus interactifs en français pour la création de personnage.

Chaque question est tolérante :

- l'utilisateur peut taper un numéro, un nom, ou valider à vide (Entrée)
  pour laisser le hasard décider ;
- en mode ``auto`` (``--auto``), plus aucune question n'est posée : tout
  est tiré au hasard dans le corpus (générateur injecté, reproductible
  via ``--seed``).

Ce module n'utilise que la bibliothèque standard.
"""

from __future__ import annotations

import random
from typing import Callable

from . import dice
from . import extract

# Fonction d'entrée injectable (pour les tests / non-interactif).
_input: Callable[[str], str] = input


def _saisie(prompt: str = "> ") -> str:
    """Lit une ligne, tolérante à Ctrl-D / Ctrl-C (retourne alors "")."""
    try:
        return _input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _norme(texte: str) -> str:
    """Clé de comparaison tolérante : minuscules, sans accents."""
    out = []
    for ch in texte.lower():
        if "à" <= ch <= "ÿ":
            # table d'accents courants -> lettre de base
            base = {
                "à": "a", "â": "a", "ä": "a",
                "è": "e", "é": "e", "ê": "e", "ë": "e",
                "ì": "i", "î": "i", "ï": "i",
                "ò": "o", "ô": "o", "ö": "o",
                "ù": "u", "û": "u", "ü": "u",
                "ç": "c", "ÿ": "y",
            }.get(ch, ch)
            out.append(base)
        else:
            out.append(ch)
    return "".join(out)


def _menu(
    titre: str,
    options: list[str],
    rng: random.Random,
    auto: bool,
    detail: dict[str, str] | None = None,
) -> str:
    """Menu numéroté à choix unique. Entrée = hasard. Tolérant en noms."""
    if auto:
        choix = rng.choice(options)
        print(f"{titre} : {choix} (tirage automatique)")
        return choix
    print(f"\n{titre}")
    for i, opt in enumerate(options, 1):
        extra = f" — {detail[opt]}" if detail and opt in detail else ""
        print(f"  {i:>2}) {opt}{extra}")
    print("   Entrée = au hasard")
    while True:
        saisie = _saisie()
        if not saisie:
            return rng.choice(options)
        if saisie.isdigit() and 1 <= int(saisie) <= len(options):
            return options[int(saisie) - 1]
        cible = _norme(saisie)
        for opt in options:
            if _norme(opt) == cible:
                return opt
        print("Réponse non comprise : tapez un numéro, un nom, ou Entrée.")


def _menu_multi(
    titre: str,
    options: list[str],
    nb: int,
    rng: random.Random,
    auto: bool,
    detail: dict[str, str] | None = None,
) -> list[str]:
    """Menu de ``nb`` choix distincts (un par question). Entrée = hasard."""
    if auto:
        choix = rng.sample(options, min(nb, len(options)))
        print(f"{titre} : {', '.join(choix)} (tirage automatique)")
        return choix
    mot = "sort(s)" if "sort" in titre.lower() else "compétence(s)"
    print(f"\n{titre} ({nb} {mot} à choisir)")
    reste = list(options)
    choisies: list[str] = []
    for i in range(nb):
        print(f"— choix {i + 1}/{nb} —")
        c = _menu("", reste, rng, auto, detail)
        choisies.append(c)
        reste = [o for o in reste if o != c]
        if not reste:
            break
    return choisies


# ---------------------------------------------------------------------------
# Questions par étape
# ---------------------------------------------------------------------------

def demander_classe(
    classes: dict[str, dict], rng: random.Random, auto: bool
) -> str:
    """Choix de la classe, avec l'aperçu (domaine, carac, complexité)."""
    noms = sorted(classes)
    detail = {
        nom: f"{info.get('predilection', '')} · {info.get('carac', '')}"
        for nom, info in classes.items()
    }
    return _menu("Choisissez une classe", noms, rng, auto, detail)


def demander_competences(
    options: list[str], nb: int, rng: random.Random, auto: bool
) -> list[str]:
    """Compétences de départ, choisies dans la liste de la classe."""
    return _menu_multi(
        "Compétences de départ", options, nb, rng, auto,
        extract.DESCRIPTIONS_COMPETENCES,
    )


def demander_equipement(
    kit_a: list[str], kit_b: list[str], rng: random.Random, auto: bool
) -> list[str]:
    """Équipement de départ : kit A (matériel prêt à l'emploi) ou kit B (pécule)."""
    if auto or not kit_b:
        objets = kit_a if kit_a else kit_b
        if kit_a:
            print(f"Équipement : kit A, matériel prêt à l'emploi ({', '.join(objets)})")
        else:
            print("Équipement : kit B, pécule à dépenser en ville (à acheter plus tard)")
        return list(objets)
    detail = {
        "Kit A (recommandé)": (
            "le matériel recommandé pour la classe, déjà choisi pour vous : "
            + ", ".join(kit_a)
        ),
        "Kit B (pécule)": (
            "une bourse d'or ("
            + ", ".join(kit_b)
            + ") à dépenser plus tard chez un marchand pour composer votre équipement"
        ),
    }
    choix = _menu(
        "Équipement de départ (les deux kits sont équivalents, choisissez selon vos goûts) :",
        ["Kit A (recommandé)", "Kit B (pécule)"],
        rng, auto, detail,
    )
    return list(kit_a if choix.startswith("Kit A") else kit_b)


def demander_espece(
    especes: dict[str, dict], rng: random.Random, auto: bool
) -> str:
    """Choix de l'espèce (les traits sont appliqués plus tard)."""
    return _menu(
        "Choisissez une espèce", sorted(especes), rng, auto,
        extract.DESCRIPTIONS_ESPECES,
    )


def demander_historique(
    historiques: dict[str, dict], rng: random.Random, auto: bool
) -> str:
    """Choix de l'historique."""
    return _menu(
        "Choisissez un historique", sorted(historiques), rng, auto,
        extract.DESCRIPTIONS_HISTORIQUES,
    )


def demander_alignement(
    alignements: list[str], rng: random.Random, auto: bool
) -> str:
    """Choix de l'alignement (9 options)."""
    return _menu(
        "Choisissez un alignement", list(alignements), rng, auto,
        extract.DESCRIPTIONS_ALIGNEMENTS,
    )


def demander_langues(
    langues: tuple[str, list[str], list[str]], rng: random.Random, auto: bool
) -> list[str]:
    """Langues connues : le commun + une langue au d12 (variante rare)."""
    commun, d12, rares = langues
    if auto:
        langue = rng.choice(d12)
        print(f"Langue : {commun}, {langue} (tirage automatique)")
        return [commun, langue]
    print(f"\nVous connaissez le {commun}.")
    langue = _menu(
        "Choisissez une langue supplémentaire (d12)", d12, rng, auto,
        extract.DESCRIPTIONS_LANGUES,
    )
    langues_connues = [commun, langue]
    # Variante : une langue rare, facultative.
    saisie = _saisie("Langue rare (variante) ? o/N : ")
    if _norme(saisie) in ("o", "oui", "y", "yes"):
        langues_connues.append(
            _menu("Langue rare :", rares, rng, auto, extract.DESCRIPTIONS_LANGUES)
        )
    return langues_connues


def demander_carac_valeurs(
    valeurs_defaut: list[int], rng: random.Random, auto: bool
) -> list[int]:
    """Caractéristiques : valeurs optimisées pour la classe (défaut) ou achat de points."""
    if auto:
        valeurs = list(valeurs_defaut)
        print(f"Caractéristiques : {valeurs} (standard, tirage automatique)")
        return valeurs
    meth = _menu(
        "Méthode de génération des caractéristiques :",
        ["Valeurs standard (optimisées pour la classe)", "Achat de points (27 pts)"],
        rng,
        auto,
    )
    if meth.startswith("Valeurs"):
        return list(valeurs_defaut)
    # Achat de points : 6 valeurs saisies, vérifiées.
    while True:
        saisie = _saisie("Tapez 6 valeurs (8-15) séparées par des espaces, Entrée = valeurs standard : ")
        if not saisie:
            return list(valeurs_defaut)
        try:
            vals = [int(x) for x in saisie.replace(",", " ").split()]
        except ValueError:
            print("Il faut des nombres entiers, par exemple : 15 14 13 12 10 8")
            continue
        if len(vals) != 6:
            print("Il faut exactement six valeurs.")
            continue
        if any(v < 8 or v > 15 for v in vals):
            print("Chaque valeur doit être comprise entre 8 et 15.")
            continue
        cout = sum(extract.COUT_ACHAT.get(v, 99) for v in vals)
        if cout > 27:
            print(f"Budget dépassé ({cout} pts sur 27). Réessayez ou Entrée = standard.")
            continue
        return vals


def demander_sorts(
    sorts: list[str], nb: int, rng: random.Random, auto: bool
) -> list[str]:
    """Sorts connus : nb choix distincts dans la liste de sorts."""
    return _menu_multi(
        "Choisissez vos sorts", list(sorts), nb, rng, auto,
        extract.charger_descriptions_sorts(),
    )


def tirer_babiole(babioles: list[tuple[int, str]], rng: random.Random) -> str:
    """Babiole : tirage d100 dans la table (aucune question)."""
    tirage, nom = dice.roll_d100(babioles, rng)
    print(f"Babiole (d100 = {tirage}) : {nom}")
    return nom


def demander_nom(espece: str, rng: random.Random, auto: bool) -> str:
    """Nom du personnage : 10 noms adaptés à l'espèce sont proposés."""
    table = extract.NOMS_PAR_ESPECE.get(espece) or extract.NOMS_PAR_ESPECE["Humain"]
    # 10 propositions de noms complets, tirées au hasard dans la table.
    k = min(10, len(table["prenoms"]), len(table["noms"]))
    prenoms = rng.sample(table["prenoms"], k)
    noms = rng.sample(table["noms"], k)
    propositions = [f"{p} {n}" for p, n in zip(prenoms, noms)]
    if auto:
        full = propositions[0]
        print(f"Nom : {full} (tirage automatique)")
        return full
    print("\nChoisissez un nom (ou tapez le vôtre) :")
    for i, proposition in enumerate(propositions, 1):
        print(f"  {i:>2}) {proposition}")
    print("   Entrée = au hasard")
    while True:
        saisie = _saisie()
        if not saisie:
            return rng.choice(propositions)
        if saisie.isdigit() and 1 <= int(saisie) <= len(propositions):
            return propositions[int(saisie) - 1]
        if len(saisie) >= 2:
            return saisie
        print("Réponse non comprise : tapez un numéro, un nom, ou Entrée.")


# Ré-exports pratiques pour l'appelant.
__all__ = [
    "demander_classe",
    "demander_competences",
    "demander_equipement",
    "demander_espece",
    "demander_historique",
    "demander_alignement",
    "demander_langues",
    "demander_carac_valeurs",
    "demander_sorts",
    "tirer_babiole",
    "demander_nom",
]
