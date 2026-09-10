from __future__ import annotations

import asyncio
import logging
import unicodedata
from datetime import date, timedelta

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agent.graph import build_agent, model_candidates
from app.domain.models import (
    ConversationHistory,
    Course,
    Room,
    ScheduleChange,
    ScheduleChangeStatus,
    ScheduleEntry,
    ScheduleEntryStatus,
    Teacher,
    TimeSlot,
)
from app.services.system_config import get_gemini_model

logger = logging.getLogger(__name__)


def _is_transient_model_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    markers = (
        "503",
        "unavailable",
        "high demand",
        "resource exhausted",
        "429",
        "too many requests",
        "temporarily",
        "overloaded",
    )
    return any(m in text for m in markers)


def _is_model_not_found(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        m in text
        for m in (
            "404",
            "not_found",
            "no longer available",
            "is not found",
            "not found",
        )
    )


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def chat(
        self,
        message: str,
        *,
        external_user_id: str,
        channel: str = "api",
        teacher_id: int | None = None,
        actor_role: str = "admin",
    ) -> dict:
        extra = await self._build_context(teacher_id)
        history = await self._load_history(channel, external_user_id, limit=12)

        await self._save_message(channel, external_user_id, "user", message)

        local_reply = await self._local_command_response(
            message, actor_role=actor_role, teacher_id=teacher_id
        )
        if local_reply is not None:
            await self._save_message(
                channel, external_user_id, "assistant", local_reply
            )
            await self.session.commit()
            return {
                "reply": local_reply,
                "model": "moteur-local-fiable",
                "external_user_id": external_user_id,
                "channel": channel,
                "teacher_id": teacher_id,
            }

        preferred = await get_gemini_model(self.session)
        lc_messages = history + [HumanMessage(content=message)]
        reply: str | None = None
        used_model = preferred
        last_error: BaseException | None = None

        for model_name in model_candidates(preferred):
            for attempt in range(1, 4):
                try:
                    agent = await build_agent(
                        self.session,
                        extra_context=extra,
                        model_name=model_name,
                        actor_role=actor_role,
                        actor_teacher_id=teacher_id,
                    )
                    result = await agent.ainvoke({"messages": lc_messages})
                    reply = self._extract_reply(result["messages"])
                    used_model = model_name
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    if _is_model_not_found(exc):
                        logger.warning(
                            "Modèle Gemini %s indisponible — essai du suivant",
                            model_name,
                        )
                        break
                    if not _is_transient_model_error(exc):
                        raise
                    wait = min(2 ** attempt, 8)
                    logger.warning(
                        "Gemini %s tentative %s/3 échouée (%s) — retry dans %ss",
                        model_name,
                        attempt,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
            if reply is not None:
                break

        if reply is None:
            assert last_error is not None
            raise RuntimeError(
                "Aucun modèle Gemini disponible pour le moment "
                "(surcharge ou modèle retiré). Réessayez, ou changez le modèle "
                "dans Config IA (ex. gemini-3.5-flash-lite / gemini-3.6-flash)."
            ) from last_error

        await self._save_message(channel, external_user_id, "assistant", reply)
        await self.session.commit()

        return {
            "reply": reply,
            "model": used_model,
            "external_user_id": external_user_id,
            "channel": channel,
            "teacher_id": teacher_id,
        }

    async def _build_context(self, teacher_id: int | None) -> str | None:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        if teacher_id is None:
            return (
                "Canal administration authentifié. Identifie l'enseignant via "
                "list_teachers si le nom n'est pas clair. "
                f"Date du jour : {today.isoformat()}. Semaine courante : "
                f"{monday.isoformat()} à {sunday.isoformat()}. "
                "Les données peuvent être un jeu de démonstration : ne les présente "
                "jamais comme des observations de terrain."
            )
        teacher = await self.session.get(Teacher, teacher_id)
        if teacher is None:
            return f"teacher_id fourni={teacher_id} mais introuvable en base."
        return (
            f"Utilisateur courant = enseignant #{teacher.id} ({teacher.name}, "
            f"{teacher.email}). Priorise ses demandes. "
            f"Date du jour : {today.isoformat()}. Semaine courante : "
            f"{monday.isoformat()} à {sunday.isoformat()}."
        )

    async def _local_command_response(
        self, message: str, *, actor_role: str, teacher_id: int | None
    ) -> str | None:
        """Répond vite aux requêtes factuelles simples, sans dépendre du LLM."""
        normalized = "".join(
            char
            for char in unicodedata.normalize("NFD", message.lower())
            if unicodedata.category(char) != "Mn"
        )
        if any(term in normalized for term in ("bonjour", "aide", "que peux-tu")):
            return (
                "Bonjour. Je peux afficher le **planning de la semaine**, donner "
                "l'**état du système**, contrôler les **validations en attente** et "
                "accompagner le traitement d'une indisponibilité. Les modifications "
                "restent soumises à l'approbation de l'administration."
            )

        if any(term in normalized for term in ("etat du systeme", "resume", "synthese")):
            teacher_count = await self.session.scalar(
                select(func.count()).select_from(Teacher).where(Teacher.is_active.is_(True))
            ) or 0
            course_count = await self.session.scalar(
                select(func.count()).select_from(Course)
            ) or 0
            pending = await self.session.scalar(
                select(func.count()).select_from(ScheduleChange).where(
                    ScheduleChange.status == ScheduleChangeStatus.proposed
                )
            ) or 0
            return (
                "**État actuel du système**\n"
                f"- {teacher_count} enseignant(s) actif(s)\n"
                f"- {course_count} cours enregistré(s)\n"
                f"- {pending} proposition(s) en attente de validation\n\n"
                "Ces chiffres proviennent directement de la base de données."
            )

        if "validation" in normalized:
            pending = await self.session.scalar(
                select(func.count()).select_from(ScheduleChange).where(
                    ScheduleChange.status == ScheduleChangeStatus.proposed
                )
            ) or 0
            return (
                f"Il y a **{pending} proposition(s)** en attente. "
                "L'administration doit d'abord les approuver, puis les appliquer."
            )

        if "planning" in normalized and "semaine" in normalized:
            today = date.today()
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            stmt = (
                select(ScheduleEntry)
                .where(
                    ScheduleEntry.entry_date >= monday,
                    ScheduleEntry.entry_date <= sunday,
                    ScheduleEntry.status == ScheduleEntryStatus.scheduled,
                )
                .options(
                    selectinload(ScheduleEntry.course).selectinload(Course.teacher),
                    selectinload(ScheduleEntry.course).selectinload(Course.group),
                    selectinload(ScheduleEntry.room),
                    selectinload(ScheduleEntry.timeslot),
                )
                .order_by(ScheduleEntry.entry_date, ScheduleEntry.timeslot_id)
            )
            if actor_role == "teacher" and teacher_id is not None:
                stmt = stmt.join(Course).where(Course.teacher_id == teacher_id)
            rows = (await self.session.execute(stmt)).scalars().all()
            if not rows:
                return (
                    f"Aucune séance planifiée entre le {monday.strftime('%d/%m/%Y')} "
                    f"et le {sunday.strftime('%d/%m/%Y')}."
                )
            lines = ["**Planning de la semaine**"]
            for entry in rows:
                lines.append(
                    f"- **{entry.entry_date.strftime('%d/%m')} "
                    f"({entry.timeslot.start_time.strftime('%H:%M')} - "
                    f"{entry.timeslot.end_time.strftime('%H:%M')})** : "
                    f"{entry.course.title} · {entry.course.group.name} · "
                    f"{entry.room.name} · {entry.course.teacher.name} "
                    f"(séance #{entry.id})"
                )
            return "\n".join(lines)

        return None

    async def _load_history(
        self, channel: str, external_user_id: str, limit: int = 12
    ) -> list:
        result = await self.session.execute(
            select(ConversationHistory)
            .where(
                ConversationHistory.channel == channel,
                ConversationHistory.external_user_id == external_user_id,
            )
            .order_by(ConversationHistory.id.desc())
            .limit(limit)
        )
        rows = list(reversed(result.scalars().all()))
        messages: list = []
        for row in rows:
            if row.role == "user":
                messages.append(HumanMessage(content=row.content))
            elif row.role == "assistant":
                messages.append(AIMessage(content=row.content))
        return messages

    async def _save_message(
        self, channel: str, external_user_id: str, role: str, content: str
    ) -> None:
        self.session.add(
            ConversationHistory(
                channel=channel,
                external_user_id=external_user_id,
                role=role,
                content=content,
            )
        )

    @staticmethod
    def _extract_reply(messages: list) -> str:
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                if isinstance(msg.content, list):
                    parts = []
                    for block in msg.content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            parts.append(block)
                    text = "\n".join(p for p in parts if p).strip()
                    if text:
                        return text
                elif isinstance(msg.content, str) and msg.content.strip():
                    return msg.content.strip()
        return "Je n'ai pas pu produire de réponse."
