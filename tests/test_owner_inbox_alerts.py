"""2026-10-20 (owner): the outage and backup alerts go to his inbox group too, not only to his muted private chat.
Static checks of the chart and the workflows, which run as shell scripts outside the test suite."""
from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_FLAG_QUERY = "select value from app_flags where key = 'owner_inbox_chat_id'"


def test_the_in_cluster_alerts_read_the_group_and_never_fail_on_it():
    for name in ("healthcheck-cronjob.yaml", "backup-cronjob.yaml"):
        text = (_ROOT / "charts" / "todira" / "templates" / name).read_text()
        assert _FLAG_QUERY in text, name
        assert "> /shared/inbox_chat_id 2>/dev/null || true" in text, name  # a database problem never stops the alert
        assert "for CHAT in $INBOX $OWNER_TELEGRAM_USER_ID" in text, name  # group first, private chat as fallback


def test_the_github_alerts_read_the_group_without_printing_it():
    for name in ("watchdog-external.yaml", "offsite-backup-gdrive.yaml"):
        workflow = yaml.safe_load((_ROOT / ".github" / "workflows" / name).read_text())
        scripts = "\n".join(step.get("run", "") for job in workflow["jobs"].values() for step in job["steps"])
        assert _FLAG_QUERY in scripts, name
        assert 'echo "::add-mask::$INBOX"' in scripts, name
        assert "for CHAT in $INBOX $OWNER_TELEGRAM_USER_ID" in scripts, name
        for line in scripts.splitlines():  # never echoed, never passed through step outputs
            assert not ("$INBOX" in line and ("GITHUB_OUTPUT" in line or line.strip().startswith('echo "inbox'))), line
