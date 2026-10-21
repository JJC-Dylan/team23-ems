"""Page handlers: one function per screen described in URS section 6.

Route map
---------
======================  ====================  ===========================
Address                 Roles                 Requirement
======================  ====================  ===========================
``/``                   any signed-in user    home; staff see the searchable
                                              Employee Overview table (FR05),
                                              an employee sees their own week
``/login``              anonymous             Login View
``/logout``             any signed-in user    ends the session
``/employees/new``      HR                    add employee (FR01)
``/employees/<id>``     HR, Supervisor        detail + rota panel (FR04, FR07)
``/employees/<id>/edit``HR                    edit employee (FR03)
``/employees/<id>/delete`` HR                 delete employee (FR02)
``/employees/<id>/shift``  Supervisor        add a shift to the rota (FR06, FR10)
``/employees/<id>/shift/remove`` Supervisor   remove one rota row (FR06)
``/shifts``             HR, Supervisor        weekly store rota (FR08)
``/my-shifts``          Ordinary Employee     personal weekly timetable (FR07)
``/statistics``         HR, Supervisor        weekly totals (FR13)
``/healthz``            anonymous             liveness probe
======================  ====================  ===========================

Weekly views
------------
Every weekly screen accepts ``?week=YYYY-MM-DD``: any day of the wanted week
is enough, it is converted to that week's Monday. Without the parameter the
current week is shown. Each view offers previous/next week links, so a schedule
can be looked at without typing a URL.

The three roles deliberately see three different shapes of the same data:

* Ordinary Employee — a personal timetable (rows = shifts, columns = days).
* Supervisor — the whole shop grouped by day: who works which shift today.
* HR — the whole shop grouped by employee: what each person works this week.

Only the employee detail page changes the rota, so nobody edits the schedule by
accident from an overview.
"""

from __future__ import annotations

import urllib.parse
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from . import repositories as repo
from .database import (
    ROLE_EMPLOYEE,
    ROLE_HR,
    ROLE_SUPERVISOR,
    SHIFTS,
    WEEKDAYS,
    shift_window,
)
from .errors import HttpError
from .htmlpages import (
    DATE_RE,
    ValidationError,
    format_currency,
    format_wage,
    validate_employee,
    validate_wage_range,
)
from .security import SESSION_COOKIE_NAME, verify_password

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a runtime import cycle
    from .app import Application, _Request, _Response

HR_AND_SUPERVISOR = (ROLE_HR, ROLE_SUPERVISOR)
HR_ONLY = (ROLE_HR,)
SUPERVISOR_ONLY = (ROLE_SUPERVISOR,)
EMPLOYEE_ONLY = (ROLE_EMPLOYEE,)
ANY_ROLE = (ROLE_HR, ROLE_SUPERVISOR, ROLE_EMPLOYEE)

#: Shift name and time window, for every select box and legend in the GUI.
SHIFT_OPTIONS: tuple[dict[str, str], ...] = tuple(
    {"name": name, "time": shift_window(name)} for name in SHIFTS
)


def _app(request: "_Request") -> "Application":
    """The running application, published in the WSGI environment."""
    return request.environ["ems.app"]


# --------------------------------------------------------------------------
# Weekly helpers
# --------------------------------------------------------------------------


def _week_from_request(request: _Request) -> str:
    """The Monday of the week asked for by ``?week=`` (default: current week).

    Any day of the week is accepted, and an unreadable value falls back to the
    current week rather than showing an error: a mistyped link must never leave
    the user with a blank page.
    """
    return repo.week_dates(request.get("week"))[0]


def _with_query(path: str, **params: str) -> str:
    """Build a URL, dropping empty parameters so links stay readable."""
    clean = {key: value for key, value in params.items() if value}
    query = urllib.parse.urlencode(clean)
    return f"{path}?{query}" if query else path


