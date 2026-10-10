"""dnd_perso — Création de personnage D&D 5e selon le SRD 5.2.1 (français).

Programme autonome, sans LLM : il s'appuie sur le corpus markdown local
(`dnd/srd-5.2.1/`, `dnd/classes/`) et des constantes vérifiées.

Usage :
    python3 -m dnd_perso              # création guidée, interactive
    python3 -m dnd_perso --auto       # création automatique (tout par défaut/tirage)
    python3 -m dnd_perso --seed 42    # création reproductible
"""

__all__ = ["creation", "dice", "export", "extract", "io"]
__version__ = "0.1.0"
