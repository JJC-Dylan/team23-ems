"""Generate the Team 23 Scrum board workbook (docs/Scrum Board-Team 23.xlsx).

The board reflects the delivered state of the Employee Management System:
what is done, what is in progress and what is left before the defence. Every
card points at the file or test that proves it, so the sheet can be used both
as a status board and as evidence during the presentation.

Run with the bundled Python (openpyxl is required):

    python docs/tools/make_scrum_board.py
"""

from __future__ import annotations

import math
import os

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

DOCS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(DOCS_DIR, "Scrum Board-Team 23.xlsx")

# --- palette -------------------------------------------------------------
BLUE = "1F4E79"
INK = "16202C"
MUTED = "4A5B6E"
LINE = "D9E2EC"
HEADER_FILL = PatternFill("solid", start_color=BLUE)
TITLE_FONT = Font(name="Calibri", size=15, bold=True, color=BLUE)
SUBTITLE_FONT = Font(name="Calibri", size=10, italic=True, color=MUTED)
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
BODY_FONT = Font(name="Calibri", size=10, color=INK)
BOLD = Font(name="Calibri", size=10, bold=True, color=INK)
THIN = Side(style="thin", color=LINE)
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

STATUS_STYLE = {
    "Done": ("E8F5EC", "15803D"),
    "Busy": ("FEF3E2", "B45309"),
    "To Do": ("E6EDFD", "1D4ED8"),
}

EPICS = [
    "Employees (FR01–FR05)",
    "Security & roles (FR09/FR10, NFR02)",
    "Weekly rota (FR06–FR08)",
    "Role views (FR07/FR08)",
    "Statistics (FR13)",
    "Quality (NFR01/03/05)",
    "Documentation",
    "Delivery",
]