def _week_context(
    week_start: str, base_path: str, extra: dict[str, str] | None = None
) -> dict[str, Any]:
    """Everything a template needs to draw a week header and its navigation."""
    dates = repo.week_dates(week_start)
    monday = date.fromisoformat(dates[0])
    sunday = date.fromisoformat(dates[-1])
    today = date.today()
    extra = extra or {}

    week_days = []
    for index, iso in enumerate(dates):
        current = date.fromisoformat(iso)
        week_days.append(
            {
                "date": iso,
                "weekday": WEEKDAYS[index],
                "day": current.day,
                "month": current.strftime("%b"),
                "is_today": current == today,
            }
        )

    return {
        "week_start": dates[0],
        "week_end": dates[-1],
        "week": week_days,
        "week_label": f"{monday:%d %b %Y} – {sunday:%d %b %Y}",
        "is_current_week": dates[0] == repo.week_dates()[0],
        "today": today.isoformat(),
        "week_prev_url": _with_query(
            base_path, week=(monday - timedelta(days=7)).isoformat(), **extra
        ),
        "week_next_url": _with_query(
            base_path, week=(monday + timedelta(days=7)).isoformat(), **extra
        ),
        "week_this_url": _with_query(base_path, **extra),
    }


def _day_label(iso_date: str) -> str:
    """``2026-10-19`` -> ``Mon 19 Oct 2026`` for confirmation messages."""
    try:
        value = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    return f"{WEEKDAYS[value.weekday()]} {value:%d %b %Y}"


