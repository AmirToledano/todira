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
