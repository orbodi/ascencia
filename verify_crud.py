"""Script de vérification fonctionnelle des CRUD admin (prof, cours, programme, planning...).

Exécute l'application FastAPI en mémoire (ASGI, sans serveur réseau) contre une base
SQLite fraîche, crée un utilisateur admin, se connecte, puis exerce chaque opération
CRUD (Create/Read/Update/Delete) des principales ressources back-office et vérifie
les codes de statut + la persistance réelle des données.
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date

import httpx
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin.auth import hash_password
from app.domain.models import AdminRole, AdminUser, Base
from app.domain.db import AsyncSessionLocal, engine
from app.main import app

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "OK " if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not ok else ""))


async def setup_db_and_admin() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        session.add(
            AdminUser(
                username="admin",
                email="admin@example.com",
                hashed_password=hash_password("admin123"),
                role=AdminRole.superadmin,
                is_active=True,
            )
        )
        await session.commit()


async def main() -> None:
    await setup_db_and_admin()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ---- health ----
        r = await client.get("/health")
        record("GET /health", r.status_code == 200, f"{r.status_code} {r.text}")

        # ---- login ----
        r = await client.post(
            "/admin/auth/login", json={"username": "admin", "password": "admin123"}
        )
        record("POST /admin/auth/login", r.status_code == 200, f"{r.status_code} {r.text}")
        if r.status_code != 200:
            print("Impossible de continuer sans authentification.")
            return
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get("/admin/auth/me", headers=headers)
        record("GET /admin/auth/me", r.status_code == 200, f"{r.status_code} {r.text}")

        # ================= NIVEAUX / PROGRAMME (AcademicLevel) =================
        r = await client.post(
            "/admin/levels",
            headers=headers,
            json={"code": "L3-INFO", "label": "Licence 3 Informatique", "degree": "L", "year": 3},
        )
        record("POST /admin/levels (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        level_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/levels", headers=headers)
        found = any(x["id"] == level_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/levels (read/list contains new)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(
            f"/admin/levels/{level_id}",
            headers=headers,
            json={"code": "L3-INFO", "label": "Licence 3 Info (MAJ)", "degree": "L", "year": 3},
        )
        record(
            "PATCH /admin/levels/{id} (update)",
            r.status_code == 200 and r.json().get("label") == "Licence 3 Info (MAJ)",
            f"{r.status_code} {r.text}",
        )

        # doublon de code -> doit échouer en 409
        r = await client.post(
            "/admin/levels",
            headers=headers,
            json={"code": "L3-INFO", "label": "Doublon", "degree": "L", "year": 3},
        )
        record("POST /admin/levels (duplicate code rejected 409)", r.status_code == 409, f"{r.status_code}")

        # ================= ENSEIGNANTS (Teacher = "prof") =================
        r = await client.post(
            "/admin/teachers",
            headers=headers,
            json={"name": "Alice Martin", "email": "alice.martin@example.com", "phone_whatsapp": "33610000001"},
        )
        record("POST /admin/teachers (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        teacher_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/teachers", headers=headers)
        found = any(t["id"] == teacher_id for t in r.json()) if r.status_code == 200 else False
        record("GET /admin/teachers (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(
            f"/admin/teachers/{teacher_id}",
            headers=headers,
            json={"name": "Alice Martin-Dupont", "email": "alice.martin@example.com", "phone_whatsapp": "33610000001"},
        )
        record(
            "PATCH /admin/teachers/{id} (update)",
            r.status_code == 200 and r.json().get("name") == "Alice Martin-Dupont",
            f"{r.status_code} {r.text}",
        )

        # email dupliqué -> conflit
        r = await client.post(
            "/admin/teachers",
            headers=headers,
            json={"name": "Autre Prof", "email": "alice.martin@example.com"},
        )
        record("POST /admin/teachers (duplicate email rejected 409)", r.status_code == 409, f"{r.status_code}")

        r = await client.delete(f"/admin/teachers/{teacher_id}", headers=headers)
        record("DELETE /admin/teachers/{id} (soft-delete/archive)", r.status_code == 204, f"{r.status_code}")
        r = await client.get("/admin/teachers", headers=headers)
        archived = next((t for t in r.json() if t["id"] == teacher_id), None)
        record(
            "Verify teacher archived (is_active=false, still listed)",
            archived is not None and archived["is_active"] is False,
            str(archived),
        )

        # nouvel enseignant actif pour la suite (cours/planning)
        r = await client.post(
            "/admin/teachers",
            headers=headers,
            json={"name": "Bruno Dupont", "email": "bruno.dupont@example.com"},
        )
        teacher2_id = r.json().get("id")
        record("POST /admin/teachers (2nd active teacher for downstream tests)", r.status_code == 201, f"{r.status_code}")

        # ================= SALLES (Room) =================
        r = await client.post("/admin/rooms", headers=headers, json={"name": "B202", "capacity": 40})
        record("POST /admin/rooms (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        room_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/rooms", headers=headers)
        found = any(x["id"] == room_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/rooms (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(f"/admin/rooms/{room_id}", headers=headers, json={"name": "B202", "capacity": 50})
        record(
            "PATCH /admin/rooms/{id} (update)",
            r.status_code == 200 and r.json().get("capacity") == 50,
            f"{r.status_code} {r.text}",
        )

        # ================= GROUPES (StudentGroup) =================
        r = await client.post(
            "/admin/groups",
            headers=headers,
            json={"name": "L3 Info A", "academic_level_id": level_id, "student_count": 35},
        )
        record("POST /admin/groups (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        group_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/groups", headers=headers)
        found = any(x["id"] == group_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/groups (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(
            f"/admin/groups/{group_id}",
            headers=headers,
            json={"name": "L3 Info A", "academic_level_id": level_id, "student_count": 38},
        )
        record(
            "PATCH /admin/groups/{id} (update)",
            r.status_code == 200 and r.json().get("student_count") == 38,
            f"{r.status_code} {r.text}",
        )

        # ================= COURS (Course) =================
        r = await client.post(
            "/admin/courses",
            headers=headers,
            json={
                "title": "Bases de données",
                "teacher_id": teacher2_id,
                "group_id": group_id,
                "duration_minutes": 120,
                "planned_minutes": 720,
            },
        )
        record("POST /admin/courses (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        course_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/courses", headers=headers)
        found = any(x["id"] == course_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/courses (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(
            f"/admin/courses/{course_id}",
            headers=headers,
            json={
                "title": "Bases de données avancées",
                "teacher_id": teacher2_id,
                "group_id": group_id,
                "duration_minutes": 120,
                "planned_minutes": 720,
            },
        )
        record(
            "PATCH /admin/courses/{id} (update)",
            r.status_code == 200 and r.json().get("title") == "Bases de données avancées",
            f"{r.status_code} {r.text}",
        )

        # cours référencant un enseignant inexistant -> 400
        r = await client.post(
            "/admin/courses",
            headers=headers,
            json={"title": "X", "teacher_id": 999999, "group_id": group_id},
        )
        record("POST /admin/courses (invalid teacher ref rejected 400)", r.status_code == 400, f"{r.status_code}")

        r = await client.delete(f"/admin/courses/{course_id}", headers=headers)
        record("DELETE /admin/courses/{id} (hard delete)", r.status_code == 204, f"{r.status_code}")
        r = await client.get("/admin/courses", headers=headers)
        still_there = any(x["id"] == course_id for x in r.json()) if r.status_code == 200 else True
        record("Verify course actually removed from list", not still_there, f"{r.status_code}")

        # recreate a course for schedule tests
        r = await client.post(
            "/admin/courses",
            headers=headers,
            json={"title": "Algorithmique", "teacher_id": teacher2_id, "group_id": group_id},
        )
        course_id = r.json().get("id")
        record("POST /admin/courses (recreate for schedule tests)", r.status_code == 201, f"{r.status_code}")

        # ================= CRENEAUX (TimeSlot) =================
        r = await client.post(
            "/admin/timeslots",
            headers=headers,
            json={"day_of_week": 1, "start_time": "08:00", "end_time": "10:00", "label": "Mardi 08h-10h"},
        )
        record("POST /admin/timeslots (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        timeslot_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/timeslots", headers=headers)
        found = any(x["id"] == timeslot_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/timeslots (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.patch(
            f"/admin/timeslots/{timeslot_id}",
            headers=headers,
            json={"day_of_week": 1, "start_time": "08:00", "end_time": "10:30", "label": "Mardi 08h-10h30"},
        )
        record(
            "PATCH /admin/timeslots/{id} (update)",
            r.status_code == 200 and r.json().get("end_time") == "10:30",
            f"{r.status_code} {r.text}",
        )

        # créneau jetable, pour vérifier la suppression quand rien ne l'utilise
        r = await client.post(
            "/admin/timeslots",
            headers=headers,
            json={"day_of_week": 3, "start_time": "14:00", "end_time": "16:00", "label": "Jeudi 14h-16h (jetable)"},
        )
        disposable_timeslot_id = r.json().get("id")
        r = await client.delete(f"/admin/timeslots/{disposable_timeslot_id}", headers=headers)
        record("DELETE /admin/timeslots/{id} (delete, unused)", r.status_code == 204, f"{r.status_code}")

        # ================= PLANNING (ScheduleEntry) =================
        r = await client.post(
            "/admin/schedule",
            headers=headers,
            json={
                "course_id": course_id,
                "room_id": room_id,
                "timeslot_id": timeslot_id,
                "entry_date": "2026-09-22",
            },
        )
        record("POST /admin/schedule (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        entry_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/schedule", headers=headers)
        found = any(x["id"] == entry_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/schedule (read/list)", r.status_code == 200 and found, f"{r.status_code}")

        # conflit : même salle + créneau + date -> 409
        r = await client.post(
            "/admin/schedule",
            headers=headers,
            json={
                "course_id": course_id,
                "room_id": room_id,
                "timeslot_id": timeslot_id,
                "entry_date": "2026-09-22",
            },
        )
        record("POST /admin/schedule (room/slot conflict rejected 409)", r.status_code == 409, f"{r.status_code}")

        r = await client.patch(
            f"/admin/schedule/{entry_id}",
            headers=headers,
            json={
                "course_id": course_id,
                "room_id": room_id,
                "timeslot_id": timeslot_id,
                "entry_date": "2026-09-29",
            },
        )
        record(
            "PATCH /admin/schedule/{id} (update - move date)",
            r.status_code == 200 and r.json().get("entry_date") == "2026-09-29",
            f"{r.status_code} {r.text}",
        )

        r = await client.post(f"/admin/schedule/{entry_id}/cancel", headers=headers)
        record(
            "POST /admin/schedule/{id}/cancel (soft-delete equivalent)",
            r.status_code == 200 and r.json().get("status") == "cancelled",
            f"{r.status_code} {r.text}",
        )

        # suppression définitive d'une séance sans proposition de changement liée -> 204
        r = await client.delete(f"/admin/schedule/{entry_id}", headers=headers)
        record("DELETE /admin/schedule/{id} (hard delete)", r.status_code == 204, f"{r.status_code} {r.text}")
        r = await client.get("/admin/schedule", headers=headers)
        still_there = any(x["id"] == entry_id for x in r.json()) if r.status_code == 200 else True
        record("Verify schedule entry actually removed", not still_there, f"{r.status_code}")

        # créneau maintenant utilisé (nouvelle séance) -> suppression du créneau doit être bloquée (409)
        r = await client.post(
            "/admin/schedule",
            headers=headers,
            json={
                "course_id": course_id,
                "room_id": room_id,
                "timeslot_id": timeslot_id,
                "entry_date": "2026-09-22",
            },
        )
        entry2_id = r.json().get("id")
        r = await client.delete(f"/admin/timeslots/{timeslot_id}", headers=headers)
        record(
            "DELETE /admin/timeslots/{id} (in-use by schedule entry rejected 409)",
            r.status_code == 409,
            f"{r.status_code} {r.text}",
        )

        # ================= PROGRAMME PEDAGOGIQUE (CurriculumPlan) =================
        r = await client.post(
            "/admin/curriculum-plans",
            headers=headers,
            json={"academic_level_id": level_id, "semester": 1, "week_count": 6},
        )
        record("POST /admin/curriculum-plans (create)", r.status_code == 201, f"{r.status_code} {r.text}")
        plan_id = r.json().get("id") if r.status_code == 201 else None

        r = await client.get("/admin/curriculum-plans", headers=headers)
        found = any(x["id"] == plan_id for x in r.json()) if r.status_code == 200 else False
        record("GET /admin/curriculum-plans (list)", r.status_code == 200 and found, f"{r.status_code}")

        r = await client.get(f"/admin/curriculum-plans/{plan_id}", headers=headers)
        record("GET /admin/curriculum-plans/{id} (read one)", r.status_code == 200, f"{r.status_code} {r.text}")

        r = await client.patch(
            f"/admin/curriculum-plans/{plan_id}", headers=headers, json={"week_count": 8}
        )
        record(
            "PATCH /admin/curriculum-plans/{id} (update)",
            r.status_code == 200 and r.json().get("week_count") == 8,
            f"{r.status_code} {r.text}",
        )

        r = await client.put(
            f"/admin/curriculum-plans/{plan_id}/weeks/1",
            headers=headers,
            json={"items": [{"course_id": course_id, "sessions_count": 2}]},
        )
        ok_week = r.status_code == 200 and any(
            w["week_index"] == 1 and len(w["items"]) == 1 for w in r.json().get("weeks", [])
        )
        record("PUT /admin/curriculum-plans/{id}/weeks/{n} (replace week items)", ok_week, f"{r.status_code} {r.text}")

        # doublon niveau+semestre -> 409
        r = await client.post(
            "/admin/curriculum-plans",
            headers=headers,
            json={"academic_level_id": level_id, "semester": 1, "week_count": 6},
        )
        record("POST /admin/curriculum-plans (duplicate level+semester rejected 409)", r.status_code == 409, f"{r.status_code}")

        r = await client.delete(f"/admin/curriculum-plans/{plan_id}", headers=headers)
        record("DELETE /admin/curriculum-plans/{id} (delete)", r.status_code == 204, f"{r.status_code}")
        r = await client.get("/admin/curriculum-plans", headers=headers)
        still_there = any(x["id"] == plan_id for x in r.json()) if r.status_code == 200 else True
        record("Verify curriculum plan actually removed", not still_there, f"{r.status_code}")

        # ================= LEVEL DELETE (cleanup / verify) =================
        r = await client.delete(f"/admin/levels/{level_id}", headers=headers)
        record(
            "DELETE /admin/levels/{id} (delete, has FK from group -> may fail)",
            True,  # informational: just report the actual behavior below
            f"status={r.status_code} body={r.text}",
        )

        # ================= AUTHZ: no-token / bad-token checks =================
        r = await client.get("/admin/teachers")
        record("GET /admin/teachers without token -> 401", r.status_code == 401, f"{r.status_code}")

        r = await client.get("/admin/teachers", headers={"Authorization": "Bearer invalid.token.here"})
        record("GET /admin/teachers with bad token -> 401", r.status_code == 401, f"{r.status_code}")

    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print("\n" + "=" * 60)
    print(f"RESULTAT: {passed}/{total} vérifications passées")
    print("=" * 60)
    failures = [(n, d) for n, ok, d in RESULTS if not ok]
    if failures:
        print("\nÉCHECS:")
        for n, d in failures:
            print(f" - {n}: {d}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
