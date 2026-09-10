from datetime import date
from pathlib import Path

from app.exporters.pdf import PdfExporter, TEMPLATES_DIR


def test_week_label_matches_institutional_format():
    start, end, label = PdfExporter._week_bounds(date(2026, 5, 18))

    assert start == date(2026, 5, 18)
    assert end == date(2026, 5, 24)
    assert label == "18 au 23 mai 2026"


def test_schedule_template_uses_ascencia_logo_and_week_grid():
    template = (TEMPLATES_DIR / "schedule.html").read_text(encoding="utf-8")
    logo = TEMPLATES_DIR / "logo-ak.png"

    assert logo.is_file() and logo.stat().st_size > 0
    assert 'src="logo-ak.png"' in template
    assert "Plage horaire" in template
    assert "day.name" in template
