"""Outils exposés à l'agent Pydantic-AI (le « cerveau règles »).

Chaque outil est un mince wrapper qui appelle **en-process** la fonction de
route correspondante de `jdr_api.routers.*` (déjà testée, contrat v1). On passe
la clé interne pour satisfaire `autorise()`. Le LLM ne calcule jamais rien : il
choisit l'outil et ses arguments, le moteur renvoie du JSON.

Ces wrappers remplacent `openui/tools/dnd_perso_tool.py` (la tool OWUI qui
passait par HTTP). Ici plus de HTTP interne : appel direct, mêmes fonctions.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext

from jdr_api.routers import campagne as r_campagne
from jdr_api.routers import combat as r_combat
from jdr_api.routers import creation as r_creation
from jdr_api.routers import personnages as r_perso
from dnd_perso import variete
from settings import settings


@dataclass
class Deps:
    """Déps d'exécution de l'agent. `chat_id` = clé de session de création ;
    `campagne_id` = campagne/scénario actif choisi par le joueur (ancre le MJ) ;
    `hint_mode` = mode débutant (le MJ glisse une piste en prose à chaque tour) ;
    `demande_indice` = demande ponctuelle d'une piste pour CE tour seulement."""

    chat_id: str = "defaut"
    campagne_id: str = ""
    hint_mode: bool = False
    demande_indice: bool = False


# Clé interne : les routes appellent autorise(); on la fournit pour le mode interne.
_CLE = settings.dnd_api_key or None


def _ctx_chat(ctx: RunContext[Deps]) -> str:
    return ctx.deps.chat_id or "defaut"


# ─── Création guidée ────────────────────────────────────────────────────────

def nouveau_personnage(ctx: RunContext[Deps], choix: str = "") -> dict[str, Any]:
    """Créer un nouveau personnage D&D 5.2.1 (SRD) via une interview guidée étape
    par étape (classe, espèce, historique, compétences, langues, caractéristiques,
    alignement, équipement, sorts, nom).

    Passer la réponse du joueur EXACTEMENT mot pour mot dans `choix` (sans la
    reformuler). Laisser vide pour démarrer. Relayer au joueur la question et les
    options renvoyées, puis attendre sa réponse avant de rappeler l'outil. Quand
    `type == "fiche"`, la fiche est déjà sauvegardée : l'afficher telle quelle.
    """
    chat_id = _ctx_chat(ctx)
    if not choix:
        return r_creation.demarrer_creation({"chat_id": chat_id}, _CLE)
    return r_creation.repondre(chat_id, {"reponse": choix}, _CLE)


def lister_les_options(ctx: RunContext[Deps], etape: str) -> dict[str, Any]:
    """Lister les options d'une étape de création (« classe », « espece »,
    « historique », « competences », « langues », « alignement », « equipement »,
    « sorts »)."""
    return r_creation.options(_ctx_chat(ctx), etape, _CLE)


def abandonner_la_creation(ctx: RunContext[Deps]) -> dict[str, Any]:
    """Interrompre la création de personnage en cours (joueur qui veut arrêter)."""
    return r_creation.abandonner(_ctx_chat(ctx), _CLE)


# ─── Personnages ──────────────────────────────────────────────────────────────

def lister_les_personnages() -> dict[str, Any]:
    """Lister tous les personnages sauvegardés (seule source des PJ jouables)."""
    return r_perso.lister_personnages(_CLE)


def charger_le_personnage(nom: str) -> dict[str, Any]:
    """Charger la fiche complète d'un personnage sauvegardé (PV, or, inventaire,
    sorts, XP, section « Bonus des jets »). À appeler avant d'annoncer un bonus."""
    return r_perso.charger_personnage(nom, _CLE)


