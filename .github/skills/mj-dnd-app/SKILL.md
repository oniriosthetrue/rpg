---
name: mj-dnd-app
description: >-
  Plan, architecture et procédure complets de l'app dédiée « MJ D&D » (Maître de Jeu
  solo D&D 5.2.1/SRD) — dépôt séparé /home/linus/mj-dnd, dépôt GitHub
  https://github.com/oniriosthetrue/rpg, exposée sur rpg.minervia.fr. Stack : frontend
  Next.js (apps/web, chat SSE + fiche perso + proxy clé API) + backend FastAPI/Pydantic-AI
  (apps/api : agent, outils moteur, RAG Qdrant, contrat JSON v1) + moteur de règles
  packages/dnd_perso (stdlib) + corpus packages/corpus/srd-5.2.1. Rejoint le réseau docker
  EXTERNE de la stack LLM qwen_3.8_vnimanieAI (litellm/embedding/vllm). USE FOR :
  (re)monter/déployer la stack (build api/web, up qdrant/api/web, ingestion corpus) ;
  comprendre le chemin chat (SSE events token/outil/fin/erreur) et le split outils
  OUTILS_CTX/OUTILS_PLAIN ; diagnostiquer les PIÈGES connus (réseau externe préfixé,
  modèle litellm « IA », streaming pydantic-ai 2.55 agent.iter, embeddings CPU-bound +
  troncature, PYTHONPATH packages) ; faire tourner/étendre les tests (72 tests) ; reprendre
  le projet là où il en est (terminé, options futures listées). NE PAS confondre avec le
  skill owui-mj-dnd (l'ancienne version Open WebUI, remplacée par cette app).
---

# MJ D&D — app dédiée (plan complet)

> Projet : `/home/linus/mj-dnd` · GitHub : `oniriosthetrue/rpg` · URL : **rpg.minervia.fr**
> Docs liées : `docs/CONTRAT-API-JDR.md`, `docs/ARCHITECTURE-JDR-OWUI.md`, `docs/PLAN-COMBAT.md`, `docs/PLAN-SCENARIO.md`
> Skill réseau : `routing-architecture` (dépôt qwen_3.8_vnimanieAI) · Skill ancêtre : `owui-mj-dnd` (version OWUI, dépassée)

## 0. Contraintes NON négociables

- **La stack LLM** (vllm, litellm, embedding) vit dans `qwen_3.8_vnimanieAI` et est lancée
  **uniquement par l'opérateur**. Ce dépôt ne démarre que `web`, `api`, `qdrant`.
- **Ici l'agent PEUT monter la stack mj-dnd** (build/up/ingest) — l'utilisateur l'a autorisé.
  Mais **jamais** la stack LLM.
- **Le LLM ne calcule jamais rien** (règle d'or) : tout ce qui est chiffré passe par un outil
  qui renvoie du JSON ; tout ce qui est factuel vient du RAG avec citation.
- **Ne pas `docker restart mj-api` pendant une ingestion** (la tue, exit 137).

## 1. Architecture (3 conteneurs)

```
Internet → Caddy (VPS) → NetBird → Traefik (serveur) → mj-web:3000 (Next.js)
                                                          │ proxy serveur (injecte X-API-Key)
                                                          ▼
                                          mj-api:8000 (FastAPI, interne, non exposé)
                                          ├─ agent Pydantic-AI (agent/agent.py)
                                          ├─ outils = moteur (agent/tools.py → routers/*)
                                          ├─ RAG (rag/ → Qdrant + embeddings)
                                          └─ postprocess/anti_meta.py
                                          mj-qdrant:6333 (interne)
```
- `web` et `api` rejoignent le réseau **externe** `qwen_38_vnimanieai_mynetwork` (configuré
  via `DOCKER_NETWORK` dans `.env`, reporté sous `networks.mynetwork.name`).
- `api` n'a **aucun port publié** : seul `web` l'appelle en HTTP interne (`http://api:8000`).
- La clé `X-API-Key` est injectée **côté serveur Next** (`apps/web/lib/api.ts`), jamais dans le navigateur.

## 2. Arborescence

```
apps/web/        Next.js App Router + Tailwind. layout/page/globals.css ;
                 components/{Chat,FichePerso,Markdown}.tsx ;
                 app/api/chat/route.ts (relay SSE) ; app/api/jdr/[...chemin]/route.ts (proxy GET) ;
                 lib/api.ts (enTetes/url) ; Dockerfile multi-stage standalone.
apps/api/        FastAPI. jdr_api/{main,commun}.py + routers/{chat,creation,personnages,combat,campagne,panel}.py ;
                 agent/{agent,tools,prompt}.py ; rag/{corpus,embeddings,qdrant_store,retriever}.py ;
                 postprocess/anti_meta.py ; openui/mj.py (logique métier perso) ; settings.py.
packages/dnd_perso/  moteur de règles stdlib (models,dice,combat,campagne,creation,extract,export,io).
packages/corpus/srd-5.2.1/  ~861 fiches markdown (sorts/objets/monstres/chapitres/tables).
scripts/ingest_corpus.py    embed + upsert le corpus dans Qdrant (idempotent).
tests/                      test_{combat,campagne,dnd_perso,agent,ui_routes}.py (72 tests).
```

## 3. Démarrage / déploiement

```bash
cd /home/linus/mj-dnd
cp .env.example .env   # puis renseigner (voir §4)
docker compose up -d qdrant
docker compose build api web
docker compose up -d api web
# Ingestion (une fois, ~2,5h CPU — en tâche de fond) :
docker exec -d mj-api sh -c 'cd /app && python3 -m scripts.ingest_corpus > /tmp/ingest.log 2>&1'
tail -f /tmp/ingest.log
```

Vérification (conteneurs internes, sans port publié) :
```bash
docker exec mj-api python3 -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
docker exec mj-web node -e "fetch('http://localhost:3000').then(r=>console.log(r.status))"
# RAG réel :
docker compose exec -T api python3 -c "from rag import retriever;print(retriever.recuperer_contexte('Boule de feu')[:200])"
```

## 4. `.env` — secrets repris de la stack LLM

Reprendre depuis `qwen_3.8_vnimanieAI/.env` : `LITELLM_MASTER_KEY` → `LITELLM_API_KEY`,
`DND_API_KEY`. **`MJ_MODEL=IA`** (le nom exposé par litellm `GET /v1/models`, PAS l'id vLLM).
`DOCKER_NETWORK=qwen_38_vnimanieai_mynetwork`. `EMBED_BASE_URL=http://embedding:8080/v1`,
`EMBED_MODEL_NAME=Qwen/Qwen3-Embedding-0.6B`.

## 5. PIÈGES connus (tous corrigés — ne pas régresser)

1. **Réseau externe** : le vrai nom est `qwen_38_vnimanieai_mynetwork` (Docker préfixe du
   nom de projet), PAS `mynetwork`. → `DOCKER_NETWORK` dans `.env` + `name:` sous networks.
2. **Modèle** : via litellm le modèle s'appelle **`IA`**, pas l'id vLLM.
3. **Dockerfile api** : `COPY packages/dnd_perso ./packages/dnd_perso` (PAS `./dnd_perso`) —
   PYTHONPATH=`/app/apps/api:/app/packages`.
4. **Streaming pydantic-ai 2.55** : `run_stream()` renvoie un `StreamedRunResult` SANS
   `__aiter__`. API correcte = `agent.iter(...)` → `async for node in run` →
   `agent.is_model_request_node(node)` / `is_call_tools_node(node)` → `node.stream(run.ctx)`
   → événements `PartStartEvent`/`PartDeltaEvent` (texte) et
   `FunctionToolCallEvent`/`FunctionToolResultEvent` (outils, `.part.tool_name`).
5. **Outils** : `agent.tool(f)` impose `RunContext[...]` en 1er param. Outils sans ctx →
   `agent.tool_plain(f)`. D'où `OUTILS_CTX` (3 : creation) vs `OUTILS_PLAIN` (16).
6. **Embeddings CPU-bound** : service `embedding` = ThreadingHTTPServer CPU. 503 « model is
   loading » après rechargement → re-tentatives dans `rag/embeddings.py`. Une fiche faisait
   206 000 caractères → encode() interminable → **troncature du texte vectorisé à
   `_MAX_EMBED_CAR=4000`** dans `rag/corpus.py` (le COMPLET reste dans le payload Qdrant
   pour citations). Batch ingest = 8. ~10 s/fiche → 861 fiches ≈ 2,5h.
7. **qdrant-client 1.19** : `search()` supprimé → `query_points(collection, query=vecteur,
   limit, with_payload=True).points`. `FieldIndexInfo` absent → schéma `"keyword"`.
8. **Collision d'id** : 861 fiches → 860 points Qdrant (deux fiches partagent un id dérivé).
   Sans impact.

## 6. Contrat chat SSE (`routers/chat.py`)

POST `/api/chat` body `{message, chat_id, historique:[{role,content}], personnage}`.
Flux : retrieval RAG (contexte + citations) → `agent.iter` → anti-méta → SSE.
Événements `event:` : `token` `{texte}` (brut, finalisé au `fin`), `outil` `{nom,etat:appel|retour}`,
`fin` `{texte}` (complet nettoyé), `erreur` `{message}`. Le frontend (`components/Chat.tsx`)
consomme ce flux et rafraîchit la fiche au `fin`.

## 7. Anti-métajeu (`postprocess/anti_meta.py`)

`nettoyer()` = `corriger_emphase` (du**X** → du **X**) + `masquer_stats_monstre`
(masque `CA : 15`/`PV : 7` en bloc — libellé reste, chiffre→• — mais PAS une valeur
différentielle « tu perds 5 PV ») + retrait des étiquettes `[MÉCANIQUE]`/`[NARRATION]`.

## 8. Tests (72)

```bash
cd /home/linus/mj-dnd
export PYTHONPATH="$PWD/apps/api:$PWD/packages"
export DND_CORPUS_DIR="$PWD/packages/corpus/srd-5.2.1"
export DND_PERSO_DIR="$PWD/data-perso" DND_COMBAT_DIR="$PWD/data-combat" DND_CAMPAGNE_DIR="$PWD/data-campagne"
PYDANTIC_AI_NO_BANNER=1 .venv/bin/python -m unittest tests.test_combat tests.test_campagne tests.test_dnd_perso tests.test_agent tests.test_ui_routes
```
`test_agent.py` (Phase 4) = déterministe via `pydantic_ai.models.function.FunctionModel(fake)` :
`fake(messages,info)` renvoie `ModelResponse(parts=[ToolCallPart(nom,args)])` au 1er tour puis
`TextPart`. 2e tour = un part `part_kind=='tool-return'` existe déjà. Enregistrer le VRAI outil
pour vérifier l'exécution moteur. Asserts combat : JSON contient `ordre`+`initiative`+`"id"`
(PAS `combat_id`). RAG : monkeypatch `retriever.embeddings.embed_un` +
`retriever.qdrant_store.rechercher` (→ renvoie des PAYLOAD dicts, pas des Fiche).

## 9. Git

Dépôt initialisé (`main`), LFS activé (`*.pdf filter=lfs` — aucun PDF commité, corpus en md).
Remote `origin` = https://github.com/oniriosthetrue/rpg, `main` poussée. `.gitignore` exclut
`.env`, `.venv/`, `node_modules/`, `data-*/` (état de jeu). `.env.example` est la référence.

## 10. État & options futures

**TERMINÉ** : Phases 0–4 backend, stack montée + validée bout-en-bout, routeur `rpg` concurrent
nettoyé (l'app récupère rpg.minervia.fr), ingestion 861/861, dépôt Git publié.
**UI v2 TERMINÉE** (2026-10) : refonte frontend multi-pages sous `apps/web/app/(app)/`
(chat multi-conversations + stop + citations, `/persos` fiche éditable + wizard, `/combat`,
`/campagne`). Client `lib/jdr.ts`, proxy `app/api/jdr/[...chemin]` (GET/POST/PATCH/DELETE),
`PersoContext`. Route backend ajoutée `GET /api/combat` (lister). Checkette recette :
`docs/SMOKE-UI.md`. Tests = **72** (68 + `tests/test_ui_routes.py`).

Options (non faites) :
- **Rappel hybride** : le vectoriel coiffe un nom exact court (« Cape d'invisibilité ») sur
  d'autres objets ; la périphrase marche bien. Durcir via BM25/keyword en complément.
- **CI GitHub Actions** : lancer les 72 tests au push.
- **Partie test** en conditions réelles (créer un vrai PJ, jouer une scène).
- **PDF SRD** hors repo (ne sert qu'à régénérer le corpus, déjà en markdown).

## 11. Référence API (routes + auth + enveloppe)

**Auth** : en-tête `X-API-Key` vérifié par `commun.autorise()` (lit `DND_API_KEY`). Vide =
accès libre. Sinon une enveloppe `{"ok":false,"v":1,"type":"erreur","erreur":…}` est renvoyée.
Côté prod, la clé est injectée par Next (`lib/api.ts`) — le navigateur ne la voit jamais.

**Enveloppe v1** (`commun.enveloppe`) : toute réponse porte `v:1` + `ok` + `type` + message
données. Ne jamais casser ce contrat (cf. `docs/CONTRAT-API-JDR.md`).

**Routes** (`jdr_api/routers/*`, toutes sous `/api` sauf `/health` et `/panel`) :

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | sonde (pas d'auth) |
| POST | `/api/chat` | chat MJ — **SSE** (§6) |
| POST | `/api/creation` | démarrer création (body `{chat_id}`) |
| POST | `/api/creation/{chat_id}/reponse` | réponse à une étape |
| GET | `/api/creation/{chat_id}/options` | options d'une étape (`?etape=`) |
| GET | `/api/creation/{chat_id}/etat` | état de la session de création |
| POST | `/api/creation/{chat_id}/finaliser` · `/abandon` | finaliser / abandonner |
| GET | `/api/personnages` · `/{nom}` | liste / fiche (dict + markdown) |
| PATCH | `/api/personnages/{nom}` | actions closes (`{actions:[{action,valeur}]}`) |
| DELETE | `/api/personnages/{nom}` | supprimer |
| POST | `/api/combat/ouvrir` | rencontre → ordre d'initiative (`id`, `ordre`, `actif`) |
| GET | `/api/combat/{id}` | état (ordre, tour, actif, PV/CA/conditions) |
| POST | `/api/combat/{id}/jet-monstre` · `/jet-joueur` | jets (serveur lance / enregistre) |
| POST | `/api/combat/{id}/tour-suivant` · `/cloturer` | avancement / fin |
| PATCH | `/api/combat/{id}` | `degats`/`soigner`/`condition` sur un combattant |
| GET | `/api/campagne` · `/{id}` | liste / état campagne |
| POST | `/api/campagne/ouvrir` · `/importer` | créer / importer un scénario |
| PATCH | `/api/campagne/{id}` | mutation d'intrigue (`action` + params) |
| POST | `/api/campagne/{id}/advisory` · `/cloturer` | avis difficulté / fin |
| GET | `/api/infos` | tooltips sorts/compétences (pour le panneau) |
| GET | `/panel` | page HTML fiche joueur (lecture seule, autonome) |

**Outils agent** (`agent/tools.py`) : wrappers in-process des routes ci-dessus. `OUTILS_CTX`
(3 : `nouveau_personnage`, `lister_les_options`, `abandonner_la_creation` — prennent
`RunContext[Deps]`, `Deps.chat_id` = session de création) ; `OUTILS_PLAIN` (16 autres).
