"""Tableaux aléatoires d'aide à la création de scénario (stdlib uniquement).

But : casser la répétition des scénarios générés. Le MJ/LLM pioche des **graines
d'inspiration** dans des tableaux thématiques (crochet, PNJ, conflit/twist, saveur),
puis les **réécrit et les tisse** avec le cadrage (ton, durée, piliers) et le
background des PJ. Une graine n'est jamais copiée mot à mot : c'est un déclencheur
d'idée, pas un résultat.

Réutilise ``dice.roll_d100`` (liste de couples ``(borne_supérieure, valeur)``, bornes
cumulées jusqu'à 100). Le ``random.Random`` est injecté pour rendre les tirages
reproductibles à la demande — **aucune seed n'est persistée** ici : les tirages sont
jetables (un système de « lore » pourra s'y greffer plus tard).
"""

from __future__ import annotations

import random

from dnd_perso import dice

# ---------------------------------------------------------------------------
# Tables — chaque liste = couples (borne supérieure cumulée, valeur), cumuls 1..100.
# ---------------------------------------------------------------------------

# Crochet / accroche : ce qui met les PJ en route.
TABLE_CROCHETS: list[tuple[int, str]] = [
    (6, "Un proche des PJ disparaît en laissant un objet personnel et une trace étrange."),
    (12, "Une récompense officielle est offerte pour une tâche qui sent le piège ou l'injustice."),
    (18, "Un objet de valeur arrive entre les mains des PJ — et son ancien propriétaire le réclame."),
    (24, "Un présage, une prophétie ou une lettre inachevée désigne nommément les PJ."),
    (30, "Un lieu familier change du tout au tout au réveil (disparu, verrouillé, transformé)."),
    (36, "Un étranger meurt dans les bras des PJ en confiant une dernière demande inachevée."),
    (42, "Une dette ancienne ressurgit : quelqu'un exige un paiement que les PJ ignorent devoir."),
    (48, "Un enfant ou un témoin improbable affirme avoir vu quelque chose d'impossible."),
    (54, "Une invitation mondaine cache un test, un piège ou un marché dangereux."),
    (60, "Un rival / une faction rivale devance les PJ sur une découverte qui leur revenait."),
    (66, "Un phénomène naturel impossible (marée inversée, neige en été, silence total) appelle une enquête."),
    (72, "Un allié de confiance se met à mentir ou à disparaître sans explication."),
    (78, "Un objet commun se révèle maudit, vivant ou doué de volonté."),
    (84, "Un procès, une émeute ou une loi nouvelle menace indirectement les PJ ou les leurs."),
    (90, "Un message chiffré / un rêve partagé par plusieurs PJ ordonne la même action."),
    (96, "Un cadavre est découvert avec les armes ou les effets personnels des PJ, innocents."),
    (100, "Une porte, une carte ou un passage s'ouvre pour la première fois — et appelle."),
]

# PNJ marquant : antagoniste ou allié, avec une motivation et une faille inattendues.
TABLE_PNJ: list[tuple[int, str]] = [
    (7, "Un antagoniste convaincu d'être le héros ; sa cause est défendable, ses moyens sont atroces."),
    (14, "Un allié qui ment par omission — il sait quelque chose de crucial et tait pour se protéger."),
    (21, "Un enfant ou une figure vulnérable qui en sait bien plus qu'il n'y paraît."),
    (28, "Un fonctionnaire intègre dont la bureaucratie bloque malgré lui les PJ."),
    (35, "Un ancien héros déchu, brisé par une faute que les PJ pourraient répéter."),
    (42, "Un marchand d'informations qui donne le vrai et le faux au même prix, par amusement."),
    (49, "Un traître au sein d'un camp ami, motivé par une dette du cœur et non par l'or."),
    (56, "Une créature non-hostile que tout le monde croit monstre ; elle ne demande qu'un service."),
    (63, "Un fanatique au calme glaçant, poli et logique, qu'aucune menace ne fait plier."),
    (70, "Un double / sosie qui vole la place, la réputation ou le nom d'un PNJ aimé des PJ."),
    (77, "Un guérisseur / conseiller dont les bons conseils créent malgré lui de nouvelles dettes."),
    (84, "Un enfant soldat ou jeune exécutant qui obéit par peur, et peut basculer d'un côté ou l'autre."),
    (91, "Un rival sympathique qui vise le même objectif que les PJ, par des moyens légaux."),
    (100, "Un PNJ qui connaît le futur des PJ et refuse d'en dire plus qu'une énigme."),
]

