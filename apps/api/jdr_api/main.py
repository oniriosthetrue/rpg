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

from fastapi import FastAPI

from jdr_api.routers import campagne, chat, combat, creation, panel, personnages

app = FastAPI(
    title="mj-dnd-api",
    description=(
        "Backend MJ D&D 5.2.1 (SRD) : agent Pydantic-AI + moteur de règles + RAG. "
        "Contrat : docs/CONTRAT-API-JDR.md"
    ),
    version="1.0.0",
)

# Chat du MJ (agent + RAG + outils) — streaming SSE.
app.include_router(chat.router)
app.include_router(creation.router)
app.include_router(personnages.router)
app.include_router(combat.router)
app.include_router(campagne.router)
# Panneau HTML « fiche du joueur » (lecture seule, servi sous /jdr/panel via Traefik).
app.include_router(panel.router)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    """Sonde de vie (pour docker compose / healthcheck)."""
    return {"ok": True, "v": 1, "type": "sante", "service": "jdr-api"}
