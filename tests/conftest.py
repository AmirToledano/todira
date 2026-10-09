import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# In production images, todira_common is copied to /app/todira_common and each service's own
# files (scraper/*.py etc) are copied directly into /app too, with PYTHONPATH=/app (see
# bot/scraper/website Dockerfiles) - so `import todira_common` and e.g. `import normalize` both
# resolve as top-level modules. Mirror that layout here so tests import the same way production
# does, without needing package installs.
sys.path.insert(0, str(_ROOT / "common"))
sys.path.insert(0, str(_ROOT / "scraper"))
sys.path.insert(0, str(_ROOT / "bot"))
# website/ deliberately NOT added here: both scraper/main.py and website/main.py are named
# main.py, so a bare `import main` would be ambiguous once both directories are on sys.path (last
# one inserted wins). test_website_contact.py loads website/main.py directly via importlib
# instead, under an unambiguous name — see that file's own comment.


# --- legacy ?uid= -> signed ?t= shim for the website tests (2026-10-02) ---------------------------
# The site no longer trusts a bare ?uid=<telegram id> (see todira_common/uid_token.py); the bot's
# links carry a signed ?t= token instead. Most website tests were written when `uid=222` was how a
# request "logged in", and test business logic, not auth. So every TestClient request that names a
# uid (in the URL, params or form data) also gets the signed token for that uid appended — exactly
# what a real bot link carries. Tests that check the bare-uid rejection itself opt out with
# @pytest.mark.no_uid_shim.
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _sign_legacy_uid_requests(request, monkeypatch):
    if request.node.get_closest_marker("no_uid_shim"):
        return
    from urllib.parse import parse_qs, urlsplit

    from starlette.testclient import TestClient
    from todira_common.uid_token import generate_uid_token

    original = TestClient.request

    def _uid_from(url, params, data):
        candidates = []
        query = urlsplit(str(url)).query
        if query:
            parsed = parse_qs(query)
            if "t" in parsed:
                return None
            candidates += parsed.get("uid", [])
        if isinstance(params, dict):
            if "t" in params:
                return None
            candidates.append(params.get("uid"))
        if isinstance(data, dict):
            candidates.append(data.get("uid"))
        for value in candidates:
            if value is not None and str(value).isdigit():
                return int(value)
        return None

    def request_with_signed_uid(self, method, url, *args, **kwargs):
        uid = _uid_from(url, kwargs.get("params"), kwargs.get("data"))
        if uid is not None:
            token = generate_uid_token(uid)
            if isinstance(kwargs.get("params"), dict):
                # httpx replaces a URL's own query string when `params` is given, so add it there.
                kwargs["params"] = {**kwargs["params"], "t": token}
            else:
                url = f"{url}{'&' if '?' in str(url) else '?'}t={token}"
        return original(self, method, url, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", request_with_signed_uid)


def pytest_configure(config):
    config.addinivalue_line("markers", "no_uid_shim: do not add the signed ?t= token to requests that name a uid")


@pytest.fixture(autouse=True)
def _reset_homeless_fetch_counters(monkeypatch):
    """homeless_client keeps per-PROCESS counters (ZenRows fallback credits used, free-route failure streak); a test run is one
    process, so every test starts from a clean slate instead of inheriting the previous test's count."""
    import homeless_client

    monkeypatch.setattr(homeless_client, "_zenrows_requests_this_process", 0)
    monkeypatch.setattr(homeless_client, "_free_consecutive_failures", 0)
    monkeypatch.setattr(homeless_client, "_free_route_blocked", False)
