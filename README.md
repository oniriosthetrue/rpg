# MJ D&D — Maître de Jeu D&D 5e (app dédiée)

Interface MJ autonome pour le JDR D&D 5.2.1 (SRD), en remplacement d'Open WebUI.

- **Frontend** : Next.js (App Router + Tailwind) — `apps/web`
- **Backend** : FastAPI + Pydantic-AI — `apps/api`
- **Moteur de règles** : `packages/dnd_perso` (stdlib only, réutilisé de l'existant)
- **Corpus SRD** : `packages/corpus` (~861 fiches markdown + PDF source en Git LFS)
- **RAG** : recherche hybride BM25 + Qdrant et service d'embeddings OpenAI-compatible

## Principe directeur

Un vrai JDR a **deux cerveaux distincts** :

| | Cerveau narratif | Cerveau règles |
|---|---|---|
| Contenu | descriptions, dialogues, ambiance | chiffres, jets, tables, statistiques |
| Support | le **modèle** (créativité) | les **outils** + le **RAG** (déterminisme) |

**Règle d'or : le LLM ne calcule jamais rien.** Il *demande* une action (`roller_des`),
il *lit* une fiche (`lookup`), et il *raconte* le résultat. Tout ce qui est chiffré vient
d'un outil qui renvoie du JSON. Tout ce qui est factuel vient du RAG, avec citation.

## Structure

```
rpg/
├─ apps/
│  ├─ web/          # Next.js — chat streaming + panneaux fiche/combat/campagne
│  └─ api/          # FastAPI + Pydantic-AI — agent, tools, RAG, contrat JSON v1
├─ packages/
│  ├─ dnd_perso/    # moteur de règles (stdlib only)
│  └─ corpus/       # srd-5.2.1/ — corpus RAG (fiches .md) + PDF (LFS)
├─ docs/            # CONTRAT-API-JDR.md, ARCHITECTURE.md, ADR/
├─ scripts/         # ingest_corpus.py, embedding_server.py, check_corpus.py, arena.py
├─ tests/           # tests purs du moteur + tests agent
├─ docker-compose.yml
└─ .env.example
```

## Démarrage rapide

> ⚠️ La stack LLM (vllm, litellm, embedding) tourne dans le dépôt `qwen_3.8_vnimanieAI`
> et est lancée **uniquement manuellement** par l'opérateur. Ce dépôt ne démarre que
> `web`, `api` et `qdrant`, qui se branchent sur l'existant via le réseau docker
> **externe** de cette stack.

### Réseau

Le réseau à rejoindre est préfixé par le nom du projet compose de l'autre stack :
`qwen_38_vnimanieai_mynetwork` (et non `mynetwork`). Il est configurable via
`DOCKER_NETWORK` dans `.env` (reporté sous `networks.mynetwork.name`).

### Démarrage

```bash
cp .env.example .env          # renseigner URL/clés + DOCKER_NETWORK de la stack existante
# MJ_MODEL = le nom exposé par litellm (GET /v1/models), pas l'id vLLM (ex. « IA »).
# Définir WEB_AUTH_USERNAME et un WEB_AUTH_PASSWORD dédié avant le déploiement.
docker compose up -d qdrant
docker compose build api web
docker compose up -d api web
```

Le site et ses routes API demandent une authentification HTTP Basic. Si
`WEB_AUTH_PASSWORD` est vide, `DND_API_KEY` sert de mot de passe de secours;
préférer un mot de passe dédié dans `.env`. L'authentification est prévue derrière
HTTPS et utilise un compte partagé.

Vérification (les conteneurs `api`/`web` n'ont pas de port publié — on teste depuis
l'intérieur) :

```bash
docker exec mj-api python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
docker exec mj-web node -e "fetch('http://localhost:3000').then(r=>console.log(r.status))"
```

L'app est exposée sur **rpg.minervia.fr** (routeur Traefik `mj-web`, priorité 100).

### Ingestion du corpus (une fois)

```bash
# Long (~2,5 h sur CPU) : lancer en tâche de fond pour ne pas bloquer le shell.
docker exec -d mj-api sh -c 'cd /app && python3 -m scripts.ingest_corpus > /tmp/ingest.log 2>&1'
tail -f /tmp/ingest.log
```

Idempotent (upsert par id dérivé) : relancer met à jour sans doublon. Le texte
vectorisé est tronqué à 4 000 caractères (le service embeddings est CPU-bound) ;
le texte COMPLET reste dans le payload Qdrant pour les citations. Ne pas
`docker restart mj-api` pendant l'ingestion (cela tue le job).

### Sauvegardes

Le script `scripts/backup.py` produit une archive protégée contenant les fiches
de `data-perso/` et un snapshot cohérent de la collection Qdrant. Il supprime
les snapshots temporaires de Qdrant après téléchargement et conserve 14 jours
d'archives par défaut.

```bash
python3 scripts/backup.py
```

Par défaut, les archives sont écrites dans `~/backups/mj-dnd`. Le dossier
doit être accessible en écriture par l'utilisateur qui exécute le script ; on
peut choisir une autre destination avec `--destination` ou `DND_BACKUP_DIR`.
Pour une exécution quotidienne à 03:00, ajouter cette ligne au crontab de
l'utilisateur propriétaire des conteneurs Docker :

```cron
0 3 * * * /usr/bin/python3 /home/linus/rpg/scripts/backup.py --destination /home/linus/backups/mj-dnd --retention-days 14 >> /home/linus/backups/mj-dnd/backup.log 2>&1
```

Adapter les chemins si le dépôt ou le répertoire d'archives se trouvent
ailleurs. Le dossier d'archives contient des données de personnages : le garder
hors Git et prévoir une copie hors machine pour se protéger d'une panne disque.

## Documentation

- [`docs/CONTRAT-API-JDR.md`](docs/CONTRAT-API-JDR.md) — le contrat JSON v1 (à ne pas casser).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture et décisions.
