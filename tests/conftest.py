import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

# In production images, dorin_common is copied to /app/dorin_common and each service's own
# files (scraper/*.py etc) are copied directly into /app too, with PYTHONPATH=/app (see
# bot/scraper/website Dockerfiles) - so `import dorin_common` and e.g. `import normalize` both
# resolve as top-level modules. Mirror that layout here so tests import the same way production
# does, without needing package installs.
sys.path.insert(0, str(_ROOT / "common"))
sys.path.insert(0, str(_ROOT / "scraper"))
sys.path.insert(0, str(_ROOT / "bot"))
# website/ deliberately NOT added here: both scraper/main.py and website/main.py are named
# main.py, so a bare `import main` would be ambiguous once both directories are on sys.path (last
# one inserted wins). test_website_contact.py loads website/main.py directly via importlib
# instead, under an unambiguous name — see that file's own comment.
