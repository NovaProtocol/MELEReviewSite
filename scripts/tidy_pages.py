#!/usr/bin/env python3
"""Tidy the page transcriptions before they are assembled into chapters.

The transcriber is faithful to the printing, which includes things a reader does
not need: the book's little emoji section markers, bold wrapped around headings,
heading levels invented per page, and the page markers. This strips those and
leaves the prose, the tables, the formulas and the figures.

    python3 scripts/tidy_pages.py /tmp/ingest/out/pages
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# The book marks sections with glyphs; they are decoration, not content.
MARKS = "☑✔✓❖◆◇▪▫■◼□◾📖📝🖉✎✏➤►▶•●○◦"
MARK_LINE = re.compile(rf"^\s*[{MARKS}]+\s*")
MARK_ANY = re.compile(rf"[{MARKS}]\ufe0f?\s*")
MARKER_LINE = re.compile(r"^\s*\*—\s*pdf page .*?—\*\s*$")
HEADER_LINE = re.compile(r"^\s*(CHAPTER|PAGE):.*$", re.I)
HEADING = re.compile(r"^(#{1,6})\s*(.*)$")
# The figure pass left the transcriber's label list behind: once the figure is
# drawn, a list of its labels is noise in the prose.
LABELS = re.compile(r"^\s*Labels?\s*:", re.I)
TEX_INLINE = re.compile(r"\\\((.*?)\\\)")
TEX_BLOCK = re.compile(r"\\\[(.*?)\\\]", re.S)
EMPHASIS = re.compile(r"[*_]{1,3}")


def tidy(text: str) -> str:
    # Drop a label block whole: the line, the list under it, and the blank after.
    kept: list[str] = []
    skipping = False
    for line in text.splitlines():
        if LABELS.match(line):
            skipping = True
            continue
        if skipping:
            if not line.strip():
                skipping = False
            elif line.lstrip().startswith(("-", "*", "+")) or line.startswith(" ") or line.startswith("\t"):
                continue
            else:
                skipping = False
        kept.append(line)
    text = "\n".join(kept)

    # The transcriber writes mathematics as \( \) and \[ \]; the site reads
    # $ and $$. Normalise outside code, where the delimiters are literal.
    pieces = re.split(r"(```.*?```)", text, flags=re.S)
    for index, piece in enumerate(pieces):
        if piece.startswith("```"):
            continue
        piece = TEX_BLOCK.sub(lambda m: "$$" + m.group(1).strip() + "$$", piece)
        piece = TEX_INLINE.sub(lambda m: "$" + m.group(1) + "$", piece)
        pieces[index] = piece
    text = "".join(pieces)

    lines = []
    for line in text.splitlines():
        # CHAPTER:/PAGE: are kept: the chapter writer needs them to place the
        # page. They never reach the assembled chapter.
        if MARKER_LINE.match(line):
            continue
        line = MARK_ANY.sub("", line)
        line = MARK_LINE.sub("", line)

        heading = HEADING.match(line)
        if heading:
            level, title = heading.groups()
            title = EMPHASIS.sub("", title).strip().strip(":").strip()
            if not title:
                continue
            line = f"{level} {title}"

        if line.rstrip() in {"---", "***", "___"}:
            continue
        lines.append(line.rstrip())

    joined = "\n".join(lines)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip() + "\n"


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "out/pages")
    changed = 0
    for path in sorted(root.glob("*.md")):
        original = path.read_text()
        cleaned = tidy(original)
        if cleaned != original:
            path.write_text(cleaned)
            changed += 1
    print(f"tidied {changed} of {len(list(root.glob('*.md')))} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
