"""Post-traitement de la réponse du MJ (anti-métajeu + mise en page).

Portage des regex du filtre OWUI `filtre_anti_meta_mj.py` (v2.5), hébergé ici
côté backend au lieu d'un outlet Open WebUI. Logique identique :

- corriger l'emphase Markdown collée au mot précédent ;
- masquer les stats de monstre (CA / PV énoncés en bloc de stats) ;
- retirer les anciennes étiquettes [MÉCANIQUE]/[NARRATION].
"""

from __future__ import annotations

import re

# Le modèle colle parfois les marqueurs d'emphase au mot précédent (« du**Royaume** »).
# La lookahead `(?=\w)` ne touche QUE les marqueurs OUVRANTS (suivis d'un mot).
_ESPACE_EMPHASE = re.compile(r"(\w)(\*+)(?=\w)")

# Anti-fuite « stats de monstre ». On masque UNIQUEMENT les formes explicites de
# bloc de stats (« CA : 15 », « PV : 7 »), JAMAIS une valeur différentielle
# (« tu perds 5 PV ») — d'où le séparateur `:`/`=` requis pour PV.
_LEAK_CA = re.compile(r"(\bCA\b(?:\s+d'armure)?\s*[:=]?\s*)(\d+)", re.IGNORECASE)
_LEAK_PV = re.compile(r"((?:points de vie|PV)\s*[:=]\s*)(\d+)", re.IGNORECASE)

# Filet de sécurité : retirer les anciennes balises de bloc si le modèle en émet.
_BLOC_MJ = re.compile(
    r"(?:^|\n)\s*\*{0,2}\[?\s*(MÉCANIQUE|MECANIQUE|NARRATION)\s*\]?\s*\*{0,2}\s*:?\s*",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Anti-fuite « réflexion du MJ à voix haute ».
#
# On découpe la réponse en phrases et on retire celles où le MJ énonce ses
# intentions, son plan ou ses vérifications d'outils au lieu de raconter la
# scène. On ne cible que des tournures à la 1re personne clairement
# métanarratives (verbes de planification / vérification / conception), pour ne
# jamais supprimer de narration (« Je te regarde… », un PNJ qui « note » quelque
# chose restent intacts).
# ---------------------------------------------------------------------------
_REFLEXION = re.compile(
    r"""^\s*
    (?:
        Je\s+vais?\b                          # « je vais », « je vais d'abord relire »
      | Je\s+(?:dois|peux|viens\s+de)\b
      | Je\s+(?:vérifie|vérifiais|vérifierai|vérifirai|charge|chargeais|chargerai|
             relis|relisais|relirai|consulte|consultais|consulterai|parcours|
             examine|examinais|contrôle|controle|prépare|prepare|préparais|
             note|remarque|constate|me\s+souviens)\b
      | Il\s+me\s+faut\b
      | Il\s+(?:faudra|faut)\b
      | La\s+trame\s+est\b
      | Le\s+cadrage\s+est\b
      | Voici\s+ce\s+que\s+vous\b
      | Voici\s+(?:vos|les|tes)\s+options\b
      | Tout\s+d[ée]pend\s+de\b
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Découpage en phrases (garde la ponctuation finale).
_PHRASE = re.compile(r"[^.!?]*[.!?]+|[^.!?]+$")

# Amorce typique d'une « liste de menu » (catalogue d'options). Si une telle amorce
# apparaît, on retire les lignes à puces/numérotées qui l'entourent.
_MENU_AMORCE = re.compile(
    r"(?:du\s+plus\s+(?:évident|evident)|chaque\s+action\s+a\s+un\s+c[oû]t|"
    r"voici\s+ce\s+que\s+vous\s+pouvez|voici\s+(?:vos|tes)\s+options|"
    r"vos\s+options\s+sont|tes\s+options\s+sont|que\s+souhaitez[-\s]vous\s+faire|"
    r"options?\s+qui\s+s'?offrent)",
    re.IGNORECASE,
)
# Ligne de liste : puce (-, *, •), numéro (1. / 1)) ou court préfixe emoji.
# On exclut le bloc citation `>` (texte destiné aux joueurs) pour ne jamais le retirer.
_LIGNE_LISTE = re.compile(r"^\s*(?!>)(?:[-*•]|\d+[.)]|\W{1,3}\s)\s*\S.*$")


def corriger_emphase(texte: str) -> str:
    if not isinstance(texte, str) or "*" not in texte:
        return texte
    return _ESPACE_EMPHASE.sub(r"\1 \2", texte)


def masquer_stats_monstre(texte: str) -> str:
    """Remplace par « • » les chiffres de CA / PV énoncés en bloc de stats."""
    if not isinstance(texte, str):
        return texte
    texte = _LEAK_CA.sub(r"\1•", texte)
    texte = _LEAK_PV.sub(r"\1•", texte)
    texte = _BLOC_MJ.sub("\n", texte)
    return texte


def retirer_reflexion(texte: str) -> str:
    """Retire les phrases de réflexion/métajeu du MJ (1re personne, planification)."""
    if not isinstance(texte, str) or not texte.strip():
        return texte
    morceaux = _PHRASE.findall(texte)
    if not morceaux:
        return texte
    gardees = [p for p in morceaux if not _REFLEXION.match(p.strip())]
    return "".join(gardees)


def retirer_menu(texte: str) -> str:
    """Retire les lignes à puces/numérotées formant un « menu » d'options.

    On n'agit QUE si le texte contient une amorce de menu (ex. « du plus évident au
    plus fin », « chaque action a un coût »), pour ne jamais casser une liste
    légitime de la narration (inventaire, PNJ présents, etc.).
    """
    if not isinstance(texte, str) or not _MENU_AMORCE.search(texte):
        return texte
    gardees: list[str] = []
    for ligne in texte.split("\n"):
        if _MENU_AMORCE.search(ligne):
            continue
        if _LIGNE_LISTE.match(ligne) and len(ligne.strip()) <= 120:
            continue
        gardees.append(ligne)
    return "\n".join(gardees)


def nettoyer(texte: str) -> str:
    """Chaîne complète appliquée à la réponse du MJ."""
    texte = masquer_stats_monstre(corriger_emphase(texte))
    texte = retirer_reflexion(texte)
    texte = retirer_menu(texte)
    return texte.strip()
