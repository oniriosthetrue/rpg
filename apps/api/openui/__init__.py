"""Intégration Open WebUI du créateur de personnage D&D 5.2.1.

Ce paquet est la couche « MJ headless » au-dessus de `dnd_perso` (qu'il
importe en lecture seule, sans jamais le modifier) :

- pas d'`input()` ni de `print()` : tout passe par des valeurs de retour ;
- le joueur répond en langage libre, la réponse est normalisée puis validée ;
- en cas d'échec, un choix est tiré au hasard (comme en mode `--auto`) ;
- la fiche finale est rendue en markdown, prête à être affichée dans le chat.

L'orchestration de la création est découpée en étapes fines (classe,
compétences, équipement, origines, caractéristiques, alignement,
finalisation) afin que le Maître du Jeu puisse poser une question à la fois.
"""

from .mj import abandonner, continuer, demarrer, etat_session, lister_options, personnage_final

__all__ = [
    "demarrer",
    "continuer",
    "abandonner",
    "personnage_final",
    "lister_options",
    "etat_session",
]
