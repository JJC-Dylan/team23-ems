"""Generate URS version 1.3 from the team's URS 1.2 document.

The team keeps the authoritative URS outside this repository (the course
deliverables folder). This script takes that document, applies the weekly-rota
revision requested by the client after the demonstration of 2026-10-18, and
writes ``docs/URS-Team23-1.3.docx`` next to the project. The 1.2 file itself is
never modified.

Run with the bundled Python (python-docx is required):

    python docs/tools/make_urs_1_3.py
    python docs/tools/make_urs_1_3.py --source "C:\\path\\to\\URS-Team23-1.2.docx"

Content of the revision (URS 1.3)
---------------------------------
* Confirmed shift times: Morning 08:00-12:00, Afternoon 14:00-18:00,
  Evening 20:00-22:00. No shift crosses midnight.
* A rota record is one employee, one date and one shift, so an employee may
  work several shifts on the same day.
* The rota is read as a week, with previous/next-week navigation.
* Three role-specific weekly views: the employee's personal timetable, the
  Supervisor's view grouped by day and the HR view grouped by employee.
"""

from __future__ import annotations

import argparse
import os
from copy import deepcopy

from docx import Document
from docx.text.paragraph import Paragraph

DOCS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(DOCS_DIR, "URS-Team23-1.3.docx")
SOURCE_NAME = "URS-Team23-1.2.docx"


def find_source() -> str:
    """Locate URS 1.2 on the desktop when no path is given."""
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    for root, _dirs, files in os.walk(desktop):
        for name in files:
            if name == SOURCE_NAME:
                return os.path.join(root, name)
    raise FileNotFoundError(
        f"{SOURCE_NAME} was not found below {desktop}; pass --source explicitly."
    )


def set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    """Replace a paragraph's text while keeping the formatting of its first run."""
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text
    for run in runs[1:]:
        run.text = ""


def set_cell_text(cell, text: str) -> None:
    """Replace a table cell's text, keeping the formatting of its first run."""
    paragraphs = cell.paragraphs
    for extra in paragraphs[1:]:
        extra._element.getparent().remove(extra._element)
    set_paragraph_text(paragraphs[0], text)


def add_row_like_last(table, values: list[str]) -> None:
    """Append a row that copies the formatting of the table's last row."""
    new_row = deepcopy(table.rows[-1]._tr)
    table._tbl.append(new_row)
    for cell, value in zip(table.rows[-1].cells, values):
        set_cell_text(cell, value)


def insert_paragraph_after(anchor: Paragraph, text: str) -> Paragraph:
    """Insert a paragraph after ``anchor``, copying the anchor's formatting."""
    new_element = deepcopy(anchor._p)
    anchor._p.addnext(new_element)
    paragraph = Paragraph(new_element, anchor._parent)
    set_paragraph_text(paragraph, text)
    return paragraph


