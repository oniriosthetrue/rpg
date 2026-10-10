"""jdr_api — microservice HTTP de création de personnage JDR (D&D 5.2.1, SRD).

Ce package ne contient que la couche HTTP (FastAPI). Toute la logique est
dans `openui/mj.py` (orchestration) et `dnd_perso/` (modèles, corpus).
Le contrat d'échange est défini dans `dnd/CONTRAT-API-JDR.md`.
"""
