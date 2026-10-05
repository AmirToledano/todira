"""Import every module of a service the way its container will run it, from a clean install of ONLY that
service's own requirements.txt. Catches a third-party package that todira_common (or the service)
imports but the service's requirements.txt doesn't list — CI's test job installs requirements-test.txt (a
superset), so such a gap passed CI and then crash-looped the real pod (bot, itsdangerous, 2026-10-05).

Only the service's OWN modules are imported (todira_common is loaded transitively, so a package that only an
unused todira_common module needs is not flagged).

Usage: python check_service_imports.py <dir containing the service's modules + todira_common>
A module that fails for any reason other than a missing THIRD-PARTY package (e.g. it needs a database or a
token at import time) is ignored — only ModuleNotFoundError for a package we don't ship counts.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
for name, value in {
    "DATABASE_URL": "postgresql://u:p@localhost/db",
    "TELEGRAM_BOT_TOKEN": "0:test",
    "SESSION_SECRET_KEY": "x",
}.items():
    os.environ.setdefault(name, value)

local = {m.name for m in pkgutil.iter_modules([str(root)])}
modules = sorted(local)
# todira_common modules are NOT enumerated: a service only needs the ones it actually loads, and those are
# pulled in transitively by importing the service's own modules below.
for sub in sorted(p for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists() and p.name != "todira_common"):
    modules += [f"{sub.name}.{m.name}" for m in pkgutil.iter_modules([str(sub)])]

missing: dict[str, list[str]] = {}
for module in modules:
    if module in ("main", "__main__"):
        continue  # entry points start the app
    try:
        importlib.import_module(module)
    except ModuleNotFoundError as exc:
        top = (exc.name or "").split(".")[0]
        if top and top not in local and top != "todira_common":
            missing.setdefault(top, []).append(module)
    except Exception:
        pass  # needs a DB/token/etc. at import time — not what this check is for

if missing:
    for package, users in sorted(missing.items()):
        print(f"MISSING third-party package '{package}' (imported by: {', '.join(users[:5])})")
    sys.exit(1)
print(f"OK: {len(modules)} modules import cleanly from this service's own requirements")
