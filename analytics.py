"""Umami analytics, served from our own domain.

Ad/tracker blockers often block cloud.umami.is, so we serve Umami's script at /u/script.js and forward its
events from /api/send to Umami Cloud. Enabled only when UMAMI_WEBSITE_ID is set (see fly.toml), so local
runs don't load it. `data-domains` also stops the script from recording anything off the production domain.
"""

import os
import time
import urllib.error
import urllib.request

from flask import Flask, Response, request

SCRIPT_URL = "https://cloud.umami.is/script.js"
SEND_URL = "https://gateway.umami.is/api/send"  # the script's default collection endpoint
WEBSITE_ID = os.environ.get("UMAMI_WEBSITE_ID", "")
DOMAINS = os.environ.get("UMAMI_DOMAINS", "arxivexplorer.com,www.arxivexplorer.com")
# Umami's CDN rejects Python's default User-Agent with a 403.
FETCH_UA = "arxiv-explorer/1.0 (+https://arxivexplorer.com)"
SCRIPT_PATH = "/u/script.js"
SCRIPT_TTL = 24 * 3600

_script: dict = {"body": b"", "fetched": 0.0}


def external_scripts() -> list[dict]:
    """Script tag attributes for Dash's `external_scripts`; empty when analytics is off."""
    if not WEBSITE_ID:
        return []
    return [
        {
            "src": SCRIPT_PATH,
            "defer": "defer",
            "data-website-id": WEBSITE_ID,
            "data-domains": DOMAINS,
            # "/" makes the script post to same-origin /api/send (it strips the trailing slash).
            "data-host-url": "/",
        }
    ]


def _client_ip() -> str:
    # Fly puts the visitor's address in Fly-Client-IP; fall back to the direct peer.
    return request.headers.get("Fly-Client-IP") or request.remote_addr or ""


def register(server: Flask) -> None:
    if not WEBSITE_ID:
        return

    @server.get(SCRIPT_PATH)
    def umami_script():
        if time.time() - _script["fetched"] > SCRIPT_TTL or not _script["body"]:
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(SCRIPT_URL, headers={"User-Agent": FETCH_UA}), timeout=10
                ) as r:
                    _script.update(body=r.read(), fetched=time.time())
            except urllib.error.URLError:
                if not _script["body"]:
                    return Response("", status=502)
        return Response(
            _script["body"], mimetype="application/javascript", headers={"Cache-Control": "public, max-age=3600"}
        )

    @server.post("/api/send")
    def umami_send():
        headers = {
            "Content-Type": "application/json",
            "User-Agent": request.headers.get("User-Agent", ""),
            "X-Forwarded-For": _client_ip(),
        }
        if cache := request.headers.get("x-umami-cache"):
            headers["x-umami-cache"] = cache
        req = urllib.request.Request(SEND_URL, data=request.get_data(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return Response(r.read(), status=r.status, mimetype="application/json")
        except urllib.error.HTTPError as e:
            return Response(e.read(), status=e.code, mimetype="application/json")
        except urllib.error.URLError:
            return Response("", status=502)
