from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools_factory import build_planning_tools
from app.config import settings
from app.services.system_config import get_gemini_model, get_system_prompt

# Modèles actuels (Gemini 3.x) — les 2.x sont retirés pour les nouveaux comptes
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]


async def build_agent(
    session: AsyncSession,
    extra_context: str | None = None,
    *,
    model_name: str | None = None,
    actor_role: str = "admin",
    actor_teacher_id: int | None = None,
):
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY manquante dans .env — impossible de démarrer l'agent."
        )

    system_prompt = await get_system_prompt(session)
    resolved_model = model_name or await get_gemini_model(session)
    prompt = system_prompt
    if extra_context:
        prompt = f"{system_prompt}\n\nContexte session:\n{extra_context}"

    llm = ChatGoogleGenerativeAI(
        model=resolved_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.2,
        max_retries=2,
    )
    tools = build_planning_tools(
        session,
        actor_role=actor_role,
        actor_teacher_id=actor_teacher_id,
    )
    return create_react_agent(model=llm, tools=tools, prompt=prompt)


def model_candidates(preferred: str) -> list[str]:
    ordered = [preferred]
    for m in FALLBACK_MODELS:
        if m not in ordered:
            ordered.append(m)
    return ordered