#: (status, epic index, card, owner, evidence / notes)
CARDS = [
    ("Done", 0, "Add / edit / delete employee records", "Dylan",
     "app/views.py, repositories.py; FR01–FR03"),
    ("Done", 0, "Field-level validation + friendly error page", "Dylan",
     "htmlpages.validate_employee; FR11"),
    ("Done", 0, "Delete cascades to all rota rows", "Morty",
     "FK ON DELETE CASCADE; TC-19; test_delete_also_removes_the_linked_shift"),
    ("Done", 0, "Search by name / address / phone / e-mail", "Dylan",
     "repositories.search_employees; FR04"),
    ("Done", 0, "Wage-range + weekly-shift filters and sorting", "Dylan",
     "search_employees + the filter bar on the home page; FR12"),
    ("Done", 0, "Employee table with weekly shift summary", "Jensen",
     "templates/partials/employee_table.html; FR05"),

    ("Done", 1, "Role-based access control for the three roles", "Morty",
     "route role lists + dispatcher; FR09/FR10, NFR02"),
    ("Done", 1, "CSRF protection on every form", "Morty",
     "per-session token, refused with 400; tests"),
    ("Done", 1, "PBKDF2 passwords + server-side sessions", "Morty",
     "app/security.py; NFR02"),
    ("Done", 1, "Login lands on Home, then branches by role", "Dylan",
     "views.login; URS section 7"),

    ("Done", 2, "Dated rota rows (employee + date + shift)", "Morty",
     "shifts table + unique index; TC-31/32"),
    ("Done", 2, "Several shifts on the same day", "Spring",
     "unique(employee_id, work_date, shift_name); TC-32/55"),
    ("Done", 2, "Week navigation ?week= (prev / next / this)", "Spring",
     "_week_context(); all weekly pages; TC-52/53"),
    ("Done", 2, "Legacy database upgraded and reseeded", "Morty",
     "initialize() + _reseed_demo_rota(); SchemaMigrationTests; TC-57"),
    ("Done", 2, "Current-week demonstration rota seed", "Spring",
     "database.seed / _demo_rota; one employee with an empty week"),
    ("Done", 2, "Rota panel on the detail page (Supervisor only)", "Spring",
     "employee_detail.html; FR10; HR has no panel"),

    ("Done", 3, "Employee weekly timetable (shift × day grid)", "Jensen",
     "templates/my_shifts.html; FR07; TC-41/55"),
    ("Done", 3, "Supervisor roster grouped by day", "Spring",
     "templates/store_shifts.html + day_roster(); FR08; TC-38"),
    ("Done", 3, "HR roster grouped by employee + filters", "Spring",
     "store_shifts.html + employee_roster(); FR08/FR12; TC-54"),
    ("Done", 3, "Home = searchable Employee overview + actions", "Jensen",
     "templates/home_staff.html; FR05; /employees removed"),
    ("Done", 3, "Employee home: own details + this week's shifts", "Jensen",
     "templates/home_employee.html"),
    ("Done", 3, "Employees-per-shift distribution table", "Jensen",
     "employee_counts_per_shift(); shift-table on the home page"),

    ("Done", 4, "Weekly KPIs (employees / shifts / unassigned / wage)", "Jensen",
     "home_staff.html; FR13; TC-58"),
    ("Done", 4, "Weekly statistics page", "Jensen",
     "templates/statistics.html; FR13"),

    ("Done", 5, "137 automated tests", "Morty",
     "tests/; Ran 137 tests — OK"),
    ("Done", 5, "40 end-to-end HTTP checks", "Morty",
     "docs/verify_running_app.py"),
    ("Done", 5, "7 persistence checks", "Morty",
     "docs/verify_persistence.py; NFR03"),
    ("Done", 5, "Performance check with 400+ employees", "Morty",
     "tests/test_nonfunctional.py; NFR01"),

    ("Done", 6, "URS 1.3 (weekly rota + three role views)", "Morty",
     "docs/URS-Team23-1.3.docx"),
    ("Done", 6, "Test Plan 1.1 (60 cases + traceability)", "Morty",
     "docs/Test Plan-Team23-1.1.docx"),
    ("Done", 6, "Code Guide (code walkthrough)", "Jensen",
     "docs/Code Guide-Team 23.docx"),
    ("Done", 6, "README updated (rota, upgrade path, 137 tests)", "Dylan",
     "README.md"),
    ("Done", 6, "Demo script + Q&A preparation", "Spring",
     "docs/答辩演示脚本.md, docs/答辩准备包.md"),
    ("Done", 6, "Verification scripts updated for weekly rota", "Morty",
     "docs/verify_running_app.py, docs/verify_persistence.py"),

    ("Done", 7, "Push to GitHub (master @ b0c6f7c)", "All",
     "origin/master synced, working tree clean"),

    ("Busy", 7, "Copy URS 1.3 / Test Plan / Code Guide to the course folder", "Dylan",
     "manual copy; the sandbox cannot write outside the workspace"),
    ("Busy", 7, "Demo rehearsal with the three accounts", "All",
     "run app.py, walk docs/答辩演示脚本.md end to end"),

    ("To Do", 6, "Update Acceptance Q&A (EN + bilingual)", "Spring",
     "Q20 still says one shift per employee; update counts and overview wording"),
    ("To Do", 7, "Confirm the other-group test report is submitted", "Morty",
     "a deliverable listed in the Project Plan"),
    ("To Do", 7, "Defence slides (finish / confirm)", "Jensen",
     "follow the demo storyline: rota → views → docs → tests"),
    ("To Do", 7, "Optional: tag release v1.1 + CHANGELOG", "Dylan",
     "after submission; tag the pushed commit"),
]

TEST_INVENTORY = [
    ("tests/test_auth_and_access.py", 20, "Integration"),
    ("tests/test_employees.py", 34, "Integration"),
    ("tests/test_shifts.py", 58, "Integration (weekly rota, migration)"),
    ("tests/test_nonfunctional.py", 7, "Non-functional"),
    ("tests/test_templateengine.py", 10, "Unit"),
    ("tests/test_live_server.py", 8, "System / E2E"),
]

