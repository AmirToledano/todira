"""Builds common/todira_common/assets/streets.json.gz: every street of every locality, for the bot's "did you mean".

Owner request (2026-11-11): people type street names in many spellings, so the bot offers names from a list. Inputs,
written by .github/workflows/fetch-streets-data.yaml to the data/streets branch (git show origin/data/streets:<file>):
  streets.tsv          city code|city|street code|street   (the official list, data.gov.il)
  listing_streets.tsv  city|street|live listings          (spellings our live listings use)

Usage: python scripts/build_streets.py streets.tsv listing_streets.tsv

Each locality is stored under our own spelling (cities.resolve_locality). Its streets are the official names, the ones
our listings use most first; a listings spelling of an official street is not added twice (place_names.street_key).
"""
from __future__ import annotations

import collections
import gzip
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

from todira_common.cities import resolve_locality
from todira_common.place_names import street_key

OUT = ROOT / "common" / "todira_common" / "assets" / "streets.json.gz"
LOCALITY_ITSELF = "9000"  # the official list's code for a row that names the locality, not a street
# The official list abbreviates the first word; people read (and type) it in full.
FIRST_WORD = {"שד": "שדרות", "סמ": "סמטת", "מד": "מדרגות", "שכ": "שכונת", "ש": "שכונת", "רח": "רחוב"}


def display_name(name: str) -> str:
    first, _sep, rest = name.partition(" ")
    return f"{FIRST_WORD[first]} {rest}" if rest and first in FIRST_WORD else name


def main(streets_path: str, listing_streets_path: str) -> None:
    popularity: dict[tuple[str, str], int] = collections.Counter()
    for line in pathlib.Path(listing_streets_path).read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        city, street, count = parts[0], parts[1].strip(), int(parts[2])
        key = street_key(street)
        if city and key:
            popularity[(city, key)] += count

    official: dict[str, dict[str, str]] = collections.defaultdict(dict)
    unknown_cities = collections.Counter()
    for line in pathlib.Path(streets_path).read_text(encoding="utf-8").splitlines():
        parts = line.split("|")
        if len(parts) != 4 or parts[2].strip() == LOCALITY_ITSELF:
            continue
        city = resolve_locality(parts[1].strip())
        name = display_name(" ".join(parts[3].split()))
        if not city:
            unknown_cities[parts[1].strip()] += 1
            continue
        key = street_key(name)
        if key and not key.isdigit():  # "רחוב 1064": numbered streets nobody writes in an ad
            official[city].setdefault(key, name)

    data = {}
    for city, by_key in official.items():
        names = sorted(by_key.items(), key=lambda kv: (-popularity.get((city, kv[0]), 0), kv[1]))
        data[city] = [name for _key, name in names]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    print(f"{len(data)} localities, {sum(len(v) for v in data.values())} streets -> {OUT} ({OUT.stat().st_size // 1024} KB)")
    if unknown_cities:
        print("localities not in our list (skipped):", ", ".join(f"{c} ({n})" for c, n in unknown_cities.most_common(15)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
