"""robots.txt, sitemap.xml and real 404s for unknown paths."""

import re
import xml.etree.ElementTree as ET

import pytest

import app as site

SITE = "https://arxivexplorer.com"
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@pytest.fixture(scope="module")
def client():
    return site.server.test_client()


def test_robots_txt(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200 and r.mimetype == "text/plain"
    body = r.get_data(as_text=True)
    assert "User-agent: *" in body and "Disallow: /_dash" not in body
    assert f"Sitemap: {SITE}/sitemap.xml" in body


@pytest.fixture(scope="module")
def sitemap_urls(client):
    r = client.get("/sitemap.xml")
    assert r.status_code == 200 and r.mimetype == "application/xml"
    root = ET.fromstring(r.get_data())
    urls = [u.findtext("s:loc", namespaces=NS) for u in root.findall("s:url", NS)]
    lastmods = {u.findtext("s:lastmod", namespaces=NS) for u in root.findall("s:url", NS)}
    assert len(lastmods) == 1 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", lastmods.pop())
    return urls


def test_sitemap_lists_home_groups_categories_and_papers(sitemap_urls):
    assert sitemap_urls[0] == f"{SITE}/"
    assert f"{SITE}/?cat=group%3APhysics" in sitemap_urls
    assert f"{SITE}/?cat=cs.LG" in sitemap_urls
    assert sum("&paper=" in u for u in sitemap_urls) == len(site.papers)
    assert len(sitemap_urls) == len(set(sitemap_urls)) < 50_000


def test_sitemap_urls_match_canonical_tags(client, sitemap_urls):
    for url in [f"{SITE}/?cat=cs.LG", next(u for u in sitemap_urls if "paper=1706.03762" in u)]:
        html = client.get(url.removeprefix(SITE)).get_data(as_text=True)
        canonical = re.search(r'<link rel="canonical" href="([^"]*)">', html).group(1).replace("&amp;", "&")
        assert canonical == url


@pytest.mark.parametrize("path", ["/nonexistent-page", "/cs.LG", "/wp-login.php", "/a/b/c"])
def test_unknown_paths_are_404(client, path):
    r = client.get(path)
    assert r.status_code == 404
    body = r.get_data(as_text=True)
    assert 'href="/"' in body and "react-entry-point" not in body


@pytest.mark.parametrize("path", ["/", "/?cat=cs.LG", "/_dash-layout", "/_dash-dependencies", "/assets/style.css"])
def test_real_routes_still_work(client, path):
    assert client.get(path).status_code == 200