SNAPSHOT = [
    ("Repository", "https://github.com/JJC-Dylan/team23-ems"),
    ("Branch / HEAD", "master @ b0c6f7c (pushed, tree clean)"),
    ("Commits", "cc15a6a initial · adf844c weekly rota · b0c6f7c docs"),
    ("Iteration", "2 — post-demonstration weekly rota (2026-10-18 → 2026-10-21)"),
    ("Functional requirements", "FR01–FR13 delivered; FR14–FR18 Won't-have"),
    ("Non-functional requirements", "NFR01–NFR06 met"),
    ("Automated tests", "137 pass (Python 3.10.1)"),
    ("End-to-end checks", "40 pass (docs/verify_running_app.py)"),
    ("Persistence checks", "7 pass (docs/verify_persistence.py)"),
    ("Documents", "URS 1.3 · Test Plan 1.1 · Code Guide · README"),
    ("Owner legend", "Dylan = employee module · Spring = rota · Morty = database · Jensen = frontend (suggested)"),
]

COVERAGE = [
    ("FR01", "HR can add a new employee record", "Done", "views.employee_create; TC-06"),
    ("FR02", "HR can delete employee records", "Done", "views.employee_delete; TC-18/19"),
    ("FR03", "HR can edit employee information", "Done", "views.employee_edit; TC-15"),
    ("FR04", "Search an employee and open the detail view", "Done", "repositories.search_employees; TC-22"),
    ("FR05", "Full overview list of all employees", "Done", "Home: Employee overview table; TC-21"),
    ("FR06", "Supervisor plans the weekly rota (day + shift)", "Done", "views.employee_assign_shift; TC-31/32"),
    ("FR07", "View one employee's weekly shifts / own timetable", "Done", "my_shifts.html, employee_detail.html; TC-41"),
    ("FR08", "Full-store weekly rota for HR and Supervisor", "Done", "store_shifts.html; TC-38/54"),
    ("FR09", "Supervisor reads employee data without edit rights", "Done", "RBAC + read-only pages; TC-29"),
    ("FR10", "Only the Supervisor changes the rota", "Done", "route roles + tests; TC-44"),
    ("FR11", "Human-readable validation errors", "Done", "htmlpages.validate_employee; TC-07"),
    ("FR12", "Filter the employee list (wage, shift, sort)", "Done", "search_employees + filter bar; TC-25/26"),
    ("FR13", "Workforce statistics", "Done", "KPIs, distribution table, statistics page; TC-58"),
    ("FR14", "Department management", "Won't-have", "Out of scope per URS"),
    ("FR15", "In-store attendance registration", "Won't-have", "Out of scope per URS"),
    ("FR16", "Automatic shift generation", "Won't-have", "Out of scope per URS"),
    ("FR17", "Product-stock / depot restock management", "Won't-have", "Out of scope per URS"),
    ("FR18", "Employee self-service website", "Won't-have", "Out of scope per URS"),
    ("NFR01", "Response time ≤ 2 s", "Met", "test_nonfunctional.py; 400+ employees"),
    ("NFR02", "Role-based access control", "Met", "dispatcher + route roles; auth tests"),
    ("NFR03", "Data persists after restart", "Met", "verify_persistence.py; SQLite file"),
    ("NFR04", "User-friendly error handling", "Met", "error.html + validation; TC-14"),
    ("NFR05", "10 concurrent users", "Met", "concurrency tests; threaded server"),
    ("NFR06", "Simple, usable interface", "Met", "shared layout, print styles, timetables"),
]

NEXT_STEPS = [
    ("High", "Update Acceptance Q&A (EN + bilingual)", "Documentation", "Spring",
     "Before defence", "Both documents describe the weekly rota, 137 tests and the current views", "To Do"),
    ("High", "Copy URS 1.3 / Test Plan / Code Guide to the course folder", "Delivery", "Dylan",
     "Before submission", "All three documents present with the 1.3 / 1.1 versions", "Busy"),
    ("High", "Demo rehearsal with the three accounts", "Delivery", "All",
     "Day before defence", "Login → home → rota → views → statistics → 403 demo all pass", "Busy"),
    ("Medium", "Confirm the other-group test report is submitted", "Delivery", "Morty",
     "Before submission", "Report handed in (Project Plan deliverable)", "To Do"),
    ("Medium", "Defence slides (finish / confirm)", "Delivery", "Jensen",
     "Before defence", "Slides follow the same storyline as the demo script", "To Do"),
    ("Low", "Optional: tag release v1.1 + CHANGELOG", "Delivery", "Dylan",
     "After submission", "git tag pushed and listed on GitHub", "To Do"),
]


