"""A small WSGI test client so tests exercise the real request pipeline."""

from __future__ import annotations

import io
import re
import urllib.parse
from typing import Any


class Response:
    """Captured result of one test request."""

    def __init__(self, status: int, headers: list[tuple[str, str]], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body
        self.text = body.decode("utf-8", errors="replace")

    def header(self, name: str) -> str:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return ""

    @property
    def location(self) -> str:
        return self.header("Location")

    @property
    def cookies(self) -> dict[str, str]:
        jar: dict[str, str] = {}
        for key, value in self.headers:
            if key.lower() != "set-cookie":
                continue
            first = value.split(";", 1)[0]
            if "=" in first:
                name, cookie_value = first.split("=", 1)
                jar[name.strip()] = cookie_value.strip()
        return jar

    def contains(self, needle: str) -> bool:
        return needle in self.text

    def csrf_token(self) -> str:
        match = re.search(r'name="_csrf_token"\s+value="([^"]*)"', self.text)
        if match is None:
            raise AssertionError("the page has no CSRF token field")
        return match.group(1)


class TestClient:
    """Drives a WSGI application while remembering cookies and CSRF tokens."""

    def __init__(self, application: Any, host: str = "127.0.0.1", port: int = 8000) -> None:
        self.application = application
        self.host = host
        self.port = port
        self.cookies: dict[str, str] = {}
        self._csrf = ""

    # -- request plumbing --------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        form: dict[str, str] | None = None,
        include_csrf: bool = True,
    ) -> Response:
        body = b""
        payload = dict(form or {})
        if method.upper() == "POST" and include_csrf and "_csrf_token" not in payload:
            payload["_csrf_token"] = self._csrf
        if method.upper() == "POST":
            body = urllib.parse.urlencode(payload).encode("utf-8")

        path_only, _, query = path.partition("?")
        environ: dict[str, Any] = {
            "REQUEST_METHOD": method.upper(),
            "PATH_INFO": path_only,
            "QUERY_STRING": query,
            "SERVER_NAME": self.host,
            "SERVER_PORT": str(self.port),
            "SERVER_PROTOCOL": "HTTP/1.1",
            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(body),
            "wsgi.errors": io.StringIO(),
            "wsgi.multithread": True,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False,
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_HOST": f"{self.host}:{self.port}",
        }
        if self.cookies:
            environ["HTTP_COOKIE"] = "; ".join(
                f"{key}={value}" for key, value in self.cookies.items()
            )

        captured: dict[str, Any] = {}

        def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
            captured["status"] = int(status.split(" ", 1)[0])
            captured["headers"] = headers

        chunks = self.application(environ, start_response)
        raw = b"".join(chunks)
        response = Response(captured["status"], captured["headers"], raw)

        for name, value in response.cookies.items():
            if value == "":
                self.cookies.pop(name, None)
            else:
                self.cookies[name] = value
        try:
            self._csrf = response.csrf_token()
        except AssertionError:
            pass
        return response

    # -- convenience -------------------------------------------------------

    def get(self, path: str) -> Response:
        return self.request("GET", path)

    def post(
        self, path: str, form: dict[str, str] | None = None, include_csrf: bool = True
    ) -> Response:
        return self.request("POST", path, form, include_csrf=include_csrf)

    def login(self, username: str, password: str) -> Response:
        """Sign in through the real login form."""
        page = self.get("/login")
        token = page.csrf_token()
        response = self.post(
            "/login",
            {"username": username, "password": password, "_csrf_token": token},
            include_csrf=False,
        )
        # The login page has no session yet, so its token field is empty; the
        # authenticated home page has no form at all. Read a real token from the
        # employee overview, which every non-employee role may open.
        self.refresh_csrf(routes=("/employees", "/my-shifts", "/"))
        return response

    def refresh_csrf(self, routes: tuple[str, ...] = ("/employees", "/my-shifts", "/")) -> None:
        """Re-read the CSRF token from a page that carries a form."""
        for route in routes:
            try:
                page = self.get(route)
            except Exception:  # noqa: BLE001 - a failed probe tries the next route
                continue
            try:
                self._csrf = page.csrf_token()
                return
            except AssertionError:
                continue
