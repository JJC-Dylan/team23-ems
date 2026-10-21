"""End-to-end test over a real HTTP socket, not just the WSGI callable.

This proves the page the user actually opens works: the threaded server binds,
serves static files, sets a session cookie and renders the marketplace of pages
over real HTTP. It also demonstrates the ten-user concurrency requirement
(NFR05) under a small burst of parallel requests.
"""

from __future__ import annotations

import http.cookiejar
import os
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

from app.app import Application
from app.server import build_server
from tests.base import PROJECT_ROOT


class LiveServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import tempfile

        cls.temp_dir = tempfile.mkdtemp(prefix="ems-live-")
        cls.db_path = os.path.join(cls.temp_dir, "live.db")
        cls.application = Application(db_path=cls.db_path, base_dir=PROJECT_ROOT)
        cls.server = build_server(cls.application, host="127.0.0.1", port=0)
        cls.port = int(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, kwargs={"poll_interval": 0.1})
        cls.thread.daemon = True
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        import shutil

        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    # -- helpers -----------------------------------------------------------

    def opener(self) -> urllib.request.OpenerDirector:
        jar = http.cookiejar.CookieJar()
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def get(self, opener, path: str):
        return opener.open(f"http://127.0.0.1:{self.port}{path}", timeout=10)

    def sign_in(self, opener, username: str, password: str) -> None:
        login_page = self.get(opener, "/login").read().decode("utf-8")
        token_marker = 'name="_csrf_token" value="'
        start = login_page.index(token_marker) + len(token_marker)
        token = login_page[start : login_page.index('"', start)]
        payload = urllib.parse.urlencode(
            {"username": username, "password": password, "_csrf_token": token}
        ).encode("utf-8")
        self.get(opener, "/login")
        response = opener.open(
            urllib.request.Request(
                f"http://127.0.0.1:{self.port}/login", data=payload, method="POST"
            ),
            timeout=10,
        )
        self.assertIn("Employee", response.read().decode("utf-8"))

    # -- tests -------------------------------------------------------------

    def test_login_page_is_served_over_http(self) -> None:
        opener = self.opener()
        response = self.get(opener, "/login")
        self.assertEqual(response.status, 200)
        self.assertIn("Employee Management System", response.read().decode("utf-8"))

    def test_static_stylesheet_is_served_with_the_right_type(self) -> None:
        opener = self.opener()
        response = self.get(opener, "/static/css/app.css")
        self.assertEqual(response.status, 200)
        self.assertIn("text/css", response.headers.get("Content-Type", ""))
        self.assertIn("--brand", response.read().decode("utf-8"))

    def test_static_javascript_is_served(self) -> None:
        opener = self.opener()
        response = self.get(opener, "/static/js/app.js")
        self.assertEqual(response.status, 200)
        self.assertIn("javascript", response.headers.get("Content-Type", ""))

    def test_static_path_traversal_is_refused(self) -> None:
        opener = self.opener()
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.get(opener, "/static/../app.py")
        self.assertEqual(context.exception.code, 404)

    def test_health_endpoint(self) -> None:
        opener = self.opener()
        self.assertEqual(self.get(opener, "/healthz").read().decode("utf-8"), "ok")

    def test_full_sign_in_flow_and_a_page_render(self) -> None:
        opener = self.opener()
        self.sign_in(opener, "hr", "hr123")
        page = self.get(opener, "/").read().decode("utf-8")
        self.assertIn("Li Wei", page)
        self.assertIn("Add new employee", page)

    def test_anonymous_request_ends_at_the_login_page(self) -> None:
        opener = self.opener()
        response = self.get(opener, "/")
        self.assertIn("/login", response.geturl())

    def test_parallel_requests_are_handled(self) -> None:
        """NFR05: a burst of concurrent signed-in users is served correctly."""
        results: list[int] = []
        lock = threading.Lock()

        def worker() -> None:
            opener = self.opener()
            try:
                self.sign_in(opener, "hr", "hr123")
                response = self.get(opener, "/")
                code = response.status
            except Exception:  # noqa: BLE001 - recorded as a failure below
                code = 0
            with lock:
                results.append(code)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(len(results), 10)
        self.assertTrue(all(code == 200 for code in results), f"unexpected statuses: {results}")


if __name__ == "__main__":
    unittest.main()
