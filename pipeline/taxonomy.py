"""Scrape arXiv's category taxonomy into data/taxonomy.json.

Run rarely (categories change maybe once a year): `uv run python -m pipeline.taxonomy`
"""

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://arxiv.org/category_taxonomy"
OUT = Path(__file__).resolve().parents[1] / "data" / "taxonomy.json"

# Archive-level codes still attached to older papers (e.g. astro-ph before its 2009 split).
GENERAL = {
    "astro-ph": ("Physics", "Astrophysics", "Astrophysics papers from before the archive was split (2009)."),
    "cond-mat": ("Physics", "Condensed Matter", "Condensed matter papers without a subject class."),
    "q-bio": (
        "Quantitative Biology",
        "Quantitative Biology",
        "Quantitative biology papers without a subject class.",
    ),
}


def parse(html: str) -> list[dict]:
    root = BeautifulSoup(html, "html.parser").find(id="category_taxonomy_list")
    rows, group, archive, current = [], None, None, None
    for tag in root.find_all(["h2", "h3", "h4", "p"]):
        text = re.sub(r"\s+", " ", tag.get_text(" ")).strip()
        if tag.name == "h2":
            group = archive = text
        elif tag.name == "h3":
            archive = re.sub(r"\s*\(.*\)$", "", text)
        elif tag.name == "h4":
            code, _, name = text.partition(" ")
            current = {"code": code, "name": name.strip("() "), "group": group, "archive": archive}
            rows.append(current)
        elif tag.name == "p" and current is not None and "description" not in current:
            current["description"] = text
    for code, (grp, arch, desc) in GENERAL.items():
        rows.append({"code": code, "name": f"{arch} (general)", "group": grp, "archive": arch, "description": desc})
    return rows


def main():
    html = requests.get(URL, timeout=60).text
    rows = parse(html)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} categories to {OUT}")


if __name__ == "__main__":
    main()
