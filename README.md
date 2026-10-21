# MeítǐShāngchéng — Employee Management System

A web application for the Employee Management System described in **Team 23's Project Plan**
and **User Requirements Specification (URS)** for MeítǐShāngchéng hardware store, Zhengzhou
(parent company: Jupiter).

It replaces the Excel spreadsheets and online calendars the client uses today with one
centralised system for **employee records** and **weekly Morning / Afternoon / Evening
rotas**, with strict role-based access control for **Human Resources**, **Supervisor**
and **Ordinary Employee**.

* **Python standard library only** — no `pip install`, no virtual environment needed.
* **Python 3.10 or newer** — the test suite is run on the oldest supported version.
* **SQLite storage** — data survives restarts (URS NFR03).
* **137 automated tests** covering every Must-have requirement.

---

## 1. Running it in PyCharm

1. Open PyCharm and choose **File → Open…**, then select the `team23-website` folder.
2. PyCharm will detect `app.py` as the entry point.
   If it asks for an interpreter, pick any **Python 3.10 or newer**.
   Accepting PyCharm's default (a new Virtualenv on your system Python) is fine,
   because there are no third-party packages to install.
3. Right-click **`app.py`** → **Run 'app'**
   (or click the green ▶ arrow next to `if __name__ == "__main__":`).
4. The console prints a banner, the database is created automatically on first run, and
   your browser opens at <http://127.0.0.1:8000/login>.

To stop the server, click the red ■ **Stop** button in PyCharm (or press `Ctrl+C`).

### Running it from a terminal instead

```bash
cd team23-website
python app.py
```

### Command-line options

| Option | Meaning |
|---|---|
| `--host 127.0.0.1` | Interface to bind (default: this computer only) |
| `--port 8000` | Port to listen on; use `--port 0` for any free port |
| `--no-browser` | Do not open a browser window automatically |
| `--db PATH` | Use a different SQLite database file |
| `--reset-db` | Delete the database and start again from the demonstration data |

Example: `python app.py --port 8100 --reset-db`

---

## 2. Demo accounts

URS section 4.2 records the assumption that login accounts are created *outside* this
application. For a self-contained demonstration the system therefore ships one ready
account per role:

| Role | Username | Password | What this role can do |
|---|---|---|---|
| Human Resources (HR) | `hr` | `hr123` | Add, edit and delete employee records; search employees; view the weekly rota of the whole store **grouped by employee**, with filters by shift and by employee name. **Cannot** change the rota. |
| Supervisor | `supervisor` | `super123` | Search and view employees; view the weekly rota of the whole store **grouped by day** (who works which shift today); **plan** Morning/Afternoon/Evening shifts on any date, several per day. **Cannot** create, edit or delete employees. |
| Ordinary Employee | `employee` | `emp123` | View **only their own weekly timetable** (three shift rows × Monday–Sunday columns). |

The `employee` account is linked to the employee record **Li Wei**, who works the
Morning shift Monday to Friday plus an Evening shift on Wednesday, so the personal
timetable has content immediately.

---

## 3. Screens (URS section 6)

| Screen | Address | Who sees it |
|---|---|---|
| Login | `/login` | Everyone |
| Home | `/` | All signed-in users — staff see the **Employee overview** (searchable table) with the quick actions; an Ordinary Employee sees their own week |
| Add employee | `/employees/new` | HR |
| Employee Detail + rota panel (one week at a time, add/remove entries) | `/employees/<id>` | HR (read-only rota), Supervisor (rota editable) |
| Edit employee | `/employees/<id>/edit` | HR |
| Store Weekly Rota | `/shifts` | HR (grouped by employee, filterable), Supervisor (grouped by day) |
| My Work Shifts — personal weekly timetable | `/my-shifts` | Ordinary Employee |
| Statistics (weekly totals) | `/statistics` | HR, Supervisor |
| Health probe | `/healthz` | — |

