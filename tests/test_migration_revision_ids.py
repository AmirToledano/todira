"""Regression guard for a real bug found live 2026-09-08: alembic's own bookkeeping table
(`alembic_version.version_num`) is created as a plain `VARCHAR(32)` — a migration whose `revision`
string is longer than 32 characters makes EVERY future `alembic upgrade head` fail with
`DataError: value too long for type character varying(32)` the moment it tries to record that
revision as current. This isn't a transient/Postgres-readiness failure (the kind
migrations-job.yaml's own 30-attempt retry loop exists for) — it's deterministic and retrying it
doesn't help, so it just burns the whole retry budget and times out the Helm pre-upgrade hook,
failing the deploy (confirmed live: migration 0010's original id, "0010_whatsapp_notifications_
optin" at 33 chars, did exactly this — see that file's own comment for the fix, renaming to the
25-char "0010_whatsapp_notif_optin").

A cheap static check here (no real Postgres needed) catches the next instance of this before it
ever reaches a real deploy.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"

# alembic's default Alembic-managed version table column width — see this module's own docstring.
_ALEMBIC_VERSION_NUM_MAX_LENGTH = 32

_REVISION_RE = re.compile(r'^revision\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def _migration_files() -> list[Path]:
    files = sorted(VERSIONS_DIR.glob("*.py"))
    assert files, f"no migration files found under {VERSIONS_DIR} — is the path right?"
    return files


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.name)
def test_revision_id_fits_alembic_version_column(path: Path):
    match = _REVISION_RE.search(path.read_text())
    assert match, f"{path.name}: couldn't find a `revision = \"...\"` line"
    revision = match.group(1)
    assert len(revision) <= _ALEMBIC_VERSION_NUM_MAX_LENGTH, (
        f"{path.name}: revision id {revision!r} is {len(revision)} chars, over the "
        f"alembic_version.version_num VARCHAR({_ALEMBIC_VERSION_NUM_MAX_LENGTH}) limit — "
        "every `alembic upgrade head` past this migration will fail with a DataError. "
        "Shorten the revision id (it doesn't need to spell out the whole migration name)."
    )


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.name)
def test_revision_id_matches_filename_prefix(path: Path):
    """Not required by alembic itself, but every migration in this project so far names its file
    after its own revision id exactly — catches a copy-paste-and-rename slip (like this test's own
    file once briefly had, mid-fix) before it causes confusion finding "which file is revision X"."""
    match = _REVISION_RE.search(path.read_text())
    assert match
    revision = match.group(1)
    assert path.stem == revision, (
        f"{path.name}: filename stem {path.stem!r} doesn't match its own revision id {revision!r}"
    )
