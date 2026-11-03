"""2026-11-02 (owner): the site menu (base.html). Every row of the hamburger menu has an icon and a name (the owner's
admin rows used to be three bare icons), the extra pages sit in a labelled "more" section, the owner gets a labelled
admin section, and the desktop row gets a small "more" menu with the same extra pages."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from base64 import b64encode
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import itsdangerous
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_nav_menu", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402
from i18n import TRANSLATIONS  # noqa: E402

MORE_PAGES = ("/rent", "/calculator", "/moving-checklist", "/rental-contract-check", "/post")
NEW_KEYS = ("nav.more", "nav.channel", "nav.admin", "nav.admin_dashboard", "nav.admin_messages",
            "nav.admin_users", "nav.admin_posts")


@pytest.fixture
def client():
    with patch.object(website_main, "OWNER_TELEGRAM_USER_ID", "111"):
        yield TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _panel(html: str) -> str:
    start = html.index('id="nav-panel"')
    return html[start:html.index('class="nav-panel-foot"', start)]


def _desktop_more(html: str) -> str:
    start = html.index('id="nav-more"')
    return html[start:html.index("</details>", start)]


def _rows(chunk: str) -> list[tuple[str, str]]:
    """(opening tag, inner html) of every link in a chunk of the menu."""
    return re.findall(r"(<a [^>]*>)(.*?)</a>", chunk, flags=re.S)


def test_every_menu_row_has_an_icon_and_a_name(client):
    resp = client.get("/moving-checklist?lang=he")
    assert resp.status_code == 200
    rows = _rows(_panel(resp.text))
    assert len(rows) >= 10
    for _tag, inner in rows:
        assert '<svg class="ic' in inner
        label = re.search(r"<span>(.*?)</span>", inner)
        assert label and label.group(1).strip()


def test_the_more_section_lists_the_extra_pages_the_channel_and_contact(client):
    panel = _panel(client.get("/moving-checklist?lang=he").text)
    more = panel[panel.index('id="nav-section-more"'):]
    assert 'aria-labelledby="nav-section-more"' in panel
    assert '<span class="nav-section-title" id="nav-section-more">עוד</span>' in panel
    for path in MORE_PAGES:
        assert f'href="{path}"' in more
    assert 'href="https://t.me/todira_dirot" target="_blank" rel="noopener"' in more
    assert "ערוץ הטלגרם" in more
    assert 'href="/contact"' in more and "צור קשר" in more


def test_the_current_extra_page_is_highlighted_in_both_menus(client):
    html = client.get("/moving-checklist?lang=he").text
    active = [tag for tag, _ in _rows(_panel(html)) if 'aria-current="page"' in tag]
    assert active == ['<a href="/moving-checklist" class="active" aria-current="page">']
    desktop = _desktop_more(html)
    assert '<summary class="active">' in desktop
    assert '<a href="/moving-checklist" class="active" aria-current="page">' in desktop


def test_the_desktop_more_menu_holds_the_extra_pages_and_is_not_active_elsewhere(client):
    html = client.get("/rental-contract-check?lang=en").text
    desktop = _desktop_more(html)
    for path in MORE_PAGES:
        assert f'href="{path}"' in desktop
    assert "Telegram channel" in desktop and ">More<" in desktop
    assert '<summary class="active">' in desktop  # the contract page is one of the extra pages

    with patch.object(website_main, "_rent_medians", lambda: {}):
        calc = client.get("/calculator?lang=he").text
    assert '<a href="/calculator" class="active" aria-current="page">' in _panel(calc)
    assert '<a href="/moving-checklist" class="active"' not in calc


def test_a_visitor_sees_no_admin_section(client):
    html = client.get("/moving-checklist?lang=he").text
    assert "nav-section-admin" not in html
    assert 'href="/admin' not in html


def _session_cookie(data: dict) -> str:
    signer = itsdangerous.TimestampSigner(website_main.SESSION_SECRET_KEY)
    return signer.sign(b64encode(json.dumps(data).encode("utf-8"))).decode("utf-8")


class _FakeSession:
    def __init__(self, user):
        self._user = user

    def get(self, model_cls, obj_id):
        return self._user if self._user.id == obj_id else None

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: [])

    def execute(self, stmt):
        return SimpleNamespace(first=lambda: self._user)


@contextmanager
def _wrap(session):
    yield session


def test_the_owner_gets_a_labelled_admin_section(client):
    owner = SimpleNamespace(id=1, telegram_user_id=111, first_name="Amir", telegram_username="amir")
    with patch.object(website_main, "get_session", lambda: _wrap(_FakeSession(owner))):
        resp = client.get("/admin/messages?lang=he", cookies={"session": _session_cookie({"user_id": 1})})
    assert resp.status_code == 200
    panel = _panel(resp.text)
    admin = panel[panel.index('id="nav-section-admin"'):]
    assert ">ניהול</span>" in admin
    for href, name in (("/admin", "דשבורד"), ("/admin/messages", "תיבת הודעות"), ("/admin/users", "ניהול משתמשים"),
                       ("/admin/posts", "מודעות של בעלי דירות")):
        assert re.search(rf'<a href="{re.escape(href)}"[^>]*>.*?<span>{name}</span></a>', admin, flags=re.S)
    assert '<a href="/admin/messages" class="active" aria-current="page">' in admin


def test_new_menu_texts_exist_in_every_language_without_long_dashes():
    for key in NEW_KEYS:
        entry = TRANSLATIONS[key]
        assert set(entry) >= {"he", "en", "ru", "fr", "ar"}
        assert all(value.strip() and "—" not in value and "–" not in value for value in entry.values())
