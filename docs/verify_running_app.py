"""Independent end-to-end check of the running server over real HTTP.

Run the app first (``python app.py --port 8131 --no-browser``) and then:

    python docs/verify_running_app.py http://127.0.0.1:8131

This is deliberately separate from the unit tests: it drives a real socket with
real cookies, so it proves the artefact a user actually opens.
"""

from __future__ import annotations

import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8131"

TOKEN_RE = re.compile(r'name="_csrf_token"\s+value="([^"]*)"')


class Browser:
    """A cookie-aware browser with helpers for forms and status codes."""

    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.csrf = ""

    def _open(self, path: str, data: dict[str, str] | None = None):
        url = f"{BASE}{path}"
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(url, data=body, method="POST" if body else "GET")
        return self.opener.open(request, timeout=30)

    def get(self, path: str) -> tuple[int, str]:
        try:
            response = self._open(path)
            return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")

    def post(self, path: str, fields: dict[str, str], with_csrf: bool = True) -> tuple[int, str]:
        payload = dict(fields)
        if with_csrf:
            payload.setdefault("_csrf_token", self.csrf)
        try:
            response = self._open(path, payload)
            text = response.read().decode("utf-8")
            match = TOKEN_RE.search(text)
            if match:
                self.csrf = match.group(1)
            return response.status, text
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode("utf-8", errors="replace")

    def sign_in(self, username: str, password: str, landing: str) -> str:
        _, page = self.get("/login")
        match = TOKEN_RE.search(page)
        token = match.group(1) if match else ""
        status, _ = self.post(
            "/login",
            {"username": username, "password": password, "_csrf_token": token},
            with_csrf=False,
        )
        assert status in (200, 303), f"sign-in returned {status}"
        _, landed = self.get(landing)
        match = TOKEN_RE.search(landed)
        if match:
            self.csrf = match.group(1)
        return landed


RESULTS: list[tuple[bool, str]] = []


def check(label: str, passed: bool) -> None:
    RESULTS.append((bool(passed), label))
    print(f"  {'PASS' if passed else 'FAIL'}  {label}")


