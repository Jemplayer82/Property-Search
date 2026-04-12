"""
MLS Listing Search — powered by HomeHarvest (Redfin / Zillow / Realtor.com)
Run manually or via the web app.
"""

import json
import csv
import sys
from datetime import datetime
from pathlib import Path

try:
    from homeharvest import scrape_property
except ImportError:
    print("Missing dependency. Run: pip install homeharvest")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

LISTING_TYPE_MAP = {
    "for sale": "for_sale",
    "sold":     "sold",
    "pending":  "pending",
}


def fetch_listings(config: dict) -> list[dict]:
    filters  = config["filters"]
    location = config["location"]
    status_list = filters.get("status", ["for sale"])
    listing_type = LISTING_TYPE_MAP.get(status_list[0], "for_sale")

    prop_types = filters.get("property_types", [])
    hh_type_map = {
        "house":        "single_family",
        "multi-family": "multi_family",
        "condo":        "condos",
        "townhouse":    "townhomes",
        "land":         "land",
        "mobile":       "mobile",
    }
    hh_types = list({hh_type_map[p] for p in prop_types if p in hh_type_map}) or None

    kwargs = {
        "location":     location,
        "listing_type": listing_type,
    }
    if filters.get("min_price"):
        kwargs["price_min"] = filters["min_price"]
    if filters.get("max_price"):
        kwargs["price_max"] = filters["max_price"]
    if filters.get("min_beds"):
        kwargs["beds_min"] = filters["min_beds"]
    if filters.get("min_baths"):
        kwargs["baths_min"] = filters["min_baths"]
    if filters.get("min_sqft"):
        kwargs["sqft_min"] = filters["min_sqft"]
    if filters.get("max_sqft"):
        kwargs["sqft_max"] = filters["max_sqft"]
    if filters.get("distance"):
        kwargs["radius"] = float(filters["distance"])
    if hh_types:
        kwargs["property_type"] = hh_types

    try:
        df = scrape_property(**kwargs)
    except Exception as e:
        if "no results" in str(e).lower():
            return []
        raise

    if df is None or df.empty:
        return []

    import pandas as pd

    def safe(v, fallback=""):
        try:
            v_str = str(v)
            if v_str.lower() in ("nan", "none", "<na>", ""):
                return fallback
            if pd.isna(v):
                return fallback
        except Exception:
            pass
        return v

    listings = []
    for _, row in df.iterrows():
        mls_id_val = safe(row.get("mls_id"), "")
        url_val = safe(row.get("property_url"), "")
        mls_id = str(mls_id_val or url_val)
        listings.append({
            "id":             mls_id,
            "address":        str(safe(row.get("street"), "")),
            "city":           str(safe(row.get("city"), "")),
            "state":          str(safe(row.get("state"), "")),
            "zip":            str(safe(row.get("zip_code"), "")),
            "price":          safe(row.get("list_price")),
            "beds":           safe(row.get("beds")),
            "baths":          safe(row.get("full_baths")),
            "sqft":           safe(row.get("sqft")),
            "property_type":  str(safe(row.get("style"), "")),
            "year_built":     safe(row.get("year_built")),
            "days_on_market": safe(row.get("days_on_mls")),
            "list_date":      str(safe(row.get("list_date"), "")),
            "url":            str(safe(row.get("property_url"), "")),
            "photo":          safe(row.get("primary_photo"), ""),
            "latitude":       safe(row.get("latitude")),
            "longitude":      safe(row.get("longitude")),
            "fetched_at":     datetime.now().isoformat(timespec="seconds"),
        })

    results = [l for l in listings if l["id"]]

    current_year = datetime.now().year
    max_age = filters.get("max_age")
    min_age = filters.get("min_age")

    if max_age:
        min_built = current_year - int(max_age)
        results = [l for l in results if l["year_built"] and str(l["year_built"]).isdigit() and int(l["year_built"]) >= min_built]
    if min_age:
        max_built = current_year - int(min_age)
        results = [l for l in results if l["year_built"] and str(l["year_built"]).isdigit() and int(l["year_built"]) <= max_built]

    return results


def load_seen(path: Path) -> set:
    if path.exists():
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen(path: Path, seen: set):
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def append_to_csv(path: Path, listings: list[dict]):
    if not listings:
        return
    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=listings[0].keys())
        if write_header:
            writer.writeheader()
        writer.writerows(listings)


def fmt_price(val) -> str:
    try:
        return f"${int(float(str(val).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(val)


def main():
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    out_cfg     = config["output"]
    results_dir = SCRIPT_DIR / out_cfg["results_dir"]
    seen_file   = results_dir / out_cfg["seen_listings_file"]
    csv_file    = results_dir / out_cfg["csv_filename"]
    results_dir.mkdir(exist_ok=True)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Searching: {config['location']}")
    try:
        listings = fetch_listings(config)
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)

    seen = load_seen(seen_file)
    new_listings = [l for l in listings if l["id"] not in seen]
    print(f"  Fetched {len(listings)} · New: {len(new_listings)}")

    if new_listings:
        append_to_csv(csv_file, new_listings)
        for l in new_listings:
            seen.add(l["id"])
        save_seen(seen_file, seen)

    print(f"Done. Total tracked: {len(seen)}")


if __name__ == "__main__":
    main()