def style_header_row(sheet, row: int, columns: int) -> None:
    for column in range(1, columns + 1):
        cell = sheet.cell(row=row, column=column)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = BORDER
    sheet.row_dimensions[row].height = 24


def paint_status(cell) -> None:
    fill, color = STATUS_STYLE.get(str(cell.value), ("FFFFFF", INK))
    cell.fill = PatternFill("solid", start_color=fill)
    cell.font = Font(name="Calibri", size=10, bold=True, color=color)


def auto_height(text: str, width: int) -> int:
    lines = max(1, math.ceil(len(str(text)) / max(width - 2, 8)))
    return max(18, 14 * lines + 4)


def build_board(workbook: Workbook) -> None:
    sheet = workbook.active
    sheet.title = "Board"
    sheet.sheet_properties.tabColor = BLUE

    sheet["A1"] = "Team 23 — Employee Management System · Scrum board"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:E1")
    sheet["A2"] = (
        "Iteration 2 (post-demo weekly rota). Filter by Status or Epic; change a card by "
        "editing its Status cell (dropdown). Every card points at the file or test that proves it."
    )
    sheet["A2"].font = SUBTITLE_FONT
    sheet["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    sheet.merge_cells("A2:E2")
    sheet.row_dimensions[2].height = 30

    headers = ["Status", "Epic", "Card", "Owner", "Evidence / notes"]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=3, column=index, value=header)
    style_header_row(sheet, 3, len(headers))

    widths = {"A": 10, "B": 30, "C": 58, "D": 10, "E": 55}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    row = 4
    for status, epic_index, card, owner, evidence in CARDS:
        sheet.cell(row=row, column=1, value=status)
        sheet.cell(row=row, column=2, value=EPICS[epic_index])
        sheet.cell(row=row, column=3, value=card)
        sheet.cell(row=row, column=4, value=owner)
        sheet.cell(row=row, column=5, value=evidence)
        for column in range(1, 6):
            cell = sheet.cell(row=row, column=column)
            cell.border = BORDER
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=column in (2, 3, 5),
                horizontal="center" if column == 1 else "left",
            )
            cell.font = BODY_FONT
        paint_status(sheet.cell(row=row, column=1))
        sheet.cell(row=row, column=3).font = BOLD
        sheet.row_dimensions[row].height = max(
            auto_height(card, widths["C"]),
            auto_height(evidence, widths["E"]),
            auto_height(EPICS[epic_index], widths["B"]),
        )
        row += 1

    last_row = row - 1
    sheet.auto_filter.ref = f"A3:E{last_row}"
    sheet.freeze_panes = "A4"

    validation = DataValidation(type="list", formula1='"Done,Busy,To Do"', allow_blank=False)
    validation.error = "Choose Done, Busy or To Do."
    validation.errorTitle = "Status"
    sheet.add_data_validation(validation)
    validation.add(f"A4:A{last_row}")

    sheet.print_title_rows = "3:3"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def build_board_view(workbook: Workbook) -> None:
    """Epic × status matrix, mirroring the sticky-note board."""
    sheet = workbook.create_sheet("Board View")
    sheet.sheet_properties.tabColor = "2F6FA8"

    sheet["A1"] = "Board view — epics × status"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:D1")
    sheet["A2"] = "Same cards as the Board sheet, grouped the way a physical board is laid out."
    sheet["A2"].font = SUBTITLE_FONT
    sheet.merge_cells("A2:D2")

    headers = ["Epic", "To Do", "Busy", "Done"]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=3, column=index, value=header)
    style_header_row(sheet, 3, 4)
    for column, color in ((2, STATUS_STYLE["To Do"][0]), (3, STATUS_STYLE["Busy"][0]), (4, STATUS_STYLE["Done"][0])):
        cell = sheet.cell(row=3, column=column)
        cell.fill = PatternFill("solid", start_color=color)
        cell.font = Font(name="Calibri", size=10, bold=True, color=INK)

    sheet.column_dimensions["A"].width = 28
    for column in ("B", "C", "D"):
        sheet.column_dimensions[column].width = 46

    row = 4
    for epic_index, epic in enumerate(EPICS):
        sheet.cell(row=row, column=1, value=epic)
        sheet.cell(row=row, column=1).font = BOLD
        sheet.cell(row=row, column=1).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(row=row, column=1).fill = PatternFill("solid", start_color="F4F7FB")
        sheet.cell(row=row, column=1).border = BORDER

        needed_lines = 1
        for status_column, status in ((2, "To Do"), (3, "Busy"), (4, "Done")):
            cards = [c[2] for c in CARDS if c[0] == status and c[1] == epic_index]
            text = "\n".join(f"• {card}" for card in cards)
            cell = sheet.cell(row=row, column=status_column, value=text)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
            cell.font = BODY_FONT
            if cards:
                cell.fill = PatternFill("solid", start_color=STATUS_STYLE[status][0])
            # Each bullet wraps on its own; estimate the height from both the
            # number of bullets and the length of the longest one.
            lines = sum(max(1, math.ceil((len(card) + 2) / 40)) for card in cards)
            needed_lines = max(needed_lines, lines + max(0, len(cards) - 1))
        sheet.row_dimensions[row].height = max(28, 14 * needed_lines + 8)
        row += 1

    sheet.print_title_rows = "3:3"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.sheet_properties.pageSetUpPr.fitToPage = True


