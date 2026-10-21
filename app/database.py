"""SQLite persistence layer for the Employee Management System.

Responsibilities
----------------
* Own the database schema (users, employees, shifts).
* Provide short-lived, thread-safe connections with foreign keys enforced,
  so deleting an employee cascades to that employee's shift records
  (URS Use Case 5, main success scenario step 3).
* Seed the database on first run with the three roles required by the URS
  and a small demonstration data set.

Requirement traceability
------------------------
NFR03 (employee and shift data persist after restarts) is satisfied by
storing everything in a single SQLite file that is created once and reused.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Iterator

# --------------------------------------------------------------------------
# Domain constants (URS section 2 Background & Business Context, section 3)
# --------------------------------------------------------------------------

#: The three fixed daily shifts. Custom shift creation is explicitly not
#: required (URS 4.2 Assumptions).
SHIFTS: tuple[str, ...] = ("Morning", "Afternoon", "Evening")

#: Clock window of each shift, confirmed with the client after the
#: demonstration (2026-10-18). No shift crosses midnight, so a rota row always
#: belongs to exactly one calendar date.
SHIFT_TIMES: dict[str, tuple[str, str]] = {
    "Morning": ("08:00", "12:00"),
    "Afternoon": ("14:00", "18:00"),
    "Evening": ("20:00", "22:00"),
}

#: Weekday labels, Monday first; used by every weekly view.
WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def shift_window(shift_name: str) -> str:
    """Human-readable time window of a shift, e.g. ``08:00 - 12:00``."""
    start, end = SHIFT_TIMES.get(shift_name, ("", ""))
    if not start:
        return ""
    return f"{start} - {end}"

#: End-user roles defined in URS 3 Stakeholder and User Analysis.
ROLE_HR = "HR"
ROLE_SUPERVISOR = "Supervisor"
ROLE_EMPLOYEE = "Ordinary Employee"
ROLES: tuple[str, ...] = (ROLE_HR, ROLE_SUPERVISOR, ROLE_EMPLOYEE)

#: Human-readable explanation of what each role may do; used by the GUI.
ROLE_DESCRIPTIONS: dict[str, str] = {
    ROLE_HR: (
        "Full read-write access to employee records: create, edit and delete "
        "employees, search employees and view all shift schedules. "
        "Cannot assign work shifts."
    ),
    ROLE_SUPERVISOR: (
        "Read-only access to employee records, plus manual work-shift "
        "assignment for subordinates. Cannot create, edit or delete employees."
    ),
    ROLE_EMPLOYEE: (
        "Read-only access: can view only their own assigned work shifts."
    ),
}

DEFAULT_DB_FILENAME = "employee_management.db"


def default_db_path() -> str:
    """Return the default database file path (``<project root>/data/...``).

    The project root is the parent directory of this package, which keeps the
    data file next to the source code so it is easy to find in PyCharm.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    override = os.environ.get("EMS_DB_PATH")
    if override:
        return os.path.abspath(override)
    return os.path.join(project_root, "data", DEFAULT_DB_FILENAME)


# --------------------------------------------------------------------------
# Connection handling
# --------------------------------------------------------------------------


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with the conventions this project relies on."""
    directory = os.path.dirname(os.path.abspath(db_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection(db_path: str) -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and always closes."""
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    display_name  TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('HR', 'Supervisor', 'Ordinary Employee')),
    employee_id   INTEGER REFERENCES employees(id) ON DELETE SET NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    address      TEXT    NOT NULL,
    hourly_wage  REAL    NOT NULL CHECK (hourly_wage > 0),
    phone        TEXT    NOT NULL DEFAULT '',
    email        TEXT    NOT NULL DEFAULT '',
    hired_on     TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS shifts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    work_date   TEXT    NOT NULL,
    shift_name  TEXT    NOT NULL CHECK (shift_name IN ('Morning', 'Afternoon', 'Evening')),
    assigned_at TEXT    NOT NULL,
    assigned_by TEXT    NOT NULL DEFAULT ''
);

-- A rota row is "this employee, on this day, in this shift". One employee may
-- work several shifts on the same day (the client confirmed this after the
-- demonstration), so the shift name is part of the key.
CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_employee_date_shift
    ON shifts(employee_id, work_date, shift_name);
