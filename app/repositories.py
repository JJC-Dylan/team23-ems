"""Query layer: every SQL statement the application runs lives here.

Keeping SQL in one module makes the requirement mapping easy to follow and
keeps request handling in :mod:`app.app` free of database details.

The rota is dated: a row means "this employee works this shift on this day",
and one employee may hold several rows for the same day. The weekly views are
therefore built from two shapes:

* :func:`employee_week_shifts` — one person, one week (the personal timetable).
* :func:`day_roster` / :func:`employee_roster` — the whole shop, grouped by day
  for the Supervisor and by employee for HR.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any

from .database import SHIFTS, WEEKDAYS, connection, shift_window, week_dates


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


#: Order shifts the way the store runs them (Morning, then Afternoon, Evening).
_SHIFT_ORDER = """
    CASE s.shift_name
        WHEN 'Morning' THEN 1
        WHEN 'Afternoon' THEN 2
        WHEN 'Evening' THEN 3
        ELSE 4
    END
"""


# --------------------------------------------------------------------------
# Users and authentication
# --------------------------------------------------------------------------


def find_user_by_username(db_path: str, username: str) -> sqlite3.Row | None:
    """Look up a login account; used at sign-in and for username collisions."""
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1",
            (username,),
        ).fetchone()


def create_user(
    db_path: str,
    username: str,
    password_hash: str,
    display_name: str,
    role: str,
    employee_id: int | None = None,
) -> int:
    """Insert a login account and return its id.

    URS 4.2 assumes accounts are created outside the application; this helper
    exists for tests and for a future administration screen.
    """
    with connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, display_name, role, employee_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, password_hash, display_name, role, employee_id, _now()),
        )
        return int(cursor.lastrowid)


# --------------------------------------------------------------------------
# Employees
# --------------------------------------------------------------------------

_EMPLOYEE_COLUMNS = """
    e.id, e.name, e.address, e.hourly_wage, e.phone, e.email, e.hired_on,
    e.created_at, e.updated_at
"""

#: The shift names one employee works during the week of the query, e.g.
#: ``Morning, Evening``, or NULL when the whole week is empty. The overview is
#: one row per employee, so the rota of the week is summarised into one cell.
_WEEK_SHIFT_LABEL = """
    (SELECT GROUP_CONCAT(shift_name, ', ') FROM (
        SELECT DISTINCT s2.shift_name
          FROM shifts s2
         WHERE s2.employee_id = e.id
           AND s2.work_date BETWEEN :week_start AND :week_end
         ORDER BY CASE s2.shift_name
                      WHEN 'Morning' THEN 1
                      WHEN 'Afternoon' THEN 2
                      ELSE 3
                  END
    )) AS shift_name
"""

#: Number of shift slots the employee holds in the week of the query.
_WEEK_SHIFT_COUNT = """
    (SELECT COUNT(*)
       FROM shifts s3
      WHERE s3.employee_id = e.id
        AND s3.work_date BETWEEN :week_start AND :week_end) AS shift_count
