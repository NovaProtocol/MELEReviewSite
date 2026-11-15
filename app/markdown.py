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
    if value.startswith("/media/"):
        return value
    if value.startswith("/") and not image:
        return value
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None


def _inline(text: str) -> str:
    """Inline markup, applied to text that is already escaped.

    Escaping first is what makes this safe: every character the author wrote has
    become an entity, so the only tags in the result are the ones written here.
    """
    # Code first: its contents are literal, so nothing inside may be rewritten.
    spans: list[str] = []

    def stash(match: re.Match) -> str:
        spans.append(f"<code>{match.group(1)}</code>")
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", stash, text)

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

    for index, span in enumerate(spans):
        text = text.replace(f"\x00{index}\x00", span)
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
    out += [f"<th>{_inline(html.escape(cell))}</th>" for cell in head]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append(
            "<tr>" + "".join(f"<td>{_inline(html.escape(cell))}</td>" for cell in row) + "</tr>"
        )
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
            index += 1
            block: list[str] = []
            while index < total and not lines[index].strip().startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            body = html.escape("\n".join(block), quote=False)
            out.append(f'<pre class="md-code"><code>{body}</code></pre>')
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            title = html.escape(heading.group(2).strip())
            out.append(f"<h{level}>{_inline(title)}</h{level}>")
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
            quoted = html.escape(" ".join(block))
            out.append(f"<blockquote>{_inline(quoted)}</blockquote>")
            continue

        if _BULLET.match(stripped) or _NUMBER.match(stripped):
            ordered = bool(_NUMBER.match(stripped))
            pattern = _NUMBER if ordered else _BULLET
            items = []
            while index < total:
                match = pattern.match(lines[index].strip())
                if not match:
                    break
                item = html.escape(match.group(1).strip())
                items.append(f"<li>{_inline(item)}</li>")
                index += 1
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
        prose = html.escape(" ".join(paragraph))
        out.append(f"<p>{_inline(prose)}</p>")

    return "\n".join(out)


def to_plain(text: str | None, limit: int = 0) -> str:
    """The prose without its markup, for a list or a page title."""
    if not text:
        return ""
    stripped = MEDIA_REF.sub("", text)
    stripped = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
    stripped = re.sub(r"[*~`^#>]+", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped[:limit] if limit else stripped
