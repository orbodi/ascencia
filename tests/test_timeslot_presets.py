from datetime import time

import pytest
from sqlalchemy import select

from app.admin.routes.schedule import (
    STANDARD_TIMESLOT_PRESET_BANDS,
    apply_standard_timeslot_presets_to_session,
)
from app.domain.models import TimeSlot


@pytest.mark.asyncio
async def test_creates_three_bands_per_selected_day(session):
    rows = await apply_standard_timeslot_presets_to_session(session, [0, 1])

    assert len(rows) == 6  # 3 bandes x 2 jours
    by_day: dict[int, list[TimeSlot]] = {}
    for slot in rows:
        by_day.setdefault(slot.day_of_week, []).append(slot)
    for day, slots in by_day.items():
        keys = {(s.start_time, s.end_time) for s in slots}
        assert keys == {(band[0], band[1]) for band in STANDARD_TIMESLOT_PRESET_BANDS}


@pytest.mark.asyncio
async def test_morning_band_is_shared_between_days_not_duplicated_per_group(session):
    rows = await apply_standard_timeslot_presets_to_session(session, [0])
    morning = [s for s in rows if s.start_time == time(8, 0) and s.end_time == time(12, 0)]
    assert len(morning) == 1


@pytest.mark.asyncio
async def test_afternoon_and_evening_bands_are_distinct(session):
    rows = await apply_standard_timeslot_presets_to_session(session, [0])
    afternoon = [s for s in rows if s.start_time == time(13, 0)]
    evening = [s for s in rows if s.start_time == time(18, 0)]
    assert len(afternoon) == 1
    assert len(evening) == 1
    assert "B1-B2" in afternoon[0].label
    assert "B3-M1-M2" in evening[0].label
    # Rien entre 13h30 et 18h00 pour le groupe B3/M1/M2 (voulu : cours du
    # soir uniquement, cf. échange avec l'administration).
    assert afternoon[0].end_time == time(17, 0)
    assert evening[0].start_time == time(18, 0)


@pytest.mark.asyncio
async def test_idempotent_no_duplicates_on_second_call(session):
    await apply_standard_timeslot_presets_to_session(session, [0, 1, 2, 3, 4])
    await apply_standard_timeslot_presets_to_session(session, [0, 1, 2, 3, 4])

    all_slots = (await session.execute(select(TimeSlot))).scalars().all()
    assert len(all_slots) == 15  # 3 bandes x 5 jours, pas de doublons


@pytest.mark.asyncio
async def test_does_not_touch_or_duplicate_a_manually_created_slot_with_same_hours(
    session,
):
    manual = TimeSlot(
        day_of_week=0,
        start_time=time(8, 0),
        end_time=time(12, 0),
        label="Créneau personnalisé du lundi",
    )
    session.add(manual)
    await session.commit()

    rows = await apply_standard_timeslot_presets_to_session(session, [0])

    morning = [s for s in rows if s.start_time == time(8, 0) and s.end_time == time(12, 0)]
    assert len(morning) == 1
    assert morning[0].label == "Créneau personnalisé du lundi"


@pytest.mark.asyncio
async def test_monday_to_friday_default_labels_stay_within_column_length(session):
    rows = await apply_standard_timeslot_presets_to_session(session, [0, 1, 2, 3, 4])
    assert all(len(s.label) <= 40 for s in rows)
