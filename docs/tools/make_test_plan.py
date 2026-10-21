"""Generate the formal Test Plan document (DOCX) for Team 23.

Run with the bundled Python:
    python docs/tools/make_test_plan.py

Writes "Test Plan-Team 23.docx" into the course deliverables folder and a copy
next to the project. The content mirrors the tests that actually exist in
tests/ and the two verification scripts, so the document stays truthful.
"""

from __future__ import annotations

import os

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm, RGBColor

DELIVERABLES_DIR = (
    r"C:\Users\金俊臣\Desktop\唧唧C的文件\2026下期-软件工程项目规划"
)
PROJECT_DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

OUTPUT_NAME = "Test Plan-Team 23.docx"

#: Printable width of the page in centimetres (A4 portrait minus 2 cm margins).
PRINTABLE_WIDTH_CM = 17.0
#: Widest a table may become, leaving slack for cell padding and borders.
MAX_TABLE_CM = 16.6


def add_caption(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT


def add_table(
    document: Document,
    headers: list[str],
    rows: list[list[str]],
    widths: list[float] | None = None,
) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Fixed layout: without this the renderer recomputes column widths from the
    # cell contents, which can push a wide table far past the printable area.
    table.autofit = False
    header_cells = table.rows[0].cells
    for index, header in enumerate(headers):
        header_cells[index].text = ""
        run = header_cells[index].paragraphs[0].add_run(header)
        run.bold = True
        run.font.size = Pt(9)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = ""
            run = cells[index].paragraphs[0].add_run(str(value))
            run.font.size = Pt(8.5)
    if widths:
        widths = list(widths)
        total = sum(widths)
        if total > MAX_TABLE_CM:
            # Trim the widest column so the table always fits the text area.
            widest = max(range(len(widths)), key=lambda i: widths[i])
            widths[widest] = round(widths[widest] - (total - MAX_TABLE_CM), 3)
        for index, width in enumerate(widths):
            table.columns[index].width = Cm(width)
        for row in table.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Cm(width)
        _pin_table_width(table, sum(widths))
    document.add_paragraph()


def _pin_table_width(table, total_cm: float) -> None:
    """Write an explicit ``tblW`` and ``tblLayout`` so widths are honoured."""
    tbl_pr = table._tbl.tblPr
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for tag in ("tblW", "tblLayout"):
        existing = tbl_pr.find(f"{namespace}{tag}")
        if existing is not None:
            tbl_pr.remove(existing)

    width = OxmlElement("w:tblW")
    width.set(qn("w:type"), "dxa")
    width.set(qn("w:w"), str(int(round(total_cm * 567))))  # 1 cm = 567 twips
    tbl_pr.append(width)

    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)