def _parse_work_date(text: str) -> str | None:
    """Validate a ``YYYY-MM-DD`` form value; ``None`` when unusable."""
    text = (text or "").strip()
    if not DATE_RE.match(text):
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def _timetable_rows(
    shifts_by_date: dict[str, list[str]], week: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn ``{date: [shift, ...]}`` into the grid rows of the timetable.

    One row per fixed shift; one cell per day, marked when that shift is worked.
    """
    rows: list[dict[str, Any]] = []
    for shift_name in SHIFTS:
        cells = [
            {
                "date": day["date"],
                "weekday": day["weekday"],
                "assigned": shift_name in shifts_by_date.get(day["date"], []),
                "is_today": day["is_today"],
            }
            for day in week
        ]
        rows.append(
            {
                "shift": shift_name,
                "time": shift_window(shift_name),
                "cells": cells,
                "assigned_count": sum(1 for cell in cells if cell["assigned"]),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def register(app: Application) -> None:
    """Attach every route to the application."""

    app.route("/healthz")(lambda request, response: response.text("ok"))
    app.route("/login", methods=("GET", "POST"), roles=())(login)
    app.route("/logout", methods=("GET", "POST"), roles=ANY_ROLE)(logout)
    app.route("/", roles=ANY_ROLE)(home)

    app.route("/employees/new", methods=("GET", "POST"), roles=HR_ONLY)(employee_create)
    app.route(r"/employees/(?P<employee_id>\d+)", roles=HR_AND_SUPERVISOR)(employee_detail)
    app.route(
        r"/employees/(?P<employee_id>\d+)/edit", methods=("GET", "POST"), roles=HR_ONLY
    )(employee_edit)
    app.route(
        r"/employees/(?P<employee_id>\d+)/delete", methods=("POST",), roles=HR_ONLY
    )(employee_delete)
    app.route(
        r"/employees/(?P<employee_id>\d+)/shift", methods=("POST",), roles=SUPERVISOR_ONLY
    )(employee_assign_shift)
    app.route(
        r"/employees/(?P<employee_id>\d+)/shift/remove",
        methods=("POST",),
        roles=SUPERVISOR_ONLY,
    )(employee_clear_shift)

    app.route("/shifts", roles=HR_AND_SUPERVISOR)(store_shifts)
    app.route("/my-shifts", roles=EMPLOYEE_ONLY)(my_shifts)
    app.route("/statistics", roles=HR_AND_SUPERVISOR)(statistics)


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


def login(request: _Request, response: _Response) -> None:
    """Login View: username and password, then role-dependent navigation."""
    if request.session is not None:
        response.redirect("/")
        return

    error = ""
    username = ""
    next_path = request.get("next") or request.form_value("next") or "/"
    if not next_path.startswith("/"):
        next_path = "/"

    if request.method == "POST":
        username = request.form_value("username").strip()
        password = request.form_value("password")

        if not username or not password:
            error = "Please enter both your username and your password."
        else:
            row = repo.find_user_by_username(_app(request).db_path, username)
            if row is None or not verify_password(password, row["password_hash"]):
                # Deliberately identical message for unknown user and wrong
                # password so the form never reveals which accounts exist.
                error = "Username or password is incorrect. Please try again."
            else:
                session = _app(request).sessions.create(row)
                # URS 7: the flow starts from Login, enters the System Home
                # Page and branches by role from there, so every role lands on
                # "/" and the home page decides what it shows.
                destination = "/"
                if next_path not in ("/", "/login"):
                    destination = next_path
                response.set_cookie(SESSION_COOKIE_NAME, session.token, max_age=8 * 60 * 60)
                response.redirect(destination)
                return

    response.html(
        _app(request).render(
            request,
            "login.html",
            page_title="Sign in",
            error=error,
            username=username,
            next_path=next_path,
        )
    )


def logout(request: _Request, response: _Response) -> None:
    """End the session and return to the login screen."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    _app(request).sessions.destroy(token)
    response.clear_cookie(SESSION_COOKIE_NAME)
    response.redirect("/login")


# --------------------------------------------------------------------------
# Home
# --------------------------------------------------------------------------


def home(request: _Request, response: _Response) -> None:
    """Role-aware landing page for the signed-in user."""
    session = request.session
    assert session is not None  # guaranteed by the route's role list
    app: Application = _app(request)

    context: dict[str, Any] = {"page_title": "Home", "session_role": session.role}

    if session.is_ordinary_employee:
        context.update(_own_week_context(app, session, repo.week_dates()[0]))
        response.html(app.render(request, "home_employee.html", **context))
        return

    week_start = repo.week_dates()[0]
    week = _week_context(week_start, "/shifts")

    # The staff home page carries the searchable employee table itself, so it
    # accepts the same filters as the Employee Overview view (FR04, FR05, FR12).
    query = request.get("q").strip()
    shift_filter = request.get("shift").strip()
    if shift_filter not in (*SHIFTS, "Unassigned"):
        shift_filter = ""
    sort = request.get("sort", "name").strip()
    wage_min_text = request.get("wage_min").strip()
    wage_max_text = request.get("wage_max").strip()
    wage_min, wage_max, filter_problem = validate_wage_range(wage_min_text, wage_max_text)

    employees = repo.search_employees(
        app.db_path,
        query=query,
        wage_min=wage_min,
        wage_max=wage_max,
        shift=shift_filter,
        sort=sort,
        week_start=week_start,
    )
    shift_counts = repo.week_summary_counts(app.db_path, week_start)
    context.update(
        {
            "total_employees": repo.count_employees(app.db_path),
            "result_count": len(employees),
            "employees": employees,
            "shift_counts": shift_counts,
            "shift_people": repo.employee_counts_per_shift(app.db_path, week_start),
            "assigned_total": shift_counts["Total"],
            "unassigned_total": repo.count_employees_without_week_shifts(
                app.db_path, week_start
            ),
            "average_wage": format_currency(repo.average_hourly_wage(app.db_path)),
            "week": week,
            "week_label": week["week_label"],
            "shift_options": SHIFT_OPTIONS,
            "format_currency": format_currency,
            "can_manage": session.can_manage_employees,
            "query": query,
            "shift_filter": shift_filter,
            "sort": sort,
            "wage_min": wage_min_text,
            "wage_max": wage_max_text,
            "filter_problem": filter_problem,
        }
    )
    response.html(app.render(request, "home_staff.html", **context))


# --------------------------------------------------------------------------
# Employee overview and detail
# --------------------------------------------------------------------------


def employee_detail(request: _Request, response: _Response) -> None:
    """Employee Detail View with the rota panel for Supervisors."""
    app: Application = _app(request)
    session = request.session
    assert session is not None

    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        raise HttpError(
            404,
            "Employee not found",
            "That employee record does not exist. It may have been deleted.",
        )

    week_start = _week_from_request(request)
    week = _week_context(week_start, f"/employees/{employee_id}")
    rota = repo.employee_week_rows(app.db_path, employee_id, week_start)
    form_date = week["today"] if week["today"] in {
        day["date"] for day in week["week"]
    } else week["week_start"]

    response.html(
        app.render(
            request,
            "employee_detail.html",
            page_title=str(employee["name"]),
            employee=employee,
            rota=rota,
            shift_count=len(rota),
            hourly_wage_text=format_currency(employee["hourly_wage"]),
            can_edit=session.can_manage_employees,
            can_assign=session.can_assign_shifts,
            shift_options=SHIFT_OPTIONS,
            form_date=form_date,
            week=week,
            week_label=week["week_label"],
            form={},
            errors={},
        )
    )


def employee_create(request: _Request, response: _Response) -> None:
    """FR01: HR adds a new employee record.

    Extension 1A of URS Use Case 1 is implemented here: on invalid input the
    system shows a friendly message per field, stays on the form and preserves
    everything the user already typed.
    """
    app: Application = _app(request)

    if request.method == "POST":
        form = {
            "name": request.form_value("name"),
            "address": request.form_value("address"),
            "hourly_wage": request.form_value("hourly_wage"),
            "phone": request.form_value("phone"),
            "email": request.form_value("email"),
            "hired_on": request.form_value("hired_on"),
        }
        try:
            cleaned = validate_employee(form)
        except ValidationError as error:
            response.html(
                app.render(
                    request,
                    "employee_form.html",
                    page_title="Add employee",
                    mode="create",
                    employee=None,
                    form=form,
                    errors=error.errors,
                )
            )
            return

        employee_id = repo.create_employee(app.db_path, cleaned)
        request.flash(f"Employee {cleaned['name']} was added successfully.", "success")
        response.redirect(f"/employees/{employee_id}")
        return

    response.html(
        app.render(
            request,
            "employee_form.html",
            page_title="Add employee",
            mode="create",
            employee=None,
            form={},
            errors={},
        )
    )


def employee_edit(request: _Request, response: _Response) -> None:
    """FR03: HR edits and updates existing employee information."""
    app: Application = _app(request)
    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        raise HttpError(
            404,
            "Employee not found",
            "That employee record does not exist. It may have been deleted.",
        )

    if request.method == "POST":
        form = {
            "name": request.form_value("name"),
            "address": request.form_value("address"),
            "hourly_wage": request.form_value("hourly_wage"),
            "phone": request.form_value("phone"),
            "email": request.form_value("email"),
            "hired_on": request.form_value("hired_on"),
        }
        try:
            cleaned = validate_employee(form)
        except ValidationError as error:
            response.html(
                app.render(
                    request,
                    "employee_form.html",
                    page_title=f"Edit {employee['name']}",
                    mode="edit",
                    employee=employee,
                    form=form,
                    errors=error.errors,
                )
            )
            return

        if repo.update_employee(app.db_path, employee_id, cleaned):
            request.flash(f"Employee {cleaned['name']} was updated.", "success")
        else:
            request.flash("That employee record no longer exists.", "error")
        response.redirect(f"/employees/{employee_id}")
        return

    response.html(
        app.render(
            request,
            "employee_form.html",
            page_title=f"Edit {employee['name']}",
            mode="edit",
            employee=employee,
            form={
                "name": employee["name"],
                "address": employee["address"],
                "hourly_wage": format_wage(employee["hourly_wage"]),
                "phone": employee["phone"],
                "email": employee["email"],
                "hired_on": employee["hired_on"],
            },
            errors={},
        )
    )


def employee_delete(request: _Request, response: _Response) -> None:
    """FR02: HR deletes a record; linked rota rows cascade (Use Case 5).

    The confirmation dialog lives in the overview page, so by the time this
    handler runs the user has already confirmed. Cancelling simply never
    reaches this route, which is extension 1A of Use Case 5.
    """
    app: Application = _app(request)
    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        raise HttpError(
            404,
            "Employee not found",
            "That employee record does not exist. It may already have been deleted.",
        )

    name = str(employee["name"])
    shifts_planned = sum(
        len(names) for names in repo.employee_week_shifts(app.db_path, employee_id).values()
    )
    repo.delete_employee(app.db_path, employee_id)
    detail = (
        f"; the {shifts_planned} rota row(s) of this employee were removed as well"
        if shifts_planned
        else ""
    )
    request.flash(f"Employee {name} was deleted{detail}.", "success")
    response.redirect("/")


# --------------------------------------------------------------------------
# Shifts (dated weekly rota)
# --------------------------------------------------------------------------


def employee_assign_shift(request: _Request, response: _Response) -> None:
    """FR06/FR10: a Supervisor puts one employee into one shift on one day.

    The form carries a date and a shift, so the same employee may be given a
    second shift on the same day. Extension 1A of URS Use Case 2: when the
    target record cannot be found the system reports it and returns to the
    employee overview on the home page.
    """
    app: Application = _app(request)
    session = request.session
    assert session is not None

    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        request.flash("That employee record could not be found.", "error")
        response.redirect("/")
        return

    work_date = _parse_work_date(request.form_value("work_date"))
    choice = request.form_value("shift_name").strip()
    anchor = f"/employees/{employee_id}"

    if work_date is None:
        request.flash(
            "Please choose the working date for this shift. Nothing was changed.",
            "error",
        )
        response.redirect(anchor)
        return
    if choice not in SHIFTS:
        request.flash(
            "Please choose Morning, Afternoon or Evening. Nothing was changed.", "error"
        )
        response.redirect(f"{anchor}?week={work_date}")
        return

    repo.assign_shift(app.db_path, employee_id, work_date, choice, session.display_name)
    request.flash(
        f"{employee['name']} now works the {choice} shift "
        f"({shift_window(choice)}) on {_day_label(work_date)}.",
        "success",
    )
    response.redirect(f"{anchor}?week={work_date}")


def employee_clear_shift(request: _Request, response: _Response) -> None:
    """FR06: remove exactly one rota row (one employee, one day, one shift)."""
    app: Application = _app(request)

    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        request.flash("That employee record could not be found.", "error")
        response.redirect("/")
        return

    work_date = _parse_work_date(request.form_value("work_date"))
    choice = request.form_value("shift_name").strip()
    anchor = f"/employees/{employee_id}"

    if work_date is None or choice not in SHIFTS:
        request.flash(
            "That rota entry could not be identified, so nothing was removed.", "error"
        )
        response.redirect(anchor)
        return

    if repo.clear_shift(app.db_path, employee_id, work_date, choice):
        request.flash(
            f"The {choice} shift of {employee['name']} on {_day_label(work_date)} "
            "was removed.",
            "success",
        )
    else:
        request.flash(
            f"There was no {choice} shift for {employee['name']} on "
            f"{_day_label(work_date)}.",
            "error",
        )
    response.redirect(f"{anchor}?week={work_date}")


def store_shifts(request: _Request, response: _Response) -> None:
    """FR08: the weekly store rota for HR and Supervisor.

    Both roles read the same data but see a different shape, as confirmed with
    the client: the Supervisor reads the week day by day ("who is in today"),
    HR reads it employee by employee ("what does this person work this week")
    and may filter. URS 6 states that shift-modification controls are hidden
    here; the rota is changed from the employee detail page only.
    """
    app: Application = _app(request)
    session = request.session
    assert session is not None

    week_start = _week_from_request(request)
    query = request.get("q").strip()
    shift_filter = request.get("shift").strip()
    if shift_filter not in (*SHIFTS, "Unassigned"):
        shift_filter = ""

    extra = {"shift": shift_filter, "q": query}
    week = _week_context(week_start, "/shifts", extra)
    counts = repo.week_summary_counts(app.db_path, week_start)

    context: dict[str, Any] = {
        "page_title": "Store shift overview",
        "week": week,
        "week_label": week["week_label"],
        "counts": counts,
        "total_employees": repo.count_employees(app.db_path),
        "unassigned_total": repo.count_employees_without_week_shifts(
            app.db_path, week_start
        ),
        "query": query,
        "shift_filter": shift_filter,
        "shift_options": SHIFT_OPTIONS,
        "is_supervisor_view": session.is_supervisor,
        "days": [],
        "employees": [],
        "listed_count": 0,
    }

    if session.is_supervisor:
        # Day-by-day overview: the Supervisor reads the week as "who is in
        # which shift today", so no filtering is offered here.
        days = repo.day_roster(app.db_path, week_start)
        context["days"] = days
        context["listed_count"] = sum(day["total"] for day in days)
    else:
        roster = repo.employee_roster(app.db_path, week_start)
        if query:
            needle = query.casefold()
            roster = [person for person in roster if needle in person["name"].casefold()]
        if shift_filter == "Unassigned":
            roster = [person for person in roster if person["shift_count"] == 0]
        elif shift_filter:
            roster = [
                person
                for person in roster
                if any(shift_filter in names for names in person["days"].values())
            ]
        context["employees"] = roster
        context["listed_count"] = len(roster)

    response.html(app.render(request, "store_shifts.html", **context))


def my_shifts(request: _Request, response: _Response) -> None:
    """FR07: an Ordinary Employee views only their own weekly timetable."""
    app: Application = _app(request)
    session = request.session
    assert session is not None

    week_start = _week_from_request(request)
    context = _own_week_context(app, session, week_start)
    context["page_title"] = "My work shifts"
    context["shift_options"] = SHIFT_OPTIONS
    response.html(app.render(request, "my_shifts.html", **context))


def _own_week_context(
    app: Application, session, week_start: str
) -> dict[str, Any]:
    """The signed-in Ordinary Employee's own timetable for one week."""
    week = _week_context(week_start, "/my-shifts")
    context: dict[str, Any] = {
        "employee": None,
        "profile_linked": False,
        "week": week,
        "week_label": week["week_label"],
        "timetable": [],
        "rota": [],
        "shift_count": 0,
    }
    if session.employee_id is None:
        return context

    employee = repo.get_employee(app.db_path, session.employee_id)
    if employee is None:
        return context

    shifts_by_date = repo.employee_week_shifts(
        app.db_path, session.employee_id, week["week_start"]
    )
    context.update(
        {
            "employee": employee,
            "profile_linked": True,
            "hourly_wage_text": format_currency(employee["hourly_wage"]),
            "timetable": _timetable_rows(shifts_by_date, week["week"]),
            "rota": repo.employee_week_rows(
                app.db_path, session.employee_id, week["week_start"]
            ),
            "shift_count": sum(len(names) for names in shifts_by_date.values()),
        }
    )
    return context


# --------------------------------------------------------------------------
# Statistics (FR13)
# --------------------------------------------------------------------------


def statistics(request: _Request, response: _Response) -> None:
    """Weekly totals: who works how much in the week being looked at."""
    app: Application = _app(request)

    week_start = _week_from_request(request)
    week = _week_context(week_start, "/statistics")
    employees = repo.search_employees(app.db_path, week_start=week_start)
    shift_counts = repo.week_summary_counts(app.db_path, week_start)
    wages = [float(row["hourly_wage"]) for row in employees]

    response.html(
        app.render(
            request,
            "statistics.html",
            page_title="Statistics",
            week=week,
            week_label=week["week_label"],
            total_employees=len(employees),
            shift_counts=shift_counts,
            assigned_total=shift_counts["Total"],
            unassigned_total=repo.count_employees_without_week_shifts(
                app.db_path, week_start
            ),
            average_wage=format_currency(repo.average_hourly_wage(app.db_path)),
            lowest_wage=format_currency(min(wages)) if wages else "Not set",
            highest_wage=format_currency(max(wages)) if wages else "Not set",
            wage_bill=format_currency(sum(wages)) if wages else "Not set",
            employees=employees,
            shift_options=SHIFT_OPTIONS,
            format_currency=format_currency,
        )
    )
