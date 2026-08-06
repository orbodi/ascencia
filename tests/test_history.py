import pytest

from app.domain.models import AuditLog
from app.services.history_service import HistoryService


@pytest.mark.asyncio
async def test_history_confirmations_and_reschedules(session):
    session.add_all(
        [
            AuditLog(
                action="presence_confirmed",
                payload={
                    "entry_id": 1,
                    "teacher_id": 1,
                    "course_title": "Algo",
                    "entry_date": "2026-08-03",
                },
            ),
            AuditLog(
                action="apply_schedule_change",
                payload={
                    "entry_id": 2,
                    "teacher_id": 2,
                    "course_title": "Réseaux",
                    "after": {"entry_date": "2026-08-06"},
                },
            ),
            AuditLog(action="seed_demo", payload={}),
        ]
    )
    await session.commit()

    all_items = await HistoryService(session).teacher_actions(kind="all")
    assert all_items["summary"]["confirmations"] == 1
    assert all_items["summary"]["reschedules"] == 1

    only_conf = await HistoryService(session).teacher_actions(kind="confirmations")
    assert only_conf["count"] == 1
    assert only_conf["items"][0]["action"] == "presence_confirmed"
