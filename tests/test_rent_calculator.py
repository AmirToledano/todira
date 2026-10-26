"""/calculator renders with the medians the page's script reads (2026-10-24)."""
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
_WEBSITE_DIR = Path(__file__).resolve().parent.parent / "website"
sys.path.insert(0, str(_WEBSITE_DIR))
_spec = importlib.util.spec_from_file_location("website_main_calc", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

from fastapi.testclient import TestClient  # noqa: E402


def test_calculator_page_carries_the_medians():
    medians = {"3": [["חיפה", 4500, 120], ["תל אביב", 8200, 400]]}
    with patch.object(website_main, "_rent_medians", lambda: medians):
        resp = TestClient(website_main.app).get("/calculator")
    assert resp.status_code == 200
    assert "מחשבון שכירות" in resp.text and "4500" in resp.text and "start=calculator" in resp.text