CREATE INDEX IF NOT EXISTS idx_shifts_work_date ON shifts(work_date);
CREATE INDEX IF NOT EXISTS idx_employees_name ON employees(name);
"""

#: Columns the current ``shifts`` table must have. A table that carries no
#: ``work_date`` is the pre-weekly layout and cannot be migrated because its
#: rows hold no date.
_SHIFT_TABLE_COLUMNS = {
    "employee_id",
    "work_date",
    "shift_name",
    "assigned_at",
    "assigned_by",
}


def initialize(db_path: str) -> bool:
    """Create the schema when missing and upgrade an older ``shifts`` table.

    An early version of this project stored one *current* shift per employee,
    with no date. Because the client has since confirmed a weekly rota, such a
    database is rebuilt with the dated layout. Rota rows cannot be carried over
    (they carry no date), so the demonstration rota is regenerated; employee
    and login-account rows are left untouched.

    Returns ``True`` when the old table had to be rebuilt.
    """
    rebuilt = False
    with connection(db_path) as conn:
        existing = {
            row["name"] for row in conn.execute("PRAGMA table_info(shifts)").fetchall()
        }
        if existing and not _SHIFT_TABLE_COLUMNS.issubset(existing):
            conn.execute("DROP TABLE shifts")
            rebuilt = True
        conn.executescript(SCHEMA)
        if rebuilt:
            _reseed_demo_rota(conn)
    return rebuilt


# --------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------

#: Demonstration accounts. URS 4.2 records the assumption that login accounts
#: are created outside this application; for a self-contained demonstration
#: the system therefore ships one ready account per role.
SEED_USERS: tuple[dict[str, Any], ...] = (
    {
        "username": "hr",
        "password": "hr123",
        "display_name": "Human Resources",
        "role": ROLE_HR,
    },
    {
        "username": "supervisor",
        "password": "super123",
        "display_name": "Store Supervisor",
        "role": ROLE_SUPERVISOR,
    },
    {
        "username": "employee",
        "password": "emp123",
        "display_name": "Ordinary Employee",
        "role": ROLE_EMPLOYEE,
    },
)

#: Demonstration employees: one of them is linked to the "employee" login so
#: that the Ordinary Employee role has data to display.
#:
#: ``shift`` is the shift the person normally works, Monday to Friday.
#: ``extra_shifts`` adds a second shift on a chosen weekday (0 = Monday) so the
#: demonstration shows that one person may work several shifts on one day.
#: An employee whose ``shift`` is ``None`` keeps an empty week, which shows the
#: empty timetable cells.
SEED_EMPLOYEES: tuple[dict[str, Any], ...] = (
    {
        "name": "Li Wei",
        "address": "12 Jinshui Road, Zhengzhou",
        "hourly_wage": 32.5,
        "phone": "138-0000-0001",
        "email": "li.wei@meitishangcheng.example",
        "hired_on": "2026-03-02",
        "shift": "Morning",
        "extra_shifts": {2: "Evening"},  # Wednesday: Morning and Evening
    },
    {
        "name": "Zhang Min",
        "address": "88 Wenhua Street, Zhengzhou",
        "hourly_wage": 28.0,
        "phone": "138-0000-0002",
        "email": "zhang.min@meitishangcheng.example",
        "hired_on": "2026-04-15",
        "shift": "Afternoon",
        "extra_shifts": {},
    },
    {
        "name": "Chen Hao",
        "address": "5 Nongye Avenue, Zhengzhou",
        "hourly_wage": 35.75,
        "phone": "138-0000-0003",
        "email": "chen.hao@meitishangcheng.example",
        "hired_on": "2026-05-20",
        "shift": "Evening",
        "extra_shifts": {},
    },
    {
        "name": "Wang Fang",
        "address": "240 Huayuan Lane, Zhengzhou",
        "hourly_wage": 26.5,
        "phone": "138-0000-0004",
        "email": "wang.fang@meitishangcheng.example",
        "hired_on": "2026-06-01",
        "shift": None,
        "extra_shifts": {},
    },
    {
        "name": "Sun Jie",
        "address": "31 Dahe Road, Zhengzhou",
        "hourly_wage": 41.0,
        "phone": "138-0000-0005",
        "email": "sun.jie@meitishangcheng.example",
        "hired_on": "2026-02-10",
        "shift": "Morning",
        "extra_shifts": {1: "Evening"},  # Tuesday: Morning and Evening
    },
)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def week_dates(anchor: date | str | None = None) -> list[str]:
    """The seven ISO dates of the week containing ``anchor``, Monday first.

    ``anchor`` may be a :class:`datetime.date`, an ISO date string (the form the
    weekly views receive in ``?week=``) or ``None`` for the current week. An
    unreadable anchor falls back to the current week rather than failing.
    """
    if isinstance(anchor, str):
        try:
            today = date.fromisoformat(anchor.strip())
        except ValueError:
            today = datetime.now().date()
    else:
        today = anchor or datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    return [(monday + timedelta(days=offset)).isoformat() for offset in range(7)]


def _demo_rota(spec: dict[str, Any], dates: list[str] | None = None) -> list[tuple[str, str]]:
    """The demonstration rota of one employee as ``(work_date, shift_name)``.

    Monday to Friday carry the person's normal shift; ``extra_shifts`` adds the
    second shift of the same day. Saturday and Sunday are left empty.
    """
    dates = dates or week_dates()
    rows: list[tuple[str, str]] = []
    if spec.get("shift"):
        rows.extend((dates[index], str(spec["shift"])) for index in range(5))
    for index, shift_name in sorted(spec.get("extra_shifts", {}).items()):
        rows.append((dates[index], str(shift_name)))
    return rows


def _insert_demo_rota(
    conn: sqlite3.Connection, employee_id: int, spec: dict[str, Any], dates: list[str]
) -> None:
    """Write one demonstration rota into an open connection."""
    for work_date, shift_name in _demo_rota(spec, dates):
        conn.execute(
            """
            INSERT INTO shifts
                (employee_id, work_date, shift_name, assigned_at, assigned_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (employee_id, work_date, shift_name, _now(), "Seed data"),
        )


