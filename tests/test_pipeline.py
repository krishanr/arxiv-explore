from datetime import UTC, datetime, timedelta

from pipeline.ads import arxiv_id, posting_year_filter, to_paper
from pipeline.fetch import is_due, plan
from pipeline.jsonl import read_jsonl
from pipeline.taxonomy import parse

NOW = datetime(2026, 11, 25, tzinfo=UTC)


def test_posting_year_filter_styles():
    assert posting_year_filter(2017) == "identifier:2017arXiv*"
    old = posting_year_filter(2003)
    assert old.startswith("identifier:(") and "arXiv\\:hep-th/03*" in old and "arXiv\\:math/03*" in old
    both = posting_year_filter(2007)
    assert "2007arXiv*" in both and "arXiv\\:hep-th/07*" in both
    assert "arXiv\\:hep-th/91*" in posting_year_filter(1991)


def test_arxiv_ids_and_years():
    assert arxiv_id(["10.1000/xyz", "arXiv:1706.03762", "2017arXiv170603762V"]) == "1706.03762"
    assert arxiv_id(["10.1000/xyz"]) is None


def test_to_paper_truncates_authors():
    doc = {
        "identifier": ["arXiv:1"],
        "title": ["T"],
        "author": [f"A{i}" for i in range(50)],
        "citation_count": 5,
    }
    p = to_paper(doc)
    assert p["arxiv_id"] == "1" and p["title"] == "T" and len(p["authors"]) == 10 and p["n_authors"] == 50


def test_is_due():
    recent, old = NOW.year, NOW.year - 10
    assert is_due(None, old, NOW)
    assert not is_due((NOW - timedelta(days=3)).isoformat(), recent, NOW)
    assert is_due((NOW - timedelta(days=7)).isoformat(), recent, NOW)
    assert not is_due((NOW - timedelta(days=7)).isoformat(), old, NOW)
    assert is_due((NOW - timedelta(days=30)).isoformat(), old, NOW)


def test_plan_orders_unfetched_then_recent_then_stalest():
    categories = {"a": {"count": 10}, "b": {"count": 0}}
    week_ago, month_ago = (NOW - timedelta(days=8)).isoformat(), (NOW - timedelta(days=40)).isoformat()
    state = {f"a|{y}": week_ago for y in range(2020, 2027)} | {"a|2020": month_ago, "a|2021": month_ago}
    del state["a|2024"]
    tasks = plan(["a", "b"], categories, state, NOW, first_year=2020)
    # 2024 never fetched; 2022-2026 are recent (week-old => due); 2020/2021 are old and month-stale.
    assert tasks[0] == ("a", 2024)
    assert set(tasks[1:5]) == {("a", 2022), ("a", 2023), ("a", 2025), ("a", 2026)}
    assert set(tasks[5:]) == {("a", 2020), ("a", 2021)}


def test_taxonomy_parse():
    html = """<div id="category_taxonomy_list">
      <h2>Physics</h2><h3>Astrophysics<br><span>(astro-ph)</span></h3>
      <h4>astro-ph.CO <span>(Cosmology and Nongalactic Astrophysics)</span></h4><p>Early universe.</p>
      <h2>Mathematics</h2><h4>math.AP <span>(Analysis of PDEs)</span></h4><p>PDEs.</p></div>"""
    rows = {r["code"]: r for r in parse(html)}
    assert rows["astro-ph.CO"] == {
        "code": "astro-ph.CO",
        "name": "Cosmology and Nongalactic Astrophysics",
        "group": "Physics",
        "archive": "Astrophysics",
        "description": "Early universe.",
    }
    assert rows["math.AP"]["archive"] == "Mathematics" and rows["math.AP"]["description"] == "PDEs."
    assert rows["astro-ph"]["name"] == "Astrophysics (general)"


def test_jsonl_roundtrip_with_unicode_line_separators(tmp_path):
    import json

    rows = [{"abstract": "line one\u2028line two\x85end"}, {"abstract": "ok"}]
    path = tmp_path / "x.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    assert read_jsonl(path) == rows
