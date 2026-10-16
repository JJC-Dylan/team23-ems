"""MeítǐShāngchéng Employee Management System - start here in PyCharm.

Run this file (right-click -> Run 'app', or the green arrow next to
``if __name__ == "__main__"``). No packages need to be installed: the project
uses only the Python standard library.

Command-line options
--------------------
``--host``      interface to bind (default 127.0.0.1, this computer only)
``--port``      port to listen on (default 8000; use 0 for any free port)
``--db``        path to the SQLite database file
``--no-browser``do not open a web browser automatically
``--reset-db``  delete the database and start from the seeded demonstration data
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

# Allow "python app.py" and PyCharm's "run this file" from any working directory.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.app import Application  # noqa: E402
from app.database import default_db_path  # noqa: E402
from app.server import serve_forever  # noqa: E402


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "MeítǐShāngchéng Employee Management System: employee records and "
            "Morning/Afternoon/Evening shift planning."
        )
    )
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on")
    parser.add_argument("--db", default=None, help="path to the SQLite database file")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser automatically"
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="delete the existing database and recreate the demonstration data",
    )
    return parser.parse_args(argv)


def reset_database(db_path: str) -> None:
    """Remove the database file so the next start seeds a fresh one."""
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Database removed: {db_path}")


def open_browser_when_ready(url: str, timeout: float = 20.0) -> None:
    """Wait for the server to answer, then open the browser."""

    def worker() -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1.0):
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        try:
            webbrowser.open(url)
        except Exception:  # pragma: no cover - headless environments
            pass

    threading.Thread(target=worker, daemon=True).start()


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    db_path = os.path.abspath(arguments.db) if arguments.db else default_db_path()

    if arguments.reset_db:
        reset_database(db_path)

    application = Application(db_path=db_path, base_dir=PROJECT_ROOT)

    banner = f"""
==============================================================
  MeítǐShāngchéng - Employee Management System
  Team 23  |  ZZULI & Fontys
--------------------------------------------------------------
  Database      : {db_path}
  Listening on  : http://{arguments.host}:{arguments.port}
  Sign in with  : hr / hr123            (Human Resources)
                  supervisor / super123 (Store Supervisor)
                  employee / emp123     (Ordinary Employee)
--------------------------------------------------------------
  Press Ctrl+C in this console to stop the server.
==============================================================
"""
    print(banner)
    if application.seeded_now:
        print("First run: the database was created and filled with demonstration data.\n")

    if not arguments.no_browser:
        open_browser_when_ready(f"http://{arguments.host}:{arguments.port}/login")

    try:
        serve_forever(application, host=arguments.host, port=arguments.port)
    except KeyboardInterrupt:
        print("\nServer stopped. Employee and shift data is saved in the database file.")
    except OSError as error:
        print(
            f"\nCould not start the server on {arguments.host}:{arguments.port}.\n"
            f"Reason: {error}\n"
            "Another program may already use that port. Try: python app.py --port 8100\n",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
