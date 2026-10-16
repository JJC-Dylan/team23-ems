"""Query layer: every SQL statement the application runs lives here.

Keeping SQL in one module makes the requirement mapping easy to follow and
keeps request handling in :mod:`app.app` free of database details.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Iterable

from .database import SHIFTS, connection


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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
    e.created_at, e.updated_at,
    s.shift_name AS shift_name, s.assigned_at AS shift_assigned_at,
    s.assigned_by AS shift_assigned_by
"""


def get_employee(db_path: str, employee_id: int) -> sqlite3.Row | None:
    """Return one employee together with the currently assigned shift (FR04)."""
    with connection(db_path) as conn:
        return conn.execute(
            f"""
            SELECT {_EMPLOYEE_COLUMNS}
            FROM employees e
            LEFT JOIN shifts s ON s.employee_id = e.id
            WHERE e.id = ?
            """,
            (employee_id,),
        ).fetchone()


def count_employees(db_path: str) -> int:
    """Total number of employee records (FR13 statistics)."""
    with connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM employees").fetchone()
        return int(row["total"])


def count_employees_on_shift(db_path: str) -> dict[str, int]:
    """Employee count per shift, always including the three fixed shift names."""
    with connection(db_path) as conn:
        rows = conn.execute(
            "SELECT shift_name, COUNT(*) AS total FROM shifts GROUP BY shift_name"
        ).fetchall()
    counts = {name: 0 for name in SHIFTS}
    for row in rows:
        if row["shift_name"] in counts:
            counts[row["shift_name"]] = int(row["total"])
    return counts


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
) -> list[sqlite3.Row]:
    """Employee overview data with search and filters.

    ``query`` matches the name or the address (FR04, FR05). ``wage_min`` and
    ``wage_max`` implement the Could-have wage-range filter (FR12). ``shift``
    filters by the currently assigned shift. ``sort`` accepts ``name``,
    ``name_desc``, ``wage``, ``wage_desc`` or ``newest``.
    """
    order_map = {
        "name": "e.name COLLATE NOCASE ASC",
        "name_desc": "e.name COLLATE NOCASE DESC",
        "wage": "e.hourly_wage ASC, e.name COLLATE NOCASE ASC",
        "wage_desc": "e.hourly_wage DESC, e.name COLLATE NOCASE ASC",
        "newest": "e.created_at DESC, e.id DESC",
    }
    order_by = order_map.get(sort, order_map["name"])

    clauses: list[str] = []
    parameters: list[Any] = []

    if query:
        clauses.append("(e.name LIKE ? OR e.address LIKE ? OR e.email LIKE ? OR e.phone LIKE ?)")
        pattern = f"%{query}%"
        parameters.extend([pattern, pattern, pattern, pattern])
    if wage_min is not None:
        clauses.append("e.hourly_wage >= ?")
        parameters.append(wage_min)
    if wage_max is not None:
        clauses.append("e.hourly_wage <= ?")
        parameters.append(wage_max)
    if shift == "Unassigned":
        clauses.append("s.shift_name IS NULL")
    elif shift in SHIFTS:
        clauses.append("s.shift_name = ?")
        parameters.append(shift)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT {_EMPLOYEE_COLUMNS}
        FROM employees e
        LEFT JOIN shifts s ON s.employee_id = e.id
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


# --------------------------------------------------------------------------
# Shifts
# --------------------------------------------------------------------------


def assign_shift(
    db_path: str, employee_id: int, shift_name: str, assigned_by: str
) -> None:
    """Create or replace the shift assigned to an employee (FR06, FR10).

    A single current shift per employee keeps the full-store overview a clean
    table, so re-assignment updates the existing row.
    """
    with connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO shifts (employee_id, shift_name, assigned_at, assigned_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(employee_id) DO UPDATE SET
                shift_name = excluded.shift_name,
                assigned_at = excluded.assigned_at,
                assigned_by = excluded.assigned_by
            """,
            (employee_id, shift_name, _now(), assigned_by),
        )


def clear_shift(db_path: str, employee_id: int, assigned_by: str) -> bool:
    """Remove an employee's shift assignment (the "Not assigned" option)."""
    with connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM shifts WHERE employee_id = ?", (employee_id,))
        return cursor.rowcount > 0


def get_employee_shift(db_path: str, employee_id: int) -> sqlite3.Row | None:
    """The shift currently assigned to one employee (FR07)."""
    with connection(db_path) as conn:
        return conn.execute(
            "SELECT * FROM shifts WHERE employee_id = ?",
            (employee_id,),
        ).fetchone()


def store_shift_overview(db_path: str) -> list[sqlite3.Row]:
    """Every employee with the assigned shift, for the full-store table (FR08)."""
    with connection(db_path) as conn:
        return conn.execute(
            f"""
            SELECT {_EMPLOYEE_COLUMNS}
            FROM employees e
            LEFT JOIN shifts s ON s.employee_id = e.id
            ORDER BY
                CASE s.shift_name
                    WHEN 'Morning' THEN 1
                    WHEN 'Afternoon' THEN 2
                    WHEN 'Evening' THEN 3
                    ELSE 4
                END,
                e.name COLLATE NOCASE ASC
            """
        ).fetchall()


def shift_summary_counts(rows: Iterable[sqlite3.Row]) -> dict[str, int]:
    """Count rows per shift label, including ``Unassigned``."""
    counts = {name: 0 for name in SHIFTS}
    counts["Unassigned"] = 0
    for row in rows:
        label = row["shift_name"] or "Unassigned"
        counts[label] = counts.get(label, 0) + 1
    return counts
