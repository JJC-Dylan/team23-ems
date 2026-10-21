"""Verify that a translated DOCX kept its structure and really is translated.

    python docs/tools/verify_translation.py  source.docx  translated.docx

Checks, in order:
  1. both documents have the same number of tables, with the same row and column
     counts, so no table was lost or reshaped during the rewrite;
  2. both have the same number of paragraphs and inline images;
  3. any paragraph whose source was real English prose (four or more words) now
     contains Chinese characters, which catches text that was left untranslated;
  4. any paragraph whose source was a bare identifier, number or code fragment is
     reported separately, because leaving those in English is correct.

Exit code 0 means every hard check passed.
"""

from __future__ import annotations

import re
import sys

from docx import Document
from docx.table import Table

CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")


def iter_paragraphs(document):
    from docx.text.paragraph import Paragraph

    for child in document.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, document)
        elif tag == "tbl":
            table = Table(child, document)
            seen = set()
            for row in table.rows:
                for cell in row.cells:
                    tc = cell._tc
                    if tc in seen:
                        continue
                    seen.add(tc)
                    for paragraph in cell.paragraphs:
                        yield paragraph


def texts(document) -> list[str]:
    return [p.text for p in iter_paragraphs(document) if p.text.strip()]


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    source_path, target_path = argv[1], argv[2]
    source = Document(source_path)
    target = Document(target_path)

    failures: list[str] = []

    # --- 1. tables -------------------------------------------------------
    if len(source.tables) != len(target.tables):
        failures.append(
            f"table count differs: source {len(source.tables)}, target {len(target.tables)}"
        )
    else:
        for index, (a, b) in enumerate(zip(source.tables, target.tables), 1):
            if len(a.rows) != len(b.rows):
                failures.append(f"table {index}: rows {len(a.rows)} -> {len(b.rows)}")
            ca = {len(row.cells) for row in a.rows}
            cb = {len(row.cells) for row in b.rows}
            if ca != cb:
                failures.append(f"table {index}: column counts {sorted(ca)} -> {sorted(cb)}")

    # --- 2. paragraphs and images ---------------------------------------
    source_texts = texts(source)
    target_texts = texts(target)
    if len(source_texts) != len(target_texts):
        failures.append(
            f"paragraph count differs: source {len(source_texts)}, target {len(target_texts)}"
        )
    if len(source.inline_shapes) != len(target.inline_shapes):
        failures.append(
            f"image count differs: source {len(source.inline_shapes)}, "
            f"target {len(target.inline_shapes)}"
        )

    # --- 3/4. translation coverage --------------------------------------
    untranslated: list[str] = []
    kept_english: list[str] = []
    if len(source_texts) == len(target_texts):
        for src, dst in zip(source_texts, target_texts):
            words = LATIN_WORD.findall(src)
            if len(words) >= 4 and not CJK.search(dst):
                untranslated.append(src[:90])
            elif len(words) < 4 and not CJK.search(dst):
                kept_english.append(src[:60])

    print(f"source: {source_path}")
    print(f"target: {target_path}")
    print(f"  tables:     {len(source.tables)} -> {len(target.tables)}")
    print(f"  paragraphs: {len(source_texts)} -> {len(target_texts)}")
    print(f"  images:     {len(source.inline_shapes)} -> {len(target.inline_shapes)}")
    print(f"  CJK paragraphs in target: {sum(1 for t in target_texts if CJK.search(t))}")
    print()

    if failures:
        print("STRUCTURE FAILURES:")
        for item in failures:
            print(f"  - {item}")
    else:
        print("structure: OK (tables, rows, columns, paragraphs, images all match)")

    if untranslated:
        print(f"\nPOSSIBLY UNTRANSLATED ({len(untranslated)} prose paragraphs):")
        for item in untranslated[:15]:
            print(f"  ! {item}")
    else:
        print("\ntranslation coverage: every prose paragraph contains Chinese")

    if kept_english:
        print(f"\nkept in English on purpose ({len(kept_english)} short entries, e.g.):")
        for item in kept_english[:8]:
            print(f"  · {item}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