def build_summary(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("Summary")
    sheet.sheet_properties.tabColor = "0F766E"

    sheet["A1"] = "Project snapshot"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:D1")

    row = 3
    for label, value in SNAPSHOT:
        sheet.cell(row=row, column=1, value=label).font = BOLD
        sheet.cell(row=row, column=1).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(row=row, column=2, value=value).font = BODY_FONT
        sheet.cell(row=row, column=2).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        for column in range(1, 5):
            sheet.cell(row=row, column=column).border = BORDER
        sheet.row_dimensions[row].height = auto_height(value, 90)
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Automated test inventory").font = Font(
        name="Calibri", size=11, bold=True, color=BLUE
    )
    row += 1
    for index, header in enumerate(["Test module", "Cases", "Level", "Result"], start=1):
        sheet.cell(row=row, column=index, value=header)
    style_header_row(sheet, row, 4)
    row += 1
    for module, cases, level in TEST_INVENTORY:
        sheet.cell(row=row, column=1, value=module)
        sheet.cell(row=row, column=2, value=cases)
        sheet.cell(row=row, column=3, value=level)
        sheet.cell(row=row, column=4, value="Pass")
        for column in range(1, 5):
            sheet.cell(row=row, column=column).border = BORDER
            sheet.cell(row=row, column=column).font = BODY_FONT
            sheet.cell(row=row, column=column).alignment = Alignment(vertical="top", wrap_text=True)
        sheet.cell(row=row, column=4).fill = PatternFill("solid", start_color=STATUS_STYLE["Done"][0])
        row += 1
    sheet.cell(row=row, column=1, value="TOTAL automated").font = BOLD
    sheet.cell(row=row, column=2, value=sum(c for _, c, _ in TEST_INVENTORY)).font = BOLD
    sheet.cell(row=row, column=3, value="—")
    sheet.cell(row=row, column=4, value="Pass").font = BOLD
    for column in range(1, 5):
        sheet.cell(row=row, column=column).border = BORDER
        sheet.cell(row=row, column=column).fill = PatternFill("solid", start_color="F4F7FB")

    row += 2
    for label, value in (
        ("Website status", "Runs with python app.py (default http://127.0.0.1:8000)"),
    ):
        sheet.cell(row=row, column=1, value=label).font = BOLD
        sheet.cell(row=row, column=2, value=value).font = BODY_FONT
        sheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        row += 1

    sheet.column_dimensions["A"].width = 30
    sheet.column_dimensions["B"].width = 10
    sheet.column_dimensions["C"].width = 32
    sheet.column_dimensions["D"].width = 18


