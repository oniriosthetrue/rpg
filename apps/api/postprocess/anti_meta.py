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
# apparaît, on retire le bloc d'options qui la suit (puces, sections emoji, lignes
# longues) jusqu'au prochain séparateur `---` ou question de clôture.
_MENU_AMORCE = re.compile(
    r"(?:du\s+plus\s+(?:évident|evident)|chaque\s+action\s+a\s+un\s+c[oû]t|"
    r"voici\s+ce\s+que\s+vous\s+pouvez|voici\s+(?:vos|tes)\s+options|"
    r"vos\s+options\s+sont|tes\s+options\s+sont|que\s+souhaitez[-\s]vous\s+faire|"
    r"options?\s+qui\s+s'?offrent|ce\s+que\s+tu\s+peux\s+faire|"
    r"ce\s+que\s+vous\s+pouvez\s+faire|\btu\s+pourrais\b|\bvous\s+pourriez\b|"
    r"(?:tu\s+peux|vous\s+pouvez)\s*:\s*$)",
    re.IGNORECASE | re.MULTILINE,
)
# Ligne de liste : puce (-, *, •), numéro (1. / 1)) ou court préfixe emoji.
# On exclut le bloc citation `>` (texte destiné aux joueurs) pour ne jamais le retirer.
_LIGNE_LISTE = re.compile(r"^\s*(?!>)(?:[-*•]|\d+[.)]|\W{1,3}\s)\s*\S.*$")
# Séparateur horizontal Markdown (fin d'un bloc de menu).
_SEP_HR = re.compile(r"^\s*-{3,}\s*$")
# Question courte de clôture (« Que fais-tu ? », « Tu fais quoi ? ») : on la garde.
_QUESTION_CLOTURE = re.compile(r"^\s*\S.{0,58}\?\s*$")

