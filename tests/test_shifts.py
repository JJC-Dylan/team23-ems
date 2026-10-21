"""Weekly rota tests: dates, days, several shifts per day and the three views.

Maps to FR06, FR07, FR08 and FR10, to URS Use Cases 2, 3, 4 and 6, and to the
client's post-demonstration change request of 2026-10-18: the schedule is a
*week*, an employee may work several shifts on one day, and each role reads a
different shape of the same data.

The demonstration rota is seeded for the current week, so the tests compute the
current week from the same helper the application uses.
"""

from __future__ import annotations

import sqlite3
import unittest
from datetime import date, timedelta

from app import repositories as repo
from app.app import Application
from app.database import SHIFT_TIMES, initialize, shift_window, week_dates
from tests.base import ApplicationTestCase, PROJECT_ROOT


class WeeklyTestCase(ApplicationTestCase):
    """Shared helpers for the weekly rota tests."""

    def week(self) -> list[str]:
        return week_dates()

    def rota(self, employee_id: int) -> list[tuple[str, str]]:
        """The stored rota rows of one employee, straight from SQLite."""
        connection = sqlite3.connect(self.application.db_path)
        try:
            rows = connection.execute(
                "SELECT work_date, shift_name FROM shifts WHERE employee_id = ? "
                "ORDER BY work_date, shift_name",
                (employee_id,),
            ).fetchall()
        finally:
            connection.close()
        return [(str(row[0]), str(row[1])) for row in rows]

    def shift_rows_in_db(self) -> int:
        connection = sqlite3.connect(self.application.db_path)
        try:
            return int(connection.execute("SELECT COUNT(*) FROM shifts").fetchone()[0])
        finally:
            connection.close()

    def timetable_cell_status(self, text: str, date: str, shift: str) -> str:
        """Return ``on``/``off`` for one cell of the rendered timetable."""
        marker = f'data-date="{date}" data-shift="{shift}"'
        index = text.find(marker)
        self.assertNotEqual(index, -1, f"no timetable cell for {date} / {shift}")
        start = text.rfind("class=", 0, index)
        fragment = text[start:index]
        if "timetable__cell--on" in fragment:
            return "on"
        if "timetable__cell--off" in fragment:
            return "off"
        self.fail(f"cell {date}/{shift} has no on/off class: {fragment!r}")
        return ""


class ShiftTimeTests(ApplicationTestCase):
    """The shift times confirmed with the client on 2026-10-18."""

    def test_confirmed_times_are_used(self) -> None:
        self.assertEqual(SHIFT_TIMES["Morning"], ("08:00", "12:00"))
        self.assertEqual(SHIFT_TIMES["Afternoon"], ("14:00", "18:00"))
        self.assertEqual(SHIFT_TIMES["Evening"], ("20:00", "22:00"))

    def test_shift_window_text(self) -> None:
        self.assertEqual(shift_window("Morning"), "08:00 - 12:00")
        self.assertEqual(shift_window("Evening"), "20:00 - 22:00")
        self.assertEqual(shift_window("Unknown"), "")

    def test_no_shift_crosses_midnight(self) -> None:
        for start, end in SHIFT_TIMES.values():
            self.assertLess(start, end, "a shift must not end on the next day")


class WeekDateTests(ApplicationTestCase):
    """Week arithmetic: any day of the week resolves to Monday..Sunday."""

    def test_week_starts_on_monday_and_has_seven_days(self) -> None:
        dates = week_dates("2026-10-14")  # a Wednesday
        self.assertEqual(len(dates), 7)
        self.assertEqual(dates[0], "2026-10-12")
        self.assertEqual(dates[6], "2026-10-18")

    def test_any_day_of_the_week_gives_the_same_week(self) -> None:
        monday = week_dates("2026-10-12")
        for day in ("2026-10-12", "2026-10-15", "2026-10-18"):
            with self.subTest(day=day):
                self.assertEqual(week_dates(day), monday)

    def test_unreadable_anchor_falls_back_to_the_current_week(self) -> None:
        self.assertEqual(week_dates("not-a-date"), week_dates())
        self.assertEqual(week_dates(""), week_dates())

    def test_consecutive_weeks_are_seven_days_apart(self) -> None:
        self.assertEqual(repo.week_dates("2026-10-19")[0], "2026-10-19")
        self.assertEqual(repo.week_dates("2026-10-26")[0], "2026-10-26")


