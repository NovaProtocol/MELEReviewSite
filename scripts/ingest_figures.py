#!/usr/bin/env python3
"""Draw the diagrams a transcribed page describes.

The transcription leaves each figure as a fenced sketch. This reads that sketch
alongside the page image, asks the model for a small structured spec, and draws a
clean figure with matplotlib: boxes and arrows rather than a photocopy. The point
is a figure that teaches, not one that matches the scan line for line.

    uv run --with pymupdf --with httpx --with matplotlib scripts/ingest_figures.py \
        --pdf book.pdf --pages /tmp/ingest/out/pages --token-file key.md \
        --base-url https://melereview.projectnova.download --admin-pass '...'

Each drawn figure is uploaded through the site's media endpoint, so it lives in the
`media` table like any other upload, and the fenced block in the page file is
replaced with `![figure](/media/<uid>)`. Re-running the chapter writer is then
enough to publish.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pymupdf
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

API = "https://api.commandcode.ai/provider/v1/chat/completions"
MODEL = "deepseek/deepseek-v4.1-flash"
HEADERS = {"User-Agent": "curl/8.5.0", "Accept": "application/json"}
FENCE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.S)
DPI = 150
INK = "#1b2430"
ACCENT = "#2f9e8f"
PAPER = "#ffffff"

PROMPT = """You are redrawing a figure from a mechanical engineering reference book.

You are given the book page and the transcriber's sketch of its figure. Return ONE
JSON object, nothing else, describing the figure as a clean diagram:

{"type": "tree", "title": "...", "root": {"label": "...", "children": [...]}}
  for hierarchies (number systems, classifications, families)

{"type": "flow", "title": "...", "steps": ["...", "..."]}
  for a sequence of stages or a process

{"type": "bars", "title": "...", "unit": "...", "items": [{"label": "...", "value": 1.0}]}
  for comparisons of quantities

{"type": "none"}
  when the sketch is not a figure (a table, a list, or unreadable)

Rules: keep labels short, expand abbreviations a reader would not know, and use the
book's own wording for names. Do not invent numbers that the page does not show."""


def clean(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def spec_for(client: httpx.Client, key: str, png: bytes, sketch: str) -> dict | None:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT + "\n\nSketch:\n" + sketch[:1500]},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode()
                        },
                    },
                ],
            }
        ],
        "max_tokens": 1200,
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


def _wrap(label: str, width: int = 18) -> str:
    return "\n".join(textwrap.wrap(label, width)) or label


def draw(spec: dict, destination: Path) -> bool:
    kind = spec.get("type")
    title = spec.get("title") or ""
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=DPI)
    ax.set_facecolor(PAPER)
    ax.axis("off")

    if kind == "flow" and spec.get("steps"):
        steps = spec["steps"][:8]
        for index, step in enumerate(steps):
            y = 1 - index * (1 / max(len(steps), 1))
            box = FancyBboxPatch(
                (0.06, y - 0.075),
                0.5,
                0.12,
                boxstyle="round,pad=0.012,rounding_size=0.02",
                linewidth=1.2,
                edgecolor=ACCENT,
                facecolor="#eef7f5",
            )
            ax.add_patch(box)
            ax.text(
                0.31,
                y - 0.015,
                _wrap(str(step), 34),
                ha="center",
                va="center",
                fontsize=9,
                color=INK,
            )
            if index < len(steps) - 1:
                ax.add_patch(
                    FancyArrowPatch(
                        (0.31, y - 0.085),
                        (0.31, y - 0.155),
                        arrowstyle="-|>",
                        mutation_scale=12,
                        color=ACCENT,
                    )
                )
        ax.set_xlim(0, 0.62)
        ax.set_ylim(0 - (1 / max(len(steps), 1)), 1)

    elif kind == "bars" and spec.get("items"):
        items = spec["items"][:10]
        labels = [str(item.get("label", "")) for item in items]
        values = [float(item.get("value", 0)) for item in items]
        positions = range(len(items))
        ax.barh(list(positions), values, color=ACCENT, height=0.6)
        ax.set_yticks(list(positions))
        ax.set_yticklabels(labels, fontsize=9, color=INK)
        ax.invert_yaxis()
        ax.set_xticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        for position, value in zip(positions, values):
            ax.text(
                value,
                position,
                f"  {value:g}" + (spec.get("unit") or ""),
                va="center",
                fontsize=8.5,
                color=INK,
            )
        ax.set_xlim(0, max(values) * 1.25 if values else 1)

    elif kind == "tree" and spec.get("root"):
        # A layered tree: leaves take consecutive places along the bottom, every
        # parent sits above the middle of its children. Counting nodes in visit
        # order (the obvious way) drew a diagonal, which teaches nothing.
        positions: dict[int, tuple[float, float]] = {}
        counter = {"next": 0.0}

        def layout(node, depth: int) -> float:
            children = node.get("children") or []
            if children:
                xs = [layout(child, depth + 1) for child in children]
                x = sum(xs) / len(xs)
            else:
                x = counter["next"]
                counter["next"] += 1.0
            positions[id(node)] = (x, -float(depth))
            return x

        layout(spec["root"], 0)
        for node, _depth in [(n, 0) for n in [spec["root"]]]:
            pass

        def edges(node):
            for child in node.get("children") or []:
                start = positions[id(node)]
                end = positions[id(child)]
                ax.add_patch(
                    FancyArrowPatch(
                        (start[0], start[1] - 0.12),
                        (end[0], end[1] + 0.12),
                        arrowstyle="-",
                        linewidth=1.0,
                        color="#9fb7b3",
                        shrinkA=0,
                        shrinkB=0,
                    )
                )
                edges(child)

        edges(spec["root"])

        def nodes(node):
            x, y = positions[id(node)]
            ax.text(
                x,
                y,
                _wrap(str(node.get("label", "")), 16),
                ha="center",
                va="center",
                fontsize=8.5,
                color=INK,
                bbox={
                    "boxstyle": "round,pad=0.3",
                    "facecolor": "#eef7f5",
                    "edgecolor": ACCENT,
                    "linewidth": 1.0,
                },
            )
            for child in node.get("children") or []:
                nodes(child)

        nodes(spec["root"])
        width = max(counter["next"], 1)
        ax.set_xlim(-0.6, width - 0.4)
        ax.set_ylim(min(y for _x, y in positions.values()) - 0.5, 0.5)
    else:
        plt.close(fig)
        return False

    if title:
        ax.set_title(title, fontsize=10.5, color=INK, pad=10)
    fig.tight_layout()
    fig.savefig(destination, facecolor=PAPER, bbox_inches="tight")
    plt.close(fig)
    return True


