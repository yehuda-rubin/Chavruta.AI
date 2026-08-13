"""Every backend path the browser calls must be proxied — in BOTH the dev rewrites and nginx.

This is the third time the same failure shape has appeared. A path missing from the proxy list does
not error anywhere: Next owns the origin, finds no page, and serves its own 404 HTML, which the
client tries to parse as JSON. The user sees whatever that particular screen shows when a call fails
— for /jobs it was every async generation returning markup, for /orgs it was the school panel saying
"you do not have permission", which sent the search in entirely the wrong direction for weeks. The
server logs stay clean throughout, because nothing ever reached the server.

Both config files carry a comment telling the reader to keep them in step. This is what actually
keeps them in step.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_TS = ROOT / "web" / "lib" / "api.ts"
NEXT_CFG = ROOT / "web" / "next.config.mjs"
NGINX = ROOT / "docker" / "nginx.conf"

# Paths the client calls that are NOT backend routes, with the reason. Anything else the client
# fetches has to be proxied.
NOT_BACKEND = {
    "feedback",     # bare /feedback is a real Next page; only /feedback/submit is the API, and both
                    # config files special-case it (see the comments there)
}


def _client_prefixes() -> set[str]:
    """First path segment of every same-origin path web/lib/api.ts fetches."""
    src = API_TS.read_text(encoding="utf-8")
    found = set()
    # req<T>("/x/y") and req<T>(`/x/${id}`) — both quote styles, template literals included.
    for m in re.finditer(r"""req<[^>]*>\(\s*[`"']/([a-z0-9_-]+)""", src, re.I):
        found.add(m.group(1).lower())
    return found - NOT_BACKEND


def _next_prefixes() -> set[str]:
    src = NEXT_CFG.read_text(encoding="utf-8")
    return {m.group(1).lower() for m in re.finditer(r"""proxy\(\s*["']([a-z0-9_-]+)["']""", src, re.I)}


def _nginx_prefixes() -> set[str]:
    """The alternation group in nginx's API location, plus any dedicated location block."""
    src = NGINX.read_text(encoding="utf-8")
    out: set[str] = set()
    for m in re.finditer(r"location\s+~\s+\^/\(([^)]+)\)", src):
        out.update(p.strip().lower() for p in m.group(1).split("|"))
    for m in re.finditer(r"location\s+~\s+\^/([a-z0-9_-]+)/", src, re.I):
        out.add(m.group(1).lower())
    return out


def test_the_client_calls_nothing_that_next_fails_to_proxy():
    missing = _client_prefixes() - _next_prefixes()
    assert not missing, (
        f"web/lib/api.ts calls /{sorted(missing)} but web/next.config.mjs does not proxy it — "
        f"in dev those calls return Next's 404 HTML, not JSON")


def test_the_client_calls_nothing_that_nginx_fails_to_proxy():
    missing = _client_prefixes() - _nginx_prefixes()
    assert not missing, (
        f"web/lib/api.ts calls /{sorted(missing)} but docker/nginx.conf does not proxy it — "
        f"IN PRODUCTION those calls return the app's HTML and the feature is silently dead")


def test_the_two_config_files_agree():
    """They describe the same API surface. Drifting apart means a feature that works in dev and is
    dead in production, which is the hardest version of this bug to see."""
    only_next = _next_prefixes() - _nginx_prefixes()
    only_nginx = _nginx_prefixes() - _next_prefixes() - NOT_BACKEND - {"admin"}
    assert not only_next, f"proxied in next.config.mjs but not in nginx.conf: {sorted(only_next)}"
    assert not only_nginx, f"proxied in nginx.conf but not in next.config.mjs: {sorted(only_nginx)}"


@pytest.mark.parametrize("prefix", ["orgs", "jobs", "me", "sessions"])
def test_the_paths_this_has_already_bitten_us_on(prefix):
    """Named individually so a regression says which one, and so /orgs and /jobs — the two that
    actually shipped broken — can never quietly fall out of the lists again."""
    assert prefix in _next_prefixes(), f"/{prefix} lost its dev rewrite"
    assert prefix in _nginx_prefixes(), f"/{prefix} lost its nginx proxy"
