"""Work-shift tests: assignment, per-employee view and store overview.

Maps to FR06, FR07, FR08 and FR10 and to URS Use Cases 2, 3, 4 and 6.
"""

from __future__ import annotations

import unittest

from tests.base import ApplicationTestCase


class ShiftAssignmentTests(ApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("Supervisor")

    def test_assign_morning_shift(self) -> None:
        response = self.client.post("/employees/4/shift", {"shift_name": "Morning"})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.location, "/employees/4")

        detail = self.client.get("/employees/4")
        self.assertIn("Morning", detail.text)
        self.assertIn("Assigned work shifts of this employee", detail.text)

    def test_assignment_offers_only_the_three_fixed_shifts(self) -> None:
        detail = self.client.get("/employees/4")
        for name in ("Morning", "Afternoon", "Evening"):
            self.assertRegex(detail.text, rf'<option value="{name}"')
        # Custom shift creation is explicitly out of scope (URS 4.2).
        self.assertNotIn("Custom shift", detail.text)
        self.assertIn('<option value="Unassigned"', detail.text)

    def test_reassigning_replaces_the_previous_shift(self) -> None:
        self.client.post("/employees/1/shift", {"shift_name": "Evening"})
        detail = self.client.get("/employees/1")
        self.assertIn("Evening", detail.text)
        # Employee 1 starts on Morning, so only the new shift may remain.
        self.assertIn("No shifts assigned for this employee", self.client.get("/employees/4").text)

    def test_clearing_an_assignment(self) -> None:
        response = self.client.post("/employees/1/shift", {"shift_name": "Unassigned"})
        self.assertEqual(response.status, 303)
        detail = self.client.get("/employees/1")
        self.assertIn("No shifts assigned for this employee", detail.text)

    def test_invalid_shift_value_changes_nothing(self) -> None:
        response = self.client.post("/employees/1/shift", {"shift_name": "Midnight"})
        self.assertEqual(response.status, 303)
        detail = self.client.get("/employees/1")
        self.assertIn("Morning", detail.text)

    def test_assigning_to_a_missing_employee_returns_to_the_overview(self) -> None:
        """URS Use Case 2, extension 1A."""
        response = self.client.post("/employees/9999/shift", {"shift_name": "Morning"})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.location, "/employees")

        overview = self.client.get("/employees")
        self.assertIn("could not be found", overview.text)

    def test_assignment_records_who_changed_it(self) -> None:
        self.client.post("/employees/4/shift", {"shift_name": "Afternoon"})
        detail = self.client.get("/employees/4")
        self.assertIn("Store Supervisor", detail.text)

    def test_supervisor_cannot_assign_from_the_store_overview_page(self) -> None:
        """URS section 6: shift-modification controls are hidden on that page."""
        response = self.client.get("/shifts")
        self.assertNotIn('name="shift_name"', response.text)
        self.assertNotIn("Confirm shift assignment", response.text)


class SingleEmployeeShiftViewTests(ApplicationTestCase):
    """FR07 and URS Use Case 3."""

    def test_hr_sees_the_assigned_shift(self) -> None:
        client = self.sign_in("HR")
        detail = client.get("/employees/1")
        self.assertIn("Morning", detail.text)

    def test_placeholder_when_no_shift_is_assigned(self) -> None:
        client = self.sign_in("HR")
        detail = client.get("/employees/4")
        self.assertIn("No shifts assigned for this employee", detail.text)

    def test_supervisor_sees_the_assigned_shift(self) -> None:
        client = self.sign_in("Supervisor")
        detail = client.get("/employees/2")
        self.assertIn("Afternoon", detail.text)


class StoreShiftOverviewTests(ApplicationTestCase):
    """FR08, FR10 and URS Use Case 4."""

    def test_overview_lists_each_employee_with_a_shift(self) -> None:
        client = self.sign_in("Supervisor")
        response = client.get("/shifts")
        self.assertEqual(response.status, 200)
        self.assertIn("5 employee(s) listed", response.text)
        for name in ("Li Wei", "Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertIn(name, response.text)

    def test_unassigned_employee_appears_as_unassigned(self) -> None:
        client = self.sign_in("Supervisor")
        response = client.get("/shifts?shift=Unassigned")
        self.assertIn("Wang Fang", response.text)
        self.assertNotIn("Li Wei", response.text)

    def test_shift_counts_are_shown(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts")
        self.assertIn("Assigned shift", response.text)
        self.assertIn("Employees in total", response.text)

    def test_hr_can_read_the_store_overview(self) -> None:
        client = self.sign_in("HR")
        self.assertEqual(client.get("/shifts").status, 200)

    def test_assignment_is_visible_in_the_overview_afterwards(self) -> None:
        supervisor = self.sign_in("Supervisor")
        supervisor.post("/employees/4/shift", {"shift_name": "Evening"})
        overview = supervisor.get("/shifts?shift=Evening")
        self.assertIn("Wang Fang", overview.text)


class OwnShiftViewTests(ApplicationTestCase):
    """FR07 for the Ordinary Employee role and URS Use Case 6."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("Ordinary Employee")

    def test_employee_sees_only_their_own_schedule(self) -> None:
        response = self.client.get("/my-shifts")
        self.assertEqual(response.status, 200)
        self.assertIn("Li Wei", response.text)
        # Other employees must not be disclosed to an Ordinary Employee.
        for other in ("Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertNotIn(other, response.text)

    def test_placeholder_when_nothing_is_assigned(self) -> None:
        supervisor = self.sign_in("Supervisor")
        supervisor.post("/employees/1/shift", {"shift_name": "Unassigned"})

        response = self.client.get("/my-shifts")
        self.assertIn("You have not been assigned any shifts yet", response.text)

    def test_home_page_also_shows_the_own_shift_summary(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("Your current shift", response.text)
        self.assertIn("Morning", response.text)

    def test_employee_cannot_read_the_store_overview(self) -> None:
        self.assertEqual(self.client.get("/shifts").status, 403)


if __name__ == "__main__":
    unittest.main()
