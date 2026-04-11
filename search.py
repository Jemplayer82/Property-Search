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
    filters      = config["filters"]
    location     = config["location"]
    site         = config.get("site", "realtor.com")
    status_list  = filters.get("status", ["for sale"])
    listing_type = LISTING_TYPE_MAP.get(status_list[0], "for_sale")

    try:
        results = scrape_property(
            location=location,
            site_name=site,
            listing_type=listing_type,
        )
    except Exception as e:
        if "no results" in str(e).lower():
            return []
        raise

    if not results:
        return []

    listings = []
    for prop in results:
        # Skip Building objects (multi-unit — no individual price/bed/bath)
        if not hasattr(prop, "price"):
            continue

        addr = prop.address
        mls_id = getattr(prop, "mls_id", None) or prop.url
        listings.append({
            "id":             str(mls_id),
            "address":        getattr(addr, "address_one", "") or "",
            "city":           getattr(addr, "city", "") or "",
            "state":          getattr(addr, "state", "") or "",
            "zip":            getattr(addr, "zip_code", "") or "",
            "price":          getattr(prop, "price", None),
            "beds":           getattr(prop, "beds", None),
            "baths":          getattr(prop, "baths", None),
            "sqft":           getattr(prop, "square_feet", None),
            "property_type":  str(getattr(prop, "listing_type", "") or ""),
            "year_built":     getattr(prop, "year_built", None),
            "days_on_market": None,
            "list_date":      "",
            "url":            getattr(prop, "url", "") or "",
            "photo":          "",
            "latitude":       None,
            "longitude":      None,
            "fetched_at":     datetime.now().isoformat(timespec="seconds"),
        })

    # Apply filters manually
    min_price = filters.get("min_price") or 0
    max_price = filters.get("max_price") or 0
    min_beds  = filters.get("min_beds") or 0
    min_baths = filters.get("min_baths") or 0
    min_sqft  = filters.get("min_sqft")
    max_sqft  = filters.get("max_sqft")

    def passes(l):
        price = l["price"]
        if price is not None:
            try:
                p = float(price)
                if min_price and p < min_price:
                    return False
                if max_price and p > max_price:
                    return False
            except (ValueError, TypeError):
                pass
        if min_beds and l["beds"] is not None:
            try:
                if float(l["beds"]) < min_beds:
                    return False
            except (ValueError, TypeError):
                pass
        if min_baths and l["baths"] is not None:
            try:
                if float(l["baths"]) < min_baths:
                    return False
            except (ValueError, TypeError):
                pass
        if min_sqft and l["sqft"] is not None:
            try:
                if float(l["sqft"]) < min_sqft:
                    return False
            except (ValueError, TypeError):
                pass
        if max_sqft and l["sqft"] is not None:
            try:
                if float(l["sqft"]) > max_sqft:
                    return False
            except (ValueError, TypeError):
                pass
        return True

    results_filtered = [l for l in listings if l["id"] and passes(l)]

    current_year = datetime.now().year
    max_age = filters.get("max_age")
    min_age = filters.get("min_age")

    if max_age:
        min_built = current_year - int(max_age)
        results_filtered = [l for l in results_filtered if l["year_built"] and str(l["year_built"]).isdigit() and int(l["year_built"]) >= min_built]
    if min_age:
        max_built = current_year - int(min_age)
        results_filtered = [l for l in results_filtered if l["year_built"] and str(l["year_built"]).isdigit() and int(l["year_built"]) <= max_built]

    return results_filtered


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
