"""Crawler-visible HTML: per-page title, meta tags and pre-rendered content in the initial response."""

import re

import pytest

import app as site

SITE = "https://arxivexplorer.com"


@pytest.fixture(scope="module")
def client():
    return site.server.test_client()


def get(client, query: str = "") -> str:
    r = client.get("/" + query)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def meta(html: str, attr: str, name: str) -> str | None:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)"', html)
    return m.group(1) if m else None


def test_home_page(client):
    html = get(client)
    assert "<title>arXiv Explorer: the most-cited arXiv preprints by category and year</title>" in html
    assert f'<link rel="canonical" href="{SITE}/">' in html
    assert meta(html, "property", "og:url") == f"{SITE}/"
    assert meta(html, "name", "description")
    # Pre-rendered content: top papers and links to every group, inside the React entry point.
    entry = html[html.index('id="react-entry-point"') :]
    assert "Adam: A Method for Stochastic Optimization" in entry
    assert 'href="/?cat=group%3APhysics"' in entry


def test_category_page(client):
    html = get(client, "?cat=cs.LG")
    assert "<title>Most-cited Machine Learning (cs.LG) papers by year · arXiv Explorer</title>" in html
    assert f'<link rel="canonical" href="{SITE}/?cat=cs.LG">' in html
    assert meta(html, "property", "og:title") == "Most-cited Machine Learning (cs.LG) papers by year"
    assert "Machine Learning" in meta(html, "name", "description")


def test_group_page_links_to_its_categories(client):
    html = get(client, "?cat=group:Physics")
    assert "<title>Most-cited Physics papers by year · arXiv Explorer</title>" in html
    assert 'href="/?cat=hep-th"' in html


def test_paper_page(client):
    html = get(client, "?cat=cs.LG&paper=1706.03762")
    assert "<title>Attention Is All You Need (2017) · 14,575 citations · arXiv Explorer</title>" in html
    desc = meta(html, "name", "description")
    assert desc.startswith("Vaswani, Ashish et al., 2017. 14,575 citations.")
    assert meta(html, "name", "twitter:card") == "summary"
    assert "The dominant sequence transduction models" in html  # abstract is pre-rendered


def test_paper_canonical_is_the_same_whichever_category_it_was_reached_from(client):
    a = get(client, "?cat=cs.LG&paper=1706.03762")
    b = get(client, "?cat=cs.CL&paper=1706.03762")
    canon = re.search(r'<link rel="canonical" href="([^"]*)">', a).group(1)
    assert canon == re.search(r'<link rel="canonical" href="([^"]*)">', b).group(1)
    assert canon.startswith(f"{SITE}/?cat=") and canon.endswith("&amp;paper=1706.03762")


def test_invalid_or_malicious_params_fall_back_to_home(client):
    html = get(client, "?cat=%3Cscript%3Ealert(1)%3C/script%3E&paper=%22%3E%3Cimg%20src=x%3E")
    assert "<script>alert(1)" not in html and "<img src=x>" not in html
    assert f'<link rel="canonical" href="{SITE}/">' in html


def test_titles_strip_ads_markup_and_escape_html(client):
    # ADS titles carry formatting tags, e.g. "Atomically Thin MoS<SUB>2</SUB>: ...".
    paper_id = next(i for i, t in site.papers["title"].items() if t.startswith("Atomically Thin MoS<SUB>2</SUB>"))
    html = get(client, f"?paper={paper_id}")
    assert "<title>Atomically Thin MoS2: A New Direct-Gap Semiconductor (" in html
    assert "<SUB>" not in html and "&lt;SUB&gt;" not in html


def test_special_characters_are_escaped():
    paper_id = next(i for i, t in site.papers["title"].items() if "&" in t)
    head, entry = site.page_html(*site.parse_url(f"?paper={paper_id}"))
    title = site.plain_text(site.papers.at[paper_id, "title"])
    assert title.replace("&", "&amp;") in head and title not in head


def test_app_still_boots_with_custom_index(client):
    html = get(client, "?cat=cs.LG")
    assert '<div id="react-entry-point">' in html and 'id="_dash-config"' in html
