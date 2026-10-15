"""Point d'entrée du microservice `jdr-api`.

Expose la création guidée de personnage D&D 5.2.1 (`openui/mj.py`) et la
gestion des fiches (`dnd_perso`) derrière une API HTTP JSON, conformément
au contrat `dnd/CONTRAT-API-JDR.md`.

Lancement en développement (depuis la racine du dépôt) :
    python3 -m uvicorn jdr_api.main:app --host 0.0.0.0 --port 8000

En production : voir `jdr_api/Dockerfile` (service `jdr-api` du docker-compose).
Le service n'est PAS exposé sur Traefik : il n'est joignable que par les
conteneurs du réseau docker `mynetwork` (Open WebUI), via `http://jdr-api:8000`.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from auth import scope, store
from jdr_api.routers import auth, campagne, chat, combat, creation, panel, personnages


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ouvre/crée la base d'authentification (SQLite) au démarrage.
    store.initialiser()
    yield


app = FastAPI(
    title="mj-dnd-api",
    description=(
        "Backend MJ D&D 5.2.1 (SRD) : agent Pydantic-AI + moteur de règles + RAG. "
        "Contrat : docs/CONTRAT-API-JDR.md"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Authentification par compte (publique : inscription/connexion/vérification).
app.include_router(auth.router)

# Routes protégées : chaque requête exige une session valide (`X-Session`) et
# isole les données du compte (sous-dossier `data/<user_id>/`).
_PROTEGE = {"dependencies": [Depends(scope.utilisateur_courant)]}

# Chat du MJ (agent + RAG + outils) — streaming SSE.
app.include_router(chat.router, **_PROTEGE)
app.include_router(creation.router, **_PROTEGE)
app.include_router(personnages.router, **_PROTEGE)
app.include_router(combat.router, **_PROTEGE)
app.include_router(campagne.router, **_PROTEGE)
# Panneau HTML « fiche du joueur » (lecture seule, servi sous /jdr/panel via Traefik).
app.include_router(panel.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    """Sonde de vie (pour docker compose / healthcheck)."""
    return {"ok": True, "v": 1, "type": "sante", "service": "jdr-api"}
