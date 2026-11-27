"""Security headers on every response, a CSP that covers Dash's inline scripts, and no dev endpoints."""

import base64
import hashlib
import re

import pytest

import app as site


@pytest.fixture(scope="module")
def client():
    return site.server.test_client()


@pytest.mark.parametrize("path", ["/", "/?cat=cs.LG&paper=1706.03762", "/sitemap.xml", "/robots.txt", "/nope"])
def test_security_headers_on_every_response(client, path):
    h = client.get(path).headers
    assert h["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    csp = h["Content-Security-Policy"]
    for directive in ["default-src 'self'", "object-src 'none'", "frame-ancestors 'none'", "base-uri 'self'"]:
        assert directive in csp


def directive(csp: str, name: str) -> str:
    return next(d.strip() for d in csp.split(";") if d.strip().startswith(name + " "))


def test_csp_allows_every_inline_script_dash_runs_and_nothing_else(client):
    r = client.get("/")
    html = r.get_data(as_text=True)
    script_src = directive(r.headers["Content-Security-Policy"], "script-src")
    assert "'unsafe-inline'" not in script_src and "'unsafe-eval'" not in script_src
    html_without_comments = re.sub(r"<!--.*?-->", "", html, flags=re.S)  # e.g. the IE-only warning
    inline = re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>(.*?)</script>", html_without_comments, re.S)
    executable = [body for attrs, body in inline if "application/json" not in attrs]
    assert len(executable) >= 3  # Dash's renderer bootstrap + our two clientside callbacks
    for body in executable:
        digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in script_src


def test_csp_allows_the_bootstrap_stylesheet(client):
    style_src = directive(client.get("/").headers["Content-Security-Policy"], "style-src")
    assert "https://cdn.jsdelivr.net" in style_src


def test_dev_reload_endpoint_is_hidden_in_production(client):
    assert client.get("/_reload-hash").status_code == 404
