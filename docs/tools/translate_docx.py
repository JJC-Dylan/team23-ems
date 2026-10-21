"""Extract translatable text from a DOCX and write a translation back.

Two modes, so the translation can be produced separately from the rewrite:

    python docs/tools/translate_docx.py extract  input.docx  strings.json
    python docs/tools/translate_docx.py apply   input.docx  strings.json  zh.json  output.docx

The extractor emits a JSON list of strings in document order (paragraphs first,
then table cells, deduplicating merged cells). ``zh.json`` must be a JSON list
of the same length; ``apply`` writes each translated string into the first run
of the paragraph, keeping that run's formatting, the paragraph style, the
alignment, the tables and everything else untouched.
"""

from __future__ import annotations

import json
import sys

from docx import Document
from docx.table import Table

# Text that carries no meaning to translate.
SKIP_IF_ALREADY_EMPTY = True


def _unique_cells(table: Table):
    """Yield each cell once, skipping the duplicates produced by merged cells.

    The key is the underlying ``tc`` XML element, not ``id()`` of the Python
    proxy: proxies are created on demand and their ids are reused, which would
    make this skip unrelated cells.
    """
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            tc = cell._tc
            if tc in seen:
                continue
            seen.add(tc)
            yield cell


def iter_paragraphs_ordered(document: Document):
    """Yield every paragraph in document order, including those inside tables."""
    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph

            yield Paragraph(child, document)
        elif tag == "tbl":
            table = Table(child, document)
            for cell in _unique_cells(table):
                for paragraph in cell.paragraphs:
                    yield paragraph


def collect_strings(document: Document) -> list[str]:
    strings: list[str] = []
    for paragraph in iter_paragraphs_ordered(document):
        text = paragraph.text
        if text.strip():
            strings.append(text)
    return strings


def write_back(document: Document, translations: list[str]) -> int:
    """Replace each non-empty paragraph with its translation, keeping formatting."""
    index = 0
    changed = 0
    for paragraph in iter_paragraphs_ordered(document):
        if not paragraph.text.strip():
            continue
        if index >= len(translations):
            raise SystemExit(
                f"not enough translations: needed at least {index + 1}, got {len(translations)}"
            )
        new_text = translations[index]
        index += 1
        if new_text == paragraph.text:
            continue

        runs = paragraph.runs
        if not runs:
            paragraph.add_run(new_text)
            changed += 1
            continue

        # Put the whole translation in the first run (keeping its character
        # formatting) and blank the others; this keeps the paragraph style,
        # alignment and the table layout intact.
        runs[0].text = new_text
        for run in runs[1:]:
            run.text = ""
        changed += 1
    return changed


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    mode = argv[1]

    if mode == "extract":
        if len(argv) != 4:
            print("usage: extract input.docx strings.json")
            return 2
        source, out = argv[2], argv[3]
        document = Document(source)
        strings = collect_strings(document)
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(strings, handle, ensure_ascii=False, indent=1)
        print(f"extracted {len(strings)} strings -> {out}")
        total_chars = sum(len(s) for s in strings)
        print(f"total characters: {total_chars}")
        return 0

    if mode == "apply":
        if len(argv) != 6:
            print("usage: apply input.docx strings.json zh.json output.docx")
            return 2
        source, strings_path, zh_path, out = argv[2], argv[3], argv[4], argv[5]
        document = Document(source)
        with open(strings_path, encoding="utf-8") as handle:
            original = json.load(handle)
        with open(zh_path, encoding="utf-8") as handle:
            translations = json.load(handle)
        if len(original) != len(translations):
            raise SystemExit(
                f"length mismatch: {len(original)} source strings vs "
                f"{len(translations)} translations"
            )
        changed = write_back(document, translations)
        document.save(out)
        print(f"rewrote {changed} paragraphs -> {out}")
        return 0

    print(f"unknown mode: {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
