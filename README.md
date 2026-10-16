# MeítǐShāngchéng — Employee Management System

A web application for the Employee Management System described in **Team 23's Project Plan**
and **User Requirements Specification (URS)** for MeítǐShāngchéng hardware store, Zhengzhou
(parent company: Jupiter).

It replaces the Excel spreadsheets and online calendars the client uses today with one
centralised system for **employee records** and **Morning / Afternoon / Evening shift
planning**, with strict role-based access control for **Human Resources**, **Supervisor**
and **Ordinary Employee**.

* **Python standard library only** — no `pip install`, no virtual environment needed.
* **Python 3.10 or newer** — the test suite is run on the oldest supported version.
* **SQLite storage** — data survives restarts (URS NFR03).
* **97 automated tests** covering every Must-have requirement.

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
| Human Resources (HR) | `hr` | `hr123` | Add, edit and delete employee records; search employees; view all shift schedules. **Cannot** assign shifts. |
| Supervisor | `supervisor` | `super123` | Search and view employees; view all shift schedules; **manually assign** Morning/Afternoon/Evening shifts. **Cannot** create, edit or delete employees. |
| Ordinary Employee | `employee` | `emp123` | View **only their own** work shifts. |

The `employee` account is linked to the employee record **Li Wei**, who starts on the
Morning shift, so the read-only view has content immediately.

---

## 3. Screens (URS section 6)

| Screen | Address | Who sees it |
|---|---|---|
| Login | `/login` | Everyone |
| Home (role-aware dashboard) | `/` | All signed-in users |
| Employee Overview (searchable table) | `/employees` | HR, Supervisor |
| Add employee | `/employees/new` | HR |
| Employee Detail + shift panel | `/employees/<id>` | HR (read-only panel), Supervisor (panel active) |
| Edit employee | `/employees/<id>/edit` | HR |
| Full-Store Shift Overview | `/shifts` | HR, Supervisor |
| My Work Shifts | `/my-shifts` | Ordinary Employee |
| Statistics | `/statistics` | HR, Supervisor |
| Health probe | `/healthz` | — |

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
| FR05 | Must | `/employees` overview | `OverviewAndSearchTests` |
| FR06 | Must | `views.employee_assign_shift` | `ShiftAssignmentTests` |
| FR07 | Must | employee detail + `/my-shifts` | `SingleEmployeeShiftViewTests`, `OwnShiftViewTests` |
| FR08 | Must | `/shifts` | `StoreShiftOverviewTests` |
| FR09 | Must | Supervisor read-only employee pages | `AccessControlTests` |
| FR10 | Must | shift panel restricted to Supervisor | `AccessControlTests` |
| FR11 | Should | `htmlpages.validate_employee` + friendly error page | `ValidationTests` |
| FR12 | Could | wage-range and shift filters + sorting | `test_wage_range_filter`, `test_shift_filter_including_unassigned` |
| FR13 | Could | total employee count on the overview, `/statistics` page | `test_statistics_page_shows_totals` |
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
│   ├── login.html           Login View
│   ├── home_staff.html      dashboard for HR and Supervisor
│   ├── home_employee.html   dashboard for an Ordinary Employee
│   ├── employees_overview.html
│   ├── employee_detail.html (includes the shift-assignment panel)
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
├── tests/                   97 automated tests
└── data/                    employee_management.db (created on first run)
```

### Design decisions worth knowing

* **One current shift per employee.** The URS full-store overview is a single table of
  employee plus assigned shift, so the `shifts` table holds one row per employee and
  re-assignment updates it. Deleting an employee removes the row by foreign-key cascade.
* **Sessions are server-side.** The browser only holds an opaque random token in an
  HttpOnly cookie, so the role cannot be tampered with from the browser.
* **CSRF protection on every state-changing form.** A per-session token is required; a
  form submitted without it changes nothing.
* **Passwords** are stored as salted PBKDF2-HMAC-SHA256 hashes, never in clear text.

---

## 6. Tests

Run all tests from the project folder:

```bash
python -m unittest discover -s tests -t . -v
```

In PyCharm you can also right-click the `tests` folder → **Run 'Unittests in tests'**.

| Test file | Tests | What it proves |
|---|---|---|
| `test_auth_and_access.py` | 19 | Login, logout, and the full FR09/FR10/NFR02 permission matrix |
| `test_employees.py` | 33 | FR01–FR05, FR11–FR13, cascade delete, persistence across restarts |
| `test_shifts.py` | 20 | FR06–FR08, FR10 and the URS use-case extensions |
| `test_nonfunctional.py` | 7 | NFR01 response time with 400+ employees, NFR05 ten concurrent users and concurrent writes |
| `test_templateengine.py` | 10 | The template engine itself (inheritance, escaping, loops) |
| `test_live_server.py` | 8 | Real HTTP over a socket, static files, path-traversal refusal, 10 parallel users |

All 97 tests pass on **Python 3.10.1**, the oldest version this project supports
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
python docs/verify_running_app.py http://127.0.0.1:8131     # 34 checks

# 3. prove data survives a restart (starts and stops the server itself)
python docs/verify_persistence.py                          # 7 checks
```

`verify_running_app.py` drives the three roles through login, CRUD, search, filtering,
shift assignment, statistics, deletion, CSRF refusal and static files.
`verify_persistence.py` writes an employee and a shift, stops the server, starts a fresh
one over the same database, and confirms both are still there.

---

## 8. Out of scope for this release

Per the URS, these are explicitly **not** delivered and are reserved for later iterations:
department management, in-store attendance registration, automatic shift generation,
product-stock and depot-restock management, a full management statistics dashboard, and an
employee self-service web portal. Login accounts, too, are assumed to be created outside
this application.