def modifier_le_personnage(nom: str, actions: list[dict]) -> dict[str, Any]:
    """Appliquer des modifications à un personnage (soins, dégâts, or, objets,
    sorts, emplacements, XP, alignement) et renvoyer la fiche mise à jour.

    Actions acceptées : `soigner`, `degats` (option `critique`), `ajouter_or`,
    `ajouter_objet`, `retirer_objet`, `apprendre_sort`, `lancer_sort`,
    `repos_long`, `gagner_xp`, `changer_alignement`.
    Ex. `[{"action": "soigner", "valeur": 5}, {"action": "ajouter_or", "valeur": 50}]`.

    `lancer_sort` **consomme un emplacement de sort** : passe le nom du sort
    (`"valeur"`), éventuellement `"niveau": N` (0 = tour de magie, jamais
    consommé). Le niveau est sinon lu dans le corpus. La fiche du personnage
    porte une section `## Emplacements de sort` (restants/max par niveau) :
    **appelle `lancer_sort` à chaque sort lancé** (sauf un tour de magie), sinon
    les emplacements ne diminuent jamais. Si la réponse est une erreur
    « Plus d'emplacement », le sort ne peut pas être lancé — le dire au joueur.
    `repos_long` restaure **tous** les emplacements (à appeler après un repos
    long en fiction).

    `retirer_objet` enlève un objet de l'inventaire (joueur qui jette, perd,
    casse, donne ou consomme un objet) — passe le nom tel que le joueur le nomme
    (« graisse de griffon », « le bocal ») : la correspondance est tolérante.
    Pour une **pile comptée** (« 20 flèches », « 4 hachettes »), passe
    `"quantite": N` pour n'en retirer que N (« 20 flèches » → « 15 flèches »
    pour `quantite: 5`) ; sans `quantite`, tout l'objet est retiré. Tu peux aussi
    préfixer le nom (« valeur": "5 flèches" »).
    IMPORTANT : dès qu'un objet (ou une partie d'une pile) quitte la fiche du
    personnage en fiction, appelle cette action pour mettre l'inventaire à jour,
    sinon il reste à tort au même montant et réapparaîtra.
    """
    return r_perso.modifier_personnage(nom, {"actions": actions}, _CLE)


def supprimer_le_personnage(nom: str) -> dict[str, Any]:
    """Supprimer définitivement un personnage. Demander au joueur de confirmer le
    nom exact (appeler d'abord `lister_les_personnages` en cas de doute)."""
    return r_perso.supprimer_personnage(nom, _CLE)


# ─── Combat ─────────────────────────────────────────────────────────────────

def ouvrir_un_combat(
    ctx: RunContext[Deps],
    combattants: list[dict],
    titre: str = "",
    combat_id: str = "",
    lieu: str = "",
) -> dict[str, Any]:
    """Ouvrir une rencontre : le serveur lance TOUTES les initiatives (d20 + bonus)
    et renvoie l'ordre de jeu.

    Un PJ : `{"type":"pj","nom":"<nom exact de la fiche>"}`. Un monstre :
    `{"type":"monstre","nom":...,"pv":7,"ca":15,"attaque":4,"degats":"1d6+2",
    "mod_degats":0,"init_bonus":2,"nb":2}`. Les stats du monstre viennent de sa
    fiche SRD (jamais inventées). `nb` crée plusieurs exemplaires. ≥ 2 combattants.

    `lieu` : le **nom exact du lieu** de la campagne où se déroule le combat. Le
    serveur n'autorise un affrontement que dans une **zone dangereuse** (un lieu du
    scénario portant une `rencontre` planifiée) et refuse si les monstres ou leur
    effectif ne correspondent pas à cette rencontre. **Ne jamais faire apparaître
    d'ennemis dans une zone sûre** : si le lieu n'a pas de `rencontre`, raconte la
    scène sans combat (ou déclare d'abord une rencontre via `ecrire_le_scenario`).

    La rencontre est automatiquement rattachée à la campagne active : supprimer
    cette campagne supprimera aussi ce combat.
    """
    corps: dict[str, Any] = {"combattants": combattants}
    if titre:
        corps["titre"] = titre
    if combat_id:
        corps["id"] = combat_id
    if lieu:
        corps["lieu"] = lieu
    campagne_id = ctx.deps.campagne_id if ctx and ctx.deps else ""
    if campagne_id:
        corps["campagne_id"] = campagne_id
    return r_combat.ouvrir(corps, _CLE)


def etat_du_combat(combat_id: str) -> dict[str, Any]:
    """Renvoyer l'état d'une rencontre : ordre d'initiative, tour, qui joue, PV/CA/
    conditions de chaque combattant."""
    return r_combat.etat(combat_id, _CLE)


