#!/usr/bin/env python3
"""
Fetch current F1 Fantasy prices and write prices.json for the APEX app.

Output shape (what the app expects):
{
  "season": 2026,
  "updated": "2026-06-15T06:00:00Z",
  "drivers":      { "VER": 28.5, "NOR": 30.0, ... },   # keyed by 3-letter code
  "constructors": { "MCL": 30.5, "RBR": 24.0, ... }    # keyed by APEX team code
}

IMPORTANT, READ ONCE:
  This reads an UNDOCUMENTED endpoint of the official F1 Fantasy game
  (fantasy-api.formula1.com). It is not an official, supported API:
    * The field names below are best-effort and MAY differ from the live
      response. Run `python scrape_prices.py --debug` once to print the raw
      keys, then adjust PRICE_KEYS / NAME_KEYS / POSITION_KEYS if needed.
    * Scraping it may be against F1's Terms of Use. Keep the frequency low
      (the workflow runs twice a week), send a real User-Agent, and stop if
      asked. This is for personal analysis.
  The APEX app works with ANY prices.json in the shape above, so if this
  endpoint changes or you'd rather source prices elsewhere, you only need to
  produce that JSON — the app side doesn't care where it came from.
"""

import argparse
import datetime as dt
import json
import sys
import urllib.request
import urllib.error

SEASON = dt.datetime.now(dt.timezone.utc).year
BASE = f"https://fantasy-api.formula1.com/partner_games/f1/{SEASON}"
UA = "apex-f1-fantasy price sync (personal, low-frequency)"
print("PLAYERS_URL =", PLAYERS_URL)
print("TEAMS_URL =", TEAMS_URL)

# Candidate field names — the script tries each in order. Adjust after --debug.
PRICE_KEYS = ["current_price", "price", "cost", "value", "price_now"]
CODE_KEYS = ["abbreviation", "code", "short_name", "team_abbreviation", "abbr"]
NAME_KEYS = ["display_name", "name", "team_name", "full_name", "known_name", "last_name"]
POSITION_KEYS = ["position", "player_type", "type", "role"]

# Map F1's constructor names/ids -> APEX team codes (match the app's codes).
CON_CODES = {
    "redbull": "RBR", "redbullracing": "RBR", "oracleredbullracing": "RBR",
    "racingbulls": "RB", "rb": "RB", "visacashappracingbulls": "RB", "vcarb": "RB",
    "mclaren": "MCL", "ferrari": "FER", "scuderiaferrari": "FER",
    "mercedes": "MER", "mercedesamg": "MER",
    "williams": "WIL", "astonmartin": "AST", "alpine": "ALP",
    "haas": "HAA", "haasf1team": "HAA",
    "kicksauber": "AUD", "sauber": "AUD", "audi": "AUD",
    "cadillac": "CAD",
}


def fetch(path):
    url = f"{BASE}/{path}"
    print(f"Fetching {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def find_records(obj):
    """Locate the list of player/team dicts anywhere in the response."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            return obj
        return []
    if isinstance(obj, dict):
        for v in obj.values():
            found = find_records(v)
            if found:
                return found
    return []


def pick(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def norm(s):
    return "".join(c for c in str(s).lower() if c.isalnum())


def to_price(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def is_driver(rec):
    pos = pick(rec, POSITION_KEYS)
    return pos is None or "driv" in str(pos).lower()


def build():
    debug = "--debug" in sys.argv
    drivers, constructors = {}, {}

    for path, bucket in (("players", "drivers"), ("teams", "constructors")):
        try:
            raw = fetch(path)
        except urllib.error.HTTPError as e:
            print(f"  ! {path}: HTTP {e.code} — endpoint may have changed", file=sys.stderr)
            continue
        except Exception as e:  # noqa
            print(f"  ! {path}: {e}", file=sys.stderr)
            continue

        records = find_records(raw)
        if debug and records:
            print(f"--- {path}: {len(records)} records; sample keys: "
                  f"{sorted(records[0].keys())}", file=sys.stderr)

        for rec in records:
            price = to_price(pick(rec, PRICE_KEYS))
            if price is None:
                continue
            if bucket == "drivers":
                code = pick(rec, CODE_KEYS)
                if not code:
                    continue
                drivers[str(code).upper()[:3]] = price
            else:
                name = pick(rec, CODE_KEYS + NAME_KEYS) or ""
                code = CON_CODES.get(norm(name))
                if not code:
                    # fall back to writing the raw name; the app can match by name
                    code = str(name)
                constructors[code] = price

    return drivers, constructors


def main():
    argparse.ArgumentParser(description=__doc__).parse_known_args()
    drivers, constructors = build()
    if not drivers and not constructors:
        print("No prices extracted — run with --debug and adjust the *_KEYS lists.",
              file=sys.stderr)
        sys.exit(1)

    out = {
        "season": SEASON,
        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "drivers": dict(sorted(drivers.items())),
        "constructors": dict(sorted(constructors.items())),
    }
    with open("prices.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote prices.json: {len(drivers)} drivers, {len(constructors)} constructors.")


if __name__ == "__main__":
    main()
