#!/usr/bin/env python3
"""Redraw the figures that are really charts.

The first figure pass drew every sketch it could into a PNG, which left pictures of
plots in the notes: PV and TS diagrams, cycle curves, performance lines. A picture of
a chart is worse than the chart, because it cannot be read against the page's own
numbers.

This reads the pages that already carry an image and asks, per figure, whether it is
a chart (drawn from numbers), a structure (Mermaid), or a machine (keep the picture).
Only the first two are replaced; a schematic of a turbine stays a picture, because
drawing it as boxes would teach less than the scan does.

    uv run --with pymupdf --with httpx scripts/refigure_pages.py --pdf book.pdf \
        --pages /tmp/ingest/out/pages --token-file key.md --workers 6
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

PROMPT = """You are improving a mechanical engineering reference page for learners.

The page currently shows a picture of one of its figures. Decide how that figure is
best presented on a web page, and return ONE JSON object, nothing else.

If the figure is a CHART -- axes, curves, lines, bars, a property diagram (PV, TS,
P-h, stress-strain, efficiency curves) -- give its shape as numbers you can read from
the page:

{"mode": "plot", "why": "...", "plot": {"type": "line"|"bar"|"scatter",
  "title": "...", "x": [numbers or category labels],
  "xlabel": "...", "ylabel": "...",
  "series": [{"name": "...", "y": [numbers]}]}}

If the figure is a STRUCTURE -- a hierarchy, a classification, a process with stages --
give it as a diagram:

{"mode": "mermaid", "why": "...", "mermaid": "flowchart TD\\n  a[\\"x\\"] --> b[\\"y\\"]"}

If the figure is a MACHINE or a physical object -- a turbine, a vessel, a thread, a
cross-section, a plant layout -- keep the picture:

{"mode": "keep", "why": "..."}

Rules: numbers must come from the page, not from memory. A diagram may have at most
12 nodes. Keep labels short. Prefer plot when the reader would want to read a value
off it."""


def clean(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def ask(client: httpx.Client, key: str, png: bytes, page_text: str) -> dict | None:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT + "\n\nPage text:\n" + page_text[:2500]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode()
                        },
                    },
                ],
            }
        ],
        "max_tokens": 2400,
        "temperature": 0,
        "thinking": {"type": "disabled"},
    }
    response = client.post(
        API, headers={"Authorization": f"Bearer {key}", **HEADERS}, json=payload, timeout=180
    )
    response.raise_for_status()
    text = response.json()["choices"][0]["message"].get("content") or ""
    found = re.search(r"\{.*\}", text, re.S)
    if not found:
        return None
    try:
        return json.loads(found.group(0))
    except ValueError:
        return None


def block_for(answer: dict) -> str | None:
    mode = answer.get("mode")
    if mode == "plot" and isinstance(answer.get("plot"), dict):
        spec = answer["plot"]
        if not spec.get("series"):
            return None
        return "```plot\n" + json.dumps(spec) + "\n```"
    if mode == "mermaid" and answer.get("mermaid"):
        source = str(answer["mermaid"]).strip()
        if not source.startswith(("flowchart", "graph")):
            source = "flowchart TD\n" + source
        return "```mermaid\n" + source + "\n```"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    key = Path(args.token_file).read_text().strip()
    if "=" in key:
        key = key.split("=", 1)[1].strip()
    pages = Path(args.pages)
    targets = [page for page in sorted(pages.glob("*.md")) if IMAGE.search(page.read_text())]
    print(f"{len(targets)} pages carry an image")

    document = pymupdf.open(args.pdf)

    def convert(path: Path) -> tuple[str, str]:
        number = int(re.sub(r"[^0-9]", "", path.stem))
        page = document[number - 1]
        pixmap = page.get_pixmap(dpi=DPI)
        png = pixmap.tobytes("png")
        text = path.read_text()
        with httpx.Client(timeout=180) as client:
            for attempt in range(3):
                try:
                    answer = ask(client, key, png, text)
                    break
                except Exception as exc:
                    if attempt == 2:
                        return str(path), f"failed: {exc}"
            else:
                return str(path), "failed"

        if not answer:
            return str(path), "no answer"
        block = block_for(answer)
        if not block:
            return str(path), f"keep ({answer.get('why', '')[:60]})"
        if not args.dry_run:
            path.write_text(IMAGE.sub(block, text, count=1))
        return str(path), f"{answer.get('mode')} ({answer.get('why', '')[:60]})"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for path, result in pool.map(convert, targets):
            print(f"{Path(path).stem}: {result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