Every weekly screen accepts `?week=YYYY-MM-DD` (any day of the week; it is converted
to that week's Monday) and offers previous / next week links.

Signing in always lands on the **Home** page (URS section 7: Login → System Home Page →
branch by role), so an Ordinary Employee first sees their own week at a glance and opens
the full timetable from there.

The navigation bar only renders the links the signed-in role is allowed to use, and every
page is also protected on the server, so hiding a button is never the only defence.

---

## 4. Requirement coverage

### Functional requirements (URS 5.1)

| ID | Priority | Where it is implemented | Test |
|---|---|---|---|
| FR01 | Must | `views.employee_create`, `repositories.create_employee` | `AddEmployeeTests` |
| FR02 | Must | `views.employee_delete` (shift rows cascade) | `DeleteEmployeeTests` |
| FR03 | Must | `views.employee_edit`, `repositories.update_employee` | `EditEmployeeTests` |
| FR04 | Must | `repositories.search_employees`, employee detail page | `OverviewAndSearchTests` |
| FR05 | Must | Employee overview table on the Home page | `OverviewAndSearchTests` |
| FR06 | Must | `views.employee_assign_shift` / `employee_clear_shift` (dated rota, several shifts per day) | `ShiftAssignmentTests` |
| FR07 | Must | employee detail weekly rota + `/my-shifts` timetable | `SingleEmployeeShiftViewTests`, `OwnShiftViewTests` |
| FR08 | Must | `/shifts` (Supervisor by day, HR by employee) | `StoreShiftOverviewTests` |
| FR09 | Must | Supervisor read-only employee pages | `AccessControlTests` |
| FR10 | Must | rota panel restricted to Supervisor | `AccessControlTests`, `HrRotaPermissionTests` |
| FR11 | Should | `htmlpages.validate_employee` + friendly error page | `ValidationTests` |
| FR12 | Could | wage-range and weekly-shift filters + sorting | `test_wage_range_filter`, `test_shift_filter_including_unassigned`, `test_hr_can_filter_by_shift` |
| FR13 | Could | weekly totals on the overview and `/statistics` | `test_statistics_page_shows_totals`, `test_week_summary_counts` |
| FR14–FR18 | Won't | deliberately **not** built (department management, attendance, automatic schedules, stock, self-service portal) | — |

### Non-functional requirements (URS 5.2)

| ID | How it is met |
|---|---|
| NFR01 | Search and list pages are single indexed SQLite queries; a query-plan test keeps them under the 2-second budget. |
| NFR02 | Every route declares its permitted roles; the dispatcher enforces them in one place. |
| NFR03 | All data lives in one SQLite file that is reused across restarts (tested). |
| NFR04 | Validation errors are plain sentences; unexpected faults render a friendly page while the traceback goes to the console only. |
| NFR05 | A thread-per-request server; a test drives ten concurrent signed-in users. |
| NFR06 | One consistent layout, large click targets, plain language, and a printable shift table. |

### Use cases (URS section 8)

Use Case 1 extension 1A (invalid input keeps the form and what was typed), Use Case 2
extension 1A (missing employee returns to the overview with a message), Use Case 3
extension 1A ("No shifts assigned for this employee"), Use Case 4 extension 1A ("No
employee data available"), Use Case 5 extension 1A (cancelling the confirmation changes
nothing) and Use Case 6 extension 1A ("You have not been assigned any shifts yet") are all
implemented and covered by tests.

---

## 5. Project layout

```
team23-website/
├── app.py                  ← RUN THIS FILE (PyCharm entry point + CLI options)
├── README.md
├── requirements.txt         (intentionally empty: standard library only)
│
├── app/                     application package
│   ├── app.py               WSGI core: routing, sessions, RBAC, CSRF, errors
│   ├── views.py             one handler per screen
│   ├── repositories.py      every SQL statement
│   ├── database.py          schema, connections, demonstration data
│   ├── security.py          password hashing (PBKDF2) and sessions
│   ├── htmlpages.py         validation rules and display helpers
│   ├── templateengine.py    small Jinja-style template engine (no dependencies)
│   ├── server.py            threaded HTTP server
│   └── errors.py            HTTP error types
│
├── templates/               HTML pages
│   ├── base.html            shared layout and navigation
│   ├── partials/            shared markup (the employee table)
│   ├── login.html           Login View
│   ├── home_staff.html      Home: employee overview table, KPIs and quick actions
│   ├── home_employee.html   Home for an Ordinary Employee
│   ├── employee_detail.html (includes the rota panel)
│   ├── employee_form.html   add / edit with inline validation messages
│   ├── store_shifts.html    Full-Store Shift Overview
│   ├── my_shifts.html       My Work Shifts
│   ├── statistics.html
│   └── error.html
│
├── static/
│   ├── css/app.css          the whole visual design
│   └── js/app.js            delete confirmation, small conveniences
│
├── tests/                   137 automated tests
└── data/                    employee_management.db (created on first run)
```

### Design decisions worth knowing

* **The rota is dated, and a person may work several shifts a day.** A `shifts` row
  means "this employee, on this date, in this shift" and the uniqueness key is
  `(employee_id, work_date, shift_name)`. Shift times are the ones confirmed with the
  client after the demonstration: Morning 08:00–12:00, Afternoon 14:00–18:00,
  Evening 20:00–22:00; none crosses midnight. See the next section for the upgrade
  path of an older database.
* **Three roles, three shapes of the same week.** The schedule is not one table shown
  to everybody: the employee reads a timetable (rows = shifts, columns = days), the
  Supervisor reads the week day by day, and HR reads it employee by employee. Only the
  employee detail page changes the rota, so an overview page can never be edited by
  accident.
* **One employee overview, on the home page.** The searchable employee table and its
  actions live on `/`; the separate `/employees` list page was removed so there is only
  one place to look. `/employees/<id>` stays the detail/edit path.
* **Sessions are server-side.** The browser only holds an opaque random token in an
  HttpOnly cookie, so the role cannot be tampered with from the browser.
* **CSRF protection on every state-changing form.** A per-session token is required; a
  form submitted without it changes nothing.
* **Passwords** are stored as salted PBKDF2-HMAC-SHA256 hashes, never in clear text.

### Upgrading a database from the previous release

The previous release stored one *current* shift per employee, with no date. Because the
client has since confirmed a weekly rota, `initialize()` detects that old `shifts` table
(no `work_date` column), rebuilds it with the dated layout and regenerates the
demonstration rota for the current week. Employee records and login accounts are left
untouched; rota rows cannot be carried over because they carry no date. To start from a
clean database instead, run `python app.py --reset-db`.

---

## 6. Tests

Run all tests from the project folder:

```bash
python -m unittest discover -s tests -t . -v
```

In PyCharm you can also right-click the `tests` folder → **Run 'Unittests in tests'**.

| Test file | Tests | What it proves |
|---|---|---|
| `test_auth_and_access.py` | 20 | Login, logout, and the full FR09/FR10/NFR02 permission matrix |
| `test_employees.py` | 34 | FR01–FR05, FR11–FR13, cascade delete, persistence across restarts |
| `test_shifts.py` | 58 | FR06–FR08, FR10, the weekly rota (dates, several shifts a day, week navigation) and the schema upgrade |
| `test_nonfunctional.py` | 7 | NFR01 response time with 400+ employees, NFR05 ten concurrent users and concurrent writes |
| `test_templateengine.py` | 10 | The template engine itself (inheritance, escaping, loops) |
| `test_live_server.py` | 8 | Real HTTP over a socket, static files, path-traversal refusal, 10 parallel users |

All 137 tests pass on **Python 3.10.1**, the oldest version this project supports
(verified by running the suite with that interpreter, not only with a newer one).

If you ever change the code, keep it compatible with 3.10: for example, an f-string may
not contain a backslash inside its `{...}` expression part before Python 3.12, so write
`indent = "\t" * depth` on its own line instead of `f"{'\t' * depth}..."`.

---

## 7. Verifying a running instance (optional, for the demo)

Two scripts check the *running* application over real HTTP with real cookies. They are
useful as a pre-demo sanity check, and as evidence for the test report.

```bash
# 1. start the app in one terminal
python app.py --port 8131 --no-browser

# 2. in a second terminal, check every screen and permission
python docs/verify_running_app.py http://127.0.0.1:8131     # 40 checks

# 3. prove data survives a restart (starts and stops the server itself)
python docs/verify_persistence.py                          # 7 checks
```

`verify_running_app.py` drives the three roles through login, CRUD, search, filtering,
weekly rota planning and removal, week navigation, statistics, deletion, CSRF refusal
and static files.
`verify_persistence.py` writes an employee and a dated rota row, stops the server, starts
a fresh one over the same database, and confirms both are still there.

---

## 8. Out of scope for this release

Per the URS, these are explicitly **not** delivered and are reserved for later iterations:
department management, in-store attendance registration, automatic shift generation,
product-stock and depot-restock management, a full management statistics dashboard, and an
employee self-service web portal. Login accounts, too, are assumed to be created outside
this application.