def lancer_le_jet_d_un_monstre(
    combat_id: str, attaquant: str, cible: str
) -> dict[str, Any]:
    """Le SERVEUR lance le d20 d'attaque + dégâts d'un MONSTRE contre une cible,
    gère critique/maladresse, touche vs CA, et répercute les dégâts sur la fiche du
    PJ touché. Réservé aux monstres. `attaquant`/`cible` = champs « cle » de l'ordre."""
    return r_combat.jet_monstre(
        combat_id, {"attaquant": attaquant, "cible": cible}, _CLE
    )


def enregistrer_le_jet_du_joueur(
    combat_id: str, attaquant: str, cible: str, de_attaque: int, de_degats: int = 0
) -> dict[str, Any]:
    """Enregistrer le jet ANNONCÉ PAR LE JOUEUR (le serveur ne lance pas son d20).
    `de_attaque` = le d20 naturel du joueur (1-20). `de_degats` = total annoncé
    (0 pour laisser le moteur lancer). Le serveur compare à la CA, gère critique
    (nat 20) / maladresse (nat 1), calcule les dégâts et met à jour les PV."""
    corps: dict[str, Any] = {
        "attaquant": attaquant,
        "cible": cible,
        "de_attaque": de_attaque,
    }
    if de_degats:
        corps["de_degats"] = de_degats
    return r_combat.jet_joueur(combat_id, corps, _CLE)


def tour_suivant_du_combat(combat_id: str) -> dict[str, Any]:
    """Avancer d'une case dans l'ordre d'initiative (saute les hors-combat) et
    renvoyer qui joue maintenant (champ « actif »)."""
    return r_combat.tour_suivant(combat_id, _CLE)


def _normaliser(texte: str) -> str:
    """Clé de comparaison : minuscule et sans accents."""
    t = unicodedata.normalize("NFD", texte.lower().strip())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def enregistrer_le_jet_hors_combat(
    nom: str, jet: str, dd: int, de_naturel: int
) -> dict[str, Any]:
    """Enregistrer et résoudre un JET DE COMPÉTENCE / SAUVEGARDE HORS COMBAT.

    Le SERVEUR calcule tout : il relit le **bonus déjà calculé** du personnage
    (section `jets` de sa fiche), additionne le d20 **annoncé par le joueur**, et
    compare au DD. **Tu ne lances jamais ce dé toi-même et tu n'écris jamais le
    total ou le résultat.** Le joueur lance son d20 et te donne le dé NATUREL
    (1-20) ; tu passes ce dé ici, puis tu racontes la conséquence à partir du
    JSON renvoyé (`total`, `reussite`).

    - `nom` : nom exact du personnage (fiche).
    - `jet` : la compétence (« Investigation », « Perception », « Persuasion »…)
      ou la sauvegarde (« Sagesse », « Dextérité »…). Le bonus correspondant est
      lu dans la fiche — ne le calcule jamais.
    - `dd` : la difficulté que TU fixes en secret (jamais révélée avant le jet).
    - `de_naturel` : le d20 naturel annoncé par le joueur (1-20).

    Nat 20 = réussite automatique, nat 1 = échec automatique (règle du d20).
    Renvoie `{ok, jet, bonus, de_naturel, total, dd, reussite}`.
    """
    fiche = r_perso.charger_personnage(nom, _CLE)
    if not fiche.get("ok"):
        return fiche
    jets = (fiche.get("personnage") or {}).get("jets") or {}
    competences = jets.get("competences") or {}
    sauvegardes = jets.get("sauvegardes") or {}

    cle = _normaliser(jet)
    bonus = type_jet = None
    for source, etiquette in ((competences, "competence"), (sauvegardes, "sauvegarde")):
        for nom_jet, val in source.items():
            if _normaliser(nom_jet) == cle:
                bonus, type_jet = val, etiquette
                break
        if bonus is not None:
            break
    # Repli tolérant : correspondance par sous-chaîne (ex. « sagesse » -> « Sagesse »).
    if bonus is None:
        for source, etiquette in ((competences, "competence"), (sauvegardes, "sauvegarde")):
            for nom_jet, val in source.items():
                if cle and (cle in _normaliser(nom_jet) or _normaliser(nom_jet) in cle):
                    bonus, type_jet = val, etiquette
                    break
            if bonus is not None:
                break
    if bonus is None:
        valides = sorted(list(competences) + list(sauvegardes))
        return {
            "ok": False,
            "type": "erreur",
            "erreur": f"Jet inconnu : « {jet} ». Choisis un nom parmi : {', '.join(valides)}.",
        }

    de = int(de_naturel)
    total = de + int(bonus)
    if de == 20:
        reussite = True
    elif de == 1:
        reussite = False
    else:
        reussite = total >= int(dd)
    return {
        "ok": True,
        "type": "jet_hors_combat",
        "jet": jet,
        "categorie": type_jet,
        "bonus": int(bonus),
        "de_naturel": de,
        "total": total,
        "reussite": reussite,
        # La difficulté (`dd`) n'est PAS renvoyée : le MJ la connaît déjà (c'est
        # lui qui l'a fixée) et la recopier l'incitait à l'énoncer (« vs DD 15 »),
        # ce qui la révèle au joueur. On ne lui rend que le strict nécessaire pour
        # raconter : le total et la réussite.
        "message": f"{jet} : d20 {de} {'+' if bonus >= 0 else '−'} {abs(int(bonus))} "
        f"= {total} → {'réussite' if reussite else 'échec'}.",
    }