# Conflit / twist : ce qui retourne la situation en cours de route.
TABLE_CONFLITS: list[tuple[int, str]] = [
    (7, "Le commanditaire est en réalité l'antagoniste ; la quête servait ses intérêts."),
    (14, "L'objet / la personne à sauver est déjà mort(e) ou remplacé(e) sans que personne le sache."),
    (21, "Deux alliés des PJ sont secrètement ennemis ; les aider l'un trahit l'autre."),
    (28, "La solution évidente aggrave le mal — chaque remède a un prix moral."),
    (35, "Le monstre traqué est un gardien nécessaire ; le vaincre libère un pire."),
    (42, "Une information fiable se révèle fabriquée pour manipuler les PJ."),
    (49, "Le temps presse pour la mauvaise raison : la vraie urgence apparaît trop tard."),
    (56, "Un PJ est, sans le savoir, la clé du problème (sang, marque, dette, prophétie)."),
    (63, "Le lieu sûr n'est pas sûr : un·e des PNJ y a préparé un piège de longue date."),
    (70, "La victoire apparente déclenche la vraie catastrophe (le sceau était le verrou, pas la menace)."),
    (77, "Un choix irréversible : sauver l'un condamne l'autre, sans information suffisante."),
    (84, "L'antagoniste propose une paix raisonnable que le groupe ne peut pas accepter sans se trahir."),
    (91, "La récompense promise a déjà été accordée à quelqu'un d'autre — qui est présent."),
    (100, "Le vrai ennemi était caché derrière les PJ depuis le début (complice, familier, protecteur)."),
]

# Saveur / détail : petites touches de vie qui singularisent un scénario.
TABLE_SAVEURS: list[tuple[int, str]] = [
    (8, "Une rumeur absurde court la ville et finit par se réaliser à moitié."),
    (16, "Un objet banal est traité comme une relique sacrée par les locaux — et ils ont raison."),
    (24, "Une coutume locale étrange régit les rencontres (silence après la nuit, don obligatoire…)."),
    (32, "Une météo anormale et persistante façonne l'humeur et le terrain."),
    (40, "Une fête, un deuil ou un marché détourne toutes les ressources et les regards."),
    (48, "Une chanson, une comptine ou une gravure répète un indice sans que nul sache d'où elle vient."),
    (56, "Un animal ou une créature suit les PJ, semblant vouloir conduire quelque part."),
    (64, "Un plat, une boisson ou une denrée rare devient un levier social inattendu."),
    (72, "Un lieu porte la trace d'une catastrophe ancienne que personne ne nomme à voix haute."),
    (80, "Un personnage secondaire a une obsession comique qui finit par servir l'intrigue."),
    (88, "Une inscription, une date ou une coordonnées semble hors de son époque."),
    (96, "Un objet personnel d'un PJ résonne avec le décor (déjà-vu, écho, reconnaissance)."),
    (100, "Un détail sensoriel récurrent (odeur, son, lumière) annonce une présence sans qu'on sache laquelle."),
]

# Nom de dimension -> table.
TABLES: dict[str, list[tuple[int, str]]] = {
    "crochets": TABLE_CROCHETS,
    "pnj": TABLE_PNJ,
    "conflits": TABLE_CONFLITS,
    "saveurs": TABLE_SAVEURS,
}

DIMENSIONS = tuple(TABLES)


def tirer_inspirations(
    dimensions: list[str] | None = None,
    nb: int = 1,
    rng: random.Random | None = None,
) -> dict[str, list[str]]:
    """Tire ``nb`` graine(s) d'inspiration par dimension demandée.

    ``dimensions`` : sous-ensemble de ``DIMENSIONS`` (défaut : toutes). Une dimension
    inconnue est ignorée silencieusement. ``nb`` : nombre de tirages par dimension.
    Retourne ``{dimension: [graine, …]}``. Les tirages sont jetables (aucune seed
    persistée) ; passe un ``rng`` figé côté appelant pour les rendre reproductibles.
    """
    rng = rng or random.Random()
    dims = list(dimensions) if dimensions else list(DIMENSIONS)
    resultats: dict[str, list[str]] = {}
    for dim in dims:
        table = TABLES.get(dim)
        if not table:
            continue
        resultats[dim] = [dice.roll_d100(table, rng)[1] for _ in range(max(1, nb))]
    return resultats
