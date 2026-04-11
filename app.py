from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json
import os
import csv
import uuid
import time
import threading
import smtplib
import requests as req
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.middleware.proxy_fix import ProxyFix
from search import fetch_listings, load_seen, save_seen, append_to_csv, fmt_price
import math
import logging

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ps-2024-secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

BASE          = Path(__file__).parent
CONFIG_FILE   = BASE / "config.json"
NOTIFY_FILE   = BASE / "notifications.json"
CLIENTS_FILE  = BASE / "clients.json"
RESULTS_DIR   = BASE / "results"
GEOCACHE_FILE = RESULTS_DIR / "geocache.json"
RESULTS_DIR.mkdir(exist_ok=True)


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def load_notify():
    if NOTIFY_FILE.exists():
        with open(NOTIFY_FILE) as f:
            return json.load(f)
    return {"enabled": False, "email": "", "smtp_host": "smtp.gmail.com",
            "smtp_port": 587, "smtp_user": "", "smtp_pass": ""}

def save_notify(n):
    with open(NOTIFY_FILE, "w") as f:
        json.dump(n, f, indent=2)

def load_clients():
    if CLIENTS_FILE.exists():
        with open(CLIENTS_FILE) as f:
            return json.load(f)
    return []

def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)

def load_geocache():
    if GEOCACHE_FILE.exists():
        with open(GEOCACHE_FILE) as f:
            return json.load(f)
    return {}

