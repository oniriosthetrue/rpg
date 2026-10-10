# Backend MJ D&D — FastAPI + Pydantic-AI + RAG Qdrant.
# Construit depuis la RACINE du dépôt (context: ./), comme l'ancien jdr-api.
FROM python:3.12-slim

WORKDIR /app

# Dépendances d'abord (cache layer).
COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Code : moteur (dnd_perso), corpus, backend (apps/api), scripts.
# dnd_perso sous packages/ pour que PYTHONPATH=/app/packages le résolve.
COPY packages/dnd_perso ./packages/dnd_perso
COPY packages/corpus ./packages/corpus
COPY apps/api ./apps/api
COPY scripts ./scripts

# `apps/api` sur le PYTHONPATH (modules jdr_api, openui, agent, rag, settings…).
# `packages` sur le PYTHONPATH (module dnd_perso).
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api:/app/packages \
    DND_CORPUS_DIR=/app/packages/corpus/srd-5.2.1

# Les données (fiches perso, combat, campagne) sont des volumes montés par compose.
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "jdr_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
