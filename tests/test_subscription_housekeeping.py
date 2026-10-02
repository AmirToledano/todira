"""website/subscription_housekeeping.py (2026-10-02): a cancelled subscription is cancelled on Takbull's
side a few days BEFORE paid_until, so a renewal charge can never fire after the customer cancelled."""
from __future__ import annotations

import datetime as dt
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

import subscription_housekeeping  # noqa: E402


class _Session:
    def __init__(self, users):
        self.users = users
        self.statements = []
        self.commits = 0

    def scalars(self, statement):
        self.statements.append(statement)
        return iter(self.users)

    def commit(self):
        self.commits += 1


def _run(users, cancel_ok=True):
    session = _Session(users)

    @contextmanager
    def _get_session():
        yield session

    with (
        patch.object(subscription_housekeeping, "get_session", _get_session),
        patch.object(subscription_housekeeping.takbull_client, "recurring_api_configured", lambda: True),
        patch.object(subscription_housekeeping.takbull_client, "cancel_subscription", return_value=cancel_ok) as mock_cancel,
    ):
        subscription_housekeeping.run_once()
    return session, mock_cancel


def test_cancelled_subscription_is_cancelled_on_takbull_and_cleared():
    user = SimpleNamespace(id=1, takbull_subscription_uniqid="uniq-1")
    session, mock_cancel = _run([user])

    mock_cancel.assert_called_once_with("uniq-1")
    assert user.takbull_subscription_uniqid is None
    assert session.commits == 1


def test_failed_cancel_is_left_for_the_next_run():
    user = SimpleNamespace(id=1, takbull_subscription_uniqid="uniq-1")
    _session, _mock = _run([user], cancel_ok=False)

    assert user.takbull_subscription_uniqid == "uniq-1"


def test_the_query_selects_users_within_the_lead_time_before_paid_until_not_only_after():
    """paid_until < now() + lead time, i.e. BEFORE the period ends - the old query was paid_until < now()."""
    session, _mock = _run([])
    compiled = session.statements[0].compile()

    text = str(compiled)
    assert "paid_until <" in text
    assert "now()" in text and "+" in text
    assert dt.timedelta(days=3) in compiled.params.values()  # the lead time is part of the query
    assert subscription_housekeeping.CANCEL_LEAD_TIME >= dt.timedelta(days=2)
