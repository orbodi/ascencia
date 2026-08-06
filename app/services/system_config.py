"""Lecture de la configuration système (prompt, modèle, nom IA, etc.)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import SYSTEM_PROMPT
from app.config import settings
from app.domain.models import SystemConfig

KEY_PROMPT = "agent_system_prompt"
KEY_MODEL = "gemini_model"
KEY_REMINDER_DAYS = "reminder_days_ahead"
KEY_AGENT_NAME = "agent_display_name"

DEFAULT_AGENT_NAME = "Ascencia"


async def get_config_value(
    session: AsyncSession, key: str, default: str | None = None
) -> str | None:
    row = await session.scalar(select(SystemConfig).where(SystemConfig.key == key))
    if row is None:
        return default
    return row.value


async def get_agent_name(session: AsyncSession) -> str:
    value = await get_config_value(session, KEY_AGENT_NAME, DEFAULT_AGENT_NAME)
    name = (value or DEFAULT_AGENT_NAME).strip()
    return name or DEFAULT_AGENT_NAME


FORMAT_HINT = """

Format d'affichage (UI back-office) :
- Planning : une ligne par séance au format
  - **Mardi 04/08 (08:00 - 10:00)** : *Cours* (Groupe) avec Prof en salle X (Séance #ID)
  Pas de tableau markdown ni HTML.
- Options de report : liste numérotée 1. 2. 3.
- Heures restantes : « Titre : Xh restantes (Yh faites / Zh prévues) »
"""


async def get_system_prompt(session: AsyncSession) -> str:
    agent_name = await get_agent_name(session)
    raw = await get_config_value(session, KEY_PROMPT)
    template = raw if raw else SYSTEM_PROMPT
    try:
        prompt = template.format(agent_name=agent_name)
    except (KeyError, ValueError, IndexError):
        if agent_name.lower() not in template.lower():
            prompt = (
                f"Tu es {agent_name}, assistant IA de gestion des emplois du temps.\n"
                f"Présente-toi uniquement sous le nom « {agent_name} ».\n\n"
                f"{template}"
            )
        else:
            prompt = template
    if "Format d'affichage" not in prompt:
        prompt = prompt.rstrip() + FORMAT_HINT
    return prompt


async def get_gemini_model(session: AsyncSession) -> str:
    value = await get_config_value(session, KEY_MODEL)
    return value if value else settings.gemini_model
