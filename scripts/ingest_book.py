#!/usr/bin/env python3
"""Transcribe a scanned book into the topic Resources panels.

The PDFs this is for are scans, not text: every page is one image and `pdftotext`
returns nothing. Each page is rendered to a PNG, sent to a vision model, and the
Markdown that comes back is appended to the chapter it belongs to. When every page
has been transcribed, each chapter is written to the topic whose name matches it.

    uv run --with pymupdf --with httpx scripts/ingest_book.py \
        --pdf book.pdf --token-file key.md \
        --base-url https://melereview.projectnova.download \
        --admin-pass '...' --dry-run

Three things this must do or it fails silently:
  - thinking mode off, or the output budget is spent on reasoning and `content`
    comes back null;
  - a User-Agent, because the gateway refuses Python's default with a 1010;
  - count what it could not read. The run reports unread pages and unmatched
    chapters instead of dropping them.
"""

from __future__ import annotations

import argparse
import base64
import difflib
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pymupdf

API = "https://api.commandcode.ai/provider/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
DPI = 170
CHAPTER = re.compile(r"Chapter\s*(\d{1,2})\s*[\u2013\u2014-]\s*([A-Za-z &/,.'-]+)", re.I)
HEADERS = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}

PROMPT = """Transcribe this page of a mechanical engineering reference book into Markdown.

Rules:
- Transcribe every word you can read. Do not summarise, shorten or reorder.
- Formulas become LaTeX: inline $...$, display $$...$$. Keep symbols, subscripts,
  superscripts and units exactly as printed.
- Tables become Markdown tables. Diagrams: draw the structure in one fenced block,
  then transcribe every label you can read.
- Do not repeat the printed page number or the running header in the body.
- If a line is genuinely unreadable, write [illegible] rather than guessing.

First line of your reply: `CHAPTER: <the chapter name from the running header>`
Second line: `PAGE: <the printed page number>`
Then the transcription."""