def build() -> Document:
    document = Document()

    # Portrait A4, the same page format as the URS and the Project Plan. The
    # printable width is stated explicitly (21 - 2 x 2.0 = 17.0 cm) and every
    # table below is sized to fit inside it.
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    style = document.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    # ---------------------------------------------------------------- title
    title = document.add_heading("Test Plan", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitle.add_run("Employee Management System for MeítǐShāngchéng")
    run.bold = True
    run.font.size = Pt(13)
    meta = document.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run(
        "Team 23  |  Zhengzhou University of Light Industry & Fontys "
        "University of Applied Sciences"
    ).font.size = Pt(9.5)
    meta2 = document.add_paragraph()
    meta2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta2.add_run("Version 1.1  |  20 October 2026").font.size = Pt(9.5)
    document.add_paragraph()

    # ------------------------------------------------------- change record
    document.add_heading("Document Change Record", level=1)
    add_table(
        document,
        ["Date", "Version", "Author", "Comments"],
        [
            [
                "2026-10-18",
                "1.0",
                "Project Team",
                "Initial Test Plan, aligned with the URS and the delivered system.",
            ],
            [
                "2026-10-20",
                "1.1",
                "Project Team",
                "Weekly rota change requested by the client after the demonstration "
                "(URS 1.3): shift times confirmed (08:00-12:00, 14:00-18:00, "
                "20:00-22:00); a rota row is now one employee, one date and one "
                "shift, so an employee may work several shifts on the same day; "
                "the weekly pages accept ?week= and offer previous/next week; the "
                "three roles now read three different shapes of the same rota. "
                "Test cases TC-19, TC-26, TC-28, TC-31 to TC-42, TC-44 and TC-47 "
                "were reworded, TC-51 to TC-60 were added, and the counts were "
                "updated (132 automated tests, 40 end-to-end checks).",
            ],
            ["", "", "", ""],
        ],
        widths=[2.6, 1.6, 3.2, 9.6],
    )

    # ------------------------------------------------------------ section 1
    document.add_heading("1 Introduction", level=1)

    document.add_heading("1.1 Document Purpose", level=2)
    document.add_paragraph(
        "This document defines how the Employee Management System delivered by "
        "Team 23 is verified against the User Requirements Specification (URS). "
        "It records the test strategy, the test environment, the test cases, the "
        "traceability from every requirement to at least one test case, and the "
        "results actually obtained. It is the reference for the acceptance "
        "evaluation of the project."
    )

    document.add_heading("1.2 Scope", level=2)
    document.add_paragraph(
        "The plan covers the three in-scope user roles (Human Resources, "
        "Supervisor and Ordinary Employee) and functional requirements "
        "FR01–FR13 together with non-functional requirements NFR01–NFR06. "
        "From version 1.1 it also covers the weekly rota (dated shift rows, "
        "several shifts per employee per day, week navigation, and the three "
        "role-specific weekly views) agreed with the client after the "
        "demonstration. "
        "Requirements FR14–FR18 are declared out of scope by the URS and are "
        "therefore not tested; they are listed in the traceability table for "
        "completeness only."
    )

    document.add_heading("1.3 Definitions and Abbreviations", level=2)
    add_table(
        document,
        ["Term", "Description"],
        [
            ["URS", "User Requirements Specification, this project's requirements document."],
            ["FR / NFR", "Functional Requirement / Non-functional Requirement."],
            ["HR", "Human Resources, the role that manages employee records."],
            ["CRUD", "Create, Read, Update, Delete."],
            ["GUI", "Graphical User Interface."],
            ["CSRF", "Cross-Site Request Forgery, a class of forged-form attack."],
            ["E2E", "End-to-end test, driving the running application over real HTTP."],
        ],
        widths=[3.0, 14.0],
    )

    # ------------------------------------------------------------ section 2
    document.add_heading("2 Test Strategy", level=1)
    document.add_paragraph(
        "Testing is layered. Each layer answers a different question, and a "
        "defect that escapes one layer is normally caught by the next."
    )
    add_table(
        document,
        ["Level", "Question answered", "How it is executed"],
        [
            [
                "1. Unit",
                "Do the individual rules (validation, password hashing, the "
                "template engine) behave as specified?",
                "Automated, tests/test_templateengine.py",
            ],
            [
                "2. Integration",
                "Do the request handlers, the database and the rendered pages "
                "work together for every role?",
                "Automated, tests/test_auth_and_access.py, test_employees.py, "
                "test_shifts.py",
            ],
            [
                "3. Non-functional",
                "Are the response-time and concurrency targets met with a "
                "realistic data volume?",
                "Automated, tests/test_nonfunctional.py (400+ employee records, "
                "10 concurrent users)",
            ],
            [
                "4. System / E2E",
                "Does the artefact the user actually opens work over a real "
                "socket, with real cookies and real forms?",
                "Automated, tests/test_live_server.py plus "
                "docs/verify_running_app.py",
            ],
            [
                "5. Persistence",
                "Does data survive a real stop/start of the process?",
                "Automated, docs/verify_persistence.py",
            ],
            [
                "6. Manual acceptance",
                "Can a human follow the URS use cases through the GUI for each "
                "role?",
                "Manual, per the steps in section 4",
            ],
        ],
        widths=[2.8, 7.2, 7.0],
    )

    document.add_heading("2.1 Test Basis", level=2)
    document.add_paragraph(
        "Test cases are derived from three sources: the functional and "
        "non-functional requirements (URS section 5), the GUI descriptions "
        "(URS section 6), and the detailed use-case models including their "
        "extension branches (URS section 8). Every extension branch in the URS "
        "use cases is treated as a test case, because those branches describe "
        "the error handling the client will actually exercise."
    )

    # ------------------------------------------------------------ section 3
    document.add_heading("3 Test Environment", level=1)
    add_table(
        document,
        ["Item", "Value"],
        [
            ["Operating system", "Windows 10/11 (64-bit), x86-64"],
            ["Runtime", "Python 3.10.1 (standard library only; no third-party packages)"],
            ["Web server", "wsgiref WSGI server with a threaded handler, bound to 127.0.0.1"],
            ["Database", "SQLite 3, single file data/employee_management.db"],
            ["Browser", "The system's default Chromium-based browser"],
            ["Test framework", "unittest (Python standard library)"],
            ["Test data", "Demonstration dataset seeded on first run: 3 login accounts, 5 employee records and one week of rota rows (Monday to Friday, two employees with a second shift on one day, one employee with an empty week)"],
            ["Network", "Loopback only; the application is not exposed to the public internet"],
        ],
        widths=[3.6, 13.4],
    )

    # ------------------------------------------------------------ section 4
    document.add_heading("4 Test Cases", level=1)
    document.add_paragraph(
        "Each case lists the requirement it verifies, the precondition, the "
        "action and the expected result. 'Auto' means the case is asserted by "
        "the automated suite; 'Manual' means it was executed through the GUI "
        "during acceptance. All results below were executed on the delivered "
        "system."
    )

    cases: list[tuple[str, str, str, str, str, str]] = [
        # id, requirement, precondition, action, expected, mode
        ("TC-01", "NFR02 / URS 7", "Login page open", "Sign in as hr / hr123 (the same landing applies to Supervisor and Ordinary Employee)", "Signed in; lands on the System Home Page; the menu matches the role (HR also sees the Add action)", "Auto + Manual"),
        ("TC-02", "NFR02", "Login page open", "Sign in with a wrong password", "Friendly error; no session created; password not echoed", "Auto"),
        ("TC-03", "FR11", "Login page open", "Submit empty username and password", "Message asks for both fields", "Auto"),
        ("TC-04", "NFR02", "Signed in", "Sign out", "Session ended; further pages redirect to login", "Auto"),
        ("TC-05", "NFR02", "Not signed in", "Open /employees/1 directly", "Redirected to the login page", "Auto"),
        ("TC-06", "FR01", "Signed in as HR", "Add an employee with name, address and wage", "Record saved; detail page shown; employee listed", "Auto + Manual"),
        ("TC-07", "FR11 / UC1 1A", "Signed in as HR", "Add an employee with an empty name", "Field-level error; form stays open with typed values preserved", "Auto + Manual"),
        ("TC-08", "FR11", "Signed in as HR", "Add an employee with wage 'abc'", "Message: hourly wage must be a number", "Auto"),
        ("TC-09", "FR11", "Signed in as HR", "Add an employee with wage -5", "Message: wage must be greater than zero", "Auto"),
        ("TC-10", "FR11", "Signed in as HR", "Add an employee with wage 99999", "Message: wage must be at most 1000.00", "Auto"),
        ("TC-11", "FR11", "Signed in as HR", "Add an employee with a 2-character address", "Message: address too short", "Auto"),
        ("TC-12", "FR11", "Signed in as HR", "Add an employee with an invalid e-mail and phone", "Both fields reported in one submission", "Auto"),
        ("TC-13", "UC1 1A", "Signed in as HR", "Submit a form with three invalid fields", "All three messages listed together; previously typed values retained", "Auto"),
        ("TC-14", "NFR04", "Signed in as HR", "Trigger a validation failure", "No traceback, SQL text or exception class shown to the user", "Auto"),
        ("TC-15", "FR03", "Employee record exists", "Edit the address and wage, then save", "Detail page shows the new values", "Auto + Manual"),
        ("TC-16", "FR11", "Signed in as HR", "Submit an edit with a negative wage", "Error shown; typed values kept; record unchanged", "Auto"),
        ("TC-17", "FR04", "Signed in as HR", "Open /employees/9999/edit", "404 'Employee not found' page", "Auto"),
        ("TC-18", "FR02", "Signed in as HR", "Delete an employee and confirm", "Record leaves the overview table", "Auto + Manual"),
        ("TC-19", "FR02 / UC5", "Employee has rota rows", "Delete that employee", "All rota rows of that employee are removed as well (cascade)", "Auto"),
        ("TC-20", "FR02", "Signed in as HR", "Delete a non-existent employee", "404 'Employee not found' page", "Auto"),
        ("TC-21", "FR05", "5 employees seeded", "Open the Home page", "The Employee overview table lists all 5; '5 employee(s) shown of 5 in total'", "Auto"),
        ("TC-22", "FR04", "5 employees seeded", "Search 'Zhang'", "Only matching employee listed", "Auto + Manual"),
        ("TC-23", "FR04", "5 employees seeded", "Search by part of an address", "Matching employee listed", "Auto"),
        ("TC-24", "FR04", "5 employees seeded", "Search a term that matches nothing", "Placeholder explains no match; total still reported", "Auto"),
        ("TC-25", "FR12", "Employees with varied wages", "Filter wage 30–36", "Only employees inside the range listed", "Auto + Manual"),
        ("TC-26", "FR12", "5 employees, one with an empty week", "Filter shift = Unassigned", "Only the employee with an empty week in the current week is listed", "Auto"),
        ("TC-27", "FR12", "5 employees", "Sort by wage high to low", "Order is descending by wage", "Auto"),
        ("TC-28", "FR13", "5 employees seeded", "Open /statistics", "Total count, the week's shift-slot counts and wage figures shown", "Auto + Manual"),
        ("TC-29", "FR09", "Signed in as Supervisor", "Open the Home page", "Employee overview table is read-only: no Add/Edit/Delete controls", "Auto + Manual"),
        ("TC-30", "FR10 / NFR02", "Signed in as Supervisor", "Request /employees/new, /edit and delete", "All three refused with 403 by the server", "Auto + Manual"),
        ("TC-31", "FR06", "Signed in as Supervisor", "Choose a working date and the Evening shift in the detail panel", "Rota row saved for that date; confirmation message; audit line shows who and when", "Auto + Manual"),
        ("TC-32", "FR06", "Signed in as Supervisor", "Add Morning, then Evening, for the same employee and date", "Both shifts are stored and shown on that day (one employee, several shifts a day)", "Auto + Manual"),
        ("TC-33", "UC2 1A", "Signed in as Supervisor", "Assign a shift to a non-existent employee", "Error message; returned to the overview", "Auto"),
        ("TC-34", "FR06", "Signed in as Supervisor", "Submit a shift value outside the three fixed shifts", "Nothing changed; message asks for a valid shift", "Auto"),
        ("TC-35", "FR06", "Signed in as Supervisor", "Remove one of two shifts of the same employee and day", "Only that row is deleted; the other shift stays", "Auto + Manual"),
        ("TC-36", "FR07", "Employee has rota rows", "Open the employee detail page", "The whole week is listed with date, weekday, shift, time, and who confirmed it; previous/next week links work", "Auto + Manual"),
        ("TC-37", "UC3 1A", "Employee has no rota rows", "Open the employee detail page", "Message 'No shifts assigned for this employee'", "Auto"),
        ("TC-38", "FR08", "Signed in as Supervisor", "Open /shifts", "The week is grouped by day; each day lists the employees of the Morning, Afternoon and Evening shift, including the empty weekend", "Auto + Manual"),
        ("TC-39", "URS 6", "Signed in as Supervisor or HR", "Inspect /shifts", "No shift-modification control on that page; changes are made from the employee detail page", "Auto"),
        ("TC-40", "UC4 1A", "No employee records", "Open /shifts", "Message 'No employee data available'", "Auto"),
        ("TC-41", "FR07", "Signed in as Ordinary Employee", "Open /my-shifts", "A personal weekly timetable: rows are the three shifts, columns are Monday to Sunday with dates; a tick marks every shift to work; no other employee disclosed", "Auto + Manual"),
        ("TC-42", "UC6 1A", "Employee has no rota rows", "Open /my-shifts", "Message 'You have not been assigned any shifts yet' with an empty timetable", "Auto"),
        ("TC-43", "NFR02", "Signed in as Ordinary Employee", "Request /employees/1, /shifts, /statistics, /employees/new", "Every page refused with 403 by the server", "Auto + Manual"),
        ("TC-44", "NFR02", "Signed in as HR", "POST a rota entry and a rota removal", "Both refused with 403: HR does not schedule shifts", "Auto"),
        ("TC-45", "NFR01", "420 employee records", "Load the list page and run a search", "Each response completes well within 2 seconds", "Auto"),
        ("TC-46", "NFR05", "Ten separate sign-ins", "Fire ten concurrent authenticated requests", "All ten answered with HTTP 200; ten live sessions created", "Auto"),
        ("TC-47", "NFR03", "Rota row written", "Stop the server, restart it over the same database", "The dated rota row is still present; demonstration data not duplicated", "Auto"),
        ("TC-48", "Security", "Signed in as HR", "Submit a form with a forged CSRF token", "Refused with 400; no data changed", "Auto"),
        ("TC-49", "Security", "Server running", "Request /static/../app.py", "Refused with 404 (no path traversal)", "Auto"),
        ("TC-50", "Security", "Database file", "Inspect stored passwords", "Only salted PBKDF2 hashes stored; no clear-text password", "Auto"),
        ("TC-51", "URS 1.3", "Server running", "Open any weekly page", "The shift times are the confirmed ones: Morning 08:00-12:00, Afternoon 14:00-18:00, Evening 20:00-22:00; no shift crosses midnight", "Auto"),
        ("TC-52", "FR08 / URS 1.3", "Signed in as Supervisor", "Open /shifts?week= with any day of a week, then with an unreadable value", "Any day resolves to that week's Monday; an unreadable value falls back to the current week", "Auto"),
        ("TC-53", "FR07 / FR08", "Signed in", "Use previous/next week on /my-shifts, /shifts, /employees/<id> and /statistics", "The same screen is shown for the neighbouring week; the current week keeps its data", "Auto + Manual"),
        ("TC-54", "FR08", "Signed in as HR", "Open /shifts and filter by shift and by employee name", "Only the matching employees remain; the filter is kept when the week is changed", "Auto + Manual"),
        ("TC-55", "FR07", "Employee works Morning and Evening on one day", "Open /my-shifts", "Both shifts are ticked in that day's column (5 morning ticks and 1 evening tick for the seeded employee)", "Auto"),
        ("TC-56", "FR04 / FR05", "Employee works several shifts in the week", "Open the Home page", "The shift column summarises the week, e.g. 'Morning, Evening'; an empty week shows 'Unassigned'", "Auto + Manual"),
        ("TC-57", "NFR03 / migration", "Database created by the previous release (shifts table without work_date)", "Start the application over that database", "The shifts table is rebuilt, the demonstration rota is regenerated for the current week, and employee and account rows are unchanged", "Auto"),
        ("TC-58", "FR13", "Seeded week (22 rota rows)", "Open /statistics and /shifts", "Per-shift slot counts (10 / 5 / 7) and a total of 22 are shown for the week", "Auto"),
        ("TC-59", "FR08", "Signed in as HR or Supervisor", "Open /shifts", "Read-only overview for both roles: no date field and no shift field are rendered", "Auto"),
        ("TC-60", "UC2 1A", "Signed in as Supervisor", "Submit a rota entry without a date or with an impossible date", "Refused with a friendly message; no row is written", "Auto"),
    ]

    add_table(
        document,
        ["ID", "Req.", "Precondition", "Action", "Expected result", "Mode"],
        [list(case) for case in cases],
        widths=[1.3, 2.1, 3.0, 4.0, 5.3, 1.3],
    )
    add_caption(document, "Table 1 — Test cases and expected results.")

    # ------------------------------------------------------------ section 5
    document.add_heading("5 Requirement Traceability", level=1)
    document.add_paragraph(
        "Every in-scope requirement is covered by at least one test case. "
        "Requirements marked 'Won't' are declared out of scope by the URS and "
        "are not implemented or tested."
    )
    add_table(
        document,
        ["Requirement", "Priority", "Covered by", "Result"],
        [
            ["FR01 Add employee", "Must", "TC-06", "Pass"],
            ["FR02 Delete employee", "Must", "TC-18, TC-19, TC-20", "Pass"],
            ["FR03 Edit employee", "Must", "TC-15, TC-16", "Pass"],
            ["FR04 Search and open detail", "Must", "TC-21, TC-22, TC-23, TC-24, TC-56", "Pass"],
            ["FR05 Full employee overview", "Must", "TC-21, TC-56", "Pass"],
            ["FR06 Plan Morning/Afternoon/Evening on a date", "Must", "TC-31, TC-32, TC-34, TC-35, TC-51, TC-60", "Pass"],
            ["FR07 View one employee's weekly shifts", "Must", "TC-36, TC-37, TC-41, TC-42, TC-53, TC-55", "Pass"],
            ["FR08 Full-store weekly rota", "Must", "TC-38, TC-39, TC-40, TC-52, TC-54, TC-59", "Pass"],
            ["FR09 Supervisor read-only employee data", "Must", "TC-29", "Pass"],
            ["FR10 Supervisor plans shifts only", "Must", "TC-30, TC-44", "Pass"],
            ["FR11 Friendly validation errors", "Should", "TC-07 … TC-13", "Pass"],
            ["FR12 Filter employee list", "Could", "TC-25, TC-26, TC-27", "Pass"],
            ["FR13 Weekly workforce statistics", "Could", "TC-28, TC-58", "Pass"],
            ["FR14 Department assignment", "Won't", "—", "Not in scope"],
            ["FR15 Attendance registration", "Won't", "—", "Not in scope"],
            ["FR16 Automatic shift generation", "Won't", "—", "Not in scope"],
            ["FR17 Stock and restock management", "Won't", "—", "Not in scope"],
            ["FR18 Employee self-service website", "Won't", "—", "Not in scope"],
            ["NFR01 Response time ≤ 2 s", "Must", "TC-45", "Pass"],
            ["NFR02 Role-based access control", "Must", "TC-01 … TC-05, TC-30, TC-43, TC-44", "Pass"],
            ["NFR03 Data persists after restart", "Must", "TC-47", "Pass"],
            ["NFR04 User-friendly error handling", "Should", "TC-14", "Pass"],
            ["NFR05 Ten concurrent users", "Should", "TC-46", "Pass"],
            ["NFR06 Simple, usable interface", "Should", "TC-01 … TC-43 (manual walkthrough)", "Pass"],
        ],
        widths=[6.2, 1.8, 6.6, 2.4],
    )
    add_caption(document, "Table 2 — Requirement traceability matrix.")

    # ------------------------------------------------------------ section 6
    document.add_heading("6 Test Execution Summary", level=1)
    document.add_paragraph(
        "The automated suite is executed with "
        "`python -m unittest discover -s tests -t . -v` from the project folder. "
        "It runs against a temporary database, so it never touches the "
        "demonstration data."
    )
    add_table(
        document,
        ["Test module", "Cases", "Level", "Result"],
        [
            ["tests/test_auth_and_access.py", "20", "Integration", "Pass"],
            ["tests/test_employees.py", "34", "Integration", "Pass"],
            ["tests/test_shifts.py", "58", "Integration (weekly rota, migration)", "Pass"],
            ["tests/test_nonfunctional.py", "7", "Non-functional", "Pass"],
            ["tests/test_templateengine.py", "10", "Unit", "Pass"],
            ["tests/test_live_server.py", "8", "System / E2E", "Pass"],
            ["TOTAL automated", "137", "—", "Pass"],
        ],
        widths=[7.0, 1.8, 4.6, 3.6],
    )
    add_caption(document, "Table 3 — Automated test inventory.")

    add_table(
        document,
        ["Verification script", "Checks", "What it proves", "Result"],
        [
            [
                "docs/verify_running_app.py",
                "40",
                "Every screen, role permission, CRUD action, weekly rota action, "
                "validation message, CSRF refusal and static asset over real HTTP",
                "Pass",
            ],
            [
                "docs/verify_persistence.py",
                "7",
                "Employee and dated rota row survive a real stop/start of the process",
                "Pass",
            ],
        ],
        widths=[5.6, 1.6, 7.4, 2.4],
    )
    add_caption(document, "Table 4 — End-to-end verification scripts.")

    # ------------------------------------------------------------ section 7
    document.add_heading("7 Entry and Exit Criteria", level=1)
    document.add_heading("7.1 Entry criteria", level=2)
    for item in (
        "The application starts from app.py without errors on Python 3.10 or newer.",
        "The database is created and seeded on first run.",
        "All three demonstration accounts can sign in.",
    ):
        document.add_paragraph(item, style="List Bullet")

    document.add_heading("7.2 Exit criteria", level=2)
    for item in (
        "All 137 automated tests pass.",
        "Both verification scripts report zero failures (40 and 7 checks).",
        "Every Must-have requirement (FR01–FR10, NFR01–NFR03) passes.",
        "Every Could/Should-have requirement that was implemented passes.",
        "No open defect with a severity of high or critical.",
    ):
        document.add_paragraph(item, style="List Bullet")

    # ------------------------------------------------------------ section 8
    document.add_heading("8 Defects Found and Fixed", level=1)
    add_table(
        document,
        ["ID", "Defect", "Severity", "Status"],
        [
            [
                "DEF-01",
                "The template engine used an f-string containing a backslash, "
                "which is only legal from Python 3.12. The application failed to "
                "start on the project's minimum version, Python 3.10.",
                "High",
                "Fixed and re-verified on Python 3.10.1",
            ],
            [
                "DEF-02",
                "On a failed employee submission the overview page could show "
                "the deleted employee's name inside the success message, which "
                "made the deletion look unsuccessful.",
                "Low",
                "Fixed (message wording) and the test now checks the table body",
            ],
            [
                "DEF-03",
                "Git could not reach GitHub from the development machine because "
                "the Git client ignored the configured system proxy.",
                "Medium",
                "Fixed by configuring http.proxy / https.proxy (environment issue, "
                "not a product defect)",
            ],
        ],
        widths=[1.8, 9.4, 2.2, 3.6],
    )
    add_caption(document, "Table 5 — Defects found during test execution.")

    # ------------------------------------------------------------ section 9
    document.add_heading("9 Limitations", level=1)
    for item in (
        "The system targets at most ten concurrent signed-in users on a single "
        "shop workstation; load beyond that was not tested.",
        "Browser compatibility was verified only in the default Chromium-based "
        "browser on Windows; other engines were not exercised.",
        "The rota is planned one week at a time: there is no recurring pattern or "
        "template, so a later week starts empty and is filled by hand. Only the "
        "current week of the demonstration data is seeded.",
        "Worked hours are not recorded, so the wage figures are indicators of the "
        "wage level and not a payroll calculation.",
        "Login accounts are assumed to be created outside the application "
        "(URS 4.2); the three seeded accounts exist for demonstration.",
    ):
        document.add_paragraph(item, style="List Bullet")

    # ----------------------------------------------------------- section 10
    document.add_heading("10 How to Reproduce the Tests", level=1)
    for step in (
        "Open the team23-website folder in PyCharm with a Python 3.10+ interpreter.",
        "Run: python -m unittest discover -s tests -t . -v  (expect 137 passing tests).",
        "Start the application: python app.py",
        "In a second terminal run: python docs/verify_running_app.py http://127.0.0.1:8000  (expect 40 passing checks).",
        "Run: python docs/verify_persistence.py  (expect 7 passing checks; it starts and stops its own server).",
    ):
        document.add_paragraph(step, style="List Number")

    return document


def main() -> None:
    document = build()

    # The project copy is always written. The extra copy in the course
    # deliverables folder is written too when that folder is reachable, but the
    # project copy is what the repository and the acceptance run use, so a
    # sandboxed or read-only deliverables folder must not stop the build.
    targets: list[str] = [os.path.join(PROJECT_DOCS_DIR, OUTPUT_NAME)]
    if os.path.isdir(DELIVERABLES_DIR):
        targets.insert(0, os.path.join(DELIVERABLES_DIR, OUTPUT_NAME))

    for target in targets:
        try:
            document.save(target)
        except (OSError, PermissionError) as error:
            print(f"skipped: {target}  ({error})")
            continue
        size = os.path.getsize(target)
        print(f"saved: {target}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
