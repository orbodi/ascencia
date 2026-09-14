"""Charge un jeu de démo (1 semaine de planning) + admin back-office.

Usage:
  python -m scripts.seed
  python -m scripts.seed --reset
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select, text

from app.admin.auth import hash_password
from app.agent.prompts import SYSTEM_PROMPT
from app.config import settings
from app.domain.db import AsyncSessionLocal
from app.domain.models import (
    AcademicLevel,
    AdminRole,
    AdminUser,
    AuditLog,
    Course,
    Room,
    ScheduleEntry,
    ScheduleEntryStatus,
    StudentGroup,
    SystemConfig,
    Teacher,
    TimeSlot,
)

TODAY = date.today()
WEEK_START = TODAY - timedelta(days=TODAY.weekday())

TABLES = [
    "distribution_deliveries",
    "presence_requests",
    "presence_campaigns",
    "processed_inbound_messages",
    "schedule_publications",
    "audit_logs",
    "conversation_history",
    "schedule_changes",
    "availabilities",
    "schedule_entries",
    "courses",
    "time_slots",
    "rooms",
    "student_groups",
    "teachers",
    "system_config",
    "admin_users",
    "academic_levels",
]


async def reset_demo_data(session) -> None:
    await session.execute(
        text("TRUNCATE TABLE " + ", ".join(TABLES) + " RESTART IDENTITY CASCADE")
    )
    await session.commit()
    print("Base démo réinitialisée (TRUNCATE).")


async def ensure_admin_and_config(session) -> None:
    admin = await session.scalar(
        select(AdminUser).where(AdminUser.username == settings.admin_username)
    )
    if admin is None:
        session.add(
            AdminUser(
                username=settings.admin_username,
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                role=AdminRole.superadmin,
                is_active=True,
            )
        )
        print(f"Admin créé: {settings.admin_username}")

    defaults = [
        (
            "agent_display_name",
            "Ascencia",
            "Nom affiché de l'assistant IA",
        ),
        (
            "agent_system_prompt",
            SYSTEM_PROMPT,
            "System prompt de l'agent (placeholder {agent_name})",
        ),
        ("gemini_model", settings.gemini_model, "Modèle Gemini actif"),
        (
            "reminder_days_ahead",
            str(settings.reminder_days_ahead),
            "Jours avant cours pour rappel présence",
        ),
        (
            "availability_form_url",
            settings.availability_form_url,
            "Lien du formulaire de collecte des disponibilités",
        ),
        (
            "planning_collection_start_date",
            "",
            "Date de début de collecte WhatsApp (AAAA-MM-JJ)",
        ),
        (
            "planning_publication_date",
            "",
            "Date d'envoi du planning aux administrateurs (AAAA-MM-JJ)",
        ),
        (
            "planning_target_week_start",
            "",
            "Lundi de la semaine cible du planning (AAAA-MM-JJ)",
        ),
    ]
    for key, value, description in defaults:
        existing = await session.scalar(
            select(SystemConfig).where(SystemConfig.key == key)
        )
        if existing is None:
            session.add(
                SystemConfig(
                    key=key,
                    value=value,
                    description=description,
                    updated_by="seed",
                )
            )
    await session.commit()


async def seed(reset: bool = False) -> None:
    async with AsyncSessionLocal() as session:
        if reset:
            await reset_demo_data(session)

        await ensure_admin_and_config(session)

        existing = await session.scalar(select(Teacher.id).limit(1))
        if existing:
            print("Seed planning déjà présent — admin/config OK.")
            return

        levels = [
            AcademicLevel(
                code="L3-INFO",
                label="L3 Informatique",
                degree="L",
                year=3,
                speciality="Informatique",
            ),
            AcademicLevel(
                code="M1-IA",
                label="M1 Intelligence Artificielle",
                degree="M",
                year=1,
                speciality="IA",
            ),
        ]
        session.add_all(levels)
        await session.flush()

        teachers = [
            Teacher(
                name="Ama Mensah (Démo)",
                email="ama.mensah@example.test",
                phone_whatsapp="+22800000001",
            ),
            Teacher(
                name="Koffi Lawson (Démo)",
                email="koffi.lawson@example.test",
                phone_whatsapp="+22800000002",
            ),
            Teacher(
                name="Akouvi Agbo (Démo)",
                email="akouvi.agbo@example.test",
                phone_whatsapp="+22800000003",
            ),
            Teacher(
                name="Komlan Dovi (Démo)",
                email="komlan.dovi@example.test",
                phone_whatsapp="+22800000004",
            ),
            Teacher(
                name="Yawa Adjevi (Démo)",
                email="yawa.adjevi@example.test",
                phone_whatsapp="+22800000005",
            ),
        ]
        groups = [
            StudentGroup(
                name="L3 Info A",
                whatsapp_group_id="grp_l3a",
                distribution_recipients=["+22800000101", "+22800000102"],
                student_count=35,
                academic_level_id=levels[0].id,
            ),
            StudentGroup(
                name="L3 Info B",
                whatsapp_group_id="grp_l3b",
                distribution_recipients=["+22800000201"],
                student_count=32,
                academic_level_id=levels[0].id,
            ),
            StudentGroup(
                name="M1 IA",
                whatsapp_group_id="grp_m1ia",
                distribution_recipients=["+22800000301"],
                student_count=28,
                academic_level_id=levels[1].id,
            ),
        ]
        rooms = [
            Room(name="A101", capacity=40),
            Room(name="B202", capacity=30),
            Room(name="C305", capacity=50),
            Room(name="Lab Info", capacity=28),
        ]

        slots: list[TimeSlot] = []
        day_names = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
        bands = [
            (time(8, 0), time(10, 0), "08-10"),
            (time(10, 15), time(12, 15), "10h15-12h15"),
        ]
        for dow in range(5):
            for start, end, band in bands:
                slots.append(
                    TimeSlot(
                        day_of_week=dow,
                        start_time=start,
                        end_time=end,
                        label=f"{day_names[dow]} {band}",
                    )
                )

        session.add_all(teachers + groups + rooms + slots)
        await session.flush()

        courses = [
            Course(
                title="Algorithmique",
                teacher_id=teachers[0].id,
                group_id=groups[0].id,
                planned_minutes=12 * 60,
            ),
            Course(
                title="Bases de données",
                teacher_id=teachers[1].id,
                group_id=groups[0].id,
                planned_minutes=10 * 60,
            ),
            Course(
                title="Réseaux",
                teacher_id=teachers[2].id,
                group_id=groups[1].id,
                planned_minutes=10 * 60,
            ),
            Course(
                title="Machine Learning",
                teacher_id=teachers[3].id,
                group_id=groups[2].id,
                planned_minutes=12 * 60,
            ),
            Course(
                title="Projet tutoré",
                teacher_id=teachers[4].id,
                group_id=groups[2].id,
                planned_minutes=8 * 60,
            ),
            Course(
                title="Python avancé",
                teacher_id=teachers[0].id,
                group_id=groups[1].id,
                planned_minutes=10 * 60,
            ),
        ]
        session.add_all(courses)
        await session.flush()

        slot_by_key = {(s.day_of_week, s.start_time): s for s in slots}
        plan = [
            (0, 0, 0, time(8, 0)),
            (1, 1, 1, time(8, 0)),
            (0, 0, 2, time(8, 0)),
            (2, 2, 2, time(10, 15)),
            (3, 3, 3, time(8, 0)),
            (5, 1, 3, time(10, 15)),
            (4, 2, 4, time(8, 0)),
        ]
        entries: list[ScheduleEntry] = []
        for course_idx, room_idx, dow, start in plan:
            slot = slot_by_key[(dow, start)]
            entry_date = WEEK_START + timedelta(days=dow)
            entries.append(
                ScheduleEntry(
                    course_id=courses[course_idx].id,
                    room_id=rooms[room_idx].id,
                    timeslot_id=slot.id,
                    entry_date=entry_date,
                    status=ScheduleEntryStatus.scheduled,
                )
            )

        session.add_all(entries)
        session.add(
            AuditLog(
                action="seed_demo",
                payload={
                    "week_start": WEEK_START.isoformat(),
                    "teachers": len(teachers),
                    "entries": len(entries),
                    "seeded_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        await session.commit()
        print(
            f"Seed OK — semaine du {WEEK_START.isoformat()} "
            f"({len(teachers)} profs, {len(entries)} séances)."
        )
        scenario_day = WEEK_START + timedelta(days=2)
        print(
            "Scénario démo : Ama Mensah (Démo) indisponible le mercredi "
            f"{scenario_day.isoformat()}."
        )
        print(f"Back-office: {settings.admin_username} / (ADMIN_PASSWORD)")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    asyncio.run(seed(reset=reset))
