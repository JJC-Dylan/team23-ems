"""A minimal Jinja2-style template engine built on the standard library.

The project must run in PyCharm without installing anything, so instead of
depending on Jinja2 this module compiles ``.html`` templates into Python
source and caches the resulting code objects.

Supported syntax
----------------
``{{ expression }}``
    Output an expression, HTML-escaped by default.
``{{ expression | safe }}``
    Output without escaping (used for pre-built markup).
``{% if %}`` / ``{% elif %}`` / ``{% else %}`` / ``{% endif %}``
``{% for item in sequence %}`` / ``{% else %}`` / ``{% endfor %}``
    ``loop.index``, ``loop.index0``, ``loop.first``, ``loop.last`` and
    ``loop.length`` are available inside the body.
``{% extends 'base.html' %}`` with ``{% block name %} ... {% endblock %}``
    Child blocks override parent blocks; ``{{ super() }}`` renders the parent
    version of the block that is currently being written.
``{% include 'partial.html' %}``
    Render another template with the current scope.
``{# comment #}``
    Discarded.

Bare names in an expression are looked up in the render context first. Code
that is not a plain identifier falls back to Python's built-ins, so helper
calls such as ``len(items)`` keep working while a context key named ``id`` or
``type`` can never shadow a builtin needed by the generated code.

Template problems raise :class:`TemplateError` naming the template, so a
broken page reports something readable instead of a bare traceback.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

from .htmlpages import escape_html

TOKEN_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})", re.DOTALL)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BLOCK_TAG_RE = re.compile(r"block\s+([A-Za-z_][A-Za-z0-9_]*)")
END_BLOCK_TAG_RE = re.compile(r"endblock\b")
EXTENDS_RE = re.compile(r"extends\s+['\"]([^'\"]+)['\"]")
SUPER_RE = re.compile(r"super\s*\(\s*\)")
LOOP_RE = re.compile(r"\bloop\b")


class TemplateError(Exception):
    """Raised when a template cannot be parsed or rendered."""


class _LoopInfo:
    """Exposes ``loop.index`` and friends inside a ``{% for %}`` body."""

    __slots__ = ("index0", "length")

    def __init__(self, index0: int, length: int) -> None:
        self.index0 = index0
        self.length = length

    @property
    def index(self) -> int:
        return self.index0 + 1

    @property
    def first(self) -> bool:
        return self.index0 == 0

    @property
    def last(self) -> bool:
        return self.index0 == self.length - 1


class _MISSING_TYPE:
    """Sentinel distinguishing "absent" from a stored ``None``."""


_MISSING = _MISSING_TYPE()

#: A name that only ever exists inside generated template code.
_RENDER_MARKER = "__tpl_marker__"


def _render_locals() -> dict[str, Any]:
    """Locals of the generated render function currently executing.

    The helper walks outwards until it finds the frame that owns the template
    marker, so it works from inside blocks, includes and nested calls while
    ignoring intermediate helper frames.
    """
    frame = sys._getframe(1)  # noqa: SLF001 - caller is generated template code
    while frame is not None:
        if _RENDER_MARKER in frame.f_locals:
            return frame.f_locals
        frame = frame.f_back
    return {}


#: Filters usable after ``|`` in an expression.
FILTERS: dict[str, Any] = {
    "safe": lambda value: value if isinstance(value, str) else str(value),
    "length": len,
    "count": len,
    "upper": lambda value: str(value).upper(),
    "lower": lambda value: str(value).lower(),
    "trim": lambda value: str(value).strip(),
    "default": lambda value, fallback="": fallback if value in ("", None) else value,
}


def _split_filters(expression: str) -> tuple[str, list[tuple[str, str | None]]]:
    """Split ``value | filter | other(arg)`` into its base and filter list."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for character in expression:
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth -= 1
        if character == "|" and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(character)
    parts.append("".join(current))

    base = parts[0].strip()
    filters: list[tuple[str, str | None]] = []
    for raw in parts[1:]:
        spec = raw.strip()
        if "(" in spec and spec.endswith(")"):
            name, argument = spec.split("(", 1)
            filters.append((name.strip(), argument[:-1].strip()))
        else:
            filters.append((spec, None))
    return base, filters


