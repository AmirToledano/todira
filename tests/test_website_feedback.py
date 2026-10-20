"""2026-10-20 (owner): a "feedback" bubble on every page opens the contact form with its own title, and a signed-in
visitor finds their own name and email already filled in."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_feedback", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def _page_config(html: str) -> dict:
    body = re.search(r"window\.__TODIRA_PAGE__ = (\{.*?\});", html, re.S).group(1)
    body = re.sub(r"(\w+):", r'"\1":', body)  # the keys are bare names
    return json.loads(body)


def test_the_bubble_is_on_every_page_but_the_contact_form_itself(client):
    assert 'class="feedback-bubble" href="/contact?topic=feedback"' in client.get("/terms").text
    assert "feedback-bubble" not in client.get("/contact").text


def test_the_bubble_opens_the_form_as_feedback(client):
    assert _page_config(client.get("/contact?topic=feedback").text)["topic"] == "feedback"
    assert _page_config(client.get("/contact?topic=<script>").text)["topic"] is None


def test_a_signed_in_visitor_finds_their_own_name_and_email_filled_in(client):
    me = {"telegram_user_id": 42, "first_name": "Dana", "telegram_username": None, "email": "dana@example.com",
          "trial_gift_until": None}
    with patch.object(website_main, "_current_user_summary", return_value=me):
        config = _page_config(client.get("/contact?topic=feedback").text)
    assert config["prefill"] == {"name": "Dana", "email": "dana@example.com"}
    assert config["uid"] == 42  # the message is tied to their account


def test_a_visitor_who_is_not_signed_in_gets_an_empty_form(client):
    with patch.object(website_main, "_current_user_summary", return_value=None):
        config = _page_config(client.get("/contact").text)
    assert config["prefill"] == {} and config["uid"] is None