"""


def get_employee(db_path: str, employee_id: int) -> sqlite3.Row | None:
    """Return one employee record (FR04). The rota is queried per week."""
    with connection(db_path) as conn:
        return conn.execute(
            f"SELECT {_EMPLOYEE_COLUMNS} FROM employees e WHERE e.id = ?",
            (employee_id,),
        ).fetchone()


def count_employees(db_path: str) -> int:
    """Total number of employee records (FR13 statistics)."""
    with connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM employees").fetchone()
        return int(row["total"])


def average_hourly_wage(db_path: str) -> float | None:
    """Average hourly wage across all employees, or ``None`` when empty."""
    with connection(db_path) as conn:
        row = conn.execute("SELECT AVG(hourly_wage) AS average FROM employees").fetchone()
    value = row["average"] if row else None
    return float(value) if value is not None else None


def create_employee(db_path: str, data: dict[str, Any]) -> int:
    """Insert an employee record (FR01) and return the new id."""
    with connection(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO employees
                (name, address, hourly_wage, phone, email, hired_on, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["address"],
                data["hourly_wage"],
                data.get("phone", ""),
                data.get("email", ""),
                data.get("hired_on", ""),
                _now(),
                _now(),
            ),
        )
        return int(cursor.lastrowid)


def update_employee(db_path: str, employee_id: int, data: dict[str, Any]) -> bool:
    """Update an existing employee record (FR03). ``False`` when it vanished."""
    with connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE employees
               SET name = ?, address = ?, hourly_wage = ?, phone = ?, email = ?,
                   hired_on = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                data["name"],
                data["address"],
                data["hourly_wage"],
                data.get("phone", ""),
                data.get("email", ""),
                data.get("hired_on", ""),
                _now(),
                employee_id,
            ),
        )
        return cursor.rowcount > 0


def delete_employee(db_path: str, employee_id: int) -> bool:
    """Delete an employee; shift rows cascade (FR02, URS Use Case 5 step 3)."""
    with connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        return cursor.rowcount > 0


def search_employees(
    db_path: str,
    query: str = "",
    wage_min: float | None = None,
    wage_max: float | None = None,
    shift: str = "",
    sort: str = "name",
    week_start: str | None = None,
) -> list[sqlite3.Row]:
    """Employee overview data with search and filters.

    ``query`` matches the name or the address (FR04, FR05). ``wage_min`` and
    ``wage_max`` implement the Could-have wage-range filter (FR12). ``shift``
    keeps only employees who work that shift at least once in the week shown;
    ``Unassigned`` keeps the employees whose week is still empty. ``sort``
    accepts ``name``, ``name_desc``, ``wage``, ``wage_desc`` or ``newest``.

    Each returned row carries ``shift_name``: the summary of that week's
    shifts (``Morning, Evening``) or ``None`` when the week is empty.
    """
    order_map = {
        "name": "e.name COLLATE NOCASE ASC",
        "name_desc": "e.name COLLATE NOCASE DESC",
        "wage": "e.hourly_wage ASC, e.name COLLATE NOCASE ASC",
        "wage_desc": "e.hourly_wage DESC, e.name COLLATE NOCASE ASC",
        "newest": "e.created_at DESC, e.id DESC",
    }
    order_by = order_map.get(sort, order_map["name"])

    dates = week_dates(week_start)
    parameters: dict[str, Any] = {"week_start": dates[0], "week_end": dates[-1]}

    clauses: list[str] = []

    if query:
        clauses.append(
            "(e.name LIKE :pattern OR e.address LIKE :pattern "
            "OR e.email LIKE :pattern OR e.phone LIKE :pattern)"
        )
        parameters["pattern"] = f"%{query}%"
    if wage_min is not None:
        clauses.append("e.hourly_wage >= :wage_min")
        parameters["wage_min"] = wage_min
    if wage_max is not None:
        clauses.append("e.hourly_wage <= :wage_max")
        parameters["wage_max"] = wage_max
    if shift == "Unassigned":
        clauses.append(
            "e.id NOT IN (SELECT employee_id FROM shifts "
            "WHERE work_date BETWEEN :week_start AND :week_end)"
        )
    elif shift in SHIFTS:
        clauses.append(
            "e.id IN (SELECT employee_id FROM shifts "
            "WHERE shift_name = :shift AND work_date BETWEEN :week_start AND :week_end)"
        )
        parameters["shift"] = shift

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT {_EMPLOYEE_COLUMNS}, {_WEEK_SHIFT_LABEL}, {_WEEK_SHIFT_COUNT}
        FROM employees e
        {where}
        ORDER BY {order_by}
    """
    with connection(db_path) as conn:
        return conn.execute(sql, parameters).fetchall()


def employee_names_by_id(db_path: str) -> dict[int, str]:
    """Id to name map; used to label shift rows and catch bad form values."""
    with connection(db_path) as conn:
        rows = conn.execute("SELECT id, name FROM employees").fetchall()
    return {int(row["id"]): str(row["name"]) for row in rows}


