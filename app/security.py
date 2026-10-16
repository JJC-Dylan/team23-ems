"""Small, dependency-free security helpers: password hashing and sessions.

Kept separate from :mod:`app.database` so the persistence layer stays free of
authentication concerns and the two modules never import each other.

Security notes for the reader
-----------------------------
* Passwords are never stored in clear text. Each password gets a unique random
  salt and is stretched with PBKDF2-HMAC-SHA256.
* Verification uses :func:`hmac.compare_digest` so comparison time does not
  reveal how much of the stored hash matched.
* Sessions are opaque random tokens held in a server-side store and referenced
  by an HttpOnly cookie, so the browser never receives authentication state it
  could tamper with.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

#: PBKDF2 work factor. Chosen to stay comfortably interactive for a small
#: internal tool while making offline guessing expensive.
PBKDF2_ITERATIONS = 200_000
_HASH_ALGORITHM = "pbkdf2_sha256"
_SALT_BYTES = 16

#: Session lifetime (NFR05 anticipates a handful of concurrent shop users;
#: an eight-hour working day is a convenient upper bound).
SESSION_TTL_SECONDS = 8 * 60 * 60

CSRF_FIELD_NAME = "_csrf_token"
SESSION_COOKIE_NAME = "ems_session"


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash string for ``password``."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{_HASH_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check ``password`` against a hash produced by :func:`hash_password`."""
    try:
        algorithm, iterations_text, salt_hex, digest_hex = stored.split("$")
        if algorithm != _HASH_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------


@dataclass
class Session:
    """Server-side session state for one logged-in user."""

    token: str
    user_id: int
    username: str
    display_name: str
    role: str
    employee_id: int | None = None
    csrf_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return (time.time() - self.last_seen_at) > SESSION_TTL_SECONDS

    # -- convenience role checks (mirrors URS section 3 permissions) --------

    @property
    def is_hr(self) -> bool:
        return self.role == "HR"

    @property
    def is_supervisor(self) -> bool:
        return self.role == "Supervisor"

    @property
    def is_ordinary_employee(self) -> bool:
        return self.role == "Ordinary Employee"

    @property
    def can_manage_employees(self) -> bool:
        """Create / edit / delete employee records: HR only (FR01-FR03, NFR02)."""
        return self.is_hr

    @property
    def can_view_employee_directory(self) -> bool:
        """Overview list and details: HR and Supervisor only (FR04, FR05, FR09)."""
        return self.is_hr or self.is_supervisor

    @property
    def can_assign_shifts(self) -> bool:
        """Manual shift assignment: Supervisor only (FR06, FR10, NFR02)."""
        return self.is_supervisor

    @property
    def can_view_store_shifts(self) -> bool:
        """Full-store shift overview: HR and Supervisor (FR08)."""
        return self.is_hr or self.is_supervisor


class SessionStore:
    """Thread-safe in-memory session store keyed by opaque token.

    The store is deliberately simple. A single shop-administration process
    serves at most a handful of users, and a restart is allowed to require a
    fresh login (only employee and shift *data* must persist, per NFR03).
    """

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds

    def create(self, user_row: Any) -> Session:
        """Create and register a session for a ``users`` table row."""
        session = Session(
            token=secrets.token_urlsafe(32),
            user_id=int(user_row["id"]),
            username=str(user_row["username"]),
            display_name=str(user_row["display_name"]),
            role=str(user_row["role"]),
            employee_id=(
                int(user_row["employee_id"]) if user_row["employee_id"] is not None else None
            ),
        )
        with self._lock:
            self._purge_expired_locked()
            self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        """Return the live session for ``token``, or ``None``."""
        if not token:
            return None
        with self._lock:
            session = self._sessions.get(token)
            if session is None:
                return None
            if (time.time() - session.last_seen_at) > self._ttl_seconds:
                del self._sessions[token]
                return None
            session.last_seen_at = time.time()
            return session

    def destroy(self, token: str | None) -> None:
        """Forget a session (logout)."""
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def active_count(self) -> int:
        """Number of live sessions; used by the diagnostics footer."""
        with self._lock:
            self._purge_expired_locked()
            return len(self._sessions)

    def _purge_expired_locked(self) -> None:
        now = time.time()
        stale = [
            token
            for token, session in self._sessions.items()
            if (now - session.last_seen_at) > self._ttl_seconds
        ]
        for token in stale:
            del self._sessions[token]