class _AttrDict(dict):
    """A mapping that also answers attribute access.

    Templates should not need to know whether a record arrived as a mapping or
    as an object, so ``employee.name`` works for both (this mirrors the
    behaviour templates expect).
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __str__(self) -> str:
        return dict.__str__(self)


class _ExpressionScope(dict):
    """Name resolver for non-trivial expressions: locals first, then context.

    Context values are wrapped so that dotted access works for records too.
    """

    def __init__(self, scope: dict[str, Any], locals_: dict[str, Any]) -> None:
        super().__init__({key: _wrap(value) for key, value in scope.items()})
        self._locals = locals_

    def __missing__(self, key: str) -> Any:
        if key in self._locals:
            return _wrap(self._locals[key])
        if key in _BUILTINS:
            return _BUILTINS[key]
        return ""


def _wrap(value: Any) -> Any:
    """Expose mappings through attribute access as well as item access.

    Both plain dictionaries and ``sqlite3.Row`` records answer item access, so
    a template can write ``employee.name`` regardless of how the query layer
    handed the record over.
    """
    if type(value) is dict:
        return _AttrDict(value)
    if hasattr(value, "keys") and hasattr(value, "__getitem__") and not isinstance(value, type):
        try:
            return _AttrDict({key: value[key] for key in value.keys()})
        except (TypeError, KeyError, IndexError):
            return value
    return value


def _lookup(expression: str, scope: dict[str, Any]) -> Any:
    """Evaluate a template expression against locals and the render context.

    Loop variables live as Python locals inside the generated render function,
    so they are checked first. Undefined names render as an empty string rather
    than aborting the page: a missing optional value must never break a screen
    the user needs. Support for ``|`` filters is applied last.
    """
    base, filters = _split_filters(expression)
    value = _evaluate(base, scope)
    for name, argument in filters:
        function = FILTERS.get(name)
        if function is None:
            raise TemplateError(f"{expression!r}: unknown filter {name!r}")
        try:
            value = function(value, argument) if argument is not None else function(value)
        except (TypeError, ValueError):
            value = ""
    return value


def _evaluate(expression: str, scope: dict[str, Any]) -> Any:
    """Resolve one filter-free expression."""
    if IDENTIFIER_RE.match(expression):
        local = _render_locals().get(expression, _MISSING)
        if local is not _MISSING:
            return _wrap(local)
        if expression in scope:
            return _wrap(scope[expression])
        return _BUILTINS.get(expression, "")
    try:
        return eval(  # noqa: S307 - expressions come from project-owned templates
            expression, {"__builtins__": _BUILTINS}, _ExpressionScope(scope, _render_locals())
        )
    except (NameError, KeyError, IndexError, TypeError):
        return ""
    except AttributeError as error:
        # A missing optional attribute must not break the page; the developer
        # can set EMS_TEMPLATE_DEBUG to see which expression was unresolved.
        if os.environ.get("EMS_TEMPLATE_DEBUG"):
            print(f"[tpl] lookup failed for {expression!r}: {error}")
        return ""
    except SyntaxError as error:
        raise TemplateError(f"could not evaluate template expression {expression!r}") from error


class _MISSING_TYPE:
    """Sentinel distinguishing "absent" from a stored ``None``."""


_MISSING = _MISSING_TYPE()


_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


class Template:
    """One compiled template file."""

    def __init__(
        self,
        name: str,
        source: str,
        engine: "TemplateEngine",
        super_callback: "Any | None" = None,
    ) -> None:
        self.name = name
        self.engine = engine
        #: Renders the next definition of the block currently being written.
        self.super_callback = super_callback
        self.blocks: dict[str, str] = {}
        body = self._extract_blocks(source)
        self.extends = self._find_extends(body)
        code = self._compile(self._strip_extends(body))
        self._namespace: dict[str, Any] = {}
        try:
            exec(code, self._namespace)  # noqa: S102 - templates are project-owned files
        except SyntaxError as error:  # pragma: no cover - development aid only
            raise TemplateError(
                f"{self.name}: generated code is invalid "
                f"({error.msg} at generated line {error.lineno})\n"
                + "\n".join(
                    f"{number:>4}: {text}"
                    for number, text in enumerate(code.splitlines(), start=1)
                )
            ) from error

    def _run_body(
        self,
        context: dict[str, Any],
        render_block: "Any | None" = None,
        super_callback: "Any | None" = None,
    ) -> str:
        """Execute this template's own compiled body (no inheritance applied).

        ``render_block`` resolves a ``{% block %}`` placeholder in the body; the
        inheritance driver passes one that knows every definition of the block,
        so a parent layout fills its slots with the most derived content.
        """
        if render_block is None:
            render_block = lambda name: ""  # noqa: E731 - empty standalone body
        namespace = dict(self._namespace)
        try:
            return namespace["render"](
                context,
                escape_html,
                _LoopInfo,
                bool,
                _lookup,
                render_block,
                lambda name: self.engine.render(name, context),
                super_callback or (lambda: ""),
            )
        except TemplateError:
            raise
        except Exception as error:  # pragma: no cover - surfaced as a friendly page
            raise TemplateError(f"{self.name}: {type(error).__name__}: {error}") from error

    def _run(self, context: dict[str, Any]) -> str:
        """Render this template's body, with its own blocks and no parent."""
        return self._run_body(context, lambda name: self._render_block_here(name, context))

    def _render_block_here(self, name: str, context: dict[str, Any]) -> str:
        body = self.blocks.get(name)
        if body is None:
            return ""
        block_template = Template(f"{self.name}#block:{name}", body, self.engine)
        return block_template._run_body(context)

    # -- parsing -----------------------------------------------------------

    def _extract_blocks(self, source: str) -> str:
        """Replace each ``{% block %}`` region with a placeholder call."""
        out: list[str] = []
        position = 0
        while True:
            match = BLOCK_TAG_RE.search(source, position)
            if match is None:
                out.append(source[position:])
                break
            tag_start = source.rfind("{%", position, match.start())
            if tag_start == -1:
                raise TemplateError(f"{self.name}: malformed block tag near '{match.group(0)}'")
            out.append(source[position:tag_start])
            body_start = source.find("%}", match.end()) + 2
            depth = 1
            cursor = body_start
            body_end = -1
            end_tag_close = -1
            while depth > 0:
                next_open = source.find("{%", cursor)
                if next_open == -1:
                    raise TemplateError(f"{self.name}: block '{match.group(1)}' is never closed")
                next_close = source.find("%}", next_open)
                if next_close == -1:
                    raise TemplateError(f"{self.name}: unterminated tag in block '{match.group(1)}'")
                tag = source[next_open + 2 : next_close].strip()
                if BLOCK_TAG_RE.match(tag):
                    depth += 1
                elif END_BLOCK_TAG_RE.match(tag):
                    depth -= 1
                    if depth == 0:
                        body_end = next_open
                        end_tag_close = next_close + 2
                        break
                cursor = next_close + 2
            name = match.group(1)
            self.blocks[name] = self._extract_blocks(source[body_start:body_end])
            out.append(f"{{% __block__ {name} %}}")
            position = end_tag_close
        return "".join(out)

    def _find_extends(self, body: str) -> str | None:
        match = EXTENDS_RE.search(body)
        return match.group(1) if match else None

    def _strip_extends(self, body: str) -> str:
        return EXTENDS_RE.sub("", body)

    # -- code generation ---------------------------------------------------

    def _parse(self, code: str, depth: int) -> list[str]:
        """Translate one template fragment into Python lines.

        ``depth`` is the current Python indentation level; opening tags such as
        ``{% if %}`` and ``{% for %}`` increase it for the text that follows and
        their closing tags decrease it again. ``block_stack`` records the kind
        and indentation of every open construct so ``{% else %}`` can be placed
        correctly in either an ``if`` or a ``for``.
        """
        lines: list[str] = []
        position = 0
        block_stack: list[list[Any]] = []  # [kind, opening depth, else already seen]
        for token in TOKEN_RE.finditer(code):
            lines.extend(self._text_lines(code[position : token.start()], "\t" * depth))
            position = token.end()
            raw = token.group(0)
            if raw.startswith("{#"):
                continue
            if raw.startswith("{{"):
                lines.extend(self._expression_lines(raw[2:-2].strip(), "\t" * depth))
                continue
            emitted, depth = self._tag_lines(
                raw[2:-2].strip(), depth, block_stack
            )
            lines.extend(emitted)
        lines.extend(self._text_lines(code[position:], "\t" * depth))
        return lines

    @staticmethod
    def _text_lines(text: str, indent: str) -> list[str]:
        return [f"{indent}__out__.append({line!r})" for line in text.split("\n")]

    def _expression_lines(self, expression: str, indent: str) -> list[str]:
        if SUPER_RE.fullmatch(expression.strip()):
            # ``{{ super() }}``: inline the next definition of this block.
            return [f"{indent}__out__.append(__super__())"]
        if expression.rstrip().endswith("| safe"):
            # Markup that is already escaped by its producer.
            return [f"{indent}__out__.append(str(__lookup({expression!r}, __ctx)))"]
        return [f"{indent}__out__.append(__escape(__lookup({expression!r}, __ctx)))"]

    def _tag_lines(
        self, tag: str, depth: int, block_stack: list[list[Any]]
    ) -> tuple[list[str], int]:
        """Emit the code for one tag and report the new indentation depth."""
        if not tag:
            # Left behind when ``{% extends %}`` is removed from a template body.
            return [], depth

        if tag.startswith("if "):
            condition = self._condition(tag[3:].strip())
            block_stack.append(["if", depth, False])
            indent = "\t" * depth
            return [f"{indent}if {condition}:", f"{indent}\tpass"], depth + 1

        if tag.startswith("elif "):
            kind, outer, _ = self._current_block(block_stack, "elif")
            if kind != "if":
                raise TemplateError(f"{self.name}: '{{% elif %}}' outside an if block")
            condition = self._condition(tag[5:].strip())
            indent = "\t" * outer
            return [f"{indent}elif {condition}:", f"{indent}\tpass"], depth

        if tag == "else":
            kind, outer, seen = self._current_block(block_stack, "else")
            if seen:
                raise TemplateError(f"{self.name}: two else branches in one block")
            block_stack[-1][2] = True
            indent = "\t" * outer
            if kind == "for":
                # Python's ``for ... else`` runs exactly when the loop was empty,
                # which is the behaviour a template's else branch expects.
                return [f"{indent}else:", f"{indent}\tpass"], outer + 1
            return [f"{indent}else:", f"{indent}\tpass"], depth

        if tag == "endif":
            kind, outer, _ = self._pop_block(block_stack, "endif")
            if kind != "if":
                raise TemplateError(f"{self.name}: '{{% endif %}}' closes a for block")
            return [], outer

        if tag.startswith("for "):
            spec = tag[4:].strip()
            if " in " not in spec:
                raise TemplateError(f"{self.name}: malformed for tag '{{% {tag} %}}'")
            target, iterable = spec.split(" in ", 1)
            target = target.strip()
            # Support both a single name and tuple unpacking such as
            # ``{% for key, value in mapping.items() %}``.
            target_names = [part.strip() for part in target.split(",")]
            if not target_names or not all(
                IDENTIFIER_RE.match(part) for part in target_names
            ):
                raise TemplateError(f"{self.name}: unsupported loop target '{target}'")
            indent = "\t" * depth
            block_stack.append(["for", depth, False])
            return (
                [
                    f"{indent}__items = list(__lookup({iterable.strip()!r}, __ctx))",
                    f"{indent}for __i, ({target}) in enumerate(__items):",
                    f"{indent}\tloop = __loop(__i, len(__items))",
                    f"{indent}\tpass",
                ],
                depth + 1,
            )

        if tag == "endfor":
            kind, outer, seen = self._pop_block(block_stack, "endfor")
            if kind != "for":
                raise TemplateError(f"{self.name}: '{{% endfor %}}' closes an if block")
            indent = "\t" * outer
            # A for/else pair may already have been written by ``{% else %}``.
            empty_branch = [] if seen else [f"{indent}else:", f"{indent}\tpass"]
            return empty_branch, outer

        if tag.startswith("include "):
            include_name = tag[len("include ") :].strip().strip("'\"")
            indent = "\t" * depth
            return [f"{indent}__out__.append(__include({include_name!r}))"], depth

        if tag.startswith("__block__ "):
            name = tag.split(" ", 1)[1].strip()
            indent = "\t" * depth
            return [f"{indent}__out__.append(__block({name!r}))"], depth

        raise TemplateError(f"{self.name}: unsupported template tag '{{% {tag} %}}'")

    def _current_block(
        self, block_stack: list[list[Any]], tag: str
    ) -> tuple[str, int, bool]:
        if not block_stack:
            raise TemplateError(f"{self.name}: '{{% {tag} %}}' without an open block")
        kind, outer, seen = block_stack[-1]
        return kind, outer, seen

    def _pop_block(
        self, block_stack: list[list[Any]], tag: str
    ) -> tuple[str, int, bool]:
        if not block_stack:
            raise TemplateError(f"{self.name}: '{{% {tag} %}}' without an open block")
        kind, outer, seen = block_stack.pop()
        return kind, outer, seen

    @staticmethod
    def _condition(expression: str) -> str:
        return f"__truth(__lookup({expression.strip()!r}, __ctx))"

    def _compile(self, body: str) -> str:
        lines = [
            "def render(__ctx, __escape, __loop, __truth, __lookup, __block, __include, __super__):",
            f"\t{_RENDER_MARKER} = True",
            "\t__out__ = []",
        ]
        lines.extend(self._parse(body, depth=1))
        lines.append("\treturn ''.join(__out__)")
        return "\n".join(lines)

    # -- rendering ---------------------------------------------------------

    def render(self, context: dict[str, Any]) -> str:
        """Render this template with inheritance applied."""
        return self._render(context)

    def _chain(self) -> list["Template"]:
        """Templates ordered root-first: the base layout, then this template.

        A template's ``{% block %}`` definitions override the same names in
        anything earlier in the chain.
        """
        parent_names: list[str] = []
        cursor = self
        while cursor is not None and cursor.extends:
            if cursor.extends in parent_names:
                raise TemplateError(f"{self.name}: template inheritance forms a loop")
            parent_names.append(cursor.extends)
            cursor = self.engine.get(cursor.extends)
        # Root-most first, so the most derived template's blocks win.
        parent_names.reverse()
        chain = [self.engine.get(name) for name in parent_names]
        chain.append(self)
        return chain

    @staticmethod
    def _definitions(chain: list["Template"]) -> dict[str, list[tuple[str, str]]]:
        """Map each block name to its definitions, most derived template first.

        Index 0 is therefore the definition that wins, and ``{{ super() }}``
        walks towards the end of the list to reach the inherited one.
        """
        definitions: dict[str, list[tuple[str, str]]] = {}
        for template in chain:
            for name, body in template.blocks.items():
                definitions.setdefault(name, []).insert(0, (template.name, body))
        return definitions

    def _render(self, context: dict[str, Any]) -> str:
        """Render this template, resolving block inheritance through the engine.

        The outermost parent supplies the layout; each ``{% block %}`` in it is
        filled by the most derived definition, and ``{{ super() }}`` walks one
        definition further towards the parent.
        """
        chain = self._chain()
        definitions = self._definitions(chain)
        rendered_cache: dict[str, str] = {}

        def render_block(name: str, index: int) -> str:
            if index == 0 and name in rendered_cache:
                return rendered_cache[name]
            found = definitions.get(name)
            if found is None or index >= len(found):
                return ""
            owner, body = found[index]
            block_template = Template(f"{owner}#block:{name}", body, self.engine)
            result = block_template._run_body(
                context,
                None,
                lambda: render_block(name, index + 1),
            )
            if index == 0:
                rendered_cache[name] = result
            return result

        layout = chain[0]
        return layout._run_body(context, lambda name: render_block(name, 0))


class TemplateEngine:
    """Loads, compiles and caches templates from a directory."""

    def __init__(self, directory: str) -> None:
        self.directory = os.path.abspath(directory)
        self._cache: dict[str, Template] = {}

    def _path(self, name: str) -> str:
        candidate = os.path.abspath(os.path.join(self.directory, name))
        if candidate != self.directory and not candidate.startswith(self.directory + os.sep):
            raise TemplateError(f"template '{name}' escapes the template directory")
        return candidate

    def source(self, name: str) -> str:
        try:
            with open(self._path(name), "r", encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError as error:
            raise TemplateError(f"template not found: {name}") from error

    def get(self, name: str) -> Template:
        template = self._cache.get(name)
        if template is None:
            template = Template(name, self.source(name), self)
            self._cache[name] = template
        return template

    def render(self, name: str, context: dict[str, Any]) -> str:
        return self.get(name).render(context)

    def clear(self) -> None:
        """Drop the compiled cache; used by tests and development reloads."""
        self._cache.clear()
