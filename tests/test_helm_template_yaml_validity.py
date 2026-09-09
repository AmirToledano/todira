"""Regression guard for a real incident, 2026-09-09: a fix to `backup-cronjob.yaml` embedded a
literal, unindented newline inside a bash string that itself lived inside a YAML block scalar
(`args: - |`) — valid-looking Python/bash reasoning, but it broke out of the block scalar and
left invalid YAML underneath. `helm upgrade` caught it immediately... in production, at 06:06 UTC,
failing the ENTIRE deploy (not just the one CronJob) for every service, discovered only because a
different incident (the previous night's backup failure) prompted a manual log check. No local or
CI check existed that could have caught this before it reached a real deploy — `test_helm_
checksum_annotations.py` and friends are static text scans, not real YAML parsing.

Helm itself isn't installable in this test environment (no network access to get.helm.sh, no apt
package) — see PROJECT_STATE.md for the two things this session actually tried. So this is a
best-effort static check, not a real `helm template` render: strip out Helm's own `{{ ... }}`
templating syntax (crudely — a whole line that's ONLY an `if`/`end`/`else`/`range`/`with`
directive is dropped entirely, matching what `{{-`/`-}}` chomping actually does at render time;
an inline `{{ .Values.x | quote }}`-style expression is replaced with a short safe placeholder so
its own contents — quotes, pipes, colons — can never confuses the YAML parser) and confirm the
result is still parseable YAML. This does NOT catch template logic errors (an undefined value, a
wrong function name) — only structural YAML validity, which is exactly the class of bug that
happened here and is cheap enough to always run.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "charts" / "todira" / "templates"

_CONTROL_DIRECTIVE_ONLY = re.compile(r"\{\{-?\s*(if|end|else|range|with)\b.*?-?\}\}")
_INLINE_EXPRESSION = re.compile(r"\{\{-?.*?-?\}\}")


def _strip_helm_syntax(text: str) -> str:
    out_lines = []
    for line in text.split("\n"):
        if _CONTROL_DIRECTIVE_ONLY.fullmatch(line.strip()):
            continue
        out_lines.append(_INLINE_EXPRESSION.sub("PLACEHOLDER", line))
    return "\n".join(out_lines)


def _template_files() -> list[Path]:
    files = sorted(TEMPLATES_DIR.glob("*.yaml"))
    assert files, f"no chart template files found under {TEMPLATES_DIR} — is the path right?"
    return files


@pytest.mark.parametrize("path", _template_files(), ids=lambda p: p.name)
def test_template_is_valid_yaml_after_stripping_helm_syntax(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        list(yaml.safe_load_all(_strip_helm_syntax(text)))
    except yaml.YAMLError as e:
        pytest.fail(f"{path.name} is not valid YAML once Helm's own {{{{ }}}} syntax is stripped "
                    f"(this would fail a real `helm upgrade` too): {e}")