# Filet de sécurité contre les « menus » servis sous forme de TABLEAU Markdown
# (ex. « | Option | Type de jet | »). Un tableau n'est retiré que si son en-tête
# contient un vocabulaire de menu (option / action / jet / compétence / type /
# difficulté) — jamais un tableau légitime de la narration (inventaire, PNJ…).
_LIGNE_TABLEAU = re.compile(r"^\s*\|.*\|\s*$")
_SEP_TABLEAU = re.compile(r"^\s*\|?\s*:?-{2,}.*\|")
_ENTETE_MENU = re.compile(
    r"\b(option|action|jet|comp[eé]tence|type\s+de|difficult[eé]|ce\s+que\s+vous|"
    r"ce\s+que\s+tu|ce\s+qu[ie]\s+vous|peu[tz]\s+(?:faire|faire))\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Anti-« synthèse ». Le MJ conclut parfois son tour par un bloc récapitulatif
# (« Résumé », « Ce que tu retiens », « En résumé », « Bilan »…) qui redit les
# indices déjà donnés et casse l'immersion. On ne cible qu'une amorce isolée
# (titre Markdown ou ligne entièrement en gras) portant un marqueur de synthèse,
# puis on retire le bloc qui la suit jusqu'au prochain séparateur `---`, titre
# ou question de clôture — jamais une narration contenant le mot « résumé ».
# ---------------------------------------------------------------------------
_MARQUEUR_SYNTHESE = re.compile(
    r"\b(r[ée]sum[ée]|r[ée]capitulatif|en\s+r[ée]sum[ée]|bilan|l'essentiel|"
    r"points?\s+cl[ée]s|d[ée]sormais|"
    r"ce\s+que\s+tu\s+(?:retiens|retires|sais|savez|as\s+retenu)|"
    r"ce\s+que\s+vous\s+(?:retenez|retiens|savez|sais|avez\s+retenu)|"
    r"ce\s+qu'[io]n\s+sait|ce\s+qu'il\s+faut\s+retenir|[àa]\s+retenir)\b",
    re.IGNORECASE,
)
# Amorce = titre (`#…`) OU ligne entièrement en gras (`**…**`), portant le marqueur.
_TITRE = re.compile(r"^\s*#{1,6}\s")
_GRAS_SEUL = re.compile(r"^\s*\*\*[^*]+\*\*\s*[:：]?\s*$")
# Titre Markdown (nouvelle section légitime) : fin d'un bloc de synthèse, conservé.
_HEADING = re.compile(r"^\s*#{1,6}\s")


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


def _retirer_tableaux_menu(texte: str) -> str:
    """Retire les blocs de tableau Markdown servant de « menu » d'options.

    Un tableau n'est retiré que si son en-tête contient un vocabulaire de menu
    (option / action / jet / compétence…). Les tableaux légitimes de la narration
    (inventaire, PNJ présents, butin) sont conservés.
    """
    lignes = texte.split("\n")
    gardees: list[str] = []
    i = 0
    n = len(lignes)
    while i < n:
        # Début d'un tableau : une ligne en-tête, puis une ligne de séparation.
        if (
            _LIGNE_TABLEAU.match(lignes[i])
            and i + 1 < n
            and _SEP_TABLEAU.match(lignes[i + 1])
        ):
            j = i + 2
            while j < n and _LIGNE_TABLEAU.match(lignes[j]):
                j += 1
            bloc = lignes[i:j]
            if _ENTETE_MENU.search(bloc[0]):
                i = j  # menu : on saute tout le bloc
                continue
            gardees.extend(bloc)
            i = j
            continue
        gardees.append(lignes[i])
        i += 1
    return "\n".join(gardees)


def retirer_menu(texte: str) -> str:
    """Retire les « menus » d'options servis par le MJ.

    Deux formes sont traitées :
    - les tableaux Markdown de type menu (détection par en-tête, voir
      `_retirer_tableaux_menu`) ;
    - les blocs d'options (puces, sections emoji, lignes longues) introduits par
      une amorce de menu (« Tu peux : », « voici vos options », « du plus évident
      au plus fin »…). On retire tout le bloc jusqu'au prochain séparateur `---`
      ou question de clôture (« Que fais-tu ? »), qu'on conserve.
    """
    if not isinstance(texte, str) or not texte.strip():
        return texte
    texte = _retirer_tableaux_menu(texte)
    if not _MENU_AMORCE.search(texte):
        return texte

    lignes = texte.split("\n")
    gardees: list[str] = []
    dans_menu = False
    for ligne in lignes:
        if dans_menu:
            # Fin du bloc : séparateur horizontal ou question de clôture.
            if _SEP_HR.match(ligne):
                dans_menu = False
                continue  # on retire aussi le séparateur qui fermait le menu
            if _QUESTION_CLOTURE.match(ligne):
                dans_menu = False
                gardees.append(ligne)
                continue
            continue  # ligne du menu : on la retire
        if _MENU_AMORCE.search(ligne):
            dans_menu = True
            continue
        gardees.append(ligne)
    return "\n".join(gardees)


def retirer_synthese(texte: str) -> str:
    """Retire les blocs de « synthèse » du MJ (Résumé / Ce que tu retiens / Bilan…).

    Un bloc commence sur une ligne d'amorce isolée (titre Markdown ou ligne
    entièrement en gras) portant un marqueur de synthèse. On retire cette amorce
    et les lignes qui la suivent jusqu'au prochain séparateur `---`, titre
    Markdown ou question de clôture (conservés). Une simple narration contenant le
    mot « résumé » n'est jamais touchée (l'amorce doit être un titre/ligne en gras).
    """
    if not isinstance(texte, str) or not texte.strip():
        return texte

    lignes = texte.split("\n")
    gardees: list[str] = []
    dans_synthese = False
    for ligne in lignes:
        if dans_synthese:
            # Fin du bloc : séparateur (retiré), nouveau titre ou question de
            # clôture (conservés).
            if _SEP_HR.match(ligne):
                dans_synthese = False
                continue  # on retire aussi le séparateur qui fermait la synthèse
            if _HEADING.match(ligne) or _QUESTION_CLOTURE.match(ligne):
                dans_synthese = False
                gardees.append(ligne)
                continue
            continue  # ligne de la synthèse : on la retire
        est_amorce = (
            (_TITRE.match(ligne) or _GRAS_SEUL.match(ligne))
            and _MARQUEUR_SYNTHESE.search(ligne)
        )
        if est_amorce:
            dans_synthese = True
            continue
        gardees.append(ligne)
    return "\n".join(gardees)


def nettoyer(texte: str) -> str:
    """Chaîne complète appliquée à la réponse du MJ."""
    texte = masquer_stats_monstre(corriger_emphase(texte))
    # Retirer les menus/synthèses AVANT la réflexion : `retirer_reflexion` découpe
    # en phrases et recolle sans égard aux sauts de ligne, ce qui détruirait la
    # structure en lignes dont `retirer_menu`/`retirer_synthese` ont besoin.
    texte = retirer_menu(texte)
    texte = retirer_synthese(texte)
    texte = retirer_reflexion(texte)
    return texte.strip()
