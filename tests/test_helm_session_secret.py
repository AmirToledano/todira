"""Every workload that signs a website login link (?t= / ?wid=) must get the SAME SESSION_SECRET_KEY the
website verifies with. Until 2026-10-05 only the website had it: the bot and the scraper signed with the
dev-only fallback key, so every link they sent opened logged-out."""
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "charts/todira/templates"


def test_signing_workloads_get_the_website_session_secret():
    for name in ("website-deployment", "bot-deployment", "scraper-cronjob", "facebook-scraper-cronjob"):
        text = (TEMPLATES / f"{name}.yaml").read_text()
        assert "- name: SESSION_SECRET_KEY" in text, name
        assert "key: session-secret-key" in text, name