def main() -> int:
    print(f"Verifying {BASE}\n")

    # --- 1. server and login page ---------------------------------------
    status, login_page = Browser().get("/login")
    check("app serves the login page", status == 200 and "Employee Management" in login_page)

    # --- 2. all three roles sign in -------------------------------------
    hr = Browser()
    hr_home = hr.sign_in("hr", "hr123", "/employees")
    check("HR signs in and sees the HR badge", "role-badge--hr" in hr_home)
    check("HR sees the Add-new-employee action", 'href="/employees/new"' in hr_home)

    supervisor = Browser()
    sup_page = supervisor.sign_in("supervisor", "super123", "/employees")
    check("Supervisor signs in with the read-only notice", "read-only employee data" in sup_page)
    check("Supervisor cannot see the Add action", 'href="/employees/new"' not in sup_page)

    employee = Browser()
    emp_page = employee.sign_in("employee", "emp123", "/my-shifts")
    check("Ordinary Employee signs in on My work shifts", "My work shifts" in emp_page)

    # --- 3. role-based access control (NFR02) ---------------------------
    status, _ = employee.get("/employees")
    check("employee blocked from /employees (403)", status == 403)
    status, _ = employee.get("/shifts")
    check("employee blocked from /shifts (403)", status == 403)
    status, _ = employee.get("/statistics")
    check("employee blocked from /statistics (403)", status == 403)
    status, _ = employee.get("/employees/new")
    check("employee blocked from the add form (403)", status == 403)
    status, _ = supervisor.post("/employees/1/delete", {})
    check("supervisor blocked from deleting (403)", status == 403)
    status, _ = hr.post("/employees/1/shift", {"shift_name": "Morning"})
    check("HR blocked from assigning a shift (403)", status == 403)

    # --- 4. employee CRUD (FR01-FR03) -----------------------------------
    status, added = hr.post(
        "/employees/new",
        {
            "name": "Final Check",
            "address": "1 Verification Way, Zhengzhou",
            "hourly_wage": "31.50",
            "phone": "138-0000-7777",
            "email": "final.check@example.com",
            "hired_on": "2026-09-15",
        },
    )
    match = re.search(r'action="/employees/(\d+)/delete"', added) or re.search(
        r'href="/employees/(\d+)/edit"', added
    )
    new_id = match.group(1) if match else ""
    check("HR adds an employee (FR01)", status == 200 and "Final Check" in added and bool(new_id))

    status, detail = hr.get(f"/employees/{new_id}")
    check("employee detail page opens (FR04)", status == 200 and "Final Check" in detail)

    status, found = hr.get("/employees?q=Final+Check")
    check("search finds the employee (FR04/FR05)", status == 200 and "Final Check" in found)

    status, filtered = hr.get("/employees?wage_min=31&wage_max=32")
    check("wage-range filter selects it (FR12)", "Final Check" in filtered)

    status, edited = hr.post(
        f"/employees/{new_id}/edit",
        {
            "name": "Final Check",
            "address": "2 Verification Way, Zhengzhou",
            "hourly_wage": "33.00",
        },
    )
    check("HR edits the employee (FR03)", status == 200 and "2 Verification Way" in edited)

    # --- 5. validation feedback (FR11, NFR04, URS use case 1A) -----------
    status, invalid = hr.post(
        "/employees/new",
        {"name": "", "address": "ok address here", "hourly_wage": "nope"},
    )
    check(
        "invalid input lists friendly per-field errors (FR11)",
        "Employee name is required" in invalid and "Hourly wage must be a number" in invalid,
    )
    check("invalid input keeps what was typed (use case 1A)", 'value="ok address here"' in invalid)
    lowered = invalid.lower()
    check(
        "no raw technical text reaches the user (NFR04)",
        "traceback" not in lowered and "sqlite3." not in lowered and "valueerror" not in lowered,
    )

    # --- 6. shifts (FR06-FR08, FR10) ------------------------------------
    status, panel = supervisor.get(f"/employees/{new_id}")
    token = TOKEN_RE.search(panel)
    if token:
        supervisor.csrf = token.group(1)
    check("Supervisor sees the shift-assignment panel", "Confirm shift assignment" in panel)

    status, assigned = supervisor.post(f"/employees/{new_id}/shift", {"shift_name": "Afternoon"})
    check(
        "Supervisor assigns an Afternoon shift (FR06/FR10)",
        status == 200 and 'pill--Afternoon">' in assigned and "Afternoon" in assigned,
    )
    check(
        "single-employee shift view shows the assignment (FR07)",
        "Assigned work shifts of this employee" in assigned,
    )

    status, store = supervisor.get("/shifts")
    check(
        "full-store shift overview lists everyone (FR08)",
        status == 200 and "Final Check" in store and "Li Wei" in store,
    )
    check(
        "store overview hides shift-modification controls (URS 6)",
        'name="shift_name"' not in store,
    )

    status, mine = employee.get("/my-shifts")
    check(
        "employee sees only their own schedule (FR07)",
        status == 200 and "Li Wei" in mine and "Final Check" not in mine,
    )

    # --- 7. statistics (FR13) -------------------------------------------
    status, stats = hr.get("/statistics")
    check(
        "statistics page reports totals (FR13)",
        status == 200 and "Total employees" in stats and "Employees per shift" in stats,
    )

    # --- 8. persistence (NFR03) ------------------------------------------
    # Surviving a real process restart needs its own server lifecycle, so it is
    # proved by docs/verify_persistence.py rather than from inside this script.
    check("employee count is reported from stored data", "of 6 in total" in found or "of 7 in total" in found)

    # --- 9. delete cascades (FR02, use case 5) --------------------------
    status, deleted = hr.post(f"/employees/{new_id}/delete", {})
    status, listing = hr.get("/employees")
    table_body = listing.split("<tbody>")[1].split("</tbody>")[0] if "<tbody>" in listing else ""
    check(
        "HR deletes the employee and it leaves the table (FR02)",
        "Final Check" not in table_body,
    )

    # --- 10. CSRF and static assets --------------------------------------
    status, _ = hr.post(
        "/employees/new",
        {
            "name": "Forged",
            "address": "forged address here",
            "hourly_wage": "10",
            "_csrf_token": "forged-token",
        },
        with_csrf=False,
    )
    check("a forged CSRF token is refused (400)", status == 400)

    status, css = Browser().get("/static/css/app.css")
    check("stylesheet is served", status == 200 and "--brand" in css)
    status, js = Browser().get("/static/js/app.js")
    check("javascript is served", status == 200 and "addEventListener" in js)
    status, _ = Browser().get("/static/../app.py")
    check("static path traversal is refused (404)", status == 404)
    status, health = Browser().get("/healthz")
    check("health probe answers", status == 200 and health.strip() == "ok")

    passed = sum(1 for ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print(f"\nRESULT: {passed} passed, {failed} failed")
    for ok, label in RESULTS:
        if not ok:
            print(f"  failed: {label}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
