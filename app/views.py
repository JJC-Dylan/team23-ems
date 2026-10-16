"""Page handlers: one function per screen described in URS section 6.

Route map
---------
======================  ====================  ===========================
Address                 Roles                 Requirement
======================  ====================  ===========================
``/``                   any signed-in user    role-aware home page
``/login``              anonymous             Login View
``/logout``             any signed-in user    ends the session
``/employees``          HR, Supervisor        Employee Overview View (FR05)
``/employees/new``      HR                    add employee (FR01)
``/employees/<id>``     HR, Supervisor        detail + shift panel (FR04, FR07)
``/employees/<id>/edit``HR                    edit employee (FR03)
``/employees/<id>/delete`` HR                 delete employee (FR02)
``/employees/<id>/shift``  Supervisor        assign shift (FR06, FR10)
``/shifts``             HR, Supervisor        Full-Store Shift Overview (FR08)
``/my-shifts``          Ordinary Employee     My Work Shifts (FR07)
``/statistics``         HR, Supervisor        totals (FR13)
``/healthz``            anonymous             liveness probe
======================  ====================  ===========================

The decorative separators in the table above are intentionally ASCII so the
file stays readable in any editor or console.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import repositories as repo
from .database import (
    ROLE_EMPLOYEE,
    ROLE_HR,
    ROLE_SUPERVISOR,
    SHIFTS,
)
from .errors import HttpError
from .htmlpages import (
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


def _app(request: "_Request") -> "Application":
    """The running application, published in the WSGI environment."""
    return request.environ["ems.app"]


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


def register(app: Application) -> None:
    """Attach every route to the application."""

    app.route("/healthz")(lambda request, response: response.text("ok"))
    app.route("/login", methods=("GET", "POST"), roles=())(login)
    app.route("/logout", methods=("GET", "POST"), roles=ANY_ROLE)(logout)
    app.route("/", roles=ANY_ROLE)(home)

    app.route("/employees", roles=HR_AND_SUPERVISOR)(employee_overview)
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
                # URS 7: the flow starts from Login and then branches by role.
                destination = "/"
                if session.is_ordinary_employee:
                    destination = "/my-shifts"
                elif next_path not in ("/", "/login"):
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
        context.update(_own_shift_context(app, session))
        response.html(app.render(request, "home_employee.html", **context))
        return

    employees = repo.search_employees(app.db_path)
    shift_counts = repo.shift_summary_counts(employees)
    context.update(
        {
            "total_employees": len(employees),
            "shift_counts": shift_counts,
            "assigned_total": sum(shift_counts.get(name, 0) for name in SHIFTS),
            "unassigned_total": shift_counts.get("Unassigned", 0),
            "average_wage": format_currency(repo.average_hourly_wage(app.db_path)),
            "recent_employees": employees[:5],
        }
    )
    response.html(app.render(request, "home_staff.html", **context))


# --------------------------------------------------------------------------
# Employee overview and detail
# --------------------------------------------------------------------------


def employee_overview(request: _Request, response: _Response) -> None:
    """Employee Overview View: searchable table with role-dependent actions."""
    app: Application = _app(request)
    session = request.session
    assert session is not None

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
    )
    total_employees = repo.count_employees(app.db_path)

    response.html(
        app.render(
            request,
            "employees_overview.html",
            page_title="Employees",
            employees=employees,
            result_count=len(employees),
            total_employees=total_employees,
            query=query,
            shift_filter=shift_filter,
            sort=sort,
            wage_min=wage_min_text,
            wage_max=wage_max_text,
            filter_problem=filter_problem,
            can_manage=session.can_manage_employees,
            shift_counts=repo.shift_summary_counts(employees),
            format_currency=format_currency,
        )
    )


def employee_detail(request: _Request, response: _Response) -> None:
    """Employee Detail View with the shift-assignment panel for Supervisors."""
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

    shift_row = repo.get_employee_shift(app.db_path, employee_id)
    response.html(
        app.render(
            request,
            "employee_detail.html",
            page_title=str(employee["name"]),
            employee=employee,
            shift_row=shift_row,
            hourly_wage_text=format_currency(employee["hourly_wage"]),
            can_edit=session.can_manage_employees,
            can_assign=session.can_assign_shifts,
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
    """FR02: HR deletes a record; linked shift rows cascade (Use Case 5).

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
    shift_was_assigned = employee["shift_name"] is not None
    repo.delete_employee(app.db_path, employee_id)
    detail = (
        "; the linked shift assignment was removed as well" if shift_was_assigned else ""
    )
    request.flash(f"Employee {name} was deleted{detail}.", "success")
    response.redirect("/employees")


