"""2026-10-19: email to Google-only users through Resend (todira_common/email_client.py) and the one-time trial email
(website/announce_trial_extension_email.py)."""
from __future__ import annotations

import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

from todira_common import email_client

_WEBSITE = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE) not in sys.path:
    sys.path.insert(0, str(_WEBSITE))
_spec = importlib.util.spec_from_file_location("trial_email", _WEBSITE / "announce_trial_extension_email.py")
trial_email = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(trial_email)


def test_nothing_is_sent_without_a_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with patch.object(email_client.httpx, "post") as post:
        assert email_client.send("a@example.com", "s", "<p>h</p>", "t") is False
    post.assert_not_called()
    assert not email_client.enabled()


def test_a_message_goes_to_resend_with_the_key_and_both_bodies(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    with patch.object(email_client.httpx, "post", return_value=SimpleNamespace(status_code=200, text="{}")) as post:
        assert email_client.send("a@example.com", "subject", "<p>h</p>", "text") is True
    kwargs = post.call_args.kwargs
    assert kwargs["headers"]["Authorization"] == "Bearer re_test"
    assert kwargs["json"]["to"] == ["a@example.com"] and kwargs["json"]["text"] == "text"
    assert "todira.app" in kwargs["json"]["from"]


def test_a_refusal_is_reported_as_not_sent(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    with patch.object(email_client.httpx, "post", return_value=SimpleNamespace(status_code=403, text="domain not verified")):
        assert email_client.send("a@example.com", "s", "h", "t") is False


def test_the_trial_email_is_the_wording_the_owner_saw():
    subject, page, text = trial_email.message_for("Dana", dt.datetime(2026, 10, 26, 7, 0, tzinfo=dt.timezone.utc))
    assert subject == "🎁 פתחנו לך עוד 7 ימי גישה מלאה בטודירה"
    assert "היי Dana," in text and "עד 26.10" in text and "https://todira.app/apartments" in text
    assert 'dir="rtl"' in page and "לדירות שלי" in page


def test_a_name_with_markup_is_escaped_in_the_html():
    _subject, page, _text = trial_email.message_for("<b>x</b>", dt.datetime(2026, 10, 26, 7, 0, tzinfo=dt.timezone.utc))
    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page
