"""Unit tests for dorin_common/gemini_client.py's parse_onboarding_message() post-processing.

The Gemini call itself is mocked out (no network, no real API key) - what's under test is the
module's own defensive logic around that call: filtering out cities the model hallucinates
outside the known list (the real bug class this project hit before - see the "Fix Gemini city
fallback" commit in git history), rejecting an invalid deal_type, and the documented "fails soft,
never raises" contract on API errors or malformed responses.
"""
import json
from unittest.mock import patch

import requests
from google.genai import errors

from dorin_common import gemini_client


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _fake_server_error(code=503):
    """A real google.genai.errors.ServerError needs a response object; a bare instance built via
    __new__ (bypassing __init__, which parses a requests.Response we don't have here) is enough to
    satisfy `except errors.ServerError` and to be logged."""
    exc = errors.ServerError.__new__(errors.ServerError)
    exc.code = code
    exc.status = "UNAVAILABLE"
    exc.details = {"message": "This model is currently experiencing high demand."}
    Exception.__init__(exc, f"{code} UNAVAILABLE. {exc.details}")
    return exc


class _FakeModels:
    def __init__(self, response_text=None, raise_exc=None, raise_sequence=None):
        self._response_text = response_text
        self._raise_exc = raise_exc
        self._raise_sequence = list(raise_sequence) if raise_sequence else None
        self.call_count = 0

    def generate_content(self, model, contents, config):
        self.call_count += 1
        if self._raise_sequence is not None:
            outcome = self._raise_sequence.pop(0)
            if outcome is not None:
                raise outcome
            return _FakeResponse(self._response_text)
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_text)


class _FakeClient:
    def __init__(self, response_text=None, raise_exc=None, raise_sequence=None):
        self.models = _FakeModels(response_text, raise_exc, raise_sequence)


def _install_fake_client(monkeypatch, response_text=None, raise_exc=None, raise_sequence=None):
    fake = _FakeClient(response_text=response_text, raise_exc=raise_exc, raise_sequence=raise_sequence)
    monkeypatch.setattr(gemini_client, "_get_client", lambda: fake)
    return fake


def test_returns_none_when_no_client_configured(monkeypatch):
    monkeypatch.setattr(gemini_client, "_get_client", lambda: None)
    result = gemini_client.parse_onboarding_message("שלום", {}, ["תל אביב"])
    assert result is None


def test_hallucinated_cities_outside_known_list_are_filtered_out(monkeypatch):
    payload = json.dumps(
        {
            "deal_type": "rent",
            "cities": ["תל אביב", "עיר שלא קיימת"],
            "missing_required": [],
            "response_message": "מעולה",
        }
    )
    _install_fake_client(monkeypatch, response_text=payload)
    result = gemini_client.parse_onboarding_message(
        "מחפש בתל אביב", {}, ["תל אביב", "חיפה"]
    )
    assert result["cities"] == ["תל אביב"]


def test_missing_cities_key_defaults_to_empty_list(monkeypatch):
    payload = json.dumps(
        {"deal_type": "rent", "missing_required": ["cities"], "response_message": "?"}
    )
    _install_fake_client(monkeypatch, response_text=payload)
    result = gemini_client.parse_onboarding_message("דירה להשכרה", {}, ["תל אביב"])
    assert result["cities"] == []


def test_deal_type_outside_allowed_set_becomes_none(monkeypatch):
    payload = json.dumps(
        {
            "deal_type": "unknown",
            "cities": [],
            "missing_required": ["deal_type"],
            "response_message": "?",
        }
    )
    _install_fake_client(monkeypatch, response_text=payload)
    result = gemini_client.parse_onboarding_message("איזה דירה", {}, ["תל אביב"])
    assert result["deal_type"] is None


def test_valid_deal_type_passes_through_unchanged(monkeypatch):
    payload = json.dumps(
        {
            "deal_type": "sublet",
            "cities": ["חיפה"],
            "missing_required": [],
            "response_message": "מעולה",
        }
    )
    _install_fake_client(monkeypatch, response_text=payload)
    result = gemini_client.parse_onboarding_message("סאבלט בחיפה", {}, ["חיפה"])
    assert result["deal_type"] == "sublet"


