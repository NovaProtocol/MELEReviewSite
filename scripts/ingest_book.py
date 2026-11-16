#!/usr/bin/env python3
"""Transcribe a scanned book into the topic Resources panels.

The PDFs this is for are scans, not text: every page is one image and `pdftotext`
returns nothing. So each page is rendered to a PNG, sent to a vision model with a
transcription prompt, and the Markdown that comes back is appended to the chapter
it belongs to. When every page has been transcribed, each chapter is written to the
topic whose name matches it.

    DEEPSEEK_API_KEY=... uv run --with pymupdf --with httpx scripts/ingest_book.py \
        --pdf /path/book.pdf --base-url https://melereview.projectnova.download \
        --page 1-712 --dry-run

`--dry-run` renders and transcribes but writes the Markdown to `out/` instead of
posting it, which is how to judge quality and cost before committing.

Requirements:
  - a DeepSeek key with the `deepseek-flash` model (the vision one);
  - the site's administrator credentials, because writing a topic page needs
    EDIT_TOPIC_CONTENT.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

import httpx
import pymupdf

API = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
DPI = 170
CHAPTER = re.compile(r"Chapter\s*(\d{1,2})\s*[\u2013\u2014-]\s*([A-Za-z &/,.'-]+)", re.I)

PROMPT = """Transcribe this page of a mechanical engineering reference book into Markdown.

Rules:
- Transcribe every word you can read. Do not summarise, shorten or reorder.
- Formulas become LaTeX: inline $...$, display $$...$$. Keep symbols, subscripts,
  superscripts and units exactly as printed.
- Tables become Markdown tables. Diagrams: describe the structure in one short
  bracketed line, then transcribe every label you can read.
- Keep the printed page number and the running header out of the body; they are
  handled separately.
- If a line is genuinely unreadable, write [illegible] rather than guessing.

First line of your reply: `CHAPTER: <the chapter name from the running header>`
Second line: `PAGE: <the printed page number>`
Then the transcription."""


def pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            start, end = part.split("-")
            out.extend(range(int(start), int(end) + 1))
        else:
            out.append(int(part))
    return out


def render(doc, index: int) -> bytes:
    pix = doc[index].get_pixmap(dpi=DPI)
    return pix.tobytes("png")


def transcribe(client: httpx.Client, key: str, png: bytes) -> str:
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
                            "url": "data:image/png;base64," + base64.b64encode(png).decode(),
                        },
                    },
                ],
            }
        ],
        "max_tokens": 4000,
        "temperature": 0,
    }
    response = client.post(
        API,
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def split_header(text: str) -> tuple[str, str, str]:
    chapter = ""
    page = ""
    body = []
    for line in text.splitlines():
        if not chapter and line.upper().startswith("CHAPTER:"):
            chapter = line.split(":", 1)[1].strip()
        elif not page and line.upper().startswith("PAGE:"):
            page = line.split(":", 1)[1].strip()
        else:
            body.append(line)
    if not chapter:
        found = CHAPTER.search(text)
        chapter = found.group(2).strip() if found else "Front matter"
    return chapter, page, "\n".join(body).strip()


def normalise(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-pass", required=True)
    parser.add_argument("--page", default="1-712")
    parser.add_argument("--out", default="out")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    doc = pymupdf.open(args.pdf)
    wanted = [index - 1 for index in pages(args.page) if 0 < index <= len(doc)]

    # The site, so the chapters can be matched to topics and the pages written.
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60) as site:
        site.get("/")
        token = site.cookies.get("melereview_csrf") or ""
        login = site.post(
            "/api/auth/login",
            json={"identifier": args.admin_user, "password": args.admin_pass},
            headers={"X-CSRF-Token": token},
        )
        login.raise_for_status()
        token = site.cookies.get("melereview_csrf") or ""
        taxonomy = site.get("/api/subjects").json()

    topics: dict[str, tuple[int, str]] = {}
    for subject in taxonomy:
        for topic in subject["topics"]:
            topics[normalise(topic["name"])] = (topic["id"], topic["name"])

    chapters: dict[str, list[str]] = {}
    unread: list[int] = []
    with httpx.Client() as api:
        for position, index in enumerate(wanted, start=1):
            png = render(doc, index)
            try:
                text = transcribe(api, key, png)
            except Exception as exc:
                print(f"page {index + 1}: {exc}", file=sys.stderr)
                unread.append(index + 1)
                continue
            chapter, page, body = split_header(text)
            chapters.setdefault(chapter, []).append(
                f"*— pdf page {index + 1}"
                + (f", printed {page}" if page else "")
                + " —*\n\n"
                + body
            )
            print(f"[{position}/{len(wanted)}] pdf {index + 1} -> {chapter}")

    missing = [name for name in chapters if normalise(name) not in topics]
    for name, parts in chapters.items():
        target = topics.get(normalise(name))
        markdown = f"# {name}\n" + "\n\n".join(parts)
        if target is None:
            (out / f"UNMATCHED-{normalise(name)}.md").write_text(markdown)
            continue
        topic_id, topic_name = target
        (out / f"{topic_id:02d}-{normalise(topic_name)}.md").write_text(markdown)
        if args.dry_run:
            continue
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=120) as site:
            site.cookies.set("melereview_csrf", token)
            saved = site.put(
                f"/api/topics/{topic_id}/pages/resources",
                json={"body": markdown},
                headers={"X-CSRF-Token": token},
            )
            saved.raise_for_status()

    print(f"\n{len(wanted)} pages, {len(chapters)} chapters, {len(unread)} unread")
    if missing:
        print("unmatched chapters:", ", ".join(sorted(missing)))
    if unread:
        print("unread pages:", ", ".join(map(str, unread)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
