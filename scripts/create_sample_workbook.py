"""Génère un classeur de démonstration sans démarrer le serveur."""

from datetime import date
from pathlib import Path
import sys

from app.domain.models import PublicationStatus, SchedulePublication
from app.exporters import excel as excel_module
from app.exporters.excel import ExcelExporter


output_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path("exports").resolve()
excel_module.EXPORTS_DIR = output_dir
publication = SchedulePublication(
    version_number="DEMO-S32-V1",
    week_start=date(2026, 8, 3),
    week_end=date(2026, 8, 9),
    status=PublicationStatus.published,
    created_by="administrateur-demo",
    snapshot_json=[
        {
            "entry_date": "2026-08-03",
            "timeslot_id": 1,
            "timeslot_label": "08:00 - 10:00",
            "group_id": 1,
            "group_name": "M2 RSI",
            "course_title": "Intelligence artificielle",
            "teacher_name": "Mme Mensah",
            "room_name": "Salle A",
            "is_new": True,
        },
        {
            "entry_date": "2026-08-04",
            "timeslot_id": 2,
            "timeslot_label": "10:15 - 12:15",
            "group_id": 2,
            "group_name": "M1 Management",
            "course_title": "Management des projets",
            "teacher_name": "M. Lawson",
            "room_name": "Salle B",
            "is_new": True,
        },
    ],
    generation_report={},
)
print(ExcelExporter().generate_publication_workbook(publication)["path"])