def test_needs_human_help_passes_through(monkeypatch):
    payload = json.dumps(
        {
            "deal_type": None,
            "cities": [],
            "missing_required": ["deal_type", "cities"],
            "response_message": "מעביר את זה לצוות",
            "needs_human_help": True,
        }
    )
    _install_fake_client(monkeypatch, response_text=payload)
    result = gemini_client.parse_onboarding_message(
        "אני רוצה לדבר עם מישהו על תלונה שיש לי", {}, ["תל אביב"]
    )
    assert result["needs_human_help"] is True


def test_api_exception_fails_soft_returns_none(monkeypatch):
    _install_fake_client(monkeypatch, raise_exc=RuntimeError("network exploded"))
    result = gemini_client.parse_onboarding_message("משהו", {}, ["תל אביב"])
    assert result is None


def test_malformed_json_response_fails_soft_returns_none(monkeypatch):
    _install_fake_client(monkeypatch, response_text="not valid json{{{")
    result = gemini_client.parse_onboarding_message("משהו", {}, ["תל אביב"])
    assert result is None


# --- 2026-09-06: one bounded retry on Gemini's own transient 5xx ("high demand") errors — added
# after real production logs (pulled via the diagnose-website-webhook workflow) showed exactly
# this ServerError on 2 of 3 live WhatsApp messages the owner sent back-to-back. Safe to do only
# because the ack-first webhook fix shipped earlier the same day decouples this function's total
# runtime from Meta's own webhook redelivery. ---


def test_server_error_is_retried_and_succeeds_on_second_attempt(monkeypatch):
    payload = json.dumps(
        {"deal_type": "rent", "cities": ["חיפה"], "missing_required": [], "response_message": "מעולה"}
    )
    fake = _install_fake_client(
        monkeypatch, raise_sequence=[_fake_server_error(), None], response_text=payload
    )
    with patch.object(gemini_client.time, "sleep") as sleep_mock:
        result = gemini_client.parse_onboarding_message("סאבלט בחיפה", {}, ["חיפה"])

    assert result["cities"] == ["חיפה"]
    assert fake.models.call_count == 2
    sleep_mock.assert_called_once_with(gemini_client._RETRY_DELAY_SECONDS)


def test_server_error_on_every_attempt_fails_soft_after_retry_budget(monkeypatch):
    fake = _install_fake_client(
        monkeypatch, raise_sequence=[_fake_server_error(), _fake_server_error()]
    )
    with patch.object(gemini_client.time, "sleep"):
        result = gemini_client.parse_onboarding_message("משהו", {}, ["תל אביב"])

    assert result is None
    assert fake.models.call_count == gemini_client._MAX_ATTEMPTS


def test_non_server_error_is_not_retried(monkeypatch):
    fake = _install_fake_client(monkeypatch, raise_exc=RuntimeError("network exploded"))
    with patch.object(gemini_client.time, "sleep") as sleep_mock:
        result = gemini_client.parse_onboarding_message("משהו", {}, ["תל אביב"])

    assert result is None
    assert fake.models.call_count == 1  # no retry spent on a non-transient error
    sleep_mock.assert_not_called()


def test_read_timeout_is_also_retried(monkeypatch):
    """2026-09-06, same-day follow-up: a second round of live logs showed the OTHER shape of
    "Gemini didn't answer" that the ServerError-only retry above missed entirely — a plain
    requests.exceptions.ReadTimeout with no error response at all (Gemini just didn't reply within
    the 10s budget)."""
    payload = json.dumps(
        {"deal_type": "sale", "cities": ["ירושלים"], "missing_required": [], "response_message": "מעולה"}
    )
    timeout_exc = requests.exceptions.ReadTimeout("Read timed out. (read timeout=10.0)")
    fake = _install_fake_client(monkeypatch, raise_sequence=[timeout_exc, None], response_text=payload)

    with patch.object(gemini_client.time, "sleep") as sleep_mock:
        result = gemini_client.parse_onboarding_message("דירה למכירה בירושלים", {}, ["ירושלים"])

    assert result["cities"] == ["ירושלים"]
    assert fake.models.call_count == 2
    sleep_mock.assert_called_once_with(gemini_client._RETRY_DELAY_SECONDS)
