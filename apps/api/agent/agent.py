"""Assemblage de l'agent Pydantic-AI du MJ.

- Modèle : OpenAI-compatible via litellm (la stack existante).
- Déps d'exécution : le `chat_id` (clé de session de création), passé à chaque run.
- Outils : ceux de `agent/tools.py` (le cerveau règles, appelés en-process).
- Prompt système : `agent/prompt.py`.

Le LLM ne calcule jamais rien : il choisit un outil, le moteur renvoie du JSON.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from agent import tools
from agent.prompt import SYSTEM_PROMPT
from agent.tools import Deps
from settings import settings


def _construire() -> Agent[Deps]:
    modele = OpenAIChatModel(
        settings.mj_model,
        provider=OpenAIProvider(
            base_url=settings.litellm_base_url,
            api_key=settings.litellm_api_key or "none",
        ),
    )
    agent: Agent[Deps] = Agent(
        modele,
        deps_type=Deps,  # deps = contexte d'exécution (chat_id de session)
        system_prompt=SYSTEM_PROMPT,
        retries=2,
    )
    for outil in tools.OUTILS_CTX:
        agent.tool(outil)
    for outil in tools.OUTILS_PLAIN:
        agent.tool_plain(outil)
    return agent


# Agent partagé (initialisation paresseuse à l'import du module).
agent = _construire()
