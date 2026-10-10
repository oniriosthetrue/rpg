"""Route de chat du MJ — streaming SSE.

Flux : question du joueur → retrieval RAG (contexte SRD + citations) → run de
l'agent Pydantic-AI (outils = moteur de règles) → post-traitement anti-méta →
SSE. Le frontend n'a qu'à consommer les événements.

Événements SSE émis (champ `event:`) :
  - `token`   : un segment de texte du MJ (déjà nettoyé anti-méta)
  - `outil`   : un appel d'outil en cours (nom) — pour afficher « … le MJ consulte »
  - `fin`     : la réponse est terminée (contient le texte complet)
  - `erreur`  : une erreur est survenue
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import StreamingResponse

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)

from agent.agent import agent
from agent.tools import Deps
from jdr_api.commun import autorise
from postprocess import anti_meta
from rag import retriever

router = APIRouter()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/chat")
async def chat(
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> StreamingResponse:
    if (err := autorise(x_api_key)) is not None:
        raise HTTPException(status_code=403, detail=err["erreur"])

    message = str(body.get("message", "") or "").strip()
    chat_id = str(body.get("chat_id") or "defaut")
    historique = body.get("historique") or []
    if not message:
        raise HTTPException(status_code=400, detail="« message » requis.")

    # 1) Retrieval RAG : contexte SRD pertinent (citations incluses).
    contexte = retriever.recuperer_contexte(message)

    # 2) Construction du prompt utilisateur (contexte RAG + question).
    prompt = message if not contexte else f"{contexte}\n\n---\n\n{message}"

    async def flux() -> AsyncIterator[str]:
        texte_final: list[str] = []
        try:
            # API pydantic-ai 2.55 : on parcourt les noeuds du run et on streame
            # chaque noeud (requête modèle = texte ; appel d'outils = tool events).
            async with agent.iter(
                prompt, deps=Deps(chat_id=chat_id), message_history=_historique(historique)
            ) as run:
                async for node in run:
                    if agent.is_model_request_node(node):
                        async with node.stream(run.ctx) as flux_modele:
                            async for event in flux_modele:
                                if isinstance(event, PartStartEvent):
                                    part = event.part
                                    if isinstance(part, TextPart) and part.content:
                                        # Nettoyage différé : émis brut, finalisé au `fin`.
                                        texte_final.append(part.content)
                                        yield _sse("token", {"texte": part.content})
                                elif isinstance(event, PartDeltaEvent):
                                    delta = event.delta
                                    if (
                                        isinstance(delta, TextPartDelta)
                                        and delta.content_delta
                                    ):
                                        texte_final.append(delta.content_delta)
                                        yield _sse("token", {"texte": delta.content_delta})
                    elif agent.is_call_tools_node(node):
                        async with node.stream(run.ctx) as flux_outils:
                            async for event in flux_outils:
                                if isinstance(event, FunctionToolCallEvent):
                                    yield _sse(
                                        "outil",
                                        {
                                            "nom": event.part.tool_name,
                                            "etat": "appel",
                                        },
                                    )
                                elif isinstance(event, FunctionToolResultEvent):
                                    yield _sse(
                                        "outil",
                                        {
                                            "nom": event.part.tool_name,
                                            "etat": "retour",
                                        },
                                    )
            # Texte complet nettoyé (anti-méta appliqué sur l'ensemble).
            complet = anti_meta.nettoyer("".join(texte_final))
            yield _sse("fin", {"texte": complet})
        except Exception as exc:  # ne jamais casser le flux silencieusement
            yield _sse("erreur", {"message": f"Erreur agent : {exc}"})

    return StreamingResponse(
        flux(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _historique(historique: Any) -> list[ModelMessage]:
    """Reconstruit le message_history Pydantic-AI à partir de la conversation
    renvoyée par le frontend : [{role: "user"|"assistant", content: "…"}].

    On ne rejoue que les messages texte (les tours d'outils intermédiaires ne
    sont pas renvoyés par le client). Suffisant pour la continuité narrative.
    """
    messages: list[ModelMessage] = []
    if not isinstance(historique, list):
        return messages
    for item in historique:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).lower()
        contenu = str(item.get("content", "") or "")
        if not contenu:
            continue
        if role == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=contenu)]))
        elif role == "assistant":
            messages.append(ModelResponse(parts=[TextPart(content=contenu)]))
    return messages
