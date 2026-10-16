"""HTTP-level error types shared by the dispatcher and the page handlers."""

from __future__ import annotations


class HttpError(Exception):
    """An error that maps to a status code and a friendly page.

    Handlers raise this instead of returning invalid markup, which keeps
    NFR04 satisfied: the end user always sees a readable explanation.
    """

    def __init__(self, status: int, title: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.title = title
        self.message = message


def not_found(message: str = "The page you requested does not exist.") -> HttpError:
    """404 helper."""
    return HttpError(404, "Page not found", message)