def count_employees_without_week_shifts(db_path: str, week_start: str | None = None) -> int:
    """How many employees have no shift at all in the week shown (FR13)."""
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total FROM employees e
             WHERE NOT EXISTS (
                   SELECT 1 FROM shifts s
                    WHERE s.employee_id = e.id
                      AND s.work_date BETWEEN ? AND ?)
            """,
            (dates[0], dates[-1]),
        ).fetchone()
    return int(row["total"])


# --------------------------------------------------------------------------
# Shifts (dated weekly rota)
# --------------------------------------------------------------------------


def assign_shift(
    db_path: str,
    employee_id: int,
    work_date: str,
    shift_name: str,
    assigned_by: str,
) -> None:
    """Put one employee into one shift on one day (FR06, FR10).

    A person may work several shifts on the same day, so the conflict key is
    employee + date + shift: assigning the same three values again only records
    who confirmed it and when.
    """
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO shifts (employee_id, work_date, shift_name, assigned_at, assigned_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(employee_id, work_date, shift_name) DO UPDATE SET
                assigned_at = excluded.assigned_at,
                assigned_by = excluded.assigned_by
            """,
            (employee_id, work_date, shift_name, _now(), assigned_by),
        )


def clear_shift(db_path: str, employee_id: int, work_date: str, shift_name: str) -> bool:
    """Remove one shift of one employee on one day.

    Only that single rota row is deleted, so the other shifts of the same day
    stay in place. ``False`` means there was nothing to remove.
    """
    with connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM shifts WHERE employee_id = ? AND work_date = ? AND shift_name = ?",
            (employee_id, work_date, shift_name),
        )
        return cursor.rowcount > 0


def employee_week_shifts(
    db_path: str, employee_id: int, week_start: str | None = None
) -> dict[str, list[str]]:
    """One employee's week: ``{work_date: [shift_name, ...]}``.

    Every date of the week is present as a key (possibly with an empty list),
    which keeps the timetable template simple. Shift names are ordered the way
    the store runs them.
    """
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT s.work_date, s.shift_name
              FROM shifts s
             WHERE s.employee_id = ? AND s.work_date BETWEEN ? AND ?
             ORDER BY s.work_date, {_SHIFT_ORDER}
            """,
            (employee_id, dates[0], dates[-1]),
        ).fetchall()
    week: dict[str, list[str]] = {day: [] for day in dates}
    for row in rows:
        week.setdefault(str(row["work_date"]), []).append(str(row["shift_name"]))
    return week


def employee_week_rows(db_path: str, employee_id: int, week_start: str | None = None) -> list[dict[str, Any]]:
    """The rota rows of one employee in a week, ready for the detail page.

    Each entry carries ``work_date``, ``weekday``, ``shift_name``, ``time``,
    ``assigned_at`` and ``assigned_by``, ordered by date and then by shift.
    """
    dates = week_dates(week_start)
    labels = dict(zip(dates, WEEKDAYS))
    with connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT s.work_date, s.shift_name, s.assigned_at, s.assigned_by
              FROM shifts s
             WHERE s.employee_id = ? AND s.work_date BETWEEN ? AND ?
             ORDER BY s.work_date, {_SHIFT_ORDER}
            """,
            (employee_id, dates[0], dates[-1]),
        ).fetchall()
    return [
        {
            "work_date": str(row["work_date"]),
            "weekday": labels.get(str(row["work_date"]), ""),
            "shift_name": str(row["shift_name"]),
            "time": shift_window(str(row["shift_name"])),
            "assigned_at": str(row["assigned_at"]),
            "assigned_by": str(row["assigned_by"]),
        }
        for row in rows
    ]


