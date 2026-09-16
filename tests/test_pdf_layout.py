from datetime import date
from pathlib import Path

from app.config.settings import Settings
from app.exporters.pdf import PdfExporter, TEMPLATES_DIR, _slug


def test_week_label_matches_institutional_format():
    start, end, label, week_number = PdfExporter._week_bounds(date(2026, 5, 18))

    assert start == date(2026, 5, 18)
    assert end == date(2026, 5, 24)
    assert label == "18 au 23 Mai 2026"
    assert week_number >= 1


def test_edt_filename_matches_reference_pattern(monkeypatch):
    monkeypatch.setattr(
        "app.exporters.pdf.settings",
        Settings(
            semester_number=2,
            semester_start_date=date(2026, 3, 30),
        ),
    )
    _, _, _, week_number = PdfExporter._week_bounds(date(2026, 5, 18))
    filename = PdfExporter._edt_filename(
        semester=2,
        week_number=week_number,
        parts=["B3", "ASI"],
    )

    assert week_number == 8
    assert filename == "EDT_S2_SEMAINE8_B3_ASI.pdf"


def test_schedule_template_uses_ascencia_logo_and_week_grid():
    template = (TEMPLATES_DIR / "schedule.html").read_text(encoding="utf-8")
    logo = TEMPLATES_DIR / "logo-ak.png"

    assert logo.is_file() and logo.stat().st_size > 0
    assert 'src="logo-ak.png"' in template
    assert "Plage Horaire" in template
    assert "EMPLOI DU TEMPS" in template
    assert "day.name" in template
    assert "FIN" in template


def test_slug_normalizes_accents():
    assert _slug("Bachelor 3 ASI") == "BACHELOR_3_ASI"
    assert _slug("été") == "ETE"