def appliquer_au_combat(
    combat_id: str, cle: str, action: str, valeur: int
) -> dict[str, Any]:
    """Appliquer dégâts / soins / condition à un combattant (`action` ∈ `degats`,
    `soigner`, `condition`). Pour un PJ, la valeur est aussi répercutée sur sa fiche."""
    return r_combat.modifier(
        combat_id, {"cle": cle, "action": action, "valeur": valeur}, _CLE
    )


def clore_le_combat(combat_id: str) -> dict[str, Any]:
    """Clôturer une rencontre (camp vaincu, fuite, reddition, fin de scène)."""
    return r_combat.cloturer(combat_id, _CLE)


# ─── Campagne / scénario ──────────────────────────────────────────────────────

def lister_les_campagnes() -> dict[str, Any]:
    """Lister les campagnes/scénarios suivis (seule source des scénarios existants)."""
    return r_campagne.lister(_CLE)


def etat_de_la_campagne(campagne_id: str) -> dict[str, Any]:
    """Relire l'état d'une campagne : phase, PNJ et attitudes, crochets et statuts,
    lieux, indices, récompenses, chronologie. À appeler en cas de doute."""
    return r_campagne.etat(campagne_id, _CLE)


def ecrire_le_scenario(
    campagne_id: str,
    titre: str = "",
    synopsis: str = "",
    accroche: str = "",
    enjeux: str = "",
    motivations: str = "",
    danger: str = "",
    pnj: list[dict] | None = None,
    defis: list[dict] | None = None,
    crochets: list[dict] | None = None,
    lieux: list[dict] | None = None,
    blocs: list[dict] | None = None,
) -> dict[str, Any]:
    """Écrire / mettre à jour la **trame** d'une campagne déjà ouverte. C'est l'outil
    qui **persiste le scénario** que tu conçois (sinon il reste dans la conversation
    et se perd au reset — la campagne demeure une coquille vide de cadrage).

    Appelle-le **juste après avoir conçu le scénario** (mode surprise : en secret,
    avant de révéler l'accroche), puis de nouveau à chaque fois que tu ajoutes un
    PNJ, un crochet, un défi, un lieu ou un bloc. Ne passe que les champs concernés
    (les autres sont préservés) ; le cadrage et l'état de phase/indices/statuts ne
    sont jamais écrasés ici.

    Format des sous-objets :
    - `pnj` : `[{"nom","objectif","faille","attitude"}]` (les 3 derniers obligatoires).
    - `crochets` : `[{"id","titre","lie_a_pj"}]` — `lie_a_pj` = nom exact d'un PJ
      (≥2 crochets liés aux PJ, un par PJ au minimum).
    - `defis` : `[{"nom","approches":[...]}]` — ≥2 approches par défi.
    - `lieux` : `[{"nom","description","obstacles","piliers":["exploration","social",
      "combat"],"zone":"sure|dangereuse","rencontre":{"titre","terrain","monstres":[{"nom","nb","cr",
      "comportement","pouvoirs_a_utiliser":[...]}]}}]` (CR lus dans la fiche SRD).
      **`zone` est important** : un lieu `"dangereuse"` porte une `rencontre` et le
      combat y est licite ; un lieu `"sure"` (village, carrefour, repaire social…) est
      une zone **sans combat possible** — n'y fais jamais apparaître d'ennemis. Par
      défaut un lieu est dangereux s'il a une `rencontre`, sûr sinon. Seules les zones
      dangereuses autorisent `ouvrir_un_combat`.
    - `blocs` : `[{"id","titre","contenu","position":"actif|reserve"}]`.
    Renvoie l'état + `avertissements_structure` (à corriger si non vide).
    """
    corps: dict[str, Any] = {}
    for cle, val in (
        ("titre", titre), ("synopsis", synopsis), ("accroche", accroche),
        ("enjeux", enjeux), ("motivations", motivations), ("danger", danger),
    ):
        if val:
            corps[cle] = val
    for cle, val in (("pnj", pnj), ("defis", defis), ("crochets", crochets),
                     ("lieux", lieux), ("blocs", blocs)):
        if val:
            corps[cle] = val
    return r_campagne.ecrire(campagne_id, corps, _CLE)