def save_geocache(cache):
    with open(GEOCACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def geocode(address, cache):
    """Geocode an address to lat/lng using Nominatim with caching and error handling."""
    if not address or not isinstance(address, str):
        logger.warning(f"Invalid address for geocoding: {address}")
        return None

    address = address.strip()

    # Check cache first
    if address in cache:
        logger.debug(f"Cache hit for address: {address}")
        return cache[address]

    try:
        logger.info(f"Geocoding address: {address}")
        resp = req.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": "PropertySearch/1.0"},
            timeout=10,  # Increased timeout
        )
        resp.raise_for_status()  # Raise exception for bad status

        data = resp.json()
        if data and len(data) > 0:
            try:
                result = {
                    "lat": float(data[0]["lat"]),
                    "lng": float(data[0]["lon"])
                }
                cache[address] = result
                logger.info(f"Successfully geocoded {address}: {result}")
                time.sleep(0.2)  # Be respectful to Nominatim API
                return result
            except (ValueError, KeyError) as e:
                logger.error(f"Error parsing geocoding response for {address}: {e}")
                return None
        else:
            logger.warning(f"No geocoding results for address: {address}")
            return None

    except req.exceptions.Timeout:
        logger.error(f"Geocoding timeout for address: {address}")
        return None
    except req.exceptions.RequestException as e:
        logger.error(f"Geocoding request error for {address}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error geocoding {address}: {e}")
        return None

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in miles between two coordinates using Haversine formula."""
    R = 3959  # Earth radius in miles
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

_US_STATES = {
    'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN',
    'IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV',
    'NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN',
    'TX','UT','VT','VA','WA','WV','WI','WY','DC',
}

def extract_zip_or_city(address):
    """Extract ZIP code (preferred), city+state, or original address for HomHarvest."""
    words = address.replace(',', ' ').split()

    # 1. Prefer 5-digit zip — scan right to left
    for w in reversed(words):
        if len(w) == 5 and w.isdigit():
            return w

    # 2. Look for a US state abbreviation scanning RIGHT TO LEFT — state is always
    #    near the end of an address, so scanning right avoids false matches with
    #    street types like "Ct" (Court) that share abbreviations with states (CT).
    for i in range(len(words) - 1, 0, -1):
        if words[i].upper() in _US_STATES:
            return words[i - 1] + ' ' + words[i].upper()

    return address

def filter_by_distance(listings, location, max_distance, geocache):
    """Filter listings by distance from a center point location.

    Args:
        listings: List of listing dictionaries
        location: Center point address to filter from
        max_distance: Maximum distance in miles
        geocache: Dictionary to cache geocoded addresses

    Returns:
        List of listings within max_distance miles of location
    """
    if not listings:
        logger.warning("No listings to filter")
        return listings

    if not max_distance or max_distance <= 0:
        logger.debug("Distance is 0 or negative, returning all listings")
        return listings

    # Geocode the center point with fallback strategy
    logger.info(f"Geocoding center point: {location} with max distance {max_distance} miles")
    coords = geocode(location, geocache)

    # If exact address fails, try extracting city/state as fallback
    if not coords:
        fallback_location = extract_zip_or_city(location)
        if fallback_location != location:
            logger.warning(f"Failed to geocode exact address, trying fallback: {fallback_location}")
            coords = geocode(fallback_location, geocache)

    if not coords:
        logger.error(f"Failed to geocode center point: {location}. Returning all listings.")
        return listings

    logger.info(f"Center point coordinates: lat={coords['lat']}, lng={coords['lng']}")

    filtered = []
    failed_coords = 0
    invalid_distance = 0

    for listing in listings:
        try:
            # Get latitude and longitude from listing
            lat_val = listing.get("latitude")
            lng_val = listing.get("longitude")

            # Validate that we have coordinate values
            if lat_val is None or lng_val is None:
                failed_coords += 1
                continue

            # Convert to string and validate
            lat_str = str(lat_val).strip()
            lng_str = str(lng_val).strip()

            # Skip if coordinates are invalid/empty
            if not lat_str or not lng_str:
                failed_coords += 1
                continue

            # Check for special invalid values
            if lat_str.lower() in ("nan", "none", "<na>", "null") or \
               lng_str.lower() in ("nan", "none", "<na>", "null"):
                invalid_distance += 1
                continue

            # Convert to float
            try:
                lat = float(lat_str)
                lng = float(lng_str)
            except ValueError:
                logger.debug(f"Could not convert coords to float: lat={lat_str}, lng={lng_str}")
                failed_coords += 1
                continue

            # Validate coordinate ranges (latitude: -90 to 90, longitude: -180 to 180)
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                logger.debug(f"Invalid coordinate ranges: lat={lat}, lng={lng}")
                invalid_distance += 1
                continue

            # Calculate distance
            distance = calculate_distance(coords["lat"], coords["lng"], lat, lng)

            # Check if within range
            if distance <= max_distance:
                filtered.append(listing)

        except Exception as e:
            logger.debug(f"Error processing listing {listing.get('address', 'unknown')}: {e}")
            continue

    logger.info(f"Distance filtering complete: {len(filtered)} of {len(listings)} listings within {max_distance} miles")
    logger.info(f"  Listings with failed coordinates: {failed_coords}")
    logger.info(f"  Listings with invalid distance values: {invalid_distance}")

    return filtered

def send_notification(listings, notify, client_name=None):
    if not notify.get("smtp_user") or not notify.get("email"):
        return
    try:
        subject = f"[Property Search] {len(listings)} New Listing(s)"
        if client_name:
            subject = f"[Property Search] {len(listings)} New Listing(s) for {client_name}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = notify["smtp_user"]
        msg["To"]      = notify["email"]

        cards = []
        for l in listings:
            is_new   = l.get("is_new", False)
            border   = "2px solid #198754" if is_new else "1px solid #dee2e6"
            new_badge = '<div style="display:inline-block;background:#198754;color:#fff;font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;margin-bottom:6px">NEW</div><br>' if is_new else ""
            photo_html = ""
            photo = l.get("photo", "")
            if photo and str(photo) not in ("", "None"):
                photo_html = f'<img src="{photo}" style="width:100%;height:180px;object-fit:cover;display:block" referrerpolicy="no-referrer">'
            view_btn = ""
            if l.get("url"):
                view_btn = f'<a href="{l["url"]}" style="display:block;text-align:center;margin-top:10px;padding:7px;border:1px solid #0d6efd;border-radius:4px;color:#0d6efd;text-decoration:none;font-size:13px">View Listing &#8599;</a>'
            cards.append(f"""
<td width="48%" valign="top" style="padding:6px">
  <div style="border:{border};border-radius:8px;overflow:hidden;font-family:Arial,sans-serif;font-size:13px;background:#fff">
    {photo_html}
    <div style="padding:12px">
      {new_badge}
      <div style="font-weight:600;font-size:14px;margin-bottom:2px">{l.get('address','—')}</div>
      <div style="color:#6c757d;margin-bottom:6px">{l.get('city','')}, {l.get('state','')} {l.get('zip','')}</div>
      <div style="color:#0d6efd;font-size:18px;font-weight:700;margin-bottom:6px">{fmt_price(l.get('price',''))}</div>
      <div style="color:#6c757d;margin-bottom:4px">
        &#127968; {l.get('beds','—')} bed &nbsp;&middot;&nbsp;
        &#128167; {l.get('baths','—')} bath &nbsp;&middot;&nbsp;
        &#128207; {l.get('sqft','—')} sqft
      </div>
      <div style="color:#6c757d">{l.get('property_type','') or ''} &middot; {l.get('days_on_market','—')} days on market</div>
      {view_btn}
    </div>
  </div>
