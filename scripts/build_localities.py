"""Builds common/todira_common/localities_data.py: every Israeli locality and area the filter can be set to.

Owner request (2026-10-13): "all the cities, moshavim, settlements, villages and areas", not only the ~140 bundled in
common/todira_common/cities.py. Inputs, both written by .github/workflows/fetch-localities-data.yaml to the
data/localities branch (git show origin/data/localities:<file>):
  localities.tsv      code|name|sub-district|regional council   (Central Bureau of Statistics list, data.gov.il)
  listing_cities.tsv  city|listings|active listings              (every listings.city value we hold)

Usage: python scripts/build_localities.py localities.tsv listing_cities.tsv

A locality's stored name must equal the listings.city spelling, since filters match cities by exact string (see
cities.py's docstring). So each official locality takes, in order: its spelling in cities.CITIES; else the most common
spelling the listings already use; else a combined listings name that contains it ("מיתר / כרמית"); else the official
name. Every other spelling (official name, listing variants, combined names, the manual aliases below) becomes an alias,
which scraper/normalize.py's canonicalize_city turns into the stored spelling for new listings.

Re-running keeps the order of EXTRA_LOCALITIES (new ones are appended), because the bot's buttons carry an index into
cities.LOCALITIES.
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

from todira_common.cities import CITIES, locality_key  # noqa: E402

OUT = ROOT / "common" / "todira_common" / "localities_data.py"

# Listings spellings with 5+ listings that match no official name by spelling alone (checked by hand, 2026-10-13).
MANUAL_ALIASES = {
    "עפרה": "עופרה",
    "כינרת מושבה": "כנרת (מושבה)",
    "דלית אל כרמל": "דאלית אל-כרמל",
    "עלמון ענתות": "עלמון",
    "חרות": "חירות",
    "ספסופה": "כפר חושן",
    "בית שיקמה": "בית שקמה",
    "נצרת עילית": "נוף הגליל",
    "עספיא": "עוספיא",
    "בנימינה": "בנימינה גבעת עדה",
    "תל אביב": "תל אביב יפו",
}
# Real localities with listings that the official list doesn't have yet (new settlements).
EXTRA_REAL = ["חירן", "כפר אלדד"]

# Areas people search by that aren't a regional council or sub-district.
CUSTOM_REGIONS = {
    "הקריות": ["קריית אתא", "קריית ביאליק", "קריית מוצקין", "קריית ים"],
    "גוש דן": [
        "תל אביב יפו", "רמת גן", "גבעתיים", "בני ברק", "חולון", "בת ים", "פתח תקווה", "ראשון לציון", "הרצליה",
        "רמת השרון", "אור יהודה", "קריית אונו", "גבעת שמואל", "יהוד מונוסון", "אזור",
    ],
}
# Sub-districts that are areas in their own right (the others are named after their main city, which already is one).
REGION_SUBDISTRICTS = {"השרון": "השרון", "כנרת": "כנרת", "גולן": "רמת הגולן"}
WEST_BANK_SUBDISTRICTS = {"בית לחם", "ג'נין", "חברון", "טול כרם", "ירדן )יריחו(", "ראמאללה", "שכם"}


def _clean(name: str) -> str:
    name = re.sub(r"\s+", " ", name.replace("־", "-")).strip()
    return re.sub(r"\s*-\s*", " ", name)


def main(localities_path: str, listing_cities_path: str) -> None:
    cbs = []
    for line in pathlib.Path(localities_path).read_text(encoding="utf-8").splitlines():
        parts = (line.split("|") + ["", "", "", ""])[:4]
        if parts[1] and "(שבט)" not in parts[1]:
            cbs.append(parts)
    listing_counts: dict[str, int] = {}
    for line in pathlib.Path(listing_cities_path).read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) == 3 and parts[1].isdigit():
            listing_counts[parts[0]] = int(parts[1])

    by_key: dict[str, list[str]] = collections.defaultdict(list)
    for name in listing_counts:
        by_key[locality_key(name)].append(name)
    composite_parts: dict[str, list[str]] = collections.defaultdict(list)
    for name in listing_counts:
        pieces = [p for p in re.split(r"\s*/\s*|\s+[-–]\s+", name) if p.strip()]
        if len(pieces) > 1:
            for piece in pieces:
                composite_parts[locality_key(piece)].append(name)

    city_by_key = {locality_key(c): c for c in CITIES}
    base_counts = collections.Counter(locality_key(re.sub(r"\(.*?\)", " ", n)) for _, n, _, _ in cbs)

    canonical_of: dict[str, str] = {}  # official name -> stored spelling
    aliases: dict[str, str] = {}
    for _, name, _, _ in cbs:
        full_key = locality_key(name)
        base_key = locality_key(re.sub(r"\(.*?\)", " ", name))
        keys = [full_key] if base_counts[base_key] > 1 else [base_key, full_key]
        canonical = None
        for key in keys:
            if key in city_by_key:
                canonical = city_by_key[key]
                break
            if by_key.get(key):
                canonical = max(by_key[key], key=lambda n: listing_counts[n])
                break
        if canonical is None:
            for key in keys:
                if composite_parts.get(key):
                    canonical = max(composite_parts[key], key=lambda n: listing_counts[n])
                    break
        if canonical is None:
            canonical = _clean(name if base_counts[base_key] > 1 else re.sub(r"\s*\(.*?\)\s*", " ", name))
        canonical_of[name] = canonical
        for key in {*keys, locality_key(name)}:
            aliases.setdefault(key, canonical)

    for alias, target in MANUAL_ALIASES.items():
        canonical = canonical_of.get(target) or city_by_key.get(locality_key(target)) or target
        aliases[locality_key(alias)] = canonical
    # every listings spelling that belongs to a known locality (variants, combined names)
    for name in listing_counts:
        key = locality_key(name)
        if key in aliases:
            continue
        pieces = [p for p in re.split(r"\s*/\s*|\s+[-–]\s+", name) if p.strip()]
        for piece in pieces:
            target = aliases.get(locality_key(piece))
            if target is not None:
                aliases[key] = target
                break

    known = set(CITIES)
    existing: list[str] = []
    if OUT.exists():
        namespace: dict = {}
        exec(compile(OUT.read_text(encoding="utf-8"), str(OUT), "exec"), namespace)
        existing = [n for n in namespace.get("EXTRA_LOCALITIES", []) if n not in known]
    new = {c for c in canonical_of.values() if c not in known} | {n for n in EXTRA_REAL if n not in known}
    new_sorted = sorted(new - set(existing), key=lambda n: (-listing_counts.get(n, 0), n))
    extra = [*existing, *new_sorted]
    for name in [*CITIES, *extra]:
        aliases.setdefault(locality_key(name), name)

    regions: dict[str, list[str]] = collections.defaultdict(list)
    for _, name, subdistrict, council in cbs:
        canonical = canonical_of[name]
        if council:
            regions[council].append(canonical)
        if subdistrict in REGION_SUBDISTRICTS:
            regions[REGION_SUBDISTRICTS[subdistrict]].append(canonical)
        if subdistrict in WEST_BANK_SUBDISTRICTS:
            regions["יהודה ושומרון"].append(canonical)
    for region, members in CUSTOM_REGIONS.items():
        regions[region].extend(members)
    regions = {r: sorted(set(m)) for r, m in sorted(regions.items()) if len(set(m)) >= 2}

    lines = [
        '"""GENERATED by scripts/build_localities.py - do not edit by hand (see that script\'s docstring).',
        "",
        "Every Israeli locality and area beyond cities.CITIES: the Central Bureau of Statistics list (data.gov.il) joined",
        'with the spellings our listings use. Exposed through todira_common.cities (LOCALITIES, REGIONS, resolve_locality)."""',
        "",
        "# Stored spellings, in a fixed order (the bot's buttons carry an index into cities.LOCALITIES = CITIES + this list).",
        "EXTRA_LOCALITIES: list[str] = [",
        *[f"    {n!r}," for n in extra],
        "]",
        "",
        "# locality_key(any spelling) -> stored spelling",
        "ALIASES: dict[str, str] = {",
        *[f"    {k!r}: {v!r}," for k, v in sorted(aliases.items())],
        "}",
        "",
        "# area (regional council, sub-district, common name) -> its localities' stored spellings",
        "REGIONS: dict[str, list[str]] = {",
        *[f"    {r!r}: {m!r}," for r, m in regions.items()],
        "}",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(CITIES)} major + {len(extra)} more localities, {len(aliases)} spellings, {len(regions)} areas -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