def faire_avancer_la_campagne(
    campagne_id: str, action: str, params: dict | None = None
) -> dict[str, Any]:
    """Déclarer un événement d'intrigue à la campagne. `action` ∈ `avancer_phase`,
    `resoudre_crochet`, `ouvrir_crochet`, `abandonner_crochet`, `rencontrer_pnj`,
    `changer_attitude`, `deplacer_bloc`, `decouvrir_lieu`, `ajouter_indice`,
    `accorder_recompense`. `params` paramètre la mutation."""
    corps: dict[str, Any] = {"action": action}
    if params:
        corps.update(params)
    return r_campagne.modifier(campagne_id, corps, _CLE)


def advisory_de_difficulte(
    campagne_id: str, monstres: list[dict]
) -> dict[str, Any]:
    """Avis de difficulté d'une rencontre (Mode B : informe, ne modifie rien).
    `monstres` = stats lues dans la fiche SRD (CR jamais inventés). Renvoie `degre`
    et `conseil` — c'est au MJ d'ajuster l'effectif ou le CR."""
    return r_campagne.advisory(campagne_id, {"monstres": monstres}, _CLE)


def clore_la_campagne(campagne_id: str) -> dict[str, Any]:
    """Clôturer une campagne quand l'intrigue est résolue."""
    return r_campagne.cloturer(campagne_id, _CLE)


def tirer_sur_une_table(dimension: str = "", nb: int = 1) -> dict[str, Any]:
    """Piocher des **graines d'inspiration** pour varier un scénario.

    Utilise-le quand une idée te semble trop prévisible ou qu'un scénario
    ressemblerait à un précédent. ``dimension`` ∈ ``crochets`` (accroche / point
    de départ), ``pnj`` (antagoniste / allié marquant), ``conflits`` (twist,
    complication, trahison), ``saveurs`` (détail de vie : rumeur, objet, coutume,
    météo). Laisse ``dimension`` vide pour piocher une graine dans chaque
    catégorie. ``nb`` = nombre de graines par catégorie (1 par défaut).

    IMPORTANT : une graine est un **déclencheur d'idée à réécrire et à tisser**
    avec le cadrage (ton, durée, piliers) et le background des PJ — jamais une
    phrase à recopier mot à mot. Renvoie ``{dimension: [graine, …]}``.
    """
    dims = [dimension] if dimension else None
    return {"ok": True, "inspirations": variete.tirer_inspirations(dims, nb)}


# Outils prenant un RunContext (session de création) → agent.tool().
OUTILS_CTX = [
    nouveau_personnage,
    lister_les_options,
    abandonner_la_creation,
    ouvrir_un_combat,
]

# Outils sans contexte → agent.tool_plain().
OUTILS_PLAIN = [
    lister_les_personnages,
    charger_le_personnage,
    modifier_le_personnage,
    supprimer_le_personnage,
    etat_du_combat,
    lancer_le_jet_d_un_monstre,
    enregistrer_le_jet_du_joueur,
    enregistrer_le_jet_hors_combat,
    tour_suivant_du_combat,
    appliquer_au_combat,
    clore_le_combat,
    lister_les_campagnes,
    etat_de_la_campagne,
    ecrire_le_scenario,
    faire_avancer_la_campagne,
    advisory_de_difficulte,
    clore_la_campagne,
    tirer_sur_une_table,
]
