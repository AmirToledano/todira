"""Regression guard for a bug class this project has now hit three times independently: a
Kubernetes Deployment's Pod is NOT restarted when only a mounted Secret/ConfigMap's *content*
changes underneath it (env vars from secretKeyRef/configMapKeyRef are read once at container
start; the Pod template itself is unchanged, so there's nothing to trigger a rollout) — first for
WhatsApp secrets (bot/website, 2026-09-06), then for Caddy's Caddyfile (2026-09-07), then found
STILL missing for the postgres secret in all three Deployments that reference it (2026-09-07 audit).

The fix each time is a `checksum/<name>: {{ include (print $.Template.BasePath "/<name>.yaml") . |
sha256sum }}` annotation on the Pod template, forcing a new Pod spec (and thus a rollout) whenever
that Secret/ConfigMap's rendered content changes. This test doesn't run `helm template` (helm
isn't available in this test environment) — it's a cheap static check that every Deployment
referencing a Secret/ConfigMap by name also carries a matching checksum annotation in the same
file, so the next instance of this exact incident class fails CI instead of silently shipping.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "charts" / "todira" / "templates"

# Logical name (the "<X>" in "{{ .Release.Name }}-<X>") -> template file that defines it, for
# every Secret/ConfigMap in the chart today.
_SECRET_OR_CONFIGMAP_SOURCES = {
    "bot-secret": "bot-secret.yaml",
    "postgres-secret": "postgres-secret.yaml",
    "caddy-config": "caddy-configmap.yaml",  # caddy-deployment.yaml's own checksum key's name
}

# The chart's own caddy-deployment.yaml names its ConfigMap "{{ .Release.Name }}-caddy-config" but
# its checksum key (matching the pattern used everywhere else) is also "caddy-config" — handled
# generically below by deriving the reference name straight from what's mounted.


def _deployment_files() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*deployment.yaml"))


@pytest.mark.parametrize("path", _deployment_files(), ids=lambda p: p.name)
def test_every_referenced_secret_or_configmap_has_a_checksum_annotation(path: Path):
    text = path.read_text(encoding="utf-8")

    # Every "{{ .Release.Name }}-<logical-name>" referenced as a secretKeyRef/configMap name
    # anywhere in the file (env vars, volumes) — these are the things whose content changing
    # should trigger a Pod restart.
    referenced_names = set(re.findall(r"\{\{\s*\.Release\.Name\s*\}\}-([\w-]+)", text))

    # Only the manifests we actually know how to source-check (Secret/ConfigMap templates in this
    # chart) — anything else referenced by name (e.g. the Deployment's own name in matchLabels) is
    # not a mounted Secret/ConfigMap and isn't this bug class.
    mounted = referenced_names & set(_SECRET_OR_CONFIGMAP_SOURCES)
    if not mounted:
        pytest.skip(f"{path.name} doesn't mount any known Secret/ConfigMap by name")

    annotations_block = re.search(r"annotations:\n(.*?)(?:\n\s*spec:)", text, re.DOTALL)
    annotations_text = annotations_block.group(1) if annotations_block else ""

    for name in mounted:
        source_file = _SECRET_OR_CONFIGMAP_SOURCES[name]
        assert f"checksum/{name}" in annotations_text or f"checksum/{name}" in text, (
            f"{path.name} mounts {{{{ .Release.Name }}}}-{name} but has no "
            f"'checksum/{name}: ...' annotation — a content-only change to {source_file} "
            "would never restart this Pod (see this test's module docstring)."
        )
        assert f'"/{source_file}"' in text, (
            f"{path.name} has a checksum/{name} annotation but it doesn't hash {source_file} "
            "itself — check it points at the right template file."
        )