class ShiftAssignmentTests(WeeklyTestCase):
    """FR06/FR10: a Supervisor plans the rota day by day."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("Supervisor")

    def test_assign_a_dated_shift(self) -> None:
        monday = self.week()[0]
        response = self.client.post(
            "/employees/4/shift", {"work_date": monday, "shift_name": "Morning"}
        )
        self.assertEqual(response.status, 303)
        self.assertEqual(response.location, f"/employees/4?week={monday}")

        detail = self.client.get(f"/employees/4?week={monday}")
        self.assertIn("Morning", detail.text)
        self.assertEqual(self.rota(4), [(monday, "Morning")])

    def test_assignment_form_has_a_date_and_the_three_fixed_shifts(self) -> None:
        detail = self.client.get("/employees/4")
        self.assertIn('name="work_date"', detail.text)
        for name in ("Morning", "Afternoon", "Evening"):
            self.assertRegex(detail.text, rf'<option value="{name}"')
        self.assertIn("08:00 - 12:00", detail.text)
        self.assertIn("14:00 - 18:00", detail.text)
        self.assertIn("20:00 - 22:00", detail.text)
        # Custom shift creation is explicitly out of scope (URS 4.2).
        self.assertNotIn("Custom shift", detail.text)

    def test_one_employee_can_work_two_shifts_on_the_same_day(self) -> None:
        monday = self.week()[0]
        self.client.post("/employees/4/shift", {"work_date": monday, "shift_name": "Morning"})
        self.client.post("/employees/4/shift", {"work_date": monday, "shift_name": "Evening"})

        self.assertEqual(
            self.rota(4), [(monday, "Evening"), (monday, "Morning")]
        )
        detail = self.client.get(f"/employees/4?week={monday}")
        self.assertIn("pill--Morning", detail.text)
        self.assertIn("pill--Evening", detail.text)

    def test_the_same_date_and_shift_is_not_duplicated(self) -> None:
        monday = self.week()[0]
        for _ in range(3):
            self.client.post(
                "/employees/4/shift", {"work_date": monday, "shift_name": "Morning"}
            )
        self.assertEqual(self.rota(4), [(monday, "Morning")])

    def test_assignment_records_who_confirmed_it(self) -> None:
        monday = self.week()[0]
        self.client.post("/employees/4/shift", {"work_date": monday, "shift_name": "Afternoon"})
        detail = self.client.get(f"/employees/4?week={monday}")
        self.assertIn("Store Supervisor", detail.text)

    def test_removing_one_shift_of_a_day_keeps_the_other(self) -> None:
        wednesday = self.week()[2]
        # The seed data gives Li Wei a Morning and an Evening shift that day.
        self.assertEqual(
            sorted(self.rota(1)),
            sorted([(day, "Morning") for day in self.week()[:5]] + [(wednesday, "Evening")]),
        )

        response = self.client.post(
            "/employees/1/shift/remove",
            {"work_date": wednesday, "shift_name": "Evening"},
        )
        self.assertEqual(response.status, 303)
        self.assertEqual(self.rota(1), [(day, "Morning") for day in self.week()[:5]])

    def test_removing_an_entry_that_does_not_exist_changes_nothing(self) -> None:
        before = self.rota(4)
        response = self.client.post(
            "/employees/4/shift/remove",
            {"work_date": self.week()[0], "shift_name": "Evening"},
        )
        self.assertEqual(response.status, 303)
        self.assertEqual(self.rota(4), before)
        follow_up = self.client.get(f"/employees/4?week={self.week()[0]}")
        self.assertIn("There was no Evening shift", follow_up.text)

    def test_invalid_shift_value_changes_nothing(self) -> None:
        monday = self.week()[0]
        before = self.rota(1)
        response = self.client.post(
            "/employees/1/shift", {"work_date": monday, "shift_name": "Midnight"}
        )
        self.assertEqual(response.status, 303)
        self.assertEqual(self.rota(1), before)
        follow_up = self.client.get(f"/employees/1?week={monday}")
        self.assertIn("Please choose Morning, Afternoon or Evening", follow_up.text)

    def test_missing_or_invalid_date_is_refused(self) -> None:
        before = self.rota(1)
        for payload in ({"shift_name": "Morning"}, {"work_date": "2026-13-40", "shift_name": "Morning"}):
            with self.subTest(payload=payload):
                response = self.client.post("/employees/1/shift", payload)
                self.assertEqual(response.status, 303)
                self.assertEqual(self.rota(1), before)
        follow_up = self.client.get("/employees/1")
        self.assertIn("Please choose the working date", follow_up.text)

    def test_assigning_to_a_missing_employee_returns_to_the_overview(self) -> None:
        """URS Use Case 2, extension 1A."""
        response = self.client.post(
            "/employees/9999/shift",
            {"work_date": self.week()[0], "shift_name": "Morning"},
        )
        self.assertEqual(response.status, 303)
        self.assertEqual(response.location, "/")

        overview = self.client.get("/")
        self.assertIn("could not be found", overview.text)

    def test_detail_lists_the_whole_week(self) -> None:
        detail = self.client.get("/employees/1")
        for day in self.week()[:5]:
            with self.subTest(day=day):
                self.assertIn(f'name="work_date" value="{day}"', detail.text)
        self.assertIn("Rota for the week of", detail.text)
        self.assertIn("6 shift(s) planned", detail.text)

    def test_detail_offers_week_navigation(self) -> None:
        detail = self.client.get("/employees/1")
        self.assertIn("Previous week", detail.text)
        self.assertIn("Next week", detail.text)
        self.assertIn(f"week={self.week()[0]}", detail.text)

    def test_supervisor_cannot_edit_or_delete_the_employee(self) -> None:
        self.assertEqual(self.client.get("/employees/1/edit").status, 403)
        self.assertEqual(self.client.post("/employees/1/delete", {}).status, 403)


class StoreShiftOverviewTests(WeeklyTestCase):
    """FR08: the whole shop, in the shape each role needs."""

    def test_supervisor_view_is_grouped_by_day(self) -> None:
        client = self.sign_in("Supervisor")
        response = client.get("/shifts")
        self.assertEqual(response.status, 200)
        for weekday in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            with self.subTest(weekday=weekday):
                self.assertIn(f">{weekday}</span>", response.text)
        for shift_name in ("Morning", "Afternoon", "Evening"):
            self.assertIn(shift_name, response.text)
        # Every day has its own table with a shift column, even the empty weekend.
        self.assertEqual(response.text.count('class="roster-table__shift"'), 7)

    def test_supervisor_view_lists_who_works_when(self) -> None:
        client = self.sign_in("Supervisor")
        text = client.get("/shifts").text
        wednesday = self.week()[2]
        # Li Wei works Morning and Evening on Wednesday, Zhang Min Afternoon.
        for employee_id, name in ((1, "Li Wei"), (2, "Zhang Min"), (5, "Sun Jie")):
            with self.subTest(employee=name):
                self.assertIn(name, text)
                self.assertIn(f'href="/employees/{employee_id}?week={wednesday}"', text)
        self.assertIn("No one assigned", text)  # the weekend is still empty

    def test_supervisor_view_is_read_only(self) -> None:
        """URS section 6: shift-modification controls are hidden on that page."""
        client = self.sign_in("Supervisor")
        response = client.get("/shifts")
        self.assertNotIn('name="shift_name"', response.text)
        self.assertNotIn("Confirm shift assignment", response.text)
        self.assertNotIn('name="work_date"', response.text)
        self.assertIn("Read-only overview", response.text)

    def test_hr_view_is_grouped_by_employee(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts")
        self.assertEqual(response.status, 200)
        self.assertIn("5 employee(s) listed", response.text)
        self.assertIn("Week summary", response.text)
        for name in ("Li Wei", "Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertIn(name, response.text)
        self.assertNotIn('class="roster-table__shift"', response.text)

    def test_hr_view_shows_each_person_week_summary(self) -> None:
        client = self.sign_in("HR")
        text = client.get("/shifts").text
        self.assertIn("Morning, Evening", text)
        self.assertIn("pill--Unassigned", text)  # Wang Fang has no shifts

    def test_hr_can_filter_by_shift(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts?shift=Morning")
        self.assertIn("Li Wei", response.text)
        self.assertIn("Sun Jie", response.text)
        self.assertNotIn("Zhang Min", response.text)

    def test_hr_can_filter_by_employee_name(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts?q=Zhang")
        self.assertIn("Zhang Min", response.text)
        self.assertNotIn("Li Wei", response.text)

    def test_hr_can_filter_the_unassigned(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts?shift=Unassigned")
        self.assertIn("Wang Fang", response.text)
        self.assertNotIn("Li Wei", response.text)

    def test_hr_view_is_read_only(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts")
        self.assertEqual(response.status, 200)
        self.assertIn("Read-only overview", response.text)
        self.assertNotIn('name="shift_name"', response.text)
        self.assertNotIn('name="work_date"', response.text)

    def test_shift_counts_are_shown(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/shifts")
        self.assertIn("Shifts planned", response.text)
        self.assertIn("Employees", response.text)
        # 4 people work Monday to Friday, two of them twice on one day.
        self.assertIn('<span class="kpi__value">22</span>', response.text)

    def test_week_navigation_reaches_another_week(self) -> None:
        client = self.sign_in("Supervisor")
        previous = client.get(f"/shifts?week={repo.week_dates()[0]}")
        self.assertEqual(previous.status, 200)

        last_week = repo.week_dates("2026-01-05")[0]
        response = client.get(f"/shifts?week={last_week}")
        self.assertEqual(response.status, 200)
        self.assertIn("05 Jan 2026", response.text)
        self.assertIn("No one assigned", response.text)

    def test_assignment_is_visible_in_the_overview_afterwards(self) -> None:
        supervisor = self.sign_in("Supervisor")
        thursday = self.week()[3]
        supervisor.post(
            "/employees/4/shift", {"work_date": thursday, "shift_name": "Evening"}
        )
        overview = supervisor.get("/shifts")
        self.assertIn("Wang Fang", overview.text)
        self.assertEqual(self.rota(4), [(thursday, "Evening")])

    def test_empty_store_shows_placeholders(self) -> None:
        """URS Use Case 4, extension 1A."""
        for employee_id in range(1, 6):
            repo.delete_employee(self.db_path, employee_id)

        hr = self.sign_in("HR")
        response = hr.get("/shifts")
        self.assertEqual(response.status, 200)
        self.assertIn("No employee data available", response.text)

        supervisor = self.sign_in("Supervisor")
        roster = supervisor.get("/shifts")
        self.assertEqual(roster.status, 200)
        self.assertEqual(roster.text.count('class="roster-table__shift"'), 7)
        self.assertIn("No one assigned", roster.text)

    def test_statistics_can_be_moved_to_another_week(self) -> None:
        client = self.sign_in("HR")
        response = client.get("/statistics?week=2026-01-05")
        self.assertEqual(response.status, 200)
        self.assertIn("05 Jan 2026", response.text)
        self.assertIn('<span class="kpi__value">0</span>', response.text)


class OwnShiftViewTests(WeeklyTestCase):
    """FR07 for the Ordinary Employee role and URS Use Case 6."""

    def setUp(self) -> None:
        super().setUp()
        self.client = self.sign_in("Ordinary Employee")

    def test_timetable_has_three_shift_rows_and_seven_day_columns(self) -> None:
        response = self.client.get("/my-shifts")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.text.count("timetable__rowhead"), 3)
        self.assertEqual(response.text.count('scope="col" class="timetable__day'), 7)
        for weekday in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            self.assertIn(f">{weekday}</span>", response.text)

    def test_each_day_carries_its_date(self) -> None:
        text = self.client.get("/my-shifts").text
        for day in self.week():
            with self.subTest(day=day):
                self.assertIn(f'data-date="{day}"', text)

    def test_ticks_appear_exactly_on_the_days_worked(self) -> None:
        text = self.client.get("/my-shifts").text
        week = self.week()
        for index, day in enumerate(week):
            expected = "on" if index < 5 else "off"
            with self.subTest(day=day):
                self.assertEqual(
                    self.timetable_cell_status(text, day, "Morning"), expected
                )
        # No afternoon or weekend work in the demonstration rota.
        for day in week:
            self.assertEqual(self.timetable_cell_status(text, day, "Afternoon"), "off")

    def test_one_day_can_show_two_shifts(self) -> None:
        text = self.client.get("/my-shifts").text
        wednesday = self.week()[2]
        self.assertEqual(self.timetable_cell_status(text, wednesday, "Morning"), "on")
        self.assertEqual(self.timetable_cell_status(text, wednesday, "Evening"), "on")
        self.assertIn("6 shift(s) in this week", text)

    def test_employee_sees_only_their_own_schedule(self) -> None:
        response = self.client.get("/my-shifts")
        self.assertIn("Li Wei", response.text)
        # Other employees must not be disclosed to an Ordinary Employee.
        for other in ("Zhang Min", "Chen Hao", "Wang Fang", "Sun Jie"):
            self.assertNotIn(other, response.text)

    def test_week_navigation_links_are_present(self) -> None:
        text = self.client.get("/my-shifts").text
        self.assertIn("Previous week", text)
        self.assertIn("Next week", text)
        monday = date.fromisoformat(self.week()[0])
        previous = (monday - timedelta(days=7)).isoformat()
        following = (monday + timedelta(days=7)).isoformat()
        self.assertIn(f"/my-shifts?week={previous}", text)
        self.assertIn(f"/my-shifts?week={following}", text)

    def test_another_week_shows_an_empty_timetable(self) -> None:
        far_away = "2026-01-05"  # a Monday long before the seeded week
        response = self.client.get(f"/my-shifts?week={far_away}")
        self.assertEqual(response.status, 200)
        self.assertIn("You have no shifts scheduled in the week shown", response.text)
        self.assertEqual(self.timetable_cell_status(response.text, far_away, "Morning"), "off")

    def test_unreadable_week_parameter_shows_the_current_week(self) -> None:
        response = self.client.get("/my-shifts?week=not-a-date")
        self.assertEqual(response.status, 200)
        self.assertIn("6 shift(s) in this week", response.text)

    def test_placeholder_when_nothing_is_assigned(self) -> None:
        supervisor = self.sign_in("Supervisor")
        for day, shift_name in self.rota(1):
            supervisor.post(
                "/employees/1/shift/remove",
                {"work_date": day, "shift_name": shift_name},
            )

        response = self.client.get("/my-shifts")
        self.assertIn("You have not been assigned any shifts yet", response.text)
        self.assertEqual(self.timetable_cell_status(response.text, self.week()[0], "Morning"), "off")

    def test_home_page_shows_this_week_shifts(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("This week's shifts", response.text)
        self.assertIn("6 shift(s) planned", response.text)
        self.assertIn("Morning", response.text)

    def test_employee_cannot_read_the_store_overview(self) -> None:
        self.assertEqual(self.client.get("/shifts").status, 403)


class HrRotaPermissionTests(WeeklyTestCase):
    """FR10: only the Supervisor may change the rota."""

    def test_hr_may_not_add_or_remove_shifts(self) -> None:
        client = self.sign_in("HR")
        monday = self.week()[0]
        add = client.post(
            "/employees/4/shift", {"work_date": monday, "shift_name": "Morning"}
        )
        self.assertEqual(add.status, 403)
        remove = client.post(
            "/employees/1/shift/remove",
            {"work_date": self.week()[2], "shift_name": "Evening"},
        )
        self.assertEqual(remove.status, 403)
        # Nothing changed.
        self.assertEqual(self.rota(4), [])
        self.assertIn((self.week()[2], "Evening"), self.rota(1))


class WeekQueryTests(WeeklyTestCase):
    """The new repository queries behind the three views."""

    def test_employee_week_shifts_has_every_date(self) -> None:
        week = repo.employee_week_shifts(self.db_path, 1)
        self.assertEqual(sorted(week), sorted(self.week()))
        self.assertEqual(week[self.week()[0]], ["Morning"])
        self.assertEqual(week[self.week()[2]], ["Morning", "Evening"])
        self.assertEqual(week[self.week()[5]], [])

    def test_employee_week_shifts_of_an_empty_employee(self) -> None:
        week = repo.employee_week_shifts(self.db_path, 4)
        self.assertTrue(all(names == [] for names in week.values()))

    def test_day_roster_groups_the_three_shifts(self) -> None:
        days = repo.day_roster(self.db_path)
        self.assertEqual(len(days), 7)
        wednesday = days[2]
        self.assertEqual(wednesday["work_date"], self.week()[2])
        self.assertEqual([group["shift_name"] for group in wednesday["groups"]],
                         ["Morning", "Afternoon", "Evening"])
        self.assertEqual(
            [person["name"] for person in wednesday["groups"][0]["employees"]],
            ["Li Wei", "Sun Jie"],
        )
        self.assertEqual(
            [person["name"] for person in wednesday["groups"][2]["employees"]],
            ["Chen Hao", "Li Wei"],
        )
        # Saturday is empty but still reported.
        self.assertEqual(days[5]["total"], 0)

    def test_employee_roster_lists_every_employee(self) -> None:
        roster = repo.employee_roster(self.db_path)
        self.assertEqual(len(roster), 5)
        by_name = {person["name"]: person for person in roster}
        self.assertEqual(by_name["Li Wei"]["shift_label"], "Morning, Evening")
        self.assertEqual(by_name["Li Wei"]["shift_count"], 6)
        self.assertEqual(by_name["Wang Fang"]["shift_label"], "")
        self.assertEqual(by_name["Wang Fang"]["shift_count"], 0)
        self.assertEqual(by_name["Li Wei"]["days"][self.week()[0]], ["Morning"])

    def test_week_summary_counts(self) -> None:
        counts = repo.week_summary_counts(self.db_path)
        self.assertEqual(counts["Morning"], 10)   # 5 days x 2 people
        self.assertEqual(counts["Afternoon"], 5)  # Zhang Min, Monday to Friday
        self.assertEqual(counts["Evening"], 7)    # Chen Hao 5 + two extra shifts
        self.assertEqual(counts["Total"], 22)

    def test_employee_counts_per_shift_counts_people(self) -> None:
        """The distribution table counts people, not shift slots."""
        people = repo.employee_counts_per_shift(self.db_path)
        self.assertEqual(people["Morning"], 2)     # Li Wei, Sun Jie
        self.assertEqual(people["Afternoon"], 1)   # Zhang Min
        self.assertEqual(people["Evening"], 3)     # Chen Hao, Li Wei, Sun Jie
        self.assertEqual(people["Unassigned"], 1)  # Wang Fang

    def test_unassigned_count(self) -> None:
        self.assertEqual(repo.count_employees_without_week_shifts(self.db_path), 1)

    def test_search_employees_summarises_the_week(self) -> None:
        rows = repo.search_employees(self.db_path, week_start=self.week()[0])
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(by_name["Li Wei"]["shift_name"], "Morning, Evening")
        self.assertEqual(by_name["Li Wei"]["shift_count"], 6)
        self.assertIsNone(by_name["Wang Fang"]["shift_name"])

    def test_assign_and_clear_are_per_day_and_shift(self) -> None:
        monday = self.week()[0]
        repo.assign_shift(self.db_path, 4, monday, "Morning", "Tester")
        repo.assign_shift(self.db_path, 4, monday, "Evening", "Tester")
        self.assertEqual(
            repo.employee_week_shifts(self.db_path, 4)[monday], ["Morning", "Evening"]
        )
        self.assertTrue(repo.clear_shift(self.db_path, 4, monday, "Morning"))
        self.assertEqual(repo.employee_week_shifts(self.db_path, 4)[monday], ["Evening"])
        self.assertFalse(repo.clear_shift(self.db_path, 4, monday, "Morning"))


class SchemaMigrationTests(WeeklyTestCase):
    """The pre-weekly ``shifts`` table is rebuilt without losing people."""

    def _replace_with_old_schema(self) -> None:
        connection = sqlite3.connect(self.application.db_path)
        try:
            connection.executescript(
                """
                DROP TABLE shifts;
                CREATE TABLE shifts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                    shift_name  TEXT    NOT NULL CHECK (shift_name IN ('Morning', 'Afternoon', 'Evening')),
                    assigned_at TEXT    NOT NULL,
                    assigned_by TEXT    NOT NULL DEFAULT ''
                );
                CREATE UNIQUE INDEX idx_shifts_employee ON shifts(employee_id);
                """
            )
            connection.execute(
                "INSERT INTO shifts (employee_id, shift_name, assigned_at, assigned_by) "
                "VALUES (4, 'Evening', '2026-10-01 09:00:00', 'Old version')"
            )
            connection.commit()
        finally:
            connection.close()

    def test_old_table_is_rebuilt_and_the_rota_is_regenerated(self) -> None:
        self._replace_with_old_schema()

        restarted = Application(db_path=self.application.db_path, base_dir=PROJECT_ROOT)
        self.assertFalse(restarted.seeded_now, "employee data must not be reseeded")

        # The old dated-less row is gone; the demonstration week is back.
        self.assertEqual(self.rota(4), [])
        self.assertGreater(len(self.rota(1)), 0)
        self.assertEqual(len(self.rota(1)), 6)
        self.assertEqual(repo.count_employees(self.db_path), 5)

        # Accounts still work after the upgrade.
        client = self.sign_in("Supervisor")
        self.assertEqual(client.get("/shifts").status, 200)

    def test_initialize_reports_the_rebuild(self) -> None:
        self._replace_with_old_schema()
        self.assertTrue(initialize(self.application.db_path))

    def test_current_schema_is_not_rebuilt(self) -> None:
        before = self.rota(1)
        self.assertFalse(initialize(self.application.db_path))
        self.assertEqual(self.rota(1), before)


if __name__ == "__main__":
    unittest.main()