def as_mermaid(spec: dict) -> str | None:
    """A spec as Mermaid source, or None when Mermaid cannot express it."""
    kind = spec.get("type")
    ident = 0

    def node(label: str) -> tuple[str, str]:
        nonlocal ident
        ident += 1
        key = f"n{ident}"
        safe = re.sub(r'["\n]', " ", str(label)).strip() or "?"
        return key, f'{key}["{safe}"]'

    if kind == "flow" and spec.get("steps"):
        lines = ["flowchart TD"]
        previous = None
        for step in spec["steps"]:
            key, shape = node(step)
            lines.append(f"  {shape}")
            if previous:
                lines.append(f"  {previous} --> {key}")
            previous = key
        return "\n".join(lines)

    if kind == "tree" and spec.get("root"):
        lines = ["flowchart TD"]

        def walk(item):
            key, shape = node(item.get("label", "?"))
            lines.append(f"  {shape}")
            for child in item.get("children") or []:
                child_key = walk(child)
                lines.append(f"  {key} --> {child_key}")
            return key

        walk(spec["root"])
        return "\n".join(lines)
    return None


def as_plot(spec: dict) -> str | None:
    """A bars spec as a plot block, which the site renders server side."""
    if spec.get("type") != "bars" or not spec.get("items"):
        return None
    payload = {
        "type": "bar",
        "title": spec.get("title") or "",
        "x": [str(item.get("label", "")) for item in spec["items"]],
        "series": [
            {
                "name": spec.get("unit") or "",
                "y": [float(item.get("value", 0)) for item in spec["items"]],
            }
        ],
    }
    return "```plot\n" + json.dumps(payload) + "\n```"


def upload(site: httpx.Client, token: str, path: Path) -> str | None:
    with path.open("rb") as handle:
        response = site.post(
            "/api/media",
            files={"file": (path.name, handle, "image/png")},
            headers={"X-CSRF-Token": token, **HEADERS},
        )
    if response.status_code >= 400:
        return None
    return response.json()["url"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pages", required=True)
    parser.add_argument("--token-file", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-pass", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default="figures")
    # mermaid: leave a diagram the site draws; image: draw a PNG and upload it.
    parser.add_argument("--format", choices=("mermaid", "image"), default="mermaid")
    args = parser.parse_args()

    key = Path(args.token_file).read_text().strip()
    pages = sorted(Path(args.pages).glob("*.md"))
    targets = []
    for page in pages:
        text = page.read_text()
        match = FENCE.search(text)
        if match:
            targets.append((page, match))
    if args.limit:
        targets = targets[: args.limit]
    print(f"{len(targets)} pages carry a figure sketch")

    site = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=180)
    site.get("/")
    token = site.cookies.get("melereview_csrf") or ""
    site.post(
        "/api/auth/login",
        json={"identifier": args.admin_user, "password": args.admin_pass},
        headers={"X-CSRF-Token": token, **HEADERS},
    ).raise_for_status()

    figures = Path(args.out)
    figures.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(args.pdf)

    def work(item):
        page, match = item
        number = int(page.stem)
        try:
            with httpx.Client() as api:
                png = doc[number - 1].get_pixmap(dpi=150).tobytes("png")
                spec = spec_for(api, key, png, clean(match.group(1)))
            if not spec or spec.get("type") == "none":
                return page, None, "no figure"

            text = page.read_text()
            if args.format == "mermaid":
                block = as_mermaid(spec) or as_plot(spec)
                if not block:
                    return page, None, "not expressible"
                replacement = (
                    "```plot\n" + block.split("```plot\n", 1)[1]
                    if block.startswith("```plot\n")
                    else "```mermaid\n" + block + "\n```"
                )
                page.write_text(text.replace(match.group(0), replacement))
                return page, "mermaid", spec.get("type")

            drawn = figures / f"{page.stem}.png"
            if not draw(spec, drawn):
                return page, None, "not drawable"
            url = upload(site, token, drawn)
            if not url:
                return page, None, "upload failed"
            page.write_text(
                text.replace(match.group(0), f"![{spec.get('title') or 'figure'}]({url})")
            )
            return page, url, spec.get("type")
        except Exception as exc:
            return page, None, str(exc)

    drawn_count = 0
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as pool:
        for done, (page, url, note) in enumerate(pool.map(work, targets), start=1):
            if url:
                drawn_count += 1
            if done % 10 == 0 or done == len(targets):
                print(f"[{done}/{len(targets)}] {drawn_count} figures drawn", flush=True)

    print(f"\n{drawn_count} of {len(targets)} sketches drawn and uploaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