def _reseed_demo_rota(conn: sqlite3.Connection) -> None:
    """Rebuild the demonstration rota after an old ``shifts`` table was dropped.

    Used by :func:`initialize` when an existing database is upgraded. Only
    employees that match a demonstration record get a rota; anyone added by
    hand simply starts with an empty week.
    """
    specs = {spec["name"]: spec for spec in SEED_EMPLOYEES}
    dates = week_dates()
    for row in conn.execute("SELECT id, name FROM employees").fetchall():
        spec = specs.get(str(row["name"]))
        if spec is not None:
            _insert_demo_rota(conn, int(row["id"]), spec, dates)


def is_empty(db_path: str) -> bool:
    """Report whether the database still needs demonstration data."""
    with connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM employees").fetchone()
        return int(row["total"]) == 0


def seed(db_path: str, password_hasher) -> bool:
    """Insert demonstration users, employees and the current week's rota.

    ``password_hasher`` is injected (rather than imported) to keep this module
    free of authentication concerns and avoid a circular import.

    Returns ``True`` when seeding happened, ``False`` when data already existed.
    """
    if not is_empty(db_path):
        return False

    dates = week_dates()
    with connection(db_path) as conn:
        existing_users = {
            row["username"] for row in conn.execute("SELECT username FROM users")
        }

        for spec in SEED_USERS:
            if spec["username"] in existing_users:
                continue
            conn.execute(
                """
                INSERT INTO users (username, password_hash, display_name, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    spec["username"],
                    password_hasher(spec["password"]),
                    spec["display_name"],
                    spec["role"],
                    _now(),
                ),
            )

        employee_ids: list[int] = []
        for spec in SEED_EMPLOYEES:
            cursor = conn.execute(
                """
                INSERT INTO employees
                    (name, address, hourly_wage, phone, email, hired_on, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    spec["name"],
                    spec["address"],
                    spec["hourly_wage"],
                    spec["phone"],
                    spec["email"],
                    spec["hired_on"],
                    _now(),
                    _now(),
                ),
            )
            employee_ids.append(int(cursor.lastrowid))
            # Fill the working week of the current week so the timetable opens
            # with a realistic grid; Saturday and Sunday stay empty, which also
            # demonstrates empty cells.
            _insert_demo_rota(conn, int(cursor.lastrowid), spec, dates)

        # Link the demonstration Ordinary Employee account to the first record
        # so that "My Work Shifts" has content (URS Use Case 6).
        if employee_ids:
            conn.execute(
                "UPDATE users SET employee_id = ? WHERE username = ?",
                (employee_ids[0], "employee"),
            )

    return True
