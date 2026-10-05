"""The bot image installs only bot/requirements.txt, while CI installs requirements-test.txt (a
superset) — so a third-party import added to todira_common that the bot loads at startup passes CI and
then crash-loops the real pod (itsdangerous, 2026-10-05). Pin that for the known case."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bot_declares_itsdangerous_because_uid_token_imports_it():
    uid_token = (ROOT / "common/todira_common/uid_token.py").read_text()
    assert "itsdangerous" in uid_token
    handlers = "".join(p.read_text() for p in (ROOT / "bot/handlers").glob("*.py"))
    assert "todira_common.uid_token" in handlers
    assert "itsdangerous" in (ROOT / "bot/requirements.txt").read_text()