# --------------------------------------------------------------------------
# Shifts
# --------------------------------------------------------------------------


def employee_assign_shift(request: _Request, response: _Response) -> None:
    """FR06/FR10: a Supervisor manually assigns Morning, Afternoon or Evening.

    Extension 1A of URS Use Case 2: when the target record cannot be found the
    system reports it and returns to the employee overview.
    """
    app: Application = _app(request)
    session = request.session
    assert session is not None

    employee_id = request.path_id()
    employee = repo.get_employee(app.db_path, employee_id)
    if employee is None:
        request.flash("That employee record could not be found.", "error")
        response.redirect("/employees")
        return

    choice = request.form_value("shift_name")
    if choice == "Unassigned":
        repo.clear_shift(app.db_path, employee_id, session.display_name)
        request.flash(f"Shift assignment removed for {employee['name']}.", "success")
    elif choice in SHIFTS:
        repo.assign_shift(app.db_path, employee_id, choice, session.display_name)
        request.flash(
            f"{employee['name']} is now assigned to the {choice} shift.", "success"
        )
    else:
        request.flash(
            "Please choose Morning, Afternoon or Evening. Nothing was changed.", "error"
        )
    response.redirect(f"/employees/{employee_id}")


def store_shifts(request: _Request, response: _Response) -> None:
    """FR08: the full-store work-shift overview for HR and Supervisor.

    URS 6 states that shift-modification controls are hidden here; assignment
    happens from the employee detail panel, so this page only reads.
    """
    app: Application = _app(request)

    shift_filter = request.get("shift").strip()
    if shift_filter not in (*SHIFTS, "Unassigned"):
        shift_filter = ""
    query = request.get("q").strip()

    rows = repo.store_shift_overview(app.db_path)
    if query:
        needle = query.casefold()
        rows = [row for row in rows if needle in str(row["name"]).casefold()]
    if shift_filter:
        rows = [
            row
            for row in rows
            if (row["shift_name"] or "Unassigned") == shift_filter
        ]

    response.html(
        app.render(
            request,
            "store_shifts.html",
            page_title="Store shift overview",
            rows=rows,
            shift_filter=shift_filter,
            query=query,
            counts=repo.shift_summary_counts(rows),
            total_employees=repo.count_employees(app.db_path),
        )
    )


def my_shifts(request: _Request, response: _Response) -> None:
    """FR07: an Ordinary Employee views only their own assigned shifts."""
    app: Application = _app(request)
    session = request.session
    assert session is not None
    context = _own_shift_context(app, session)
    context["page_title"] = "My work shifts"
    response.html(app.render(request, "my_shifts.html", **context))


def _own_shift_context(app: Application, session) -> dict[str, Any]:
    """Shift information for the signed-in Ordinary Employee."""
    if session.employee_id is None:
        return {"employee": None, "shift_row": None, "profile_linked": False}
    employee = repo.get_employee(app.db_path, session.employee_id)
    if employee is None:
        return {"employee": None, "shift_row": None, "profile_linked": False}
    return {
        "employee": employee,
        "shift_row": repo.get_employee_shift(app.db_path, session.employee_id),
        "profile_linked": True,
        "hourly_wage_text": format_currency(employee["hourly_wage"]),
    }


# --------------------------------------------------------------------------
# Statistics (FR13)
# --------------------------------------------------------------------------


def statistics(request: _Request, response: _Response) -> None:
    """A simple total-employee-count statistic plus shift distribution."""
    app: Application = _app(request)
    employees = repo.search_employees(app.db_path)
    shift_counts = repo.shift_summary_counts(employees)
    wages = [float(row["hourly_wage"]) for row in employees]

    response.html(
        app.render(
            request,
            "statistics.html",
            page_title="Statistics",
            total_employees=len(employees),
            shift_counts=shift_counts,
            assigned_total=sum(shift_counts.get(name, 0) for name in SHIFTS),
            unassigned_total=shift_counts.get("Unassigned", 0),
            average_wage=format_currency(repo.average_hourly_wage(app.db_path)),
            lowest_wage=format_currency(min(wages)) if wages else "Not set",
            highest_wage=format_currency(max(wages)) if wages else "Not set",
            wage_bill=format_currency(sum(wages)) if wages else "Not set",
            employees=employees,
        )
    )
