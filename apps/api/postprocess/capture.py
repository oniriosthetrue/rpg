"""Hook de capture : intercepte les jets de dés que le MJ lance LUI-MÊME.

Règle d'or du jeu : le MJ ne lance jamais les dés du joueur. C'est le joueur qui
jette TOUS ses dés (attaques, sauvegardes, jets de caractéristique). Le serveur
ne lance que les dés des monstres (via l'outil ``lancer_le_jet_d_un_monstre``).

Or, hors combat, aucun outil de jet n'existe : le modèle « triche » donc en
écrivant lui-même le résultat (``## Jet d'Investigation : d20 + 4 = 17 ✓``). Ce
module détecte ces réponses pour que la route de chat puisse relancer l'agent
avec une consigne corrective (voir ``routers/chat.py``).

On ne déclenche le re-run que si le joueur n'a fourni AUCUN nombre dans son
message : s'il a tapé « 16 », le MJ qui restitue « d20 : 16 + 3 = 19 » est
légitime (il applique le dé du joueur, il ne le lance pas).
"""

from __future__ import annotations

import re

# Un total de dé RÉSOLU par le MJ : une expression de dé suivie d'un résultat.
#   « d20 + 4 = 17 », « d20=17 », « 1d20 + 5 = 23 », « d100 → 42 »
_JET_RESOLU = re.compile(
    r"\d?\s*d\s*\d+\s*(?:[+\-−]\s*\d+\s*)?[=→]\s*\d+", re.IGNORECASE
)

# Un résultat coché juste après un total : « = 17 ✓ », « 19 ✗ ».
_RESULTAT_COCHÉ = re.compile(r"=\s*\d+\s*[✓✗✔✘]")

# Titre / libellé de jet accompagné d'un total : « ## Jet d'Investigation … 17 »,
# « **Jet d'attaque** : 19 ». On exige un chiffre pour ne pas capter une simple
# invitation à lancer (« Lance ton jet d'attaque ! »).
_TITRE_JET_AVEC_TOTAL = re.compile(
    r"(?:^|\n)\s*(?:#{1,6}\s*\**|\*{1,2})\s*jet\b[^\n]*?\b\d{1,3}\b",
    re.IGNORECASE,
)

# Le MJ annonce qu'il lance lui-même : « je lance un d20 », « je jette le dé »,
# « je tire un d100 ».
_MJ_ANONCE_JET = re.compile(
    r"\bje\s+(?:lance|jette|tire)\s+(?:un|le|mon|1)?\s*d\s*\d+", re.IGNORECASE
)

# Le MJ énonce le résultat obtenu pour le joueur : « tu obtiens 17 »,
# « tu réussis à 19 », « tu réalises un 23 ». On évite « tu fais N » (trop
# présent en narration : « tu fais quelques pas »).
_RESULTAT_JOUEUR = re.compile(
    r"\btu\s+(?:obtiens|obtenais|obtiendras|realises|réalises|reussis|réussis)\s+(?:un\s+)?\d{1,3}\b",
    re.IGNORECASE,
)

_PATTERNS_JET_AUTO = (
    _JET_RESOLU,
    _RESULTAT_COCHÉ,
    _TITRE_JET_AVEC_TOTAL,
    _MJ_ANONCE_JET,
    _RESULTAT_JOUEUR,
)

# Retire les lignes de jet résolu (repli si la relance corrective échoue aussi) :
# on supprime les lignes qui contiennent un total de dé résolu ou un résultat
# coché, pour ne pas laisser un dé « truqué » à l'écran.
_LIGNE_JET_RESOLU = re.compile(
    r"(\d?\s*d\s*\d+\s*(?:[+\-−]\s*\d+\s*)?[=→]\s*\d+)|=\s*\d+\s*[✓✗✔✘]",
    re.IGNORECASE,
)

# Consigne injectée lors du re-run correctif. Elle rappelle la règle d'or et
# force le MJ à s'arrêter sur la demande de lancer, sans jamais lancer lui-même.
CONSIGNE_CORRECTIVE = (
    "[MÉTAJEU — CORRECTION] Tu viens de lancer un dé toi-même (tu as écrit un "
    "résultat du type « d20 + X = Y » ou « tu obtiens N »), ce qui est STRICTEMENT "
    "INTERDIT. Le joueur lance LUI-MÊME tous ses dés. Réécris ta réponse ainsi : "
    "raconte la scène jusqu'au moment exact où le dé doit tomber, puis DEMANDE au "
    "joueur son jet (quelle caractéristique / compétence, quel modificateur) et "
    "ARRÊTE-TOI immédiatement sur cette demande. N'écris AUCUN dé, AUCUN total, "
    "AUCUN résultat. Ne résous rien."
)


def detecter_jet_auto(texte: str) -> bool:
    """Vrai si la réponse du MJ contient un jet de dé qu'il a résolu lui-même."""
    if not texte:
        return False
    return any(p.search(texte) for p in _PATTERNS_JET_AUTO)


def le_joueur_a_donne_un_de(message: str) -> bool:
    """Vrai si le message du joueur contient un nombre (il a probablement fourni
    son dé) : on ne doit alors PAS corriger la restitution du MJ."""
    if not message:
        return False
    return bool(re.search(r"\d", message))


def retirer_jet_resolu(texte: str) -> str:
    """Repli : retire les lignes énonçant un dé résolu (utilisé si la relance
    corrective produit elle aussi un jet auto)."""
    if not texte:
        return texte
    lignes = [
        ligne
        for ligne in texte.splitlines()
        if not _LIGNE_JET_RESOLU.search(ligne)
    ]
    return "\n".join(lignes).strip()
