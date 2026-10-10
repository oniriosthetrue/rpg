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


def nettoyer(texte: str) -> str:
    """Chaîne complète appliquée à chaque segment de réponse du MJ."""
    return masquer_stats_monstre(corriger_emphase(texte))
