from datetime import date, datetime, time, timezone

from app.services.planning_rules import (
    BlockingAvailability,
    CandidateCheck,
    OccupiedEntry,
    SlotWindow,
    detect_conflicts,
    times_overlap,
    windows_overlap,
)


def test_times_overlap():
    assert times_overlap(time(8, 0), time(10, 0), time(9, 0), time(11, 0))
    assert not times_overlap(time(8, 0), time(10, 0), time(10, 0), time(12, 0))


def test_windows_different_days_do_not_overlap():
    a = SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0))
    b = SlotWindow(date(2026, 8, 6), time(8, 0), time(10, 0))
    assert not windows_overlap(a, b)


def test_detect_teacher_room_group_conflicts():
    candidate = CandidateCheck(
        teacher_id=1,
        group_id=10,
        room_id=100,
        room_capacity=40,
        student_count=35,
        window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
        ignore_entry_id=1,
    )
    occupied = [
        OccupiedEntry(
            entry_id=2,
            teacher_id=1,
            group_id=11,
            room_id=101,
            window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
        ),
        OccupiedEntry(
            entry_id=3,
            teacher_id=2,
            group_id=10,
            room_id=100,
            window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
        ),
    ]
    conflicts = detect_conflicts(candidate, occupied, [])
    codes = {c.code for c in conflicts}
    assert "teacher_busy" in codes
    assert "room_busy" in codes
    assert "group_busy" in codes


def test_availability_blocks_candidate():
    candidate = CandidateCheck(
        teacher_id=1,
        group_id=10,
        room_id=100,
        room_capacity=40,
        student_count=20,
        window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
    )
    blocks = [
        BlockingAvailability(
            teacher_id=1,
            start_at=datetime(2026, 8, 5, 0, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 8, 5, 23, 59, tzinfo=timezone.utc),
            reason="absent",
        )
    ]
    conflicts = detect_conflicts(candidate, [], blocks)
    assert any(c.code == "teacher_unavailable" for c in conflicts)


def test_room_capacity():
    candidate = CandidateCheck(
        teacher_id=1,
        group_id=10,
        room_id=100,
        room_capacity=20,
        student_count=35,
        window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
    )
    conflicts = detect_conflicts(candidate, [], [])
    assert conflicts[0].code == "room_capacity"


def test_ignore_same_entry():
    candidate = CandidateCheck(
        teacher_id=1,
        group_id=10,
        room_id=100,
        room_capacity=40,
        student_count=20,
        window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
        ignore_entry_id=9,
    )
    occupied = [
        OccupiedEntry(
            entry_id=9,
            teacher_id=1,
            group_id=10,
            room_id=100,
            window=SlotWindow(date(2026, 8, 5), time(8, 0), time(10, 0)),
        )
    ]
    assert detect_conflicts(candidate, occupied, []) == []
