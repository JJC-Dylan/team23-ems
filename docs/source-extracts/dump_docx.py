"""Dump every DOCX part we need to understand: paragraphs in order and table grids."""
import sys
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn


def iter_block_items(parent):
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


def dump(path, out):
    doc = Document(path)
    lines = []
    ti = 0
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            style = block.style.name if block.style is not None else ''
            if text:
                marker = f'[{style}] ' if style and not style.startswith('Normal') else ''
                lines.append(f'{marker}{text}')
        else:
            ti += 1
            lines.append(f'<<<TABLE {ti}: {len(block.rows)}r x {len(block.columns)}c>>>')
            for row in block.rows:
                cells = []
                seen = set()
                for c in row.cells:
                    if id(c._tc) in seen:
                        continue
                    seen.add(id(c._tc))
                    cells.append(' '.join(c.text.split()))
                lines.append(' | '.join(cells))
            lines.append('<<<END TABLE>>>')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    print(f'{path}\n  -> {out}: {len(lines)} lines, {ti} tables, {len(doc.paragraphs)} paragraphs')


if __name__ == '__main__':
    dump(sys.argv[1], sys.argv[2])
