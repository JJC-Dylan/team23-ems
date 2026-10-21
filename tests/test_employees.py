"""Employee record tests: add, edit, delete, search, validate, persist.

Maps to FR01, FR02, FR03, FR04, FR05, FR11, FR12, FR13 and NFR03.
"""

from __future__ import annotations

import os
import re
import sqlite3
import unittest

from app import repositories as repo
from app.app import Application
from tests.base import ApplicationTestCase, PROJECT_ROOT
from tests.client import TestClient


def restarted_application(db_path: str) -> Application:
    """A second application over an existing database file (a "restart")."""
    return Application(db_path=db_path, base_dir=PROJECT_ROOT)


def sign_in_on(application: Application, username: str, password: str) -> TestClient:
    client = TestClient(application)
    client.login(username, password)
    return client


class AddEmployeeTests(ApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("HR")

    def test_form_is_shown(self) -> None:
        response = self.client.get("/employees/new")
        self.assertEqual(response.status, 200)
        self.assertIn("Add new employee", response.text)
        self.assertIn('name="hourly_wage"', response.text)

    def test_valid_submission_creates_the_record(self) -> None:
        response = self.client.post(
            "/employees/new",
            {
                "name": "Zhao Lei",
                "address": "77 Songshan Road, Zhengzhou",
                "hourly_wage": "29.90",
                "phone": "138-0000-0099",
                "email": "zhao.lei@example.com",
                "hired_on": "2026-09-01",
            },
        )
        self.assertEqual(response.status, 303)
        self.assertIn("/employees/", response.location)

        overview = self.client.get("/")
        self.assertIn("Zhao Lei", overview.text)
        self.assertIn("29.90", overview.text)

    def test_new_employee_is_listed_with_no_shift(self) -> None:
        self.client.post(
            "/employees/new",
            {"name": "Zhao Lei", "address": "77 Songshan Road", "hourly_wage": "29.9"},
        )
        overview = self.client.get("/?q=Zhao")
        self.assertIn("Zhao Lei", overview.text)
        self.assertIn("Unassigned", overview.text)

    def test_optional_fields_may_be_left_empty(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Minimal Person", "address": "Somewhere in Zhengzhou", "hourly_wage": "20"},
        )
        self.assertEqual(response.status, 303)


class ValidationTests(ApplicationTestCase):
    """FR11 and URS Use Case 1 extension 1A."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("HR")

    def test_empty_name_is_reported_and_form_is_kept(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "", "address": "12 Some Road, Zhengzhou", "hourly_wage": "20"},
        )
        self.assertEqual(response.status, 200)
        self.assertIn("Employee name is required", response.text)
        # Everything the user typed before the error must still be there.
        self.assertIn('value="12 Some Road, Zhengzhou"', response.text)
        self.assertIn('value="20"', response.text)

    def test_non_numeric_wage_is_reported(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Test Person", "address": "12 Some Road, Zhengzhou", "hourly_wage": "abc"},
        )
        self.assertEqual(response.status, 200)
        self.assertIn("Hourly wage must be a number", response.text)

    def test_negative_wage_is_reported(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Test Person", "address": "12 Some Road, Zhengzhou", "hourly_wage": "-5"},
        )
        self.assertIn("greater than zero", response.text)

    def test_absurd_wage_is_reported(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Test Person", "address": "12 Some Road, Zhengzhou", "hourly_wage": "99999"},
        )
        self.assertIn("at most 1000.00", response.text)

    def test_short_address_is_reported(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Test Person", "address": "ab", "hourly_wage": "20"},
        )
        self.assertIn("Address must be at least", response.text)

    def test_bad_email_and_phone_are_reported(self) -> None:
        response = self.client.post(
            "/employees/new",
            {
                "name": "Test Person",
                "address": "12 Some Road, Zhengzhou",
                "hourly_wage": "20",
                "email": "not-an-email",
                "phone": "call-me",
            },
        )
        self.assertIn("Email must look like", response.text)
        self.assertIn("Phone may contain digits", response.text)

    def test_every_problem_is_listed_together(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "", "address": "", "hourly_wage": ""},
        )
        self.assertIn("Employee name is required", response.text)
        self.assertIn("Address is required", response.text)
        self.assertIn("Hourly wage is required", response.text)
        self.assertIn("Please correct the following", response.text)

    def test_no_technical_exception_text_leaks_to_the_user(self) -> None:
        response = self.client.post(
            "/employees/new",
            {"name": "Test Person", "address": "12 Some Road, Zhengzhou", "hourly_wage": "nope"},
        )
        lowered = response.text.lower()
        for forbidden in ("traceback", "sqlite3.", "valueerror", "<class"):
            self.assertNotIn(forbidden, lowered)

    def test_invalid_wage_filter_is_reported_but_page_still_works(self) -> None:
        response = self.client.get("/?wage_min=abc")
        self.assertEqual(response.status, 200)
        self.assertIn("The wage filter was ignored", response.text)

    def test_inverted_wage_range_is_reported(self) -> None:
        response = self.client.get("/?wage_min=50&wage_max=10")
        self.assertIn("cannot be greater than the maximum", response.text)


class EditEmployeeTests(ApplicationTestCase):
    """FR03."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("HR")

    def test_edit_form_is_prefilled(self) -> None:
        response = self.client.get("/employees/1/edit")
        self.assertEqual(response.status, 200)
        self.assertIn("Li Wei", response.text)
        self.assertIn('value="32.50"', response.text)

    def test_update_changes_the_record(self) -> None:
        response = self.client.post(
            "/employees/1/edit",
            {
                "name": "Li Wei",
                "address": "99 New Address Road, Zhengzhou",
                "hourly_wage": "40.00",
                "phone": "138-0000-0001",
                "email": "li.wei@example.com",
                "hired_on": "2026-03-02",
            },
        )
        self.assertEqual(response.status, 303)

        detail = self.client.get("/employees/1")
        self.assertIn("99 New Address Road, Zhengzhou", detail.text)
        self.assertIn("40.00", detail.text)

    def test_invalid_update_keeps_the_typed_values(self) -> None:
        response = self.client.post(
            "/employees/1/edit",
            {
                "name": "Li Wei",
                "address": "99 New Address Road, Zhengzhou",
                "hourly_wage": "-1",
            },
        )
        self.assertEqual(response.status, 200)
        self.assertIn("greater than zero", response.text)
        self.assertIn('value="99 New Address Road, Zhengzhou"', response.text)

    def test_editing_a_missing_employee_reports_it(self) -> None:
        response = self.client.get("/employees/9999/edit")
        self.assertEqual(response.status, 404)
        self.assertIn("Employee not found", response.text)


class DeleteEmployeeTests(ApplicationTestCase):
    """FR02 and URS Use Case 5."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("HR")

    def test_delete_removes_the_employee_from_the_overview(self) -> None:
        response = self.client.post("/employees/2/delete", {})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.location, "/")

        overview = self.client.get("/")
        # The record must be gone from the employee table. The name may still
        # appear in the confirmation message, so the table body is what gets
        # checked; the page also carries the shift-distribution table first.
        table_body = (
            overview.text.split('<table class="table table--hover">')[1]
            .split("</tbody>")[0]
        )
        self.assertNotIn("Zhang Min", table_body)
        self.assertIn("Chen Hao", table_body)

    def test_delete_also_removes_the_linked_shift(self) -> None:
        def shift_count(employee_id: int) -> int:
            conn = sqlite3.connect(self.application.db_path)
            try:
                return int(
                    conn.execute(
                        "SELECT COUNT(*) FROM shifts WHERE employee_id = ?", (employee_id,)
                    ).fetchone()[0]
                )
            finally:
                conn.close()

        self.assertEqual(
            shift_count(1), 6, "the seed data plans six rota rows for employee 1"
        )

        self.client.post("/employees/1/delete", {})

        self.assertEqual(
            shift_count(1),
            0,
            "deleting an employee must cascade to every rota row of that employee",
        )

    def test_deleting_a_missing_employee_reports_it(self) -> None:
        response = self.client.post("/employees/9999/delete", {})
        self.assertEqual(response.status, 404)


class OverviewAndSearchTests(ApplicationTestCase):
    """FR04, FR05, FR09, FR12, FR13."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("HR")

    def test_overview_lists_every_employee_and_the_total(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("5 employee(s) shown", response.text)
        self.assertIn("of 5 in total", response.text)
        for name in ("Li Wei", "Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertIn(name, response.text)

    def test_shift_distribution_table_shows_people_per_shift(self) -> None:
        response = self.client.get("/")
        self.assertIn("Shift distribution", response.text)
        table = (
            response.text.split('<table class="table table--compact shift-table">')[1]
            .split("</table>")[0]
        )
        for shift_name in ("Morning", "Afternoon", "Evening", "Unassigned"):
            self.assertIn(f'pill pill--{shift_name}"', table)
        # Two people work Morning, one Afternoon, three Evening, one unassigned.
        counts = re.findall(r'<td class="num">(\d+)</td>', table)
        self.assertEqual(counts, ["2", "1", "3", "1"])

    def test_search_by_name(self) -> None:
        response = self.client.get("/?q=Zhang")
        self.assertIn("Zhang Min", response.text)
        self.assertNotIn("Chen Hao", response.text)

    def test_search_by_address(self) -> None:
        response = self.client.get("/?q=Nongye")
        self.assertIn("Chen Hao", response.text)
        self.assertNotIn("Li Wei", response.text)

    def test_search_without_match_shows_a_placeholder(self) -> None:
        response = self.client.get("/?q=NobodyHere")
        self.assertIn("No employee matches the current search", response.text)

    def test_wage_range_filter(self) -> None:
        response = self.client.get("/?wage_min=30&wage_max=36")
        self.assertIn("Li Wei", response.text)      # 32.50
        self.assertIn("Chen Hao", response.text)    # 35.75
        self.assertNotIn("Zhang Min", response.text)  # 28.00
        self.assertNotIn("Sun Jie", response.text)    # 41.00

    def test_shift_filter_including_unassigned(self) -> None:
        assigned = self.client.get("/?shift=Morning")
        self.assertIn("Li Wei", assigned.text)
        self.assertIn("Sun Jie", assigned.text)
        self.assertNotIn("Zhang Min", assigned.text)

        unassigned = self.client.get("/?shift=Unassigned")
        self.assertIn("Wang Fang", unassigned.text)
        self.assertNotIn("Li Wei", unassigned.text)

    def test_sorting_by_wage_descending(self) -> None:
        response = self.client.get("/?sort=wage_desc")
        text = response.text
        self.assertLess(text.index("Sun Jie"), text.index("Chen Hao"))
        self.assertLess(text.index("Chen Hao"), text.index("Li Wei"))
        self.assertLess(text.index("Li Wei"), text.index("Wang Fang"))

    def test_statistics_page_shows_totals(self) -> None:
        response = self.client.get("/statistics")
        self.assertEqual(response.status, 200)
        self.assertIn("Total employees", response.text)
        self.assertIn("Shift plan of the week", response.text)
        self.assertIn("Average hourly wage", response.text)

    def test_duplicate_names_are_still_distinguishable_by_id(self) -> None:
        self.client.post(
            "/employees/new",
            {"name": "Li Wei", "address": "Second record for the same name", "hourly_wage": "25"},
        )
        response = self.client.get("/?q=Li Wei")
        self.assertIn("#1", response.text)
        self.assertIn("#6", response.text)


class PersistenceTests(ApplicationTestCase):
    """NFR03: data survives an application restart."""

    def test_records_survive_a_new_application_instance(self) -> None:
        client = self.sign_in("HR")
        client.post(
            "/employees/new",
            {
                "name": "Persisted Person",
                "address": "1 Restart Road, Zhengzhou",
                "hourly_wage": "22.25",
            },
        )

        restarted = restarted_application(self.db_path)
        fresh = sign_in_on(restarted, "hr", "hr123")
        response = fresh.get("/?q=Persisted")
        self.assertIn("Persisted Person", response.text)
        self.assertIn("22.25", response.text)

    def test_shift_assignment_survives_a_restart(self) -> None:
        week = repo.week_dates()
        supervisor = self.sign_in("Supervisor")
        supervisor.post(
            "/employees/4/shift", {"work_date": week[0], "shift_name": "Evening"}
        )

        restarted = restarted_application(self.db_path)
        fresh = sign_in_on(restarted, "supervisor", "super123")
        detail = fresh.get(f"/employees/4?week={week[0]}")
        self.assertIn("Evening", detail.text)
        self.assertIn(week[0], detail.text)

    def test_seeding_does_not_run_twice(self) -> None:
        restarted = restarted_application(self.db_path)
        self.assertFalse(restarted.seeded_now, "an existing database must not be reseeded")
        client = sign_in_on(restarted, "hr", "hr123")
        self.assertIn("5 employee(s) shown", client.get("/").text)


if __name__ == "__main__":
    unittest.main()
