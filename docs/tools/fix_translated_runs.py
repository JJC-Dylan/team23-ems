"""Restore run formatting lost by translate_docx.py's write-back.

translate_docx.py puts the whole translated string into the *first* run of a
paragraph, even when that first run is an empty placeholder that carries
different character formatting than the run that held the original text.
This script copies the rPr of the source paragraph's first text-bearing run
onto the translated text run, so the translation inherits the formatting of
the text it replaces. Paragraph styles, tables and everything else are left
untouched.
"""

from __future__ import annotations

import copy
import sys

from docx import Document
from docx.table import Table


def unique_cells(table: Table):
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            tc = cell._tc
            if tc in seen:
                continue
            seen.add(tc)
            yield cell


def iter_paragraphs(document: Document):
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, document)
        elif tag == "tbl":
            table = Table(child, document)
            for cell in unique_cells(table):
                for paragraph in cell.paragraphs:
                    yield paragraph


def first_text_run(paragraph):
    for run in paragraph.runs:
        if run.text.strip():
            return run
    return None


def main(source: str, target: str, out_path: str | None = None) -> int:
    src = Document(source)
    out = Document(target)
    pairs = list(zip(iter_paragraphs(src), iter_paragraphs(out)))
    fixed = 0
    for sp, op in pairs:
        if not sp.text.strip():
            continue
        sr = first_text_run(sp)
        orun = first_text_run(op)
        if sr is None or orun is None:
            continue
        sr_pr = sr._element.rPr
        if sr_pr is None:
            continue
        run_element = orun._element
        existing = run_element.rPr
        if existing is not None:
            run_element.remove(existing)
        # w:rPr must be the first child of w:r
        run_element.insert(0, copy.deepcopy(sr_pr))
        fixed += 1
    destination = out_path or target
    out.save(destination)
    print(f"restored run formatting on {fixed} paragraphs -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