def build_coverage(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("Coverage")
    sheet.sheet_properties.tabColor = "B45309"

    sheet["A1"] = "Requirement coverage (URS 1.3)"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:D1")
    sheet["A2"] = "FR01–FR13 are delivered; FR14–FR18 are declared Won't-have by the URS."
    sheet["A2"].font = SUBTITLE_FONT
    sheet.merge_cells("A2:D2")

    headers = ["ID", "Requirement", "Status", "Where / evidence"]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=3, column=index, value=header)
    style_header_row(sheet, 3, 4)

    widths = {"A": 9, "B": 60, "C": 11, "D": 55}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    row = 4
    for requirement_id, requirement, status, where in COVERAGE:
        sheet.cell(row=row, column=1, value=requirement_id)
        sheet.cell(row=row, column=2, value=requirement)
        sheet.cell(row=row, column=3, value=status)
        sheet.cell(row=row, column=4, value=where)
        for column in range(1, 5):
            cell = sheet.cell(row=row, column=column)
            cell.border = BORDER
            cell.font = BODY_FONT
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=column in (2, 4),
                horizontal="center" if column in (1, 3) else "left",
            )
        status_cell = sheet.cell(row=row, column=3)
        if status == "Done":
            status_cell.fill = PatternFill("solid", start_color=STATUS_STYLE["Done"][0])
            status_cell.font = Font(name="Calibri", size=10, bold=True, color=STATUS_STYLE["Done"][1])
        elif status == "Met":
            status_cell.fill = PatternFill("solid", start_color=BLUE)
            status_cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        else:
            status_cell.fill = PatternFill("solid", start_color="EEF1F5")
            status_cell.font = Font(name="Calibri", size=10, bold=True, color="475569")
        sheet.row_dimensions[row].height = max(
            auto_height(requirement, widths["B"]), auto_height(where, widths["D"]), 18
        )
        row += 1

    sheet.freeze_panes = "A4"
    sheet.auto_filter.ref = f"A3:D{row - 1}"


def build_next_steps(workbook: Workbook) -> None:
    sheet = workbook.create_sheet("Next Steps")
    sheet.sheet_properties.tabColor = "6D28D9"

    sheet["A1"] = "What is left — ordered by priority"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells("A1:G1")
    sheet["A2"] = "Only release/defence tasks remain; the feature iteration is delivered and pushed."
    sheet["A2"].font = SUBTITLE_FONT
    sheet.merge_cells("A2:G2")

    headers = ["Priority", "Card", "Epic", "Owner", "Target", "Definition of Done", "Status"]
    for index, header in enumerate(headers, start=1):
        sheet.cell(row=3, column=index, value=header)
    style_header_row(sheet, 3, len(headers))

    widths = {"A": 9, "B": 46, "C": 26, "D": 9, "E": 18, "F": 52, "G": 9}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    row = 4
    for priority, card, epic, owner, target, done, status in NEXT_STEPS:
        sheet.cell(row=row, column=1, value=priority)
        sheet.cell(row=row, column=2, value=card)
        sheet.cell(row=row, column=3, value=epic)
        sheet.cell(row=row, column=4, value=owner)
        sheet.cell(row=row, column=5, value=target)
        sheet.cell(row=row, column=6, value=done)
        sheet.cell(row=row, column=7, value=status)
        for column in range(1, 8):
            cell = sheet.cell(row=row, column=column)
            cell.border = BORDER
            cell.font = BODY_FONT
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=column in (2, 3, 6),
                horizontal="center" if column in (1, 4, 5, 7) else "left",
            )
        paint_status(sheet.cell(row=row, column=7))
        sheet.row_dimensions[row].height = max(
            auto_height(card, widths["B"]), auto_height(done, widths["F"]), 18
        )
        row += 1

    sheet.freeze_panes = "A4"


def build() -> Workbook:
    workbook = Workbook()
    build_board(workbook)
    build_board_view(workbook)
    build_summary(workbook)
    build_coverage(workbook)
    build_next_steps(workbook)
    return workbook


def main() -> None:
    workbook = build()
    workbook.save(OUTPUT)
    print(f"saved: {OUTPUT}  ({os.path.getsize(OUTPUT):,} bytes)")
    print(f"cards: {len(CARDS)} (Done {sum(1 for c in CARDS if c[0] == 'Done')}, "
          f"Busy {sum(1 for c in CARDS if c[0] == 'Busy')}, "
          f"To Do {sum(1 for c in CARDS if c[0] == 'To Do')})")


if __name__ == "__main__":
    main()
