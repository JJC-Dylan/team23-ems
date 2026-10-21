"""Login, logout and role-based access control tests.

Covers FR09, FR10 and NFR02: the three roles must see and reach only what the
URS section 3 permission table allows.
"""

from __future__ import annotations

import unittest

from tests.base import ApplicationTestCase


class LoginTests(ApplicationTestCase):
    def test_login_page_is_public(self) -> None:
        response = self.client.get("/login")
        self.assertEqual(response.status, 200)
        self.assertIn("Sign in", response.text)
        self.assertIn("Demonstration accounts", response.text)

    def test_valid_credentials_start_a_session(self) -> None:
        response = self.client.login("hr", "hr123")
        self.assertEqual(response.status, 303)
        self.assertTrue(response.location.endswith("/"))
        self.assertIn("ems_session", self.client.cookies)

    def test_wrong_password_is_rejected(self) -> None:
        response = self.client.login("hr", "not-the-password")
        self.assertEqual(response.status, 200)
        self.assertIn("Username or password is incorrect", response.text)
        self.assertNotIn("ems_session", self.client.cookies)

    def test_unknown_user_gets_the_same_message_as_a_wrong_password(self) -> None:
        response = self.client.login("nobody", "whatever")
        self.assertIn("Username or password is incorrect", response.text)

    def test_missing_field_is_reported(self) -> None:
        page = self.client.get("/login")
        response = self.client.post(
            "/login",
            {"username": "", "password": "", "_csrf_token": page.csrf_token()},
            include_csrf=False,
        )
        self.assertIn("Please enter both your username and your password", response.text)

    def test_password_is_never_echoed_back(self) -> None:
        self.client.login("hr", "wrong-password")
        response = self.client.get("/login")
        self.assertNotIn("wrong-password", response.text)

    def test_every_role_lands_on_the_home_page(self) -> None:
        """URS 7: sign-in enters the System Home Page, then branches by role."""
        for username, password in (
            ("hr", "hr123"),
            ("supervisor", "super123"),
            ("employee", "emp123"),
        ):
            with self.subTest(user=username):
                client = self.fresh_client()
                response = client.login(username, password)
                self.assertEqual(response.status, 303)
                self.assertEqual(response.location, "/")
                home = client.get("/")
                self.assertEqual(home.status, 200)
                self.assertIn("Welcome,", home.text)

    def test_employee_home_shows_only_their_own_week(self) -> None:
        client = self.sign_in("Ordinary Employee")
        home = client.get("/")
        self.assertEqual(home.status, 200)
        self.assertIn("Welcome, Ordinary Employee", home.text)
        self.assertIn("This week's shifts", home.text)
        self.assertIn("6 shift(s) planned", home.text)
        # The home page must not leak another employee's schedule.
        for other in ("Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertNotIn(other, home.text)
        # The full timetable stays one click away.
        self.assertIn('href="/my-shifts"', home.text)

    def test_logout_ends_the_session(self) -> None:
        self.client.login("hr", "hr123")
        home = self.client.get("/")
        self.assertEqual(home.status, 200)
        self.client.post("/logout", {})
        after = self.client.get("/")
        self.assertEqual(after.status, 303)
        self.assertIn("/login", after.location)

    def test_stale_session_cookie_does_not_crash(self) -> None:
        self.client.cookies["ems_session"] = "not-a-real-token"
        response = self.client.get("/")
        self.assertEqual(response.status, 303)
        self.assertIn("/login", response.location)


class AccessControlTests(ApplicationTestCase):
    def test_anonymous_visitor_is_sent_to_login(self) -> None:
        for path in ("/", "/employees/1", "/shifts", "/statistics", "/my-shifts"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status, 303)
                self.assertIn("/login", response.location)

    def test_employee_role_cannot_open_staff_pages(self) -> None:
        client = self.sign_in("Ordinary Employee")
        for path in ("/employees/1", "/shifts", "/statistics"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status, 403)
                self.assertIn("Access denied", response.text)

    def test_employee_navigation_has_no_staff_links(self) -> None:
        client = self.sign_in("Ordinary Employee")
        response = client.get("/my-shifts")
        self.assertNotIn('href="/employees"', response.text)
        self.assertNotIn('href="/shifts"', response.text)
        self.assertIn('href="/my-shifts"', response.text)

    def test_supervisor_may_read_but_not_manage_employees(self) -> None:
        client = self.sign_in("Supervisor")

        overview = client.get("/")
        self.assertEqual(overview.status, 200)
        self.assertIn("read-only employee data", overview.text)
        self.assertNotIn('href="/employees/new"', overview.text)

        detail = client.get("/employees/1")
        self.assertEqual(detail.status, 200)
        self.assertIn("Confirm shift assignment", detail.text)
        self.assertNotIn("Edit employee", detail.text)

        self.assertEqual(client.get("/employees/new").status, 403)
        self.assertEqual(client.get("/employees/1/edit").status, 403)
        self.assertEqual(client.post("/employees/1/delete", {}).status, 403)

    def test_hr_may_manage_employees_but_not_assign_shifts(self) -> None:
        client = self.sign_in("HR")

        overview = client.get("/")
        self.assertEqual(overview.status, 200)
        self.assertIn('href="/employees/new"', overview.text)
        self.assertEqual(client.get("/employees").status, 404, "the separate overview page was removed")

        detail = client.get("/employees/1")
        self.assertEqual(detail.status, 200)
        self.assertIn("Edit employee", detail.text)
        self.assertNotIn("Confirm shift assignment", detail.text)
        # HR gets no rota panel at all, only the read-only week of that employee.
        self.assertNotIn("Add a rota entry", detail.text)
        self.assertIn("Rota for the week of", detail.text)
        self.assertNotIn('name="work_date"', detail.text)

        response = client.post("/employees/1/shift", {"shift_name": "Morning"})
        self.assertEqual(response.status, 403)

    def test_hr_and_supervisor_can_open_the_store_shift_overview(self) -> None:
        for role in ("HR", "Supervisor"):
            with self.subTest(role=role):
                client = self.sign_in(role)
                response = client.get("/shifts")
                self.assertEqual(response.status, 200)
                self.assertIn("Store shift overview", response.text)

    def test_missing_page_returns_a_friendly_404(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/no-such-page")
        self.assertEqual(response.status, 404)
        self.assertIn("Page not found", response.text)

    def test_malformed_employee_id_returns_404(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/employees/abc")
        self.assertEqual(response.status, 404)

    def test_wrong_method_is_reported(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/employees/1/delete")
        self.assertEqual(response.status, 405)
        self.assertIn("Method not allowed", response.text)

    def test_post_without_csrf_token_is_refused(self) -> None:
        client = self.sign_in("HR")
        client.get("/employees/new")
        response = client.post(
            "/employees/new",
            {"name": "Test Person", "address": "1 Test Road", "hourly_wage": "20"},
            include_csrf=True,
        )
        # The client always adds the token, so submit a deliberately wrong one.
        client2 = self.sign_in("HR")
        client2.get("/employees/new")
        forged = client2.post(
            "/employees/new",
            {
                "name": "Forged Person",
                "address": "1 Test Road",
                "hourly_wage": "20",
                "_csrf_token": "forged-token",
            },
            include_csrf=False,
        )
        self.assertEqual(forged.status, 400)
        self.assertIn("Security check failed", forged.text)
        self.assertEqual(response.status, 303)


if __name__ == "__main__":
    unittest.main()
