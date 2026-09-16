"""CRUD et helpers pour les programmes pédagogiques multi-semaines."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.models import (
    AcademicLevel,
    Course,
    CurriculumPlan,
    CurriculumWeekItem,
    StudentGroup,
)


class CurriculumService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_plans(self) -> list[CurriculumPlan]:
        result = await self.session.execute(
            select(CurriculumPlan)
            .options(
                selectinload(CurriculumPlan.academic_level),
                selectinload(CurriculumPlan.items).selectinload(
                    CurriculumWeekItem.course
                ),
            )
            .order_by(CurriculumPlan.academic_level_id, CurriculumPlan.semester)
        )
        return list(result.scalars().all())

    async def get_plan(self, plan_id: int) -> CurriculumPlan | None:
        result = await self.session.execute(
            select(CurriculumPlan)
            .where(CurriculumPlan.id == plan_id)
            .options(
                selectinload(CurriculumPlan.academic_level),
                selectinload(CurriculumPlan.items).selectinload(
                    CurriculumWeekItem.course
                ),
            )
        )
        return result.scalar_one_or_none()

    async def create_plan(
        self,
        *,
        academic_level_id: int,
        semester: int = 1,
        week_count: int = 6,
    ) -> CurriculumPlan:
        level = await self.session.get(AcademicLevel, academic_level_id)
        if level is None:
            raise ValueError("Parcours introuvable")
        if week_count < 1 or week_count > 52:
            raise ValueError("week_count doit être entre 1 et 52")
        if semester < 1 or semester > 2:
            raise ValueError("semester doit être 1 ou 2")
        existing = await self.session.scalar(
            select(CurriculumPlan).where(
                CurriculumPlan.academic_level_id == academic_level_id,
                CurriculumPlan.semester == semester,
            )
        )
        if existing:
            raise ValueError("Un programme existe déjà pour ce parcours / semestre")
        plan = CurriculumPlan(
            academic_level_id=academic_level_id,
            semester=semester,
            week_count=week_count,
        )
        self.session.add(plan)
        await self.session.commit()
        loaded = await self.get_plan(plan.id)
        assert loaded is not None
        return loaded

    async def update_plan(
        self,
        plan_id: int,
        *,
        week_count: int | None = None,
        semester: int | None = None,
    ) -> CurriculumPlan:
        plan = await self.get_plan(plan_id)
        if plan is None:
            raise ValueError("Programme introuvable")
        if week_count is not None:
            if week_count < 1 or week_count > 52:
                raise ValueError("week_count doit être entre 1 et 52")
            # Drop items beyond new horizon
            for item in list(plan.items):
                if item.week_index > week_count:
                    await self.session.delete(item)
            plan.week_count = week_count
        if semester is not None:
            if semester < 1 or semester > 2:
                raise ValueError("semester doit être 1 ou 2")
            clash = await self.session.scalar(
                select(CurriculumPlan).where(
                    CurriculumPlan.academic_level_id == plan.academic_level_id,
                    CurriculumPlan.semester == semester,
                    CurriculumPlan.id != plan.id,
                )
            )
            if clash:
                raise ValueError("Un programme existe déjà pour ce semestre")
            plan.semester = semester
        await self.session.commit()
        loaded = await self.get_plan(plan_id)
        assert loaded is not None
        return loaded

    async def delete_plan(self, plan_id: int) -> None:
        plan = await self.session.get(CurriculumPlan, plan_id)
        if plan is None:
            raise ValueError("Programme introuvable")
        await self.session.delete(plan)
        await self.session.commit()

    async def replace_week_items(
        self,
        plan_id: int,
        week_index: int,
        items: list[dict[str, int]],
    ) -> CurriculumPlan:
        plan = await self.get_plan(plan_id)
        if plan is None:
            raise ValueError("Programme introuvable")
        if week_index < 1 or week_index > plan.week_count:
            raise ValueError(f"week_index doit être entre 1 et {plan.week_count}")

        course_ids = [int(item["course_id"]) for item in items]
        if len(course_ids) != len(set(course_ids)):
            raise ValueError("Un même cours ne peut apparaître qu'une fois par semaine")

        courses = (
            await self.session.execute(
                select(Course)
                .where(Course.id.in_(course_ids))
                .options(selectinload(Course.group))
            )
        ).scalars().all() if course_ids else []
        course_by_id = {c.id: c for c in courses}
        if len(course_by_id) != len(course_ids):
            raise ValueError("Un ou plusieurs cours sont introuvables")

        for course in courses:
            group: StudentGroup | None = course.group
            if group is None or group.academic_level_id != plan.academic_level_id:
                raise ValueError(
                    f"Le cours « {course.title} » n'appartient pas à ce parcours"
                )
            if course.semester != plan.semester:
                raise ValueError(
                    f"Le cours « {course.title} » n'est pas du semestre {plan.semester}"
                )

        for existing in list(plan.items):
            if existing.week_index == week_index:
                await self.session.delete(existing)
        await self.session.flush()

        warnings: list[str] = []
        for raw in items:
            sessions = int(raw.get("sessions_count", 1))
            if sessions < 1 or sessions > 20:
                raise ValueError("sessions_count doit être entre 1 et 20")
            course = course_by_id[int(raw["course_id"])]
            planned_sessions = max(1, course.planned_minutes // course.duration_minutes)
            # Soft volume check across whole plan after replace
            self.session.add(
                CurriculumWeekItem(
                    plan_id=plan.id,
                    week_index=week_index,
                    course_id=course.id,
                    sessions_count=sessions,
                )
            )
            _ = planned_sessions  # used below after flush

        await self.session.commit()
        loaded = await self.get_plan(plan_id)
        assert loaded is not None
        volume_warnings = self._volume_warnings(loaded)
        # Attach transient warnings via generation isn't needed; API can recompute
        loaded._volume_warnings = volume_warnings  # type: ignore[attr-defined]
        return loaded

    def _volume_warnings(self, plan: CurriculumPlan) -> list[str]:
        minutes_by_course: Counter[int] = Counter()
        title_by_course: dict[int, str] = {}
        duration_by_course: dict[int, int] = {}
        planned_by_course: dict[int, int] = {}
        for item in plan.items:
            if item.course is None:
                continue
            minutes_by_course[item.course_id] += (
                item.sessions_count * item.course.duration_minutes
            )
            title_by_course[item.course_id] = item.course.title
            duration_by_course[item.course_id] = item.course.duration_minutes
            planned_by_course[item.course_id] = item.course.planned_minutes
        warnings: list[str] = []
        for course_id, minutes in minutes_by_course.items():
            planned = planned_by_course.get(course_id, 0)
            if minutes > planned:
                warnings.append(
                    f"« {title_by_course[course_id]} » : {minutes} min prévues au "
                    f"programme > volume cours ({planned} min)"
                )
        return warnings

    def serialize(self, plan: CurriculumPlan) -> dict[str, Any]:
        weeks: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for item in sorted(plan.items, key=lambda i: (i.week_index, i.id)):
            weeks[item.week_index].append(
                {
                    "id": item.id,
                    "course_id": item.course_id,
                    "course_title": item.course.title if item.course else None,
                    "sessions_count": item.sessions_count,
                    "duration_minutes": item.course.duration_minutes
                    if item.course
                    else None,
                }
            )
        week_list = [
            {"week_index": idx, "items": weeks.get(idx, [])}
            for idx in range(1, plan.week_count + 1)
        ]
        return {
            "id": plan.id,
            "academic_level_id": plan.academic_level_id,
            "academic_level_code": plan.academic_level.code
            if plan.academic_level
            else None,
            "academic_level_label": plan.academic_level.label
            if plan.academic_level
            else None,
            "semester": plan.semester,
            "week_count": plan.week_count,
            "weeks": week_list,
            "volume_warnings": getattr(plan, "_volume_warnings", None)
            or self._volume_warnings(plan),
        }

    async def intentions_for_week(
        self, academic_week: int
    ) -> tuple[dict[int, int], set[int], list[str]]:
        """Retourne (course_id→sessions, level_ids sous plan actif, warnings).

        level_ids = parcours dont le plan couvre cette semaine académique.
        """
        plans = await self.list_plans()
        intentions: Counter[int] = Counter()
        active_levels: set[int] = set()
        warnings: list[str] = []
        for plan in plans:
            if academic_week > plan.week_count:
                warnings.append(
                    f"Semaine {academic_week} hors programme "
                    f"{plan.academic_level.code if plan.academic_level else plan.id} "
                    f"(S{plan.semester}, {plan.week_count} sem.) — fallback volume"
                )
                continue
            active_levels.add(plan.academic_level_id)
            for item in plan.items:
                if item.week_index == academic_week:
                    intentions[item.course_id] += item.sessions_count
        return dict(intentions), active_levels, warnings