def revise(document: Document) -> None:
    paragraphs = document.paragraphs
    tables = document.tables
    # Capture the paragraph references before any insertion, because inserting
    # paragraphs shifts every later index.
    system_overview = paragraphs[75]

    # ---- Document Change Record (Table 1) --------------------------------
    change_record = tables[1]
    add_row_like_last(
        change_record,
        [
            "2026-10-20",
            "1.3",
            "Project Team",
            "Weekly rota revision requested by the client after the demonstration "
            "of 2026-10-18. Shift times confirmed: Morning 08:00-12:00, Afternoon "
            "14:00-18:00, Evening 20:00-22:00, none crossing midnight. A rota "
            "record now means one employee, one date and one shift, so an employee "
            "may work several shifts on the same day. The rota is read as a week "
            "with previous/next-week navigation, and the three roles have three "
            "different weekly views: personal timetable (employee), grouped by day "
            "(Supervisor) and grouped by employee with filters (HR). FR06, FR07, "
            "FR08, the role definitions, section 6 and Use Cases 2, 3, 4 and 6 "
            "were updated accordingly.",
        ],
    )

    # ---- Background (paragraph 13) ---------------------------------------
    set_paragraph_text(
        paragraphs[13],
        "Client priority:Employee management is the highest-priority objective "
        "for this project iteration.Product-stock management will only be "
        "considered if the team has remaining spare time.All other advanced "
        "features belong to future product versions.Three fixed daily shifts are "
        "planned and their times were confirmed with the client after the "
        "demonstration:Morning 08:00-12:00,Afternoon 14:00-18:00 and Evening "
        "20:00-22:00.No shift crosses midnight,so every rota record belongs to "
        "exactly one calendar date.The rota is planned and read per week(Monday "
        "to Sunday),and an employee may work more than one shift on the same day.",
    )

    # ---- Scope and objectives (paragraph 15) -----------------------------
    set_paragraph_text(
        paragraphs[15],
        "Employee management module(Must-have,core for current release)Complete "
        "employee record management,employee query,manual weekly rota "
        "planning,weekly rota viewing and workforce statistics,with role "
        "permission separation for HR,Supervisor and Ordinary Employee.The rota "
        "is stored per calendar date:one record assigns one employee to one shift "
        "on one day,and the same employee may hold several shifts on one day.",
    )

    # ---- End-user roles (Table 3) ----------------------------------------
    roles = tables[3]
    set_cell_text(
        roles.rows[1].cells[1],
        "Full read-write access to employee records.Create,edit and delete "
        "employee records;query employee information and view the weekly rota of "
        "the whole store,grouped by employee,with filters by shift and by "
        "employee name.Performs recruitment and dismissal-related personnel "
        "operations.Cannot plan or change work shifts.",
    )
    set_cell_text(
        roles.rows[2].cells[1],
        "Store team supervisor.Can query employee information and view the "
        "weekly rota of the whole store,grouped by day:which employees work the "
        "Morning,Afternoon and Evening shift on each day.Responsible for planning "
        "the weekly rota of subordinates from the employee detail page,where the "
        "same employee may be given several shifts on the same day.No permission "
        "to create or delete employee records.",
    )
    set_cell_text(
        roles.rows[3].cells[1],
        "General shop staff.Read-only access:can view only their own weekly "
        "timetable,with the three shifts as rows and Monday to Sunday as "
        "columns.Cannot modify employee data or rota plans.",
    )

    # ---- Assumptions (paragraphs 34-36) ----------------------------------
    rota_assumption = insert_paragraph_after(
        paragraphs[35],
        "The rota is planned per calendar date and displayed per week(Monday to "
        "Sunday).The shift times are Morning 08:00-12:00,Afternoon 14:00-18:00 "
        "and Evening 20:00-22:00;no shift crosses midnight.",
    )
    insert_paragraph_after(
        rota_assumption,
        "An employee may work several shifts on the same day.The rota therefore "
        "holds one record per employee,per date and per shift,and an employee's "
        "week may also be empty.",
    )

    # ---- Functional requirements (Table 5) -------------------------------
    requirements = tables[5]
    set_cell_text(
        requirements.rows[6].cells[1],
        "Supervisor can plan the weekly rota:assign the Morning,Afternoon or "
        "Evening shift to an employee on a chosen date.More than one shift may be "
        "assigned to the same employee on the same day,and single rota entries "
        "can be removed again",
    )
    set_cell_text(
        requirements.rows[7].cells[1],
        "HR and Supervisor can view the weekly rota of one single employee for the "
        "whole week,with previous/next-week navigation;an Ordinary Employee can "
        "view only their own weekly timetable",
    )
    set_cell_text(
        requirements.rows[8].cells[1],
        "HR and Supervisor can view the weekly rota of the whole store:the "
        "Supervisor view is grouped by day(which employees work each shift on each "
        "day),the HR view is grouped by employee with filters by shift and by "
        "employee name",
    )
    set_cell_text(
        requirements.rows[10].cells[1],
        "Supervisor can view the weekly store rota and plan rota entries;cannot "
        "create,edit or delete employee records",
    )
    set_cell_text(
        requirements.rows[13].cells[1],
        "A simple workforce statistic(employee count and the shift counts of the "
        "week)is displayed on the employee overview and statistics pages",
    )

    # ---- Non-functional requirements (Table 6) ---------------------------
    nonfunctional = tables[6]
    set_cell_text(
        nonfunctional.rows[2].cells[1],
        "Role-based access control:only HR can add,edit or delete employee "
        "records;only Supervisor can plan rota entries;Ordinary Employees can "
        "view only their own weekly timetable",
    )
    set_cell_text(
        nonfunctional.rows[3].cells[1],
        "Employee and rota data persist after application restarts",
    )

    # ---- GUI views (paragraphs 43-46) ------------------------------------
    set_paragraph_text(
        paragraphs[43],
        "Employee Overview View:Table view listing all employees;includes a "
        "search box and the filters by wage range,shift and sort order.A shift "
        "column summarises the shifts of the current week for each employee"
        "(e.g.'Morning,Evening').HR sees the Add/Edit/Delete action buttons.For "
        "Supervisor these modification buttons are hidden.This overview is the "
        "main content of the System Home Page for HR and Supervisor,next to the "
        "quick actions for adding an employee and opening the store rota or the "
        "statistics.Ordinary Employee cannot access this view.",
    )
    set_paragraph_text(
        paragraphs[44],
        "Employee Detail and Edit View:Displays employee personal data and,for "
        "the week being viewed,the rota records of that employee with date,"
        "weekday,shift,time,and who confirmed each record.HR can edit the fields "
        "and read the rota.For Supervisor the input boxes are disabled,showing "
        "read-only data,and the rota panel can add or remove entries.Ordinary "
        "Employee cannot access this page.",
    )
    set_paragraph_text(
        paragraphs[45],
        "Shift Assignment Panel View:Visible only for the Supervisor actor.A "
        "working-date field and a selector for Morning(08:00-12:00)/Afternoon"
        "(14:00-18:00)/Evening(20:00-22:00)plus a confirm button add one rota "
        "record;each row of the week's rota list has its own remove button."
        "Assigning the same employee,date and shift again only refreshes who "
        "confirmed it.HR performs personnel-file operations,not daily rota "
        "planning.",
    )
    my_shifts_paragraph = insert_paragraph_after(
        paragraphs[45],
        "My Work Shifts View:Personal weekly timetable for the Ordinary "
        "Employee.Rows are the three fixed shifts and columns are Monday to "
        "Sunday,each column headed with its date.A tick marks every shift the "
        "employee works that day;an empty cell marks a free day.Occupies the "
        "whole page,is read-only,and offers previous/next-week navigation.",
    )
    set_paragraph_text(
        paragraphs[46],
        "Full-Store Shift Overview View:Weekly rota for the whole store,"
        "accessible to HR and Supervisor,shown for one week at a time with "
        "previous/next-week navigation.The Supervisor view is grouped by day:for "
        "each day of the week the three shifts are listed with the employees who "
        "work them,including an explicit 'no one assigned' state.The HR view is "
        "grouped by employee:one row per employee with the shifts of every day "
        "and a week summary,and filters by shift and by employee name."
        "Shift-modification controls are hidden in both views;the rota is changed "
        "only from the employee detail page.Ordinary Employee reaches their own "
        "timetable through the separate'My Work Shifts'view.",
    )

    # ---- Use-case list in section 7 --------------------------------------
    use_cases = document.paragraphs
    for paragraph in use_cases:
        text = paragraph.text
        if text.startswith("-Add new employee-Delete employee"):
            set_paragraph_text(
                paragraph,
                text.replace(
                    "-View single-employee shift-View full-store shift overview",
                    "-View single-employee weekly rota-View full-store weekly "
                    "rota(grouped by employee)",
                ),
            )
        elif text.startswith("-Search employee(included by detail-view use cases)"
                             "-View employee details-View single-employee shift"):
            set_paragraph_text(
                paragraph,
                text.replace(
                    "-View single-employee shift-View full-store shift overview"
                    "-Manually assign work shift",
                    "-View single-employee weekly rota-View full-store weekly "
                    "rota(grouped by day)-Plan the weekly rota(add and remove "
                    "dated shifts)",
                ),
            )
        elif text.strip() == "-View own work shifts":
            set_paragraph_text(paragraph, "-View own weekly timetable")
        elif text.startswith("1.Shared use-cases:Search employee"):
            set_paragraph_text(
                paragraph,
                text.replace(
                    "3.Exclusive to Supervisor:Manually assign work shift.",
                    "3.Exclusive to Supervisor:Plan the weekly rota(add and "
                    "remove dated shifts).",
                ),
            )

    # ---- Constraint and use-case headings in section 7/8 -----------------
    for paragraph in paragraphs:
        text = paragraph.text
        if text.startswith("Functional constraint:"):
            set_paragraph_text(
                paragraph,
                "Functional constraint:Only manual rota planning on a chosen date "
                "is supported;automatic shift generation is excluded.",
            )
        elif text.startswith("Use Case 2:"):
            set_paragraph_text(
                paragraph,
                "Use Case 2:Supervisor plans the weekly rota of an "
                "employee(FR06)",
            )
        elif text.startswith("Use Case 3:"):
            set_paragraph_text(
                paragraph,
                "Use Case 3:User views the weekly rota of a single "
                "employee(FR07)",
            )
        elif text.startswith("Use Case 4:"):
            set_paragraph_text(
                paragraph,
                "Use Case 4:User browses the weekly rota of the whole "
                "store(FR08,FR10)",
            )
        elif text.startswith("Use Case 6:"):
            set_paragraph_text(
                paragraph,
                "Use Case 6:Ordinary Employee views their own weekly "
                "timetable(FR07)",
            )
        elif text.startswith("1.Shared use-cases:Search employee"):
            set_paragraph_text(
                paragraph,
                text.replace(
                    "View single-employee shift and View full-store shift "
                    "overview",
                    "View single-employee weekly rota and View full-store weekly "
                    "rota",
                ).replace(
                    "4.Exclusive to Ordinary Employee:View own work shifts only.",
                    "4.Exclusive to Ordinary Employee:View own weekly timetable "
                    "only.",
                ),
            )

    # ---- Use Case 2: plan the weekly rota (Table 8) ----------------------
    use_case_2 = tables[8]
    set_cell_text(
        use_case_2.rows[1].cells[1],
        "Supervisor plans the weekly rota of an employee",
    )
    set_cell_text(
        use_case_2.rows[2].cells[1], "Supervisor"
    )
    set_cell_text(
        use_case_2.rows[3].cells[1],
        "Supervisor is logged in;the target employee record exists in the system.",
    )
    set_cell_text(
        use_case_2.rows[4].cells[1],
        "Supervisor opens the target employee detail page and uses the rota "
        "panel.",
    )
    set_cell_text(
        use_case_2.rows[5].cells[1],
        "1.System presents a working-date field and the three shift options:"
        "Morning(08:00-12:00)/Afternoon(14:00-18:00)/Evening(20:00-22:00). "
        "2.Supervisor selects the date and one shift and confirms. 3.System saves "
        "one rota record linked to the employee ID,the date and the shift. "
        "4.System records who confirmed the entry and when. 5.The employee detail "
        "page displays the updated week,and the store rota and the employee's "
        "timetable reflect the change as well. 6.Supervisor may repeat steps 1-2 "
        "for the same employee and date to add a second shift,and may remove a "
        "single entry from the week list.",
    )
    set_cell_text(
        use_case_2.rows[6].cells[1],
        "1A(Step 2):The target employee record cannot be found in the system. "
        "1.System pops up an error notification. 2.System returns to the employee "
        "overview page and terminates the use case. "
        "2A(Step 2):The working date is missing or not a valid date,or the shift "
        "is not one of the three fixed shifts. 1.System displays a user-friendly "
        "message. 2.No rota record is written and the use case terminates.",
    )

    # ---- Use Case 3: one employee's weekly rota (Table 9) ----------------
    use_case_3 = tables[9]
    set_cell_text(
        use_case_3.rows[1].cells[1], "View the weekly rota of a single employee"
    )
    set_cell_text(
        use_case_3.rows[4].cells[1],
        "The user opens the detail page of the target employee.",
    )
    set_cell_text(
        use_case_3.rows[5].cells[1],
        "1.System loads the employee detail view for the current week. 2.System "
        "fetches and displays every rota record of that employee for the week,"
        "ordered by date and by shift,with date,weekday,shift,time,the "
        "confirmation timestamp and the actor. 3.The user may move to the "
        "previous or the next week.",
    )
    set_cell_text(
        use_case_3.rows[6].cells[1],
        "1A(Step 2):No rota record exists for this employee in the week shown. "
        "1.System shows the placeholder text\"No shifts assigned for this "
        "employee\"and still offers the week navigation. 2.The use case completes "
        "normally.",
    )

    # ---- Use Case 4: whole-store weekly rota (Table 10) ------------------
    use_case_4 = tables[10]
    set_cell_text(
        use_case_4.rows[1].cells[1], "View the weekly rota of the whole store"
    )
    set_cell_text(
        use_case_4.rows[5].cells[1],
        "1.System loads the store rota for the current week. 2.For the "
        "Supervisor the week is grouped by day:each day lists the employees of "
        "the Morning,Afternoon and Evening shift,including an explicit empty "
        "state,and every employee name links to that employee's detail page. "
        "3.For HR the week is grouped by employee:one row per employee shows the "
        "shifts of each day and a week summary,and HR may filter by shift and by "
        "employee name. 4.Both views offer previous/next-week navigation and "
        "always hide shift-modification controls;the rota is changed only from "
        "the employee detail page.",
    )
    set_cell_text(
        use_case_4.rows[6].cells[1],
        "1A(Step 1):No rota record exists for the week shown. 1.System displays "
        "the empty days(groups with\"No one assigned\")or,when no employee record "
        "exists at all,the placeholder text\"No employee data available\". "
        "2.The use case completes normally.",
    )

    # ---- Use Case 5: cascade of rota rows (Table 11) ---------------------
    use_case_5 = tables[11]
    set_cell_text(
        use_case_5.rows[5].cells[1],
        "1.System pops up a confirmation dialog for the deletion action. 2.HR "
        "confirms the deletion. 3.System removes the employee record and every "
        "rota record of that employee. 4.The employee overview list refreshes and "
        "the target entry disappears.",
    )

    # ---- Use Case 6: own weekly timetable (Table 12) ---------------------
    use_case_6 = tables[12]
    set_cell_text(
        use_case_6.rows[1].cells[1],
        "Ordinary Employee views their own weekly timetable",
    )
    set_cell_text(
        use_case_6.rows[5].cells[1],
        "1.System loads the personal timetable of the current week. 2.Rows are "
        "the three fixed shifts and columns are Monday to Sunday,each column "
        "headed with its date.A tick marks every shift the employee works that "
        "day and an empty cell marks a free day. 3.The employee may move to the "
        "previous or the next week.",
    )
    set_cell_text(
        use_case_6.rows[6].cells[1],
        "1A(Step 2):No shift has been assigned to the current employee in the "
        "week shown. 1.System shows the placeholder text\"You have not been "
        "assigned any shifts yet\"for the current week,or the empty timetable "
        "together with a message for another week. 2.The use case completes.",
    )

    # ---- System overall overview (paragraph 75) --------------------------
    set_paragraph_text(
        system_overview,
        "Three distinct end-user roles are defined,with strict role-based access "
        "control.(1)HR takes charge of the employee-record lifecycle:add,edit and "
        "delete employee personal records,and cross-check all employee and rota "
        "data through the weekly view grouped by employee;HR is not responsible "
        "for daily staff scheduling.(2)The Supervisor plans the weekly rota of "
        "subordinate staff and reads it day by day,to see who works which shift "
        "on each day;the Supervisor can browse employee and rota information but "
        "cannot create or delete employee archives.(3)Ordinary store employees "
        "can only view their own weekly timetable,without any modification "
        "privilege.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("URS_SOURCE", ""),
        help=f"the URS 1.2 .docx to revise (default: search the desktop for {SOURCE_NAME})",
    )
    parser.add_argument("--output", default=OUTPUT_PATH, help="where to write version 1.3")
    arguments = parser.parse_args()

    source = arguments.source or find_source()
    document = Document(source)
    revise(document)
    os.makedirs(os.path.dirname(os.path.abspath(arguments.output)), exist_ok=True)
    document.save(arguments.output)
    print(f"source: {source}")
    print(f"saved:  {arguments.output}  ({os.path.getsize(arguments.output):,} bytes)")


if __name__ == "__main__":
    main()
