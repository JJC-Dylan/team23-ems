"""HTTP server built on the standard library.

``wsgiref`` provides the WSGI plumbing and ``http.server`` the threading, so no
web framework is required. URS NFR05 asks for up to ten concurrent signed-in
users; a thread per request comfortably covers that for a small internal tool.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from socketserver import ThreadingMixIn
from typing import Any
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .database import DEFAULT_DB_FILENAME, default_db_path


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    """A WSGI server that handles each request on its own thread."""

    daemon_threads = True
    allow_reuse_address = True


class QuietRequestHandler(WSGIRequestHandler):
    """Request handler that prints one tidy line per request.

    The default handler writes directly to stderr in a format that is noisy in
    PyCharm's console, so the interesting parts are extracted instead. The real
    traceback for a failing request is still printed by the application.
    """

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        message = format % args
        sys.stderr.write(f"[{self.log_date_time_string()}] {message}\n")


def build_server(
    application: Any, host: str = "127.0.0.1", port: int = 8000
) -> WSGIServer:
    """Create (but do not start) the HTTP server for an application."""
    return make_server(
        host,
        port,
        application,
        server_class=ThreadedWSGIServer,
        handler_class=QuietRequestHandler,
    )


def serve_forever(
    application: Any,
    host: str = "127.0.0.1",
    port: int = 8000,
    ready: "queue.Queue[tuple[str, int]] | None" = None,
    should_stop: "threading.Event | None" = None,
) -> None:
    """Serve until interrupted.

    ``ready`` receives ``(host, port)`` once the socket is bound, which lets a
    launcher open the browser at the real address even when port 0 was used.
    ``should_stop`` allows a test to shut the loop down cleanly.
    """
    server = build_server(application, host, port)
    bound_host, bound_port = server.server_address[0], server.server_address[1]
    if ready is not None:
        ready.put((str(bound_host), int(bound_port)))

    if should_stop is not None:
        def watch() -> None:
            while not should_stop.is_set():
                time.sleep(0.15)
            threading.Thread(target=server.shutdown, daemon=True).start()

        threading.Thread(target=watch, daemon=True).start()

    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()


def database_hint() -> str:
    """Human-readable database location, printed at start-up."""
    return f"{default_db_path()}  (file name: {DEFAULT_DB_FILENAME})"
