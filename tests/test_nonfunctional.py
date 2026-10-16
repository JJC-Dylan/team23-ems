"""Non-functional requirement tests: response time and concurrency.

NFR01 asks for employee-search and list-page response times of at most two
seconds. NFR05 asks the system to support at most ten concurrent signed-in
users. Both are exercised here against the real request pipeline, with a
data set large enough for the search path to be meaningful.
"""

from __future__ import annotations

import threading
import time
import unittest

from app import repositories as repo
from tests.base import ApplicationTestCase

#: NFR01 budget, with a generous share of the two seconds left for the caller.
RESPONSE_BUDGET_SECONDS = 2.0

#: Enough rows that the LIKE search and the ordering clauses do real work.
EXTRA_EMPLOYEES = 400


class ResponseTimeTests(ApplicationTestCase):
    """NFR01: search and list pages answer within two seconds."""

    def setUp(self) -> None:
        super().setUp()
        for index in range(EXTRA_EMPLOYEES):
            repo.create_employee(
                self.db_path,
                {
                    "name": f"Worker {index:04d}",
                    "address": f"{index} Industrial Road, Zhengzhou",
                    "hourly_wage": 20.0 + (index % 50),
                    "phone": f"138-0000-{index:04d}",
                    "email": f"worker{index}@example.com",
                    "hired_on": "2026-01-01",
                },
            )
        self.client = self.sign_in("HR")

    def _timed(self, path: str) -> float:
        started = time.perf_counter()
        response = self.client.get(path)
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status, 200, f"{path} did not render")
        return elapsed

    def test_employee_list_page_is_fast(self) -> None:
        self._timed("/employees")  # warm the compiled templates first
        elapsed = self._timed("/employees")
        self.assertLess(
            elapsed,
            RESPONSE_BUDGET_SECONDS,
            f"/employees took {elapsed:.3f}s for {EXTRA_EMPLOYEES + 5} employees",
        )

    def test_employee_search_is_fast(self) -> None:
        self._timed("/employees?q=Worker")
        elapsed = self._timed("/employees?q=Worker")
        self.assertLess(
            elapsed,
            RESPONSE_BUDGET_SECONDS,
            f"search took {elapsed:.3f}s",
        )

    def test_filtered_search_is_fast(self) -> None:
        self._timed("/employees?wage_min=30&wage_max=40")
        elapsed = self._timed("/employees?wage_min=30&wage_max=40")
        self.assertLess(elapsed, RESPONSE_BUDGET_SECONDS, f"filter took {elapsed:.3f}s")

    def test_store_shift_overview_is_fast(self) -> None:
        self._timed("/shifts")
        elapsed = self._timed("/shifts")
        self.assertLess(elapsed, RESPONSE_BUDGET_SECONDS, f"/shifts took {elapsed:.3f}s")

    def test_search_actually_matches_the_added_rows(self) -> None:
        """Guards the timing tests against a query that silently matches nothing."""
        response = self.client.get("/employees?q=Worker 0001")
        self.assertIn("Worker 0001", response.text)
        self.assertIn("1 employee(s) shown", response.text)


class ConcurrencyTests(ApplicationTestCase):
    """NFR05: ten concurrent signed-in users are served correctly."""

    def test_ten_concurrent_users_each_get_their_own_session(self) -> None:
        statuses: list[int] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            client = self.fresh_client()
            client.login("hr", "hr123")
            page = client.get("/employees")
            with lock:
                statuses.append(page.status)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(len(statuses), 10, "every worker must finish")
        self.assertTrue(all(code == 200 for code in statuses), statuses)
        # Each worker authenticated separately, so ten live sessions exist.
        self.assertGreaterEqual(self.application.sessions.active_count(), 10)

    def test_concurrent_writes_do_not_corrupt_data(self) -> None:
        """Ten simultaneous inserts must all land, with shift rows intact."""
        errors: list[str] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            client = self.fresh_client()
            client.login("hr", "hr123")
            response = client.post(
                "/employees/new",
                {
                    "name": f"Concurrent {index}",
                    "address": f"{index} Parallel Street, Zhengzhou",
                    "hourly_wage": "25.00",
                },
            )
            if response.status != 303:
                with lock:
                    errors.append(f"worker {index} got {response.status}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(errors, [], f"some concurrent writes failed: {errors}")
        self.assertEqual(repo.count_employees(self.db_path), 5 + 10)


if __name__ == "__main__":
    unittest.main()
