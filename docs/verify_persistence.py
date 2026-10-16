"""Prove NFR03 over real restarts: employee and shift data survive a stop/start.

This script manages the server itself, so it exercises the actual artefact:

    python docs/verify_persistence.py

It starts ``app.py`` on a scratch port and database, writes an employee and a
shift assignment, stops the process, starts a fresh one over the same database,
and checks that both the record and the shift are still there.
"""

from __future__ import annotations

import http.cookiejar
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8142
BASE = f"http://127.0.0.1:{PORT}"
TOKEN_RE = re.compile(r'name="_csrf_token"\s+value="([^"]*)"')


class Browser:
    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.csrf = ""

    def _open(self, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        request = urllib.request.Request(
            f"{BASE}{path}", data=body, method="POST" if body else "GET"
        )
        return self.opener.open(request, timeout=20)

    def get(self, path: str) -> str:
        return self._open(path).read().decode("utf-8")

    def post(self, path: str, fields: dict[str, str], with_csrf: bool = True) -> str:
        payload = dict(fields)
        if with_csrf:
            payload.setdefault("_csrf_token", self.csrf)
        text = self._open(path, payload).read().decode("utf-8")
        match = TOKEN_RE.search(text)
        if match:
            self.csrf = match.group(1)
        return text

    def sign_in(self, username: str, password: str, landing: str) -> None:
        page = self.get("/login")
        # The login page has no session yet, so its token field is empty; the
        # sign-in form is exempt from the CSRF check for that reason.
        token = TOKEN_RE.search(page).group(1)
        self.post(
            "/login",
            {"username": username, "password": password, "_csrf_token": token},
            with_csrf=False,
        )
        self.get(landing)


def start_server(db_path: str) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, os.path.join(PROJECT_ROOT, "app.py"),
         "--port", str(PORT), "--no-browser", "--db", db_path],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=1) as response:
                if response.status == 200:
                    return process
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)
    process.kill()
    raise RuntimeError("the server did not become ready in time")


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    time.sleep(0.5)


def main() -> int:
    results: list[tuple[bool, str]] = []

    def check(label: str, passed: bool) -> None:
        results.append((bool(passed), label))
        print(f"  {'PASS' if passed else 'FAIL'}  {label}")

    workdir = tempfile.mkdtemp(prefix="ems-persist-")
    db_path = os.path.join(workdir, "persistence.db")
    process = None
    try:
        print(f"Database under test: {db_path}\n")

        # ---- first run: write an employee and assign a shift ------------
        process = start_server(db_path)
        browser = Browser()
        browser.sign_in("hr", "hr123", "/employees")
        created = browser.post(
            "/employees/new",
            {
                "name": "Persisted Person",
                "address": "9 Restart Road, Zhengzhou",
                "hourly_wage": "27.75",
            },
        )
        match = re.search(r'action="/employees/(\d+)/delete"', created) or re.search(
            r'href="/employees/(\d+)/edit"', created
        )
        employee_id = match.group(1) if match else ""
        check("first run: employee created", bool(employee_id) and "Persisted Person" in created)

        supervisor = Browser()
        supervisor.sign_in("supervisor", "super123", "/employees")
        panel = supervisor.get(f"/employees/{employee_id}")
        token = TOKEN_RE.search(panel)
        if token:
            supervisor.csrf = token.group(1)
        assigned = supervisor.post(f"/employees/{employee_id}/shift", {"shift_name": "Evening"})
        check("first run: shift assigned", "Evening" in assigned)

        stop_server(process)
        process = None
        check("server stopped cleanly", True)

        # ---- second run: same database file, fresh process --------------
        process = start_server(db_path)
        again = Browser()
        again.sign_in("hr", "hr123", "/employees")
        listing = again.get("/employees?q=Persisted")
        check(
            "employee survived the restart (NFR03)",
            "Persisted Person" in listing and "27.75" in listing,
        )

        detail = again.get(f"/employees/{employee_id}")
        check("shift assignment survived the restart (NFR03)", "Evening" in detail)

        seeded_again = again.get("/employees")
        total = re.search(r"of (\d+) in total", seeded_again)
        check(
            "demonstration data was not duplicated on restart",
            total is not None and total.group(1) == "6",
        )

        stop_server(process)
        process = None
        check("second server stopped cleanly", True)
    finally:
        if process is not None:
            stop_server(process)
        shutil.rmtree(workdir, ignore_errors=True)

    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
