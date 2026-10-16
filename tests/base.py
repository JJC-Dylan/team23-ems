"""Shared test scaffolding: every test runs against a throwaway database."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.app import Application  # noqa: E402
from tests.client import TestClient  # noqa: E402


class ApplicationTestCase(unittest.TestCase):
    """Base class providing a fresh application, database and HTTP client."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="ems-tests-")
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.application = Application(db_path=self.db_path, base_dir=PROJECT_ROOT)
        self.client = TestClient(self.application)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -- helpers -----------------------------------------------------------

    def fresh_client(self) -> TestClient:
        """A second browser, sharing the same database."""
        return TestClient(self.application)

    def sign_in(self, role: str) -> TestClient:
        """Return a client signed in as the demonstration account for a role."""
        credentials = {
            "HR": ("hr", "hr123"),
            "Supervisor": ("supervisor", "super123"),
            "Ordinary Employee": ("employee", "emp123"),
        }
        username, password = credentials[role]
        client = self.fresh_client()
        response = client.login(username, password)
        self.assertIn(
            response.status,
            (303, 302),
            f"signing in as {role} should redirect, got {response.status}",
        )
        return client
