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

from fastapi import APIRouter, Body, Header, HTTPException, Request
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
from openui import mj
from postprocess import anti_meta
from rag import retriever

router = APIRouter()


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/api/chat")
async def chat(
    request: Request,
    body: dict[str, Any] = Body(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> StreamingResponse:
    if (err := autorise(x_api_key)) is not None:
        raise HTTPException(status_code=403, detail=err["erreur"])

    message = str(body.get("message", "") or "").strip()
    chat_id = str(body.get("chat_id") or "defaut")
    campagne_id = str(body.get("campagne_id") or "").strip()
    personnage_nom = str(body.get("personnage") or "").strip()
    historique = body.get("historique") or []
    # Mode débutant (persistant, par conversation) et demande d'indice ponctuelle.
    # Les deux déclenchent une piste en prose ; aucun des deux = aucun indice.
    hint_mode = bool(body.get("hint_mode"))
    demande_indice = bool(body.get("demande_indice"))
    if not message:
        raise HTTPException(status_code=400, detail="« message » requis.")

    # 1) Retrieval RAG : contexte SRD pertinent + citations structurées.
    contexte = retriever.recuperer_contexte(message)
    sources = retriever.recuperer_sources(message)

    # 2) Construction du prompt utilisateur (contexte RAG + question).
    prompt = message if not contexte else f"{contexte}\n\n---\n\n{message}"

    # 2bis) Campagne active choisie dans l'app : on l'ancre explicitement pour que
    # le MJ cible la bonne campagne (sinon il devrait la deviner via la liste).
    if campagne_id:
        prompt = (
            f"[Campagne active : `{campagne_id}`. C'est LA campagne sur laquelle tu "
            f"travailles : passe cet identifiant à tous les outils de campagne "
            f"(etat_de_la_campagne, faire_avancer_la_campagne, …) sans le redemander "
            f"au joueur.]\n\n{prompt}"
        )

    # 2quater) Personnage actif choisi dans l'app : on ANCRE sa fiche complète
    # (dont `## Sorts connus`) dans le prompt. Sans ça, le MJ doit deviner le PJ
    # et penser à appeler `charger_le_personnage` ; s'il ne le fait pas, il n'a
    # aucune liste de sorts et peut en INVENTER un que le perso ne possède pas.
    # La fiche injectée rend la contrainte « uniquement les sorts de la fiche »
    # vérifiable à chaque tour, sans appel d'outil.
    if personnage_nom:
        fiche = mj.charger_personnage(personnage_nom)
        if fiche.get("ok") and fiche.get("fiche"):
            prompt = (
                f"[Personnage actif du joueur : **{personnage_nom}**. Voici sa fiche "
                f"officielle et à jour. RÈGLE ABSOLUE : ce personnage ne peut lancer "
                f"QUE les sorts listés dans la section `## Sorts connus` ci-dessous, "
                f"et uniquement ceux dont le niveau est autorisé par son niveau. "
                f"N'invente, ne suggère et ne décris JAMAIS un sort absent de cette "
                f"liste — si le joueur en demande un absent, dis qu'il ne le connaît "
                f"pas et propose une alternative parmi ses sorts ou une approche non "
                f"magique. Pour tout changement d'état (PV, or, objets, sorts), "
                f"passe le nom `{personnage_nom}` à `modifier_le_personnage`.]\n\n"
                f"{fiche['fiche']}\n\n---\n\n{prompt}"
            )

    # 2ter) Mode débutant / demande d'indice : le joueur réclame un coup de pouce.
    # On LÈVE explicitement l'interdiction du menu de choix pour CE tour, mais on
    # exige une unique piste en PROSE (jamais de liste, de tableau ni de jets
    # proposés). Sans cette consigne, aucune aide n'est donnée (comportement expert).
    if hint_mode or demande_indice:
        prompt = (
            "[Mode débutant actif pour ce tour : le joueur te demande un coup de "
            "pouce. À la toute fin de ta réponse, après la narration, ajoute "
            "**une seule et unique piste en prose** — une phrase (deux maximum) qui "
            "lui chuchote une direction ou la compétence la plus pertinente pour la "
            "situation présente. Cette piste reste dans la voix du MJ, sans révéler "
            "les mécaniques cachées. INTERDIT : liste à puces, tableau, menu "
            "d'options numéroté, bloc « Tu peux : », énumération de jets. Une seule "
            "phrase de conseil, en prose, puis tu t'arrêtes.]\n\n"
            f"{prompt}"
        )

    async def _run(
        prompt_texte: str, texte_final: list[str]
    ) -> AsyncIterator[str]:
        """Exécute l'agent et streame token/outil ; remplit ``texte_final``
        (brut, non nettoyé) au fil de l'eau. Ne s'occupe PAS du `fin`."""
        # API pydantic-ai 2.55 : on parcourt les noeuds du run et on streame
        # chaque noeud (requête modèle = texte ; appel d'outils = tool events).
        async with agent.iter(
            prompt_texte,
            deps=Deps(
                chat_id=chat_id,
                campagne_id=campagne_id,
                hint_mode=hint_mode,
                demande_indice=demande_indice,
            ),
            message_history=_historique(historique),
        ) as run:
            async for node in run:
                # Stop serveur : si le client a fermé le flux (bouton Stop),
                # on interrompt le run pour libérer le GPU au plus tôt.
                if await request.is_disconnected():
                    return
                if agent.is_model_request_node(node):
                    async with node.stream(run.ctx) as flux_modele:
                        async for event in flux_modele:
                            if await request.is_disconnected():
                                return
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
                                    {"nom": event.part.tool_name, "etat": "appel"},
                                )
                            elif isinstance(event, FunctionToolResultEvent):
                                yield _sse(
                                    "outil",
                                    {"nom": event.part.tool_name, "etat": "retour"},
                                )

    async def flux() -> AsyncIterator[str]:
        # Citations émises dès le début (le frontend peut les afficher sous le message).
        if sources:
            yield _sse("citations", {"sources": sources})
        try:
            # Run unique, streaming en direct. La mécanique des dés est désormais
            # arbitrée par l'outil `enregistrer_le_jet_hors_combat` (et les outils de
            # combat) : le LLM ne lance plus jamais un dé lui-même, il n'y a donc plus
            # lieu de filtrer/relancer a posteriori une réponse qui en contiendrait un.
            texte_final: list[str] = []
            async for chunk in _run(prompt, texte_final):
                yield chunk
            if await request.is_disconnected():
                return
            # Mode expert (aucun coup de pouce demandé) : on retire la question de
            # décision en queue (« Que fais-tu ? ») — le MJ doit avancer le récit.
            expert = not (hint_mode or demande_indice)
            complet = anti_meta.nettoyer("".join(texte_final), expert=expert)
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
