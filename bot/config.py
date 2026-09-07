"""Small shared config for values that don't belong to any single handler module."""
from __future__ import annotations

import os

# The public website's base URL (no trailing slash) — used to link a user straight to their
# current matching listings (e.g. f"{WEBSITE_URL}/apartments?uid={tg_user.id}") right after they
# save a filter, instead of only telling them to wait for future notifications. Sourced from
# values.yaml's existing website.domain via the WEBSITE_URL env var (see bot-deployment.yaml) so
# there's one source of truth for the domain, not a second hardcoded copy.
WEBSITE_URL = os.environ.get("WEBSITE_URL", "https://todira.app").rstrip("/")
