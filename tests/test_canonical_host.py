"""Permanent redirects from duplicate hosts (fly.dev, www) to the canonical domain."""

import pytest

import app as site


@pytest.fixture(scope="module")
def client():
    return site.server.test_client()


@pytest.mark.parametrize("host", ["arxiv-explore.fly.dev", "www.arxivexplorer.com"])
@pytest.mark.parametrize(
    ("path", "target"),
    [
        ("/", "https://arxivexplorer.com/"),
        ("/?cat=cs.LG&paper=1706.03762", "https://arxivexplorer.com/?cat=cs.LG&paper=1706.03762"),
        ("/sitemap.xml", "https://arxivexplorer.com/sitemap.xml"),
        ("/nonexistent-page", "https://arxivexplorer.com/nonexistent-page"),
    ],
)
def test_duplicate_hosts_redirect_permanently(client, host, path, target):
    r = client.get(path, headers={"Host": host})
    assert r.status_code == 301
    assert r.headers["Location"] == target


@pytest.mark.parametrize("host", ["arxivexplorer.com", "localhost", "127.0.0.1:8050"])
def test_canonical_and_local_hosts_are_served(client, host):
    assert client.get("/", headers={"Host": host}).status_code == 200


def test_health_check_is_never_redirected(client):
    r = client.get("/healthz", headers={"Host": "arxiv-explore.fly.dev"})
    assert r.status_code == 200 and r.get_data(as_text=True) == "ok"


def test_non_get_requests_are_not_redirected(client):
    # Redirecting a POST (e.g. Dash callbacks, analytics events) would drop its body.
    r = client.post("/_dash-update-component", headers={"Host": "arxiv-explore.fly.dev"}, json={})
    assert r.status_code != 301
