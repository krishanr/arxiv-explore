"""Refresh the top-cited papers per (arXiv category, posting year) from NASA ADS.

    uv run python -m pipeline.fetch [--max-queries N]

A full refresh is ~5k queries, about the ADS daily limit, so each run refreshes whatever is most
stale and stops before the budget runs out. Recent years go stale after a week and older years
after a month (their rankings barely move). Progress is saved as it goes, so an interrupted run
loses nothing.

Outputs (in data/):
  categories.json   {code: {count}}
  top_papers.jsonl  one paper per line, keyed by (category, year, rank), sorted for small git diffs
  state.json        {"<category>|<year>" or "<category>": ISO time last fetched}
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pipeline.ads import ADSClient, RateLimited, load_token
from pipeline.jsonl import read_jsonl

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TOP_K = 3
FIRST_YEAR = 1991  # arXiv's first year. Years before a category existed just return nothing.
RECENT_YEARS = 5
RECENT_TTL = timedelta(days=6)  # a bit under a week so the weekly run always picks these up
OLD_TTL = timedelta(days=27)
RESERVE = 100  # leave some daily budget for manual use
SAVE_EVERY = 200


def load_json(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default


def load_papers(path: Path) -> dict[tuple[str, int], list[dict]]:
    papers: dict[tuple[str, int], list[dict]] = {}
    if path.exists():
        for row in read_jsonl(path):
            papers.setdefault((row["category"], row["year"]), []).append(row)
    return papers


def save(categories: dict, papers: dict, state: dict) -> None:
    DATA.mkdir(exist_ok=True)
    (DATA / "categories.json").write_text(json.dumps(categories, indent=1, sort_keys=True) + "\n")
    (DATA / "state.json").write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    with open(DATA / "top_papers.jsonl", "w", encoding="utf-8") as f:
        for key in sorted(papers):
            f.writelines(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in papers[key])


def is_due(fetched: str | None, year: int | None, now: datetime) -> bool:
    if fetched is None:
        return True
    ttl = RECENT_TTL if year is not None and year > now.year - RECENT_YEARS else OLD_TTL
    return now - datetime.fromisoformat(fetched) >= ttl


def plan(
    codes: list[str], categories: dict, state: dict, now: datetime, first_year: int = FIRST_YEAR
) -> list[tuple[str, int]]:
    """Due (category, year) tasks, never-fetched first, then recent years, then the stalest."""
    tasks = []
    for code in codes:
        meta = categories.get(code)
        if not meta or not meta["count"]:
            continue
        for year in range(first_year, now.year + 1):
            fetched = state.get(f"{code}|{year}")
            if is_due(fetched, year, now):
                tasks.append((fetched is not None, year <= now.year - RECENT_YEARS, fetched or "", code, year))
    return [(code, year) for *_, code, year in sorted(tasks)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--max-queries", type=int, default=4800)
    args = parser.parse_args(argv)

    client = ADSClient(load_token(ROOT / ".env"))
    now = datetime.now(UTC)
    codes = [t["code"] for t in load_json(DATA / "taxonomy.json", [])]
    if not codes:
        raise SystemExit("data/taxonomy.json is missing; run `python -m pipeline.taxonomy` first.")
    categories = load_json(DATA / "categories.json", {})
    state = load_json(DATA / "state.json", {})
    papers = load_papers(DATA / "top_papers.jsonl")

    def budget_left() -> bool:
        if client.calls >= args.max_queries:
            return False
        return client.remaining is None or client.remaining > RESERVE

    done = 0
    try:
        # 1. Category sizes and first years (one query each, monthly).
        for code in codes:
            if budget_left() and is_due(state.get(code), None, now):
                categories[code] = client.category_summary(code)
                state[code] = now.isoformat(timespec="seconds")

        # 2. Top papers for each due (category, year).
        tasks = plan(codes, categories, state, now)
        print(f"{len(tasks)} (category, year) pairs due; ADS budget remaining: {client.remaining}")
        for code, year in tasks:
            if not budget_left():
                break
            top = client.top_papers(code, year, TOP_K)
            papers[(code, year)] = [{"category": code, "year": year, "rank": i + 1, **p} for i, p in enumerate(top)]
            if not top:
                papers.pop((code, year), None)
            state[f"{code}|{year}"] = now.isoformat(timespec="seconds")
            done += 1
            if done % SAVE_EVERY == 0:
                save(categories, papers, state)
                print(f"  {done}/{len(tasks)} done, budget remaining {client.remaining}")
    except RateLimited as e:
        print(f"Hit the ADS rate limit (resets at {e}); saving progress.")
    finally:
        save(categories, papers, state)

    left = len(plan(codes, categories, state, now))
    print(f"Refreshed {done} pairs with {client.calls} queries; {left} still due. Budget left: {client.remaining}")


if __name__ == "__main__":
    main()
