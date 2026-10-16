"""Tests for the small template engine (inheritance, escaping, loops)."""

from __future__ import annotations

import os
import tempfile
import unittest

from tests.base import PROJECT_ROOT

from app.templateengine import TemplateEngine, TemplateError


class TemplateEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = TemplateEngine(os.path.join(PROJECT_ROOT, "templates"))

    def test_variable_is_html_escaped(self) -> None:
        markup = self.engine.render("error.html", {"status": 400, "error_title": "<b>x</b>", "error_message": "a & b", "current_user": None, "flash_messages": [], "role_slug": str, "shift_slug": str, "app_version": "t", "active_sessions": 1, "path": "/", "shift_names": (), "role_descriptions": {}})
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", markup)
        self.assertIn("a &amp; b", markup)

    def test_inheritance_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "base.html"), "w", encoding="utf-8") as handle:
                handle.write("<html><body>{% block content %}base-default{% endblock %}</body></html>")
            with open(os.path.join(directory, "child.html"), "w", encoding="utf-8") as handle:
                handle.write(
                    "{% extends 'base.html' %}"
                    "{% block content %}child-content{% endblock %}"
                )
            engine = TemplateEngine(directory)
            markup = engine.render("child.html", {})
            self.assertIn("<html><body>", markup)
            self.assertIn("child-content", markup)
            self.assertNotIn("base-default", markup)

    def test_super_renders_the_parent_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "base.html"), "w", encoding="utf-8") as handle:
                handle.write("{% block content %}parent{% endblock %}")
            with open(os.path.join(directory, "child.html"), "w", encoding="utf-8") as handle:
                handle.write(
                    "{% extends 'base.html' %}"
                    "{% block content %}child+{{ super() }}{% endblock %}"
                )
            engine = TemplateEngine(directory)
            self.assertEqual(engine.render("child.html", {}), "child+parent")

    def test_loop_metadata_and_conditionals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "loop.html"), "w", encoding="utf-8") as handle:
                handle.write(
                    "{% for item in items %}"
                    "{{ loop.index }}:{{ item }}{% if not loop.last %},{% endif %}"
                    "{% endfor %}"
                )
            engine = TemplateEngine(directory)
            self.assertEqual(engine.render("loop.html", {"items": ["a", "b", "c"]}), "1:a,2:b,3:c")

    def test_for_else_branch_on_empty_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "empty.html"), "w", encoding="utf-8") as handle:
                handle.write("{% for item in items %}{{ item }}{% else %}none{% endfor %}")
            engine = TemplateEngine(directory)
            self.assertEqual(engine.render("empty.html", {"items": []}), "none")

    def test_undefined_name_renders_blank_instead_of_failing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "missing.html"), "w", encoding="utf-8") as handle:
                handle.write("before[{{ nope }}]after")
            engine = TemplateEngine(directory)
            self.assertEqual(engine.render("missing.html", {}), "before[]after")

    def test_builtin_calls_still_work_through_the_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "count.html"), "w", encoding="utf-8") as handle:
                handle.write("{{ len(items) }}")
            engine = TemplateEngine(directory)
            self.assertEqual(engine.render("count.html", {"items": [1, 2, 3]}), "3")

    def test_missing_template_raises_a_named_error(self) -> None:
        with self.assertRaises(TemplateError) as context:
            self.engine.render("does-not-exist.html", {})
        self.assertIn("does-not-exist.html", str(context.exception))

    def test_template_cannot_escape_its_directory(self) -> None:
        with self.assertRaises(TemplateError):
            self.engine.render("../app.py", {})

    def test_unclosed_block_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "broken.html"), "w", encoding="utf-8") as handle:
                handle.write("{% block content %}never closed")
            engine = TemplateEngine(directory)
            with self.assertRaises(TemplateError):
                engine.get("broken.html")


if __name__ == "__main__":
    unittest.main()
