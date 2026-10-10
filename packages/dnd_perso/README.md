# `dnd_perso/` — moteur de règles D&D 5e (pur stdlib)

Paquet Python **sans dépendance externe** qui fait tous les calculs du JDR :
création guidée de personnage, jets de dés, gestion des fiches.

## Fichiers

| Fichier | Rôle |
|---|---|
| `__init__.py` | Marqueur de package + exports publics. |
| `__main__.py` | Point d'entrée : `python3 -m dnd_perso` lance l'interview guidée. |
| `models.py` | Dataclass `Personnage` (attributs, PV, XP, sorts, équipement incl. la babiole) + `vers_dict()` / `depuis_dict()`. |
| `creation.py` | Interview guidée de création (étapes, options, validation). |
| `dice.py` | Lancer de dés (avantage/désavantage, critiques). |
| `extract.py` | Extraction des données depuis le corpus `dnd/srd-5.2.1/` (constantes en dur en secours). Dossier fiches via `DND_PERSO_DIR`, défaut `dnd_perso/perso/`. |
| `export.py` | Export de la fiche en Markdown/JSON (la babiole est fusionnée dans l'équipement). |
| `io.py` | Lecture/écriture des fiches (JSON atomique). |

## Sous-dossiers

| Dossier | Rôle |
|---|---|
| `data/` | Données statiques du package. |
| `perso/` | Fiches personnage (`.json` + `.md` par personnage). |

## Utilisation

```bash
python3 -m dnd_perso            # interview guidée en terminal
```

En production, c'est `jdr_api/` qui utilise ce package ; `openui/` n'y accède
plus directement (client HTTP vers `jdr-api`).
