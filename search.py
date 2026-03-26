"""
MLS Listing Search — powered by HomeHarvest (Redfin / Zillow / Realtor.com)
Run manually or schedule with Windows Task Scheduler.
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

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config.json"

LISTING_TYPE_MAP = {
    "for sale": "for_sale",
    "sold":     "sold",
    "pending":  "pending",
}


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_listings(config: dict) -> list[dict]:
    filters  = config["filters"]
    location = config["location"]
    status_list = filters.get("status", ["for sale"])
    listing_type = LISTING_TYPE_MAP.get(status_list[0], "for_sale")

    prop_types = filters.get("property_types", [])
    # homeharvest accepts: single_family, multi_family, condos, townhomes, land, mobile
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
        "limit":        200,
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

    listings = []
    for _, row in df.iterrows():
        mls_id = str(row.get("mls_id", "") or row.get("property_url", ""))
        listings.append({
            "id":            mls_id,
            "address":       str(row.get("street", "") or ""),
            "city":          str(row.get("city", "") or ""),
            "state":         str(row.get("state", "") or ""),
            "zip":           str(row.get("zip_code", "") or ""),
            "price":         row.get("list_price", ""),
            "beds":          row.get("beds", ""),
            "baths":         row.get("full_baths", ""),
            "sqft":          row.get("sqft", ""),
            "property_type": str(row.get("style", "") or ""),
            "year_built":    row.get("year_built", ""),
            "days_on_market": row.get("days_on_market", ""),
            "url":           str(row.get("property_url", "") or ""),
            "fetched_at":    datetime.now().isoformat(timespec="seconds"),
        })

    return [l for l in listings if l["id"]]


# ── Persistence ───────────────────────────────────────────────────────────────

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


# ── Display ───────────────────────────────────────────────────────────────────

def fmt_price(val) -> str:
    try:
        return f"${int(float(str(val).replace(',', ''))):,}"
    except (ValueError, TypeError):
        return str(val)


def print_listing(listing: dict, label: str = "NEW"):
    print(f"\n  [{label}] {listing['address']}, {listing['city']}, {listing['state']} {listing['zip']}")
    print(f"        Price: {fmt_price(listing['price'])}  |  Beds: {listing['beds']}  |  Baths: {listing['baths']}  |  Sqft: {listing['sqft']}")
    print(f"        Type: {listing['property_type']}  |  Days on market: {listing['days_on_market']}")
    if listing["url"]:
        print(f"        {listing['url']}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open(CONFIG_FILE) as f:
        config = json.load(f)

    out_cfg        = config["output"]
    results_dir    = SCRIPT_DIR / out_cfg["results_dir"]
    seen_file      = results_dir / out_cfg["seen_listings_file"]
    csv_file       = results_dir / out_cfg["csv_filename"]
    print_new_only = out_cfg.get("print_new_only", True)
    filters        = config["filters"]
    results_dir.mkdir(exist_ok=True)

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Searching: {config['location']}")
    print(f"  Filters: price ${filters.get('min_price', 0):,} to ${filters.get('max_price', 0):,}  |  "
          f"beds >= {filters.get('min_beds', 'any')}  |  baths >= {filters.get('min_baths', 'any')}")

    try:
        listings = fetch_listings(config)
    except Exception as e:
        print(f"  ERROR fetching listings: {e}")
        sys.exit(1)

    print(f"  Fetched {len(listings)} listing(s)")

    seen         = load_seen(seen_file)
    new_listings = [l for l in listings if l["id"] not in seen]
    print(f"  New since last run: {len(new_listings)}")

    if new_listings:
        append_to_csv(csv_file, new_listings)
        for l in new_listings:
            seen.add(l["id"])
        save_seen(seen_file, seen)
        print(f"  Saved to: {csv_file}")

    to_print = new_listings if print_new_only else listings
    if not to_print:
        print("  No new listings to display.")
    else:
        print(f"\n{'-'*70}")
        for listing in to_print:
            label = "NEW" if listing in new_listings else "   "
            print_listing(listing, label)
        print(f"{'-'*70}")

    print(f"\nDone. Total listings tracked: {len(seen)}")


if __name__ == "__main__":
    main()
