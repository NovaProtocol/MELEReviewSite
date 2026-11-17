#!/usr/bin/env python3
"""Force the figures that are property diagrams into plots.

The general pass asks a figure to be classified; a cycle drawn on a P-h or T-s
diagram gets read as a machine, because it also shows the equipment. But the reader
who wants the cycle wants the curve, and a photograph of a curve cannot be read
against the numbers in the prose.

So for a named list of pages this asks for the curve directly: the dome, the process
lines, and the state points, as series that the site draws with matplotlib.

    uv run --with pymupdf --with httpx scripts/plot_figures.py --pdf book.pdf \
        --pages /tmp/ingest/out/pages --token-file key.md --only 0301 0310 0490
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pymupdf

API = "https://api.commandcode.ai/provider/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
HEADERS = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
IMAGE = re.compile(r"!\[[^\]]*\]\(/media/[^)]+\)")
DPI = 150

PROMPT = """You are redrawing a property diagram from a mechanical engineering reference
page as a clean, readable chart.

Return ONE JSON object, nothing else:

{"type": "line", "title": "...", "xlabel": "...", "ylabel": "...",
 "x": [numbers],
 "series": [{"name": "saturation dome", "y": [numbers]},
            {"name": "cycle", "y": [numbers]}]}

What matters is that a student can see the SHAPE of the process and compare it with
the text: a dome, an isentropic line, a constant-pressure line, a reheat leg. Exact
axis calibration is not required; relative shape and the named states are.

Rules:
- Use 10 to 30 points for a curve, in order along x.
- Every series must have the same number of points, matching x.
- Name the series as the page names them, with states where shown ("1-2 compression").
- If the page shows two diagrams side by side (for example P-v and T-s), draw the one
  named first in the page's own caption."""


def ask(client: httpx.Client, key: str, png: bytes, text: str) -> dict | None:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT + "\n\nPage text:\n" + text[:2500]},
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
    response = client.post(
        API, headers={"Authorization": f"Bearer {key}", **HEADERS}, json=payload, timeout=180
    )
    response.raise_for_status()
    body = response.json()["choices"][0]["message"].get("content") or ""
    found = re.search(r"\{.*\}", body, re.S)
    if not found:
        return None
    try:
        return json.loads(found.group(0))
    except ValueError:
        return None


def valid(spec: dict) -> bool:
    series = spec.get("series") or []
    xs = spec.get("x") or []
    if not series or not xs:
        return False
    length = len(xs)
    return all(len(item.get("y") or []) == length for item in series)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--only", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = Path(args.token_file).read_text().strip()
    if "=" in key:
        key = key.split("=", 1)[1].strip()
    document = pymupdf.open(args.pdf)
    pages = Path(args.pages)

    def convert(stem: str) -> tuple[str, str]:
        path = pages / f"{stem}.md"
        text = path.read_text()
        if not IMAGE.search(text):
            return stem, "no image"
        pixmap = document[int(re.sub(r"[^0-9]", "", stem)) - 1].get_pixmap(dpi=DPI)
        png = pixmap.tobytes("png")
        with httpx.Client(timeout=180) as client:
            for attempt in range(3):
                try:
                    spec = ask(client, key, png, text)
                    break
                except Exception as exc:
                    if attempt == 2:
                        return stem, f"failed: {exc}"
            else:
                return stem, "failed"
        if not spec or not valid(spec):
            return stem, "no usable spec"
        if not args.dry_run:
            path.write_text(IMAGE.sub("```plot\n" + json.dumps(spec) + "\n```", text, count=1))
        names = ", ".join(item.get("name", "?") for item in spec["series"])
        return stem, f"plot: {spec.get('title', '')} [{names}]"

    with ThreadPoolExecutor(max_workers=3) as pool:
        for stem, result in pool.map(convert, args.only):
            print(f"{stem}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
