"""2026-11-13 (owner: "build all 7, no mistakes"): drawings and motion on the site. The street of buildings behind the
home page's hero (website/skyline.py) with a drawn Todi walking on it, a graph of the week that builds itself, a pin
that drops on the map, the bot's card coming apart into its checked lines, paw prints while results load, and Todi
looking for the missing page on the 404. Decoration on top of pages that read fine without it."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")

_ROOT = Path(__file__).resolve().parent.parent
_WEBSITE_DIR = _ROOT / "website"
if str(_WEBSITE_DIR) not in sys.path:
    sys.path.insert(0, str(_WEBSITE_DIR))

_spec = importlib.util.spec_from_file_location("website_main_site_animations", _WEBSITE_DIR / "main.py")
website_main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(website_main)

import i18n as website_i18n
import skyline
from fastapi.testclient import TestClient

T = website_i18n.TRANSLATIONS
STATIC = _WEBSITE_DIR / "static"


@pytest.fixture
def client():
    return TestClient(website_main.app, raise_server_exceptions=True, follow_redirects=False)


def test_the_street_is_one_valid_hidden_drawing_with_windows_to_light():
    svg = str(skyline.skyline_svg())
    root = ET.fromstring(svg)
    assert root.get("aria-hidden") == "true"
    windows = re.findall(r'class="w"', svg)
    assert len(windows) > 150
    # the same street on every visit (a fixed seed), and small enough to sit inline in the page
    assert str(skyline.skyline_svg.__wrapped__()) == svg
    assert len(svg.encode()) < 60_000


def test_the_week_counts_are_seven_whole_days_oldest_first():
    rows = [(0, 274), (1, 1051), (6, 2214), (7, 99), (None, 5), (3.0, 1890)]
    assert website_main._daily_counts(rows) == [2214, 0, 0, 1890, 0, 1051, 274]
    assert website_main._daily_counts([]) == [0] * 7


def test_the_home_page_carries_the_street_the_graph_and_the_card(client):
    html = client.get("/?lang=he").text
    assert 'id="lp-street" aria-hidden="true"' in html and 'class="lp-sky-svg"' in html
    assert html.count('class="todi-dog') == 1 and 'id="lp-walker"' in html
    assert 'id="lp-week" hidden' in html and T["landing.week_chart"]["he"] in html
    assert 'id="lp-xray-card"' in html and T["landing.xray_note"]["he"] in html
    # the card is the bot's real card: its place and every one of its lines, each with a check
    alert = website_main._landing_js("he")["demos"][1]["alert"]
    assert alert["place"] in html
    assert html.count('class="lp-xray-layer"') == len(alert["rows"]) + 2
    # todi.js has to be read before home.js uses it
    assert html.index("/static/todi.js") < html.index("/static/home.js")


def test_the_404_page_has_todi_looking_for_the_page(client):
    r = client.get("/no-such-page-at-all")
    assert r.status_code == 404
    assert 'id="lost-scene" aria-hidden="true"' in r.text and 'class="todi-dog' in r.text
    assert "/static/todi.js" in r.text and T["404.body"]["he"] in r.text


def test_the_search_page_shows_paw_prints_while_it_loads(client):
    html = client.get("/search?lang=he").text
    assert 'id="psearch-wait"' in html and 'role="status" hidden' in html
    assert html.count("<i></i>") >= 6 and T["search.sniffing"]["he"] in html


def test_the_flats_list_loads_more_with_paw_prints_not_a_spinner():
    tpl = (_WEBSITE_DIR / "templates" / "apartments.html").read_text()
    assert "apt-spinner" not in tpl and 'class="paw-steps small"' in tpl


def test_the_paw_is_served_as_an_svg_image(client):
    r = client.get("/static/paw.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")


@pytest.mark.parametrize("key", ["landing.week_chart", "landing.xray_note", "search.sniffing"])
def test_the_new_texts_exist_in_every_core_language_without_dashes(key):
    for lang in website_i18n.CORE_LANGS:
        text = T[key][lang]
        assert text and "—" not in text and "–" not in text and "·" not in text, (key, lang)


def test_every_new_motion_stops_for_reduced_motion_and_the_accessibility_menu():
    """Each new looping animation is written behind both switches: the visitor's "reduce motion" and the site's own
    accessibility menu ("stop motion" puts .a11y-no-motion on the page)."""
    css = (STATIC / "style.css").read_text() + (STATIC / "home.css").read_text()
    for name in ("td-step-a", "td-step-b", "td-bob", "td-sniff", "td-nod", "td-wag", "td-rbob", "td-rsniff", "paw-print", "lp-pin-drop", "lp-route"):
        uses = [line for line in css.splitlines() if re.search(r"animation:\s*" + name + r"\b", line)]
        assert uses, name
        assert all("html:not(.a11y-no-motion)" in line for line in uses), name
    walk = [line for line in css.splitlines() if "animation-name: td-" in line]
    assert len(walk) == 6 and all("html:not(.a11y-no-motion)" in line for line in walk)


def test_the_scripts_check_for_reduced_motion_before_moving_anything():
    todi = (STATIC / "todi.js").read_text()
    home = (STATIC / "home.js").read_text()
    assert "prefers-reduced-motion: reduce" in todi and "a11y-no-motion" in todi
    for block in ("function street()", "function weekChart(", "function xray()"):
        start = home.index(block)
        assert "reduce" in home[start:start + 3000], block


def test_the_footer_is_four_headed_groups(client):
    html = client.get("/about?lang=he").text
    footer = html[html.index('<footer class="site-footer">'):]
    assert footer.count('class="footer-col"') == 4 and 'class="footer-brand"' in footer and 'class="footer-bottom"' in footer
    for key in ("footer.cat_mine", "footer.cat_tools", "footer.cat_telegram", "footer.cat_about"):
        assert T[key]["he"] in footer
        assert all(T[key][lang] for lang in website_i18n.CORE_LANGS)


def test_todi_walks_as_a_jointed_puppet_and_the_404_has_his_pictures(client):
    html = client.get("/?lang=he").text
    assert "/static/todi/todi-rig.webp" in html and 'class="todi-dog todi-rig' in html
    # four legs, each with a hip, a knee and a paw, a quarter of a cycle apart
    assert html.count("td-h-hip") == 2 and html.count("td-f-hip") == 2 and html.count("td-j ") == 12
    assert sorted(set(re.findall(r'td-[hf]-hip" style="--ph:([0-9.]+)"', html))) == ["0.0", "0.25", "0.5", "0.75"]
    lost = client.get("/no-such-page-at-all").text
    assert "/static/todi/todi-sniff.webp" in lost and "todi-rig" not in lost
    assert "/static/todi/todi-face.webp" in client.get("/search?lang=he").text
    for name in ("todi-rig", "todi-walk1", "todi-walk2", "todi-sniff", "todi-look", "todi-face"):
        assert (STATIC / "todi" / f"{name}.webp").stat().st_size < 60_000


