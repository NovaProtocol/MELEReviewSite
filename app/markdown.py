"""A small Markdown renderer.

The subset is the one the editor offers: headings, bold, italic, strikethrough,
superscript, inline code, code fences, quotes, spoilers, links, images, bullet
and numbered lists, and pipe tables.

Everything is escaped before any markup is applied, so the only HTML that comes
out is the HTML this module writes. Links are checked for a scheme; an image may
point at an upload (`/media/<uid>`) or an absolute http(s) URL, so a renamed
domain never breaks a stored reference.
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse

MEDIA_REF = re.compile(r"!\[[^\]]*\]\(/media/([0-9a-f]{32})\)")

_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^[-*]\s+(.*)$")
_NUMBER = re.compile(r"^\d+\.\s+(.*)$")
_TABLE_DIVIDER = re.compile(r"^\|?[\s:-]+\|[\s:|-]*$")


def extract_media_uids(text: str | None) -> list[str]:
    """Every upload a piece of prose references, in order, without duplicates."""
    if not text:
        return []
    seen: list[str] = []
    for uid in MEDIA_REF.findall(text):
        if uid not in seen:
            seen.append(uid)
    return seen


def _safe_url(raw: str, *, image: bool) -> str | None:
    value = raw.strip()
    if not value or any(char in value for char in "\"'<>"):
        return None
    # Same-origin references: uploads, the static tree, and the diagram endpoint,
    # whose whole purpose is to be embedded in prose. An image may use them; a link
    # may use any local path.
    local = ("/media/", "/static/", "/api/charts/")
    if value.startswith(local):
        return value
    if value.startswith("/") and not image:
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None


def _math(cls: str, tex: str) -> str:
    """A formula, carried as source and typeset in the browser.

    The TeX is escaped into an attribute, so the only thing that reaches the page
    is text; the renderer reads it back from there.
    """
    source = html.escape(tex, quote=True)
    return f'<span class="{cls}" data-tex="{source}">{html.escape(tex)}</span>'


def _inline(text: str) -> str:
    """Inline markup, applied to raw text.

    Code and formulas are lifted out first and put back last: code because its
    contents are literal, formulas because TeX is full of characters (`_`, `*`,
    `^`) that the emphasis rules would otherwise eat. Everything left is escaped
    before any tag is written, so the only tags in the result are these.
    """
    spans: list[str] = []

    def stash(match: re.Match) -> str:
        spans.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00C{len(spans) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", stash, text)

    formulas: list[tuple[str, str]] = []

    def stash_block_math(match: re.Match) -> str:
        formulas.append(("math-display", match.group(1)))
        return f"\x00M{len(formulas) - 1}\x00"

    def stash_inline_math(match: re.Match) -> str:
        formulas.append(("math-inline", match.group(1)))
        return f"\x00M{len(formulas) - 1}\x00"

    text = re.sub(r"\$\$(.+?)\$\$", stash_block_math, text, flags=re.S)
    text = re.sub(r"(?<![$\\])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\$)", stash_inline_math, text)
    text = html.escape(text)

    def image(match: re.Match) -> str:
        alt = match.group(1)
        url = _safe_url(match.group(2), image=True)
        if url is None:
            return match.group(0)
        return f'<img src="{html.escape(url, quote=True)}" alt="{alt}" loading="lazy">'

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)

    def link(match: re.Match) -> str:
        label, url = match.group(1), _safe_url(match.group(2), image=False)
        if url is None:
            return match.group(1)
        return (
            f'<a href="{html.escape(url, quote=True)}" rel="noopener nofollow" '
            f'target="_blank">{label}</a>'
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"&gt;!(.+?)!&lt;", r'<span class="md-spoiler" tabindex="0">\1</span>', text)
    text = re.sub(r"\^([^\^\s]+)\^", r"<sup>\1</sup>", text)

    for index, (cls, tex) in enumerate(formulas):
        text = text.replace(f"\x00M{index}\x00", _math(cls, tex))
    for index, span in enumerate(spans):
        text = text.replace(f"\x00C{index}\x00", span)
    return text


def _table(lines: list[str]) -> str:
    def cells(row: str) -> list[str]:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        return [cell.strip() for cell in row.split("|")]

    head = cells(lines[0])
    body = [cells(line) for line in lines[2:]]
    out = ['<table class="md-table"><thead><tr>']
    out += [f"<th>{_inline(cell)}</th>" for cell in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render(text: str | None) -> str:
    """Markdown in, HTML out. Empty input is empty output."""
    if not text or not text.strip():
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip().lower()
            index += 1
            block: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            if language == "math":
                out.append(_math("math-display", "\n".join(block).strip()))
            elif language == "mermaid":
                # Rendered in the browser: the source is kept as text, so a reader
                # without the script still gets the diagram's definition.
                source = html.escape("\n".join(block).strip())
                out.append(f'<pre class="mermaid">{source}</pre>')
            elif language == "plot":
                from app import plots

                svg, error = plots.render("\n".join(block))
                if svg:
                    out.append(f'<figure class="md-plot">{svg}</figure>')
                else:
                    out.append(f'<p class="md-plot-error">{html.escape(error)}</p>')
            else:
                body = html.escape("\n".join(block), quote=False)
                out.append(f'<pre class="md-code"><code>{body}</code></pre>')
            continue

        # A `$$` block on its own lines, which may run over several lines.
        if stripped.startswith("$$"):
            collected = stripped[2:]
            index += 1
            if collected.endswith("$$"):
                collected = collected[:-2]
            else:
                while index < total and not lines[index].strip().endswith("$$"):
                    collected += "\n" + lines[index]
                    index += 1
                if index < total:
                    collected += "\n" + lines[index].strip()[:-2]
                    index += 1
            out.append(_math("math-display", collected.strip()))
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        # A table needs a header row and a divider directly beneath it.
        if (
            "|" in stripped
            and index + 1 < total
            and _TABLE_DIVIDER.match(lines[index + 1].strip())
            and "-" in lines[index + 1]
        ):
            block = [lines[index], lines[index + 1]]
            index += 2
            while index < total and "|" in lines[index] and lines[index].strip():
                block.append(lines[index])
                index += 1
            out.append(_table(block))
            continue

        # `>!` opens a spoiler, not a quote.
        if stripped.startswith(">") and not stripped.startswith(">!"):
            block = []
            while (
                index < total
                and lines[index].strip().startswith(">")
                and not lines[index].strip().startswith(">!")
            ):
                block.append(lines[index].strip()[1:].lstrip())
                index += 1
            out.append(f"<blockquote>{_inline(' '.join(block))}</blockquote>")
            continue

        if _BULLET.match(stripped) or _NUMBER.match(stripped):
            ordered = bool(_NUMBER.match(stripped))
            pattern = _NUMBER if ordered else _BULLET
            items = []
            while index < total:
                match = pattern.match(lines[index].strip())
                if not match:
                    break
                text = match.group(1).strip()
                index += 1
                # A list item may wrap onto indented lines; they belong to it, not
                # to a new paragraph, and breaking there restarts the numbering.
                while index < total and lines[index].strip() and lines[index][:1] in {" ", "\t"}:
                    text += " " + lines[index].strip()
                    index += 1
                items.append(f"<li>{_inline(text)}</li>")
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        paragraph: list[str] = []
        while index < total:
            candidate = lines[index]
            if not candidate.strip():
                break
            if paragraph and (
                _HEADING.match(candidate.strip())
                or candidate.strip().startswith("```")
                or _BULLET.match(candidate.strip())
                or _NUMBER.match(candidate.strip())
            ):
                break
            paragraph.append(candidate.strip())
            index += 1
        # A single newline is a line break, not a space. The editor writes notes a
        # line at a time, and joining those lines is what made a list of workings
        # come back as one long sentence after a trip through the rich editor.
        out.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")

    return "\n".join(out)


def to_plain(text: str | None, limit: int = 0) -> str:
    """The prose without its markup, for a list or a page title."""
    if not text:
        return ""
    stripped = MEDIA_REF.sub("", text)
    stripped = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
    stripped = re.sub(r"\$[^$]*\$", "math", stripped)
    stripped = re.sub(r"[*~`^#>]+", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped[:limit] if limit else stripped
