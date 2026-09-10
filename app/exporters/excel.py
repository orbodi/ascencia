from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.config import settings
from app.domain.models import SchedulePublication

EXPORTS_DIR = Path(__file__).resolve().parents[2] / "exports"

BLUE = "294394"
NAVY = "17285F"
ORANGE = "D84A08"
PALE_BLUE = "E7ECFB"
PALE_ORANGE = "FFEADF"
LINE = "D5DBEA"
WHITE = "FFFFFF"


class ExcelExporter:
    def __init__(self) -> None:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    def generate_publication_workbook(
        self, publication: SchedulePublication
    ) -> dict[str, Any]:
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Synthèse"
        planning = workbook.create_sheet("Planning complet")
        entries = sorted(
            publication.snapshot_json,
            key=lambda item: (
                item["entry_date"], item["timeslot_id"], item["group_name"]
            ),
        )
        self._write_planning_sheet(
            planning,
            entries,
            title="Planning complet",
            version=publication.version_number,
            table_name="PlanningComplet",
        )

        groups: dict[int, list[dict[str, Any]]] = {}
        for item in entries:
            groups.setdefault(int(item["group_id"]), []).append(item)
        used_names = {"Synthèse", "Planning complet"}
        for group_id, group_entries in sorted(
            groups.items(), key=lambda pair: pair[1][0]["group_name"]
        ):
            group_name = str(group_entries[0]["group_name"])
            sheet_name = self._sheet_name(group_name, used_names)
            used_names.add(sheet_name)
            sheet = workbook.create_sheet(sheet_name)
            self._write_planning_sheet(
                sheet,
                group_entries,
                title=f"Emploi du temps — {group_name}",
                version=publication.version_number,
                table_name=f"PlanningGroupe{group_id}",
            )

        self._write_summary(summary, publication, len(entries), len(groups))
        workbook.calculation.fullCalcOnLoad = True
        workbook.calculation.forceFullCalc = True
        filename = f"planning_{publication.version_number}.xlsx"
        path = EXPORTS_DIR / filename
        workbook.save(path)
        return {
            "ok": True,
            "path": str(path),
            "filename": filename,
            "entries_count": len(entries),
            "groups_count": len(groups),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _write_summary(
        self,
        sheet,
        publication: SchedulePublication,
        entries_count: int,
        groups_count: int,
    ) -> None:
        sheet.sheet_view.showGridLines = False
        sheet.merge_cells("A1:D1")
        sheet["A1"] = "EMPLOI DU TEMPS UNIVERSITAIRE"
        sheet["A1"].font = Font(name="Aptos Display", size=18, bold=True, color=WHITE)
        sheet["A1"].fill = PatternFill("solid", fgColor=NAVY)
        sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
        sheet.row_dimensions[1].height = 34
        sheet.merge_cells("A2:D2")
        sheet["A2"] = settings.university_name
        sheet["A2"].font = Font(name="Aptos", size=11, bold=True, color=BLUE)
        sheet["A2"].alignment = Alignment(horizontal="center")

        values = [
            ("Version", publication.version_number),
            ("Période", f"{publication.week_start:%d/%m/%Y} au {publication.week_end:%d/%m/%Y}"),
            ("Statut", publication.status.value.upper()),
            ("Créée par", publication.created_by),
        ]
        for row, (label, value) in enumerate(values, start=4):
            sheet.cell(row, 1, label)
            sheet.cell(row, 2, value)
            sheet.cell(row, 1).font = Font(bold=True, color=NAVY)
            sheet.cell(row, 1).fill = PatternFill("solid", fgColor=PALE_BLUE)

        last_row = max(entries_count + 4, 5)
        sheet["A9"] = "Indicateurs"
        sheet["A9"].font = Font(size=13, bold=True, color=WHITE)
        sheet["A9"].fill = PatternFill("solid", fgColor=ORANGE)
        sheet.merge_cells("A9:B9")
        sheet["A10"] = "Nombre total de séances"
        sheet["B10"] = f"=COUNTA('Planning complet'!A5:A{last_row})"
        sheet["A11"] = "Nouvelles séances"
        sheet["B11"] = (
            f'=COUNTIF(\'Planning complet\'!G5:G{last_row},"Nouvelle séance")'
        )
        sheet["A12"] = "Groupes concernés"
        sheet["B12"] = groups_count
        for row in range(10, 13):
            sheet.cell(row, 1).fill = PatternFill("solid", fgColor=PALE_ORANGE)
            sheet.cell(row, 1).font = Font(bold=True, color=NAVY)
            sheet.cell(row, 2).font = Font(bold=True, color=ORANGE)
            sheet.cell(row, 2).number_format = "0"

        sheet.merge_cells("A15:D16")
        sheet["A15"] = (
            "Document généré automatiquement depuis la version publiée. "
            "La feuille « Planning complet » constitue la source des feuilles par groupe."
        )
        sheet["A15"].alignment = Alignment(wrap_text=True, vertical="top")
        sheet["A15"].font = Font(italic=True, color="58627C")
        sheet.column_dimensions["A"].width = 30
        sheet.column_dimensions["B"].width = 28
        sheet.column_dimensions["C"].width = 18
        sheet.column_dimensions["D"].width = 18
        sheet.freeze_panes = "A4"

    def _write_planning_sheet(
        self,
        sheet,
        entries: list[dict[str, Any]],
        *,
        title: str,
        version: str,
        table_name: str,
    ) -> None:
        sheet.sheet_view.showGridLines = False
        sheet.merge_cells("A1:G1")
        sheet["A1"] = title
        sheet["A1"].font = Font(name="Aptos Display", size=16, bold=True, color=WHITE)
        sheet["A1"].fill = PatternFill("solid", fgColor=NAVY)
        sheet["A1"].alignment = Alignment(horizontal="center", vertical="center")
        sheet.row_dimensions[1].height = 32
        sheet.merge_cells("A2:G2")
        sheet["A2"] = f"{settings.university_name} · {version}"
        sheet["A2"].font = Font(bold=True, color=BLUE)
        sheet["A2"].alignment = Alignment(horizontal="center")

        headers = ["Date", "Jour", "Horaire", "Cours", "Enseignant", "Salle", "Statut"]
        for col, header in enumerate(headers, start=1):
            cell = sheet.cell(4, col, header)
            cell.font = Font(bold=True, color=WHITE)
            cell.fill = PatternFill("solid", fgColor=BLUE)
            cell.alignment = Alignment(horizontal="center", vertical="center")
        sheet.row_dimensions[4].height = 24

        day_names = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        for row, item in enumerate(entries, start=5):
            entry_date = date.fromisoformat(item["entry_date"])
            values = [
                entry_date,
                day_names[entry_date.weekday()],
                item["timeslot_label"],
                item["course_title"],
                item["teacher_name"],
                item["room_name"],
                "Nouvelle séance" if item.get("is_new", True) else "Déjà planifiée",
            ]
            for col, value in enumerate(values, start=1):
                cell = sheet.cell(row, col, value)
                cell.alignment = Alignment(vertical="center", wrap_text=col in {4, 5})
                if row % 2 == 0:
                    cell.fill = PatternFill("solid", fgColor="F5F7FC")
            sheet.cell(row, 1).number_format = "dd/mm/yyyy"
            status_cell = sheet.cell(row, 7)
            status_cell.fill = PatternFill(
                "solid",
                fgColor=PALE_ORANGE if item.get("is_new", True) else PALE_BLUE,
            )
            status_cell.font = Font(
                bold=True, color=ORANGE if item.get("is_new", True) else BLUE
            )

        end_row = max(5, len(entries) + 4)
        if not entries:
            sheet["A5"] = "Aucune séance"
            sheet.merge_cells("A5:G5")
            sheet["A5"].alignment = Alignment(horizontal="center")
        else:
            table = Table(displayName=table_name, ref=f"A4:G{end_row}")
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=False,
                showColumnStripes=False,
            )
            sheet.add_table(table)

        thin = Side(style="thin", color=LINE)
        for row in sheet.iter_rows(min_row=4, max_row=end_row, min_col=1, max_col=7):
            for cell in row:
                cell.border = Border(bottom=thin)
        widths = [14, 14, 20, 28, 25, 18, 20]
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[chr(64 + index)].width = width
        sheet.freeze_panes = "A5"
        sheet.auto_filter.ref = f"A4:G{end_row}"
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.oddFooter.center.text = f"Version {version} · &D"
        sheet.print_title_rows = "1:4"
        sheet.print_area = f"A1:G{end_row}"

    @staticmethod
    def _sheet_name(value: str, used: set[str]) -> str:
        base = re.sub(r"[\\/*?:\[\]]", "-", value).strip()[:31] or "Groupe"
        candidate = base
        index = 2
        while candidate in used:
            suffix = f" {index}"
            candidate = f"{base[:31-len(suffix)]}{suffix}"
            index += 1
        return candidate
