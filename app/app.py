"""WSGI application core: routing, sessions, RBAC and error handling.

This module contains the request lifecycle only; page content lives in
:mod:`app.views` and SQL lives in :mod:`app.repositories`.

Access control
--------------
Every route declares the roles that may reach it. The dispatcher is the single
place that turns those declarations into a decision, which is what NFR02
(role-based access control) requires:

* HR may create, edit and delete employee records.
* Supervisor may read employee data and assign shifts, but not modify records.
* Ordinary Employee may only reach the "My Work Shifts" page.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
import urllib.parse
from datetime import datetime
from typing import Any, Callable, Iterable

from .database import ROLE_DESCRIPTIONS, SHIFTS, default_db_path, initialize, seed
from .errors import HttpError, not_found
from .htmlpages import escape_html
from .security import (
    CSRF_FIELD_NAME,
    SESSION_COOKIE_NAME,
    Session,
    SessionStore,
    hash_password,
)
from .templateengine import TemplateEngine, TemplateError

Handler = Callable[["_Request", "_Response"], "_Response"]

NOT_FOUND = not_found


def role_slug(role: Any) -> str:
    """CSS-friendly form of a role name: ``Ordinary Employee`` -> ``ordinary-employee``."""
    return str(role).strip().lower().replace(" ", "-")


def shift_slug(shift: Any) -> str:
    """CSS-friendly form of a shift name: ``Unassigned`` or a real shift."""
    text = str(shift or "Unassigned").strip().lower()
    return text if text else "unassigned"


# --------------------------------------------------------------------------
# Request / response objects
# --------------------------------------------------------------------------


class _Request:
    """Parsed view of one WSGI request."""

    def __init__(self, environ: dict[str, Any]) -> None:
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO", "/") or "/"
        raw_query = environ.get("QUERY_STRING", "")
        self.query = urllib.parse.parse_qs(raw_query, keep_blank_values=True)
        self.form: dict[str, str] = {}
        if self.method == "POST":
            self.form = self._read_form(environ)
        self.cookies = self._parse_cookies(environ.get("HTTP_COOKIE", ""))
        self.session: Session | None = None
        self.params: dict[str, str] = {}
        self.user: Session | None = None  # alias set for template convenience

    # -- input helpers -----------------------------------------------------

    @staticmethod
    def _read_form(environ: dict[str, Any]) -> dict[str, str]:
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        body = environ["wsgi.input"].read(length) if length > 0 else b""
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("latin-1", errors="replace")
        parsed = urllib.parse.parse_qs(text, keep_blank_values=True)
        return {key: values[-1] for key, values in parsed.items()}

    @staticmethod
    def _parse_cookies(header: str) -> dict[str, str]:
        cookies: dict[str, str] = {}
        for chunk in header.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            cookies[key.strip()] = value.strip()
        return cookies

    def get(self, key: str, default: str = "") -> str:
        values = self.query.get(key)
        return values[-1] if values else default

    def form_value(self, key: str, default: str = "") -> str:
        return self.form.get(key, default)

    def path_id(self, key: str = "employee_id") -> int:
        """Read a numeric path parameter, raising a 404 when it is malformed."""
        raw = self.params.get(key, "")
        if not raw.isdigit():
            raise NOT_FOUND(f"The employee identifier {raw!r} is not valid.")
        return int(raw)

    def flash(self, text: str, kind: str = "info") -> None:
        """Queue a message to show after the next redirect."""
        if self.session is None:
            return
        pending = getattr(self.session, "_flash", None)
        if pending is None:
            pending = []
            self.session._flash = pending  # type: ignore[attr-defined]
        pending.append({"kind": kind, "text": text})


class _Response:
    """A response under construction for the current request."""

    def __init__(self) -> None:
        self.status = 200
        self.headers: list[tuple[str, str]] = []
        self.body = b""
        self._cookies: list[str] = []

    # -- builders ----------------------------------------------------------

    def html(self, markup: str, status: int = 200) -> "_Response":
        self.status = status
        self.body = markup.encode("utf-8")
        self.set_header("Content-Type", "text/html; charset=utf-8")
        return self

    def text(self, payload: str, status: int = 200) -> "_Response":
        self.status = status
        self.body = payload.encode("utf-8")
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        return self

    def redirect(self, location: str, status: int = 303) -> "_Response":
        self.status = status
        self.body = b""
        self.set_header("Location", location)
        return self

    def static(self, payload: bytes, content_type: str) -> "_Response":
        self.status = 200
        self.body = payload
        self.set_header("Content-Type", content_type)
        return self

    # -- helpers -----------------------------------------------------------

    def set_header(self, name: str, value: str) -> None:
        self.headers = [(k, v) for k, v in self.headers if k.lower() != name.lower()]
        self.headers.append((name, value))

    def set_cookie(self, name: str, value: str, max_age: int | None = None) -> None:
        parts = [f"{name}={value}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        self._cookies.append("; ".join(parts))

    def clear_cookie(self, name: str) -> None:
        self._cookies.append(f"{name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def apply_cookies(self) -> None:
        for cookie in self._cookies:
            self.headers.append(("Set-Cookie", cookie))

    @property
    def status_line(self) -> str:
        return f"{self.status} {HTTP_STATUS.get(self.status, 'Unknown')}"


HTTP_STATUS = {
    200: "OK",
    204: "No Content",
    303: "See Other",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}

STATIC_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


# --------------------------------------------------------------------------
# Application
# --------------------------------------------------------------------------


class Application:
    """The Employee Management System WSGI application."""

    def __init__(self, db_path: str | None = None, base_dir: str | None = None) -> None:
        self.base_dir = os.path.abspath(base_dir or os.path.dirname(os.path.dirname(__file__)))
        self.db_path = db_path or default_db_path()
        self.templates = TemplateEngine(os.path.join(self.base_dir, "templates"))
        self.static_dir = os.path.join(self.base_dir, "static")
        self.sessions = SessionStore()
        self.routes: list[tuple[re.Pattern[str], frozenset[str], tuple[str, ...], Handler]] = []
        self.started_at = datetime.now()

        initialize(self.db_path)
        seeded = seed(self.db_path, hash_password)
        self.seeded_now = seeded

        from . import views

        views.register(self)

    # -- route registration ------------------------------------------------

    def route(
        self,
        pattern: str,
        methods: Iterable[str] = ("GET",),
        roles: Iterable[str] | None = None,
    ) -> Callable[[Handler], Handler]:
        """Register a handler.

        ``pattern`` is a regular expression anchored at both ends. ``roles``
        lists the permitted roles; ``None`` means "any authenticated user"
        and an empty tuple means "no login required".
        """
        compiled = re.compile(f"^{pattern}$")
        method_set = frozenset(m.upper() for m in methods)
        role_tuple = tuple(roles) if roles is not None else ()

        def decorator(handler: Handler) -> Handler:
            self.routes.append((compiled, method_set, role_tuple, handler))
            return handler

        return decorator

    # -- WSGI entry point --------------------------------------------------

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]):
        request = _Request(environ)
        response = _Response()
        # Handlers and templates reach the application through the environment,
        # which avoids an import cycle between this module and app.views.
        environ["ems.app"] = self

        token = request.cookies.get(SESSION_COOKIE_NAME)
        request.session = self.sessions.get(token)
        request.user = request.session

        try:
            self._dispatch(request, response)
        except _RedirectTo as redirect:
            response.redirect(redirect.location)
        except HttpError as error:
            self._render_error(request, response, error)
        except TemplateError as error:
            self._log_exception(environ)
            self._render_error(
                request,
                response,
                HttpError(
                    500,
                    "Page could not be rendered",
                    "A template problem prevented this page from being displayed. "
                    f"Developer detail: {error}",
                ),
            )
        except Exception:  # noqa: BLE001 - the last line of defence for end users
            self._log_exception(environ)
            self._render_error(
                request,
                response,
                HttpError(
                    500,
                    "Something went wrong",
                    "The system could not complete that action. "
                    "Your data has not been changed. Please try again.",
                ),
            )

        response.apply_cookies()
        response.set_header("Content-Length", str(len(response.body)))
        response.set_header("X-Content-Type-Options", "nosniff")
        start_response(response.status_line, response.headers)
        return [response.body]

    def _dispatch(self, request: _Request, response: _Response) -> None:
        if request.path.startswith("/static/"):
            self._serve_static(request, response)
            return

        path_matched = False
        for pattern, methods, roles, handler in self.routes:
            match = pattern.match(request.path)
            if not match:
                continue
            path_matched = True
            if request.method not in methods:
                continue
            request.params = {k: v for k, v in match.groupdict().items() if v is not None}
            self._authorize(request, roles)
            self._check_csrf(request)
            handler(request, response)
            return

        if path_matched:
            raise HttpError(
                405,
                "Method not allowed",
                f"The address {request.path} does not accept a {request.method} request.",
            )
        raise NOT_FOUND()

    def _authorize(self, request: _Request, roles: tuple[str, ...]) -> None:
        if not roles:
            return
        if request.session is None:
            target = urllib.parse.quote(request.path, safe="")
            raise _RedirectTo(f"/login?next={target}")
        if request.session.role not in roles:
            raise HttpError(
                403,
                "Access denied",
                "Your role does not have permission to open that page. "
                "You are signed in as "
                f"{request.session.role}.",
            )

    def _check_csrf(self, request: _Request) -> None:
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return
        if request.session is None:
            return
        supplied = request.form.get(CSRF_FIELD_NAME, "")
        expected = request.session.csrf_token
        if supplied != expected:
            raise HttpError(
                400,
                "Security check failed",
                "This form could not be verified, so nothing was changed. "
                "Please go back, reload the page and submit the form again.",
            )

    def _serve_static(self, request: _Request, response: _Response) -> None:
        relative = request.path[len("/static/") :]
        target = os.path.abspath(os.path.join(self.static_dir, relative))
        if not target.startswith(self.static_dir + os.sep) or not os.path.isfile(target):
            raise NOT_FOUND("That static file does not exist.")
        extension = os.path.splitext(target)[1].lower()
        with open(target, "rb") as handle:
            payload = handle.read()
        response.static(payload, STATIC_CONTENT_TYPES.get(extension, "application/octet-stream"))

    def _render_error(self, request: _Request, response: _Response, error: HttpError) -> None:
        context = self.base_context(request)
        context.update(
            {
                "page_title": error.title,
                "status": error.status,
                "error_title": error.title,
                "error_message": error.message,
            }
        )
        try:
            markup = self.templates.render("error.html", context)
        except TemplateError:
            markup = (
                f"<h1>{error.status} {escape_html(error.title)}</h1>"
                f"<p>{escape_html(error.message)}</p>"
            )
        response.html(markup, status=error.status)

    @staticmethod
    def _log_exception(environ: dict[str, Any]) -> None:
        """Write the real traceback to the console (developers), not the page."""
        sys.stderr.write(
            f"\n[EMS] Unhandled error for {environ.get('REQUEST_METHOD')} "
            f"{environ.get('PATH_INFO')}\n"
        )
        traceback.print_exc(file=sys.stderr)

    # -- shared template context ------------------------------------------

    def base_context(self, request: _Request) -> dict[str, Any]:
        session = request.session
        return {
            "current_user": session,
            "csrf_token": session.csrf_token if session else "",
            "flash_messages": self._consume_flash(request),
            "shift_names": SHIFTS,
            "role_descriptions": ROLE_DESCRIPTIONS,
            "app_version": "1.0.0",
            "active_sessions": self.sessions.active_count(),
            "path": request.path,
            "role_slug": role_slug,
            "shift_slug": shift_slug,
        }

    def render(self, request: _Request, template: str, **context: Any) -> str:
        merged = self.base_context(request)
        merged.update(context)
        return self.templates.render(template, merged)

    # -- flash messages ---------------------------------------------------

    @staticmethod
    def _consume_flash(request: _Request) -> list[dict[str, str]]:
        session = request.session
        if session is None:
            return []
        pending = getattr(session, "_flash", None) or []
        session._flash = []  # type: ignore[attr-defined]
        return pending


class _RedirectTo(Exception):
    """Internal signal: authentication is required before continuing."""

    def __init__(self, location: str) -> None:
        super().__init__(location)
        self.location = location
