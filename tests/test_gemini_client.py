"""Unit tests for dorin_common/gemini_client.py's parse_onboarding_message() post-processing.

The Gemini call itself is mocked out (no network, no real API key) - what's under test is the
module's own defensive logic around that call: filtering out cities the model hallucinates
outside the known list (the real bug class this project hit before - see the "Fix Gemini city
fallback" commit in git history), rejecting an invalid deal_type, and the documented "fails soft,
never raises" contract on API errors or malformed responses.
"""
import json

from dorin_common import gemini_client


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, response_text=None, raise_exc=None):
        self._response_text = response_text
        self._raise_exc = raise_exc

    def generate_content(self, model, contents, config):
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_text)


class _FakeClient:
    def __init__(self, response_text=None, raise_exc=None):
        self.models = _FakeModels(response_text, raise_exc)


def _install_fake_client(monkeypatch, response_text=None, raise_exc=None):
    fake = _FakeClient(response_text=response_text, raise_exc=raise_exc)
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