def day_roster(db_path: str, week_start: str | None = None) -> list[dict[str, Any]]:
    """The whole shop, grouped by day: who works which shift on each day.

    This is the Supervisor's view: seven day groups, each holding the three
    fixed shifts with the employees assigned to them. A shift with nobody
    assigned is reported with an empty employee list so the page can show it.
    """
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT s.work_date, s.shift_name, e.id, e.name, e.phone, e.hourly_wage
              FROM shifts s
              JOIN employees e ON e.id = s.employee_id
             WHERE s.work_date BETWEEN ? AND ?
             ORDER BY s.work_date,
                      CASE s.shift_name
                          WHEN 'Morning' THEN 1
                          WHEN 'Afternoon' THEN 2
                          ELSE 3
                      END,
                      e.name COLLATE NOCASE ASC
            """,
            (dates[0], dates[-1]),
        ).fetchall()

    by_day: dict[str, dict[str, list[dict[str, Any]]]] = {
        day: {name: [] for name in SHIFTS} for day in dates
    }
    for row in rows:
        day = str(row["work_date"])
        shift_name = str(row["shift_name"])
        if day not in by_day or shift_name not in by_day[day]:
            continue
        by_day[day][shift_name].append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "phone": str(row["phone"]),
                "hourly_wage": float(row["hourly_wage"]),
            }
        )

    days: list[dict[str, Any]] = []
    today = date.today().isoformat()
    for index, day in enumerate(dates):
        groups = [
            {
                "shift_name": shift_name,
                "time": shift_window(shift_name),
                "employees": by_day[day][shift_name],
            }
            for shift_name in SHIFTS
        ]
        days.append(
            {
                "work_date": day,
                "weekday": WEEKDAYS[index],
                "is_today": day == today,
                "groups": groups,
                "total": sum(len(group["employees"]) for group in groups),
            }
        )
    return days


def employee_roster(db_path: str, week_start: str | None = None) -> list[dict[str, Any]]:
    """The whole shop, grouped by employee: each person's shifts that week.

    This is the HR view: one entry per employee carrying a ``days`` mapping
    from every date of the week to the shift names worked that day, plus a
    human-readable ``shift_label`` (``Morning, Evening``) and a count.
    """
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT e.id, e.name, e.phone, e.email, e.hourly_wage,
                   s.work_date, s.shift_name
              FROM employees e
              LEFT JOIN shifts s ON s.employee_id = e.id
                                AND s.work_date BETWEEN ? AND ?
             ORDER BY e.name COLLATE NOCASE ASC, s.work_date, {_SHIFT_ORDER}
            """,
            (dates[0], dates[-1]),
        ).fetchall()

    roster: dict[int, dict[str, Any]] = {}
    for row in rows:
        employee_id = int(row["id"])
        entry = roster.get(employee_id)
        if entry is None:
            entry = {
                "id": employee_id,
                "name": str(row["name"]),
                "phone": str(row["phone"]),
                "email": str(row["email"]),
                "hourly_wage": float(row["hourly_wage"]),
                "days": {day: [] for day in dates},
                "shift_count": 0,
            }
            roster[employee_id] = entry
        shift_name = row["shift_name"]
        if shift_name is not None and str(row["work_date"]) in entry["days"]:
            entry["days"][str(row["work_date"])].append(str(shift_name))
            entry["shift_count"] += 1

    for entry in roster.values():
        seen: list[str] = []
        for day in dates:
            for shift_name in entry["days"][day]:
                if shift_name not in seen:
                    seen.append(shift_name)
        entry["shift_label"] = ", ".join(seen)
    return list(roster.values())


def week_summary_counts(db_path: str, week_start: str | None = None) -> dict[str, int]:
    """How many shift slots are filled in the week, per shift name."""
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT shift_name, COUNT(*) AS total FROM shifts
             WHERE work_date BETWEEN ? AND ?
             GROUP BY shift_name
            """,
            (dates[0], dates[-1]),
        ).fetchall()
    counts = {name: 0 for name in SHIFTS}
    for row in rows:
        if row["shift_name"] in counts:
            counts[row["shift_name"]] = int(row["total"])
    counts["Total"] = sum(counts[name] for name in SHIFTS)
    return counts


def employee_counts_per_shift(
    db_path: str, week_start: str | None = None
) -> dict[str, int]:
    """How many employees work each shift at least once in the week.

    Unlike :func:`week_summary_counts`, which counts shift *slots*, this counts
    *people*: an employee who works both Morning and Evening appears under both,
    so the values can add up to more than the number of employees. ``Unassigned``
    counts the employees whose week is still empty.
    """
    dates = week_dates(week_start)
    with connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT shift_name, COUNT(DISTINCT employee_id) AS total FROM shifts
             WHERE work_date BETWEEN ? AND ?
             GROUP BY shift_name
            """,
            (dates[0], dates[-1]),
        ).fetchall()
        unassigned = conn.execute(
            """
            SELECT COUNT(*) AS total FROM employees e
             WHERE NOT EXISTS (
                   SELECT 1 FROM shifts s
                    WHERE s.employee_id = e.id
                      AND s.work_date BETWEEN ? AND ?)
            """,
            (dates[0], dates[-1]),
        ).fetchone()["total"]
    counts = {name: 0 for name in SHIFTS}
    for row in rows:
        if row["shift_name"] in counts:
            counts[row["shift_name"]] = int(row["total"])
    counts["Unassigned"] = int(unassigned)
    return counts
