"""Minimal NASA ADS search client.

ADS docs: https://ui.adsabs.harvard.edu/help/api/
The search API allows ~5,000 requests/day per token; remaining budget comes back in X-RateLimit-* headers.
"""

import os
import time
from pathlib import Path

import requests

SEARCH_URL = "https://api.adsabs.harvard.edu/v1/search/query"

# arXiv archives that used old-style IDs (archive/YYMMNNN) before April 2007.
OLD_ARCHIVES = [
    "astro-ph",
    "cond-mat",
    "gr-qc",
    "hep-ex",
    "hep-lat",
    "hep-ph",
    "hep-th",
    "math-ph",
    "nlin",
    "nucl-ex",
    "nucl-th",
    "physics",
    "quant-ph",
    "math",
    "cs",
    "q-bio",
    "acc-phys",
    "adap-org",
    "alg-geom",
    "ao-sci",
    "atom-ph",
    "bayes-an",
    "chao-dyn",
    "chem-ph",
    "cmp-lg",
    "comp-gas",
    "dg-ga",
    "funct-an",
    "mtrl-th",
    "patt-sol",
    "plasm-ph",
    "q-alg",
    "solv-int",
    "supr-con",
]

MAX_AUTHORS = 10


class RateLimited(Exception):
    pass


def load_token(env_file: Path) -> str:
    token = os.environ.get("ADS_API_TOKEN")
    if not token and env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("ADS_API_TOKEN="):
                token = line.split("=", 1)[1].strip().strip("\"'")
    if not token:
        raise SystemExit("ADS_API_TOKEN is not set (env var or .env file).")
    return token


def posting_year_filter(year: int) -> str:
    """ADS query clause matching papers first posted to arXiv in `year`.

    ADS's `year` field is the journal publication year, so we match on the arXiv identifier instead:
    new-style IDs (2007-04 onward) have an eprint bibcode like 2017arXiv170603762V; old-style IDs look
    like arXiv:hep-th/0301240. 2007 contains both styles.
    """
    new = f"identifier:{year}arXiv*"
    yy = f"{year % 100:02d}"
    old = "identifier:(" + " OR ".join(f"arXiv\\:{a}/{yy}*" for a in OLD_ARCHIVES) + ")"
    if year >= 2008:
        return new
    if year <= 2006:
        return old
    return f"({new} OR {old})"


def arxiv_id(identifiers: list[str]) -> str | None:
    for ident in identifiers:
        if ident.startswith("arXiv:"):
            return ident.removeprefix("arXiv:")
    return None


def to_paper(doc: dict) -> dict:
    authors = doc.get("author", [])
    return {
        "arxiv_id": arxiv_id(doc.get("identifier", [])),
        "bibcode": doc.get("bibcode"),
        "title": (doc.get("title") or [""])[0],
        "authors": authors[:MAX_AUTHORS],
        "n_authors": len(authors),
        "abstract": doc.get("abstract", ""),
        "citations": doc.get("citation_count", 0),
        "categories": doc.get("arxiv_class", []),
    }


class ADSClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"
        self.remaining: int | None = None
        self.calls = 0

    def search(self, **params) -> dict:
        for attempt in range(4):
            r = self.session.get(SEARCH_URL, params=params, timeout=60)
            self.calls += 1
            if "X-RateLimit-Remaining" in r.headers:
                self.remaining = int(r.headers["X-RateLimit-Remaining"])
            if r.status_code == 429:
                raise RateLimited(r.headers.get("X-RateLimit-Reset", ""))
            if r.status_code >= 500 or r.status_code == 408:
                time.sleep(2**attempt)
                continue
            r.raise_for_status()
            return r.json()["response"]
        r.raise_for_status()
        raise RuntimeError(f"ADS request failed after retries: {r.status_code}")

    def category_summary(self, category: str) -> dict:
        """Total paper count for a category."""
        return {"count": self.search(q=f'arxiv_class:"{category}"', rows=0)["numFound"]}

    def top_papers(self, category: str, year: int, k: int = 3) -> list[dict]:
        resp = self.search(
            q=f'arxiv_class:"{category}" {posting_year_filter(year)}',
            sort="citation_count desc",
            rows=k,
            fl="bibcode,identifier,title,author,abstract,citation_count,arxiv_class",
        )
        return [p for d in resp["docs"] if (p := to_paper(d))["arxiv_id"]]