</td>""")

        # Pair cards into rows of 2
        rows = []
        for i in range(0, len(cards), 2):
            pair = cards[i:i+2]
            if len(pair) == 1:
                pair.append('<td width="48%"></td>')
            rows.append(f"<tr>{''.join(pair)}</tr>")

        greeting = f"<p style='font-family:Arial,sans-serif'>Hi {client_name},<br>Here are your latest matching listings:</p>" if client_name else ""
        html = f"""
<div style="background:#f8f9fa;padding:20px;font-family:Arial,sans-serif">
  <h2 style="margin-bottom:4px">Property Search Results</h2>
  <p style="color:#6c757d;margin-top:0">{len(listings)} listing(s) found</p>
  {greeting}
  <table width="100%" cellspacing="0" cellpadding="0">
    {''.join(rows)}
  </table>
</div>"""

        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(notify["smtp_host"], int(notify["smtp_port"])) as s:
            s.starttls()
            s.login(notify["smtp_user"], notify["smtp_pass"])
            s.send_message(msg)
    except Exception as e:
        print(f"Email error: {e}")

def search_location_for(location):
    """Return a HomHarvest-compatible search location.
    Full street addresses are converted to zip/city so HomHarvest does an
    area search rather than a single-property lookup."""
    words = location.split()
    is_street = bool(words) and words[0].isdigit() and len(words) > 2
    return extract_zip_or_city(location) if is_street else location

def run_client_search(client, send_email=True):
    f = client["filters"]
    location = f.get("location", "")
    distance = f.get("distance", 0)

    config = {
        "location": search_location_for(location),
        "filters": {
            "min_price":      f.get("min_price", 0),
            "max_price":      f.get("max_price", 0),
            "min_beds":       f.get("min_beds", 0),
            "min_baths":      f.get("min_baths", 0),
            "property_types": f.get("property_types", []),
            "status":         [f.get("status", "for sale")],
            "min_sqft":       f.get("min_sqft"),
            "max_sqft":       f.get("max_sqft"),
            "max_age": f.get("max_age"),
            "min_age": f.get("min_age"),
            "distance": distance,
        },
        "output": {
            "results_dir":        "results",
            "seen_listings_file": f"seen_{client['id']}.json",
            "csv_filename":       f"listings_{client['id']}.csv",
            "print_new_only":     True,
        }
    }

    try:
        listings = fetch_listings(config)
    except Exception as e:
        logger.error(f"Error fetching listings for client {client['id']}: {e}", exc_info=True)
        return [], []

    seen_file = RESULTS_DIR / f"seen_{client['id']}.json"
    csv_file  = RESULTS_DIR / f"listings_{client['id']}.csv"
    seen      = load_seen(seen_file)
    new       = [l for l in listings if l["id"] not in seen]

    if new:
        append_to_csv(csv_file, new)
        for l in new:
            seen.add(l["id"])
        save_seen(seen_file, seen)

        if send_email:
            notify = load_notify()
            client_notify = dict(notify)
            client_notify["email"] = client["email"]
            client_name = f"{client['first_name']} {client['last_name']}"
            threading.Thread(target=send_notification, args=(new, client_notify, client_name), daemon=True).start()

            # Track when we last emailed this client
            all_clients = load_clients()
            for c in all_clients:
                if c["id"] == client["id"]:
                    c["last_emailed"] = datetime.now().isoformat(timespec="seconds")
                    break
            save_clients(all_clients)

    new_ids = {l["id"] for l in new}
    for l in listings:
        l["is_new"] = l["id"] in new_ids

    return listings, new


# ── General search ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("clients"))

@app.route("/search-page")
def search_page():
    cid = request.args.get('client')
    preset_client = None
    if cid:
        preset_client = next((c for c in load_clients() if c['id'] == cid), None)
    return render_template("index.html", config=load_config(), preset_client=preset_client)

@app.route("/search", methods=["POST"])
def run_search():
    config = load_config()
    data   = request.get_json() or {}

    config["location"] = search_location_for(data.get("location", config["location"]))
    f = config["filters"]
    f["min_price"]       = int(data.get("min_price") or 0)
    f["max_price"]       = int(data.get("max_price") or 0)
    f["min_beds"]        = int(data.get("min_beds") or 0)
    f["min_baths"]       = int(data.get("min_baths") or 0)
    f["status"]          = [data.get("status", "for sale")]
    f["min_sqft"] = int(data.get("min_sqft") or 0) or None
    f["max_sqft"] = int(data.get("max_sqft") or 0) or None
    f["max_age"] = data.get("max_age") or None
    f["min_age"] = data.get("min_age") or None
    f["distance"] = float(data.get("distance") or 0)
    types = data.get("property_types", [])
    if types:
        f["property_types"] = types
    save_config(config)

    distance = float(f.get("distance", 0) or 0)

    try:
        logger.info(f"Fetching listings for location: {config['location']}")
        listings = fetch_listings(config)
        logger.info(f"Fetched {len(listings)} listings")
    except Exception as e:
        logger.error(f"Error fetching listings: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    out       = config["output"]
    seen_file = RESULTS_DIR / out["seen_listings_file"]
    csv_file  = RESULTS_DIR / out["csv_filename"]
    seen      = load_seen(seen_file)
    new       = [l for l in listings if l["id"] not in seen]

    if new:
        append_to_csv(csv_file, new)
        for l in new:
            seen.add(l["id"])
        save_seen(seen_file, seen)
        notify = load_notify()
        threading.Thread(target=send_notification, args=(new, notify), daemon=True).start()

    new_ids = {l["id"] for l in new}
    for l in listings:
        l["is_new"] = l["id"] in new_ids

    return jsonify({"total": len(listings), "new": len(new), "listings": listings})


# ── Clients ───────────────────────────────────────────────────────────────────

@app.route("/clients")
def clients():
    return render_template("clients.html", clients=load_clients())

@app.route("/clients/new", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        client = {
            "id":         str(uuid.uuid4()),
            "first_name": request.form["first_name"].strip(),
            "last_name":  request.form["last_name"].strip(),
            "email":      request.form["email"].strip(),
            "email_frequency": request.form.get("email_frequency", "every_new_listing"),
            "last_emailed":    None,
            "filters": {
                "location":       request.form.get("location", "").strip(),
                "distance":       float(request.form.get("distance") or 0),
                "min_price":      int(request.form.get("min_price") or 0),
                "max_price":      int(request.form.get("max_price") or 0),
                "min_beds":       int(request.form.get("min_beds") or 0),
                "min_baths":      int(request.form.get("min_baths") or 0),
                "property_types": request.form.getlist("property_types"),
                "status":         request.form.get("status", "for sale"),
                "min_sqft": int(request.form.get("min_sqft") or 0) or None,
                "max_sqft": int(request.form.get("max_sqft") or 0) or None,
                "max_age": int(request.form.get("max_age") or 0) or None,
                "min_age": int(request.form.get("min_age") or 0) or None,
            },
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        all_clients = load_clients()
        all_clients.append(client)
        save_clients(all_clients)
        flash(f"Client {client['first_name']} {client['last_name']} created!", "success")
        return redirect(url_for("clients"))
    return render_template("client_form.html", client=None, title="New Client")

@app.route("/clients/<cid>/edit", methods=["GET", "POST"])
def edit_client(cid):
    all_clients = load_clients()
    client = next((c for c in all_clients if c["id"] == cid), None)
    if not client:
        flash("Client not found.", "danger")
        return redirect(url_for("clients"))

    if request.method == "POST":
        client["first_name"] = request.form["first_name"].strip()
        client["last_name"]  = request.form["last_name"].strip()
        client["email"]      = request.form["email"].strip()
        client["email_frequency"] = request.form.get("email_frequency", "every_new_listing")
        client["filters"] = {
            "location":       request.form.get("location", "").strip(),
            "distance":       float(request.form.get("distance") or 0),
            "min_price":      int(request.form.get("min_price") or 0),
            "max_price":      int(request.form.get("max_price") or 0),
            "min_beds":       int(request.form.get("min_beds") or 0),
            "min_baths":      int(request.form.get("min_baths") or 0),
            "property_types": request.form.getlist("property_types"),
            "status":         request.form.get("status", "for sale"),
            "min_sqft": int(request.form.get("min_sqft") or 0) or None,
            "max_sqft": int(request.form.get("max_sqft") or 0) or None,
            "max_age": int(request.form.get("max_age") or 0) or None,
            "min_age": int(request.form.get("min_age") or 0) or None,
        }
        save_clients(all_clients)
        flash("Client updated!", "success")
        return redirect(url_for("clients"))
    return render_template("client_form.html", client=client, title="Edit Client")

@app.route("/clients/<cid>/delete", methods=["POST"])
def delete_client(cid):
    all_clients = [c for c in load_clients() if c["id"] != cid]
    save_clients(all_clients)
    flash("Client deleted.", "info")
    return redirect(url_for("clients"))

@app.route("/clients/<cid>/search", methods=["POST"])
def search_for_client(cid):
    all_clients = load_clients()
    client = next((c for c in all_clients if c["id"] == cid), None)
    if not client:
        return jsonify({"error": "Client not found"}), 404
    try:
        listings, new = run_client_search(client, send_email=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"total": len(listings), "new": len(new), "listings": listings, "client": client})


@app.route("/clients/<cid>/email", methods=["POST"])
def email_client(cid):
    all_clients = load_clients()
    client = next((c for c in all_clients if c["id"] == cid), None)
    if not client:
        return jsonify({"error": "Client not found"}), 404
    try:
        listings, _ = run_client_search(client, send_email=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if not listings:
        return jsonify({"error": "No listings to send"}), 400
    notify = load_notify()
    client_notify = dict(notify)
    client_notify["email"] = client["email"]
    client_name = f"{client['first_name']} {client['last_name']}"
    threading.Thread(target=send_notification, args=(listings, client_notify, client_name), daemon=True).start()
    all_clients2 = load_clients()
    for c in all_clients2:
        if c["id"] == cid:
            c["last_emailed"] = datetime.now().isoformat(timespec="seconds")
            break
    save_clients(all_clients2)
    return jsonify({"ok": True})


# ── Map & Settings ────────────────────────────────────────────────────────────

@app.route("/map")
def map_view():
    return render_template("map.html", config=load_config())

@app.route("/api/listings")
def api_listings():
    csv_file = RESULTS_DIR / load_config()["output"]["csv_filename"]
    listings = []
    if csv_file.exists():
        with open(csv_file, encoding="utf-8") as f:
            listings = list(csv.DictReader(f))

    # Deduplicate by id, keep last occurrence
    seen_ids = {}
    for l in listings:
        if l.get('id'):
            seen_ids[l['id']] = l
    listings = list(seen_ids.values())

    # Convert lat/lng to floats and sanitize all values
    clean_listings = []
    for l in listings:
        clean_l = {}
        for key, val in l.items():
            if val is None or val == "":
                clean_l[key] = ""
            else:
                val_str = str(val).strip()
                if val_str.lower() in ("nan", "none", "<na>"):
                    clean_l[key] = ""
                else:
                    clean_l[key] = val_str

        # Parse lat/lng as floats
        try:
            lat_val = clean_l.get("latitude", "")
            lng_val = clean_l.get("longitude", "")
            if lat_val and lng_val:
                clean_l["lat"] = float(lat_val)
                clean_l["lng"] = float(lng_val)
        except (ValueError, TypeError):
            pass

        clean_listings.append(clean_l)

    return app.response_class(
        response=json.dumps(clean_listings),
        status=200,
        mimetype='application/json'
    )

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        save_notify({
            "enabled":   "enabled" in request.form,
            "email":     request.form.get("email", ""),
            "smtp_host": request.form.get("smtp_host", "smtp.gmail.com"),
            "smtp_port": int(request.form.get("smtp_port", 587)),
            "smtp_user": request.form.get("smtp_user", ""),
            "smtp_pass": request.form.get("smtp_pass", ""),
        })
        flash("Settings saved!", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", notify=load_notify())


def scheduled_searches():
    """Runs every hour — checks each client's frequency and searches if due."""
    clients = load_clients()
    now = datetime.now()
    for client in clients:
        freq = client.get("email_frequency", "every_new_listing")
        if freq == "never":
            continue
        last = client.get("last_emailed")

        if last:
            last_dt = datetime.fromisoformat(last)
            if freq == "once_daily"  and (now - last_dt) < timedelta(hours=24):
                continue
            if freq == "once_weekly" and (now - last_dt) < timedelta(days=7):
                continue
        # every_new_listing always runs; others run if interval has passed
        try:
            run_client_search(client)
        except Exception as e:
            print(f"Scheduled search error for {client.get('first_name')}: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(
    scheduled_searches, "interval", hours=1, id="auto_search",
    next_run_time=datetime.now() + timedelta(hours=1)  # don't run on startup
)
scheduler.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