def page_numbers(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            start, end = part.split("-")
            out.extend(range(int(start), int(end) + 1))
        else:
            out.append(int(part))
    return out


def split_header(text: str) -> tuple[str, str, str]:
    chapter = ""
    page = ""
    body = []
    for line in text.splitlines():
        upper = line.upper()
        if not chapter and upper.startswith("CHAPTER:"):
            chapter = line.split(":", 1)[1].strip()
        elif not page and upper.startswith("PAGE:"):
            page = line.split(":", 1)[1].strip()
        else:
            body.append(line)
    if not chapter:
        found = CHAPTER.search(text)
        chapter = found.group(2).strip() if found else "Front matter"
    # The model quotes the running header, so strip the numbering off it: the
    # chapter name is what gets matched against a topic.
    stripped = re.sub(r"^chapter\s*\d+\s*[\u2013\u2014:-]\s*", "", chapter, flags=re.I)
    chapter = stripped.strip(" -–—:") or chapter
    page = "" if "illegible" in page.lower() else page
    return chapter, page, "\n".join(body).strip()


STOPWORDS = {"and", "of", "the", "a", "an", "in", "to", "for", "with"}


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def match_key(name: str) -> str:
    """The part of a chapter name that identifies it.

    The book says "Engineering Economics", "Plane & Spherical Trigonometry" and
    "Probability & Statistics"; the taxonomy says "economics", "plane and spherical
    trigonometry" and "probability and statistics". Dropping the joining words is
    what makes those the same thing.
    """
    words = [word for word in normalise(name).split() if word not in STOPWORDS]
    return " ".join(words)


FILLER = ("engineering ", "basic ", "general ", "fundamentals of ", "principles of ")


def match_topic(name: str, topics: dict[str, tuple[int, str]]) -> str | None:
    """The taxonomy key a chapter name belongs to, exactly or closely.

    The book titles chapters more fully than the taxonomy names topics: "Engineering
    Economics" is economics, "Engineering Mechanics" is physics and mechanics. So an
    exact key, then the key without its filler words, then a containment test, then
    a similarity score.
    """
    wanted = match_key(name)
    if wanted in topics:
        return wanted
    trimmed = wanted
    for word in FILLER:
        if trimmed.startswith(word):
            trimmed = trimmed[len(word) :]
            break
    if trimmed in topics:
        return trimmed

    contained = [
        candidate
        for candidate in topics
        if candidate and (candidate in wanted or wanted in candidate)
    ]
    if contained:
        return max(contained, key=len)

    best, score = None, 0.0
    for candidate in topics:
        ratio = difflib.SequenceMatcher(None, wanted, candidate).ratio()
        if ratio > score:
            best, score = candidate, ratio
    return best if score >= 0.8 else None


def transcribe(client: httpx.Client, key: str, png: bytes, tries: int = 2) -> str:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode()
                        },
                    },
                ],
            }
        ],
        "max_tokens": 4000,
        "temperature": 0,
        "thinking": {"type": "disabled"},
    }
    last: Exception | None = None
    for attempt in range(tries):
        try:
            response = client.post(
                API,
                headers={"Authorization": f"Bearer {key}", **HEADERS},
                json=payload,
                timeout=240,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"].get("content") or ""
            if content.strip():
                return content
            last = RuntimeError("empty content")
        except Exception as exc:
            last = exc
        time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(str(last))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-pass", required=True)
    parser.add_argument("--page", default="1-712")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="out")
    parser.add_argument("--dry-run", action="store_true")
    # Rebuild the chapters from pages already saved, without calling the model.
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()

    key = Path(args.token_file).read_text().strip()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(args.pdf)
    wanted = [index - 1 for index in page_numbers(args.page) if 0 < index <= len(doc)]
    pages_dir = out / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    # One client for the whole run: the writes happen half an hour after the login,
    # so the session has to stay open rather than be rebuilt from the CSRF cookie.
    site = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180)
    site.get("/")
    token = site.cookies.get("melereview_csrf") or ""
    site.post(
        "/api/auth/login",
        json={"identifier": args.admin_user, "password": args.admin_pass},
        headers={"X-CSRF-Token": token, **HEADERS},
    ).raise_for_status()
    taxonomy = site.get("/api/subjects", headers=HEADERS).json()

    topics: dict[str, tuple[int, str]] = {}
    for subject in taxonomy:
        for topic in subject["topics"]:
            topics[match_key(topic["name"])] = (topic["id"], topic["name"])

    results: dict[int, str] = {}
    unread: list[int] = []

    if args.reuse:
        for index in wanted:
            saved = pages_dir / f"{index + 1:04d}.md"
            if saved.is_file() and saved.read_text().strip():
                results[index] = saved.read_text()
        print(f"reusing {len(results)} saved pages", flush=True)
    else:

        def work(index: int) -> tuple[int, str | None]:
            try:
                png = doc[index].get_pixmap(dpi=DPI).tobytes("png")
                with httpx.Client() as api:
                    return index, transcribe(api, key, png)
            except Exception as exc:
                print(f"page {index + 1}: {exc}", file=sys.stderr)
                return index, None

        with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
            for done, (index, text) in enumerate(pool.map(work, wanted), start=1):
                if text is None:
                    unread.append(index + 1)
                else:
                    results[index] = text
                    # Saved at once: a later failure must not cost the run.
                    (pages_dir / f"{index + 1:04d}.md").write_text(text)
                if done % 10 == 0 or done == len(wanted):
                    print(f"[{done}/{len(wanted)}] pages transcribed", flush=True)

    # The running header alternates: one page names the chapter, the next names
    # the book. So a name is only taken when it matches a topic, and every other
    # page belongs to the chapter that was current when the page turned.
    # Grouped by the normalised name, not the printed one: "ALGEBRA" and "Algebra"
    # are the same chapter, and keying on the raw text split them into two files
    # that overwrote each other.
    # Printed page numbers are read off the scan and often wrong: one trigonometry
    # page came back as "19". The PDF page is certain, so the offset between the two
    # is taken as the commonest difference and the range is computed from it.
    offsets: dict[int, int] = {}
    for index, text in results.items():
        _c, printed, _b = split_header(text)
        digits = re.sub(r"[^0-9]", "", printed)
        if digits:
            delta = (index + 1) - int(digits)
            if -50 < delta < 200:
                offsets[delta] = offsets.get(delta, 0) + 1
    offset = max(offsets, key=offsets.get) if offsets else 0

    chapters: dict[str, tuple[str, list[str]]] = {}
    spans: dict[str, dict[str, list[int]]] = {}
    current: tuple[str, str] = ("Front matter", "front matter")
    for index in sorted(results):
        chapter, page, body = split_header(results[index])
        resolved = match_topic(chapter, topics)
        if resolved:
            current = (chapter, resolved)
        chapters.setdefault(current[1], (current[0], []))[1].append(body)
        spans.setdefault(current[1], {"pdf": []})
        spans[current[1]]["pdf"].append(index + 1)

    unmatched: list[str] = []
    pending: list[tuple[int, str, str, str]] = []
    for key, (name, parts) in chapters.items():
        # Sections were marked at whatever level the page used; one level below the
        # chapter title is all a reader needs.
        body = "\n\n".join(parts)
        body = re.sub(r"^#{3,6}\s+", "## ", body, flags=re.M)
        display = name.title() if name.isupper() else name
        markdown = f"# {display}\n\n{body}"
        target = topics.get(key)
        label = key.replace(" ", "-") or "unknown"
        if target is None:
            unmatched.append(name)
            (out / f"UNMATCHED-{label}.md").write_text(markdown)
            continue
        topic_id, topic_name = target
        (out / f"{topic_id:02d}-{normalise(topic_name).replace(' ', '-')}.md").write_text(markdown)

        pages_used = (spans.get(key) or {}).get("pdf") or []
        if pages_used:
            first = max(min(pages_used) - offset, 1)
            where = f"pages {first}–{max(pages_used) - offset}"
        else:
            where = "page range unknown"
        reference = "*Prime's Mechanical Engineering Pocket Reference Manual* — " + where
        (out / f"{topic_id:02d}-{normalise(topic_name).replace(' ', '-')}-reference.md").write_text(
            reference + "\n"
        )
        pending.append((topic_id, topic_name, markdown, reference))

    failed: list[str] = []
    if not args.dry_run:
        for topic_id, topic_name, markdown, reference in pending:
            for kind, body in (("resources", markdown), ("reference", reference)):
                for attempt in range(3):
                    try:
                        response = site.put(
                            f"/api/topics/{topic_id}/pages/{kind}",
                            json={"body": body},
                            headers={"X-CSRF-Token": token, **HEADERS},
                        )
                        response.raise_for_status()
                        break
                    except Exception as exc:
                        if attempt == 2:
                            failed.append(f"{topic_name}/{kind}")
                            print(f"FAILED {topic_name}/{kind}: {exc}", file=sys.stderr)
                        else:
                            time.sleep(2 * (attempt + 1))
            print(f"wrote {topic_name} ({len(markdown)} chars + citation)")
    site.close()

    print(f"\n{len(wanted)} pages asked, {len(results)} transcribed, {len(unread)} unread")
    print(f"{len(chapters)} chapters, {len(chapters) - len(unmatched)} matched to a topic")
    if unmatched:
        print("unmatched chapters:", ", ".join(sorted(unmatched)))
    if unread:
        print("unread pages:", ", ".join(map(str, unread)))
    if failed:
        print("failed to write:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
