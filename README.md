# Property Search

A self-hosted MLS listing search tool with a web dashboard. Automatically discovers new real estate listings from Redfin, Zillow, and Realtor.com, filters them by your criteria, and tracks them over time. Supports multiple clients, scheduled searches, email notifications, and an interactive map view.

## Features

- Fetches listings from Redfin, Zillow, and Realtor.com via [HomeHarvest](https://github.com/ZacharyHampton/HomeHarvest)
- Filters by price, beds, baths, square footage, property type, location radius, age, days on market, and HOA fees
- Tracks seen listings to surface only new results on each run
- Maintains a persistent CSV log of all discoveries
- Manages multiple clients, each with their own saved search filters
- Sends email alerts for new matches on a per-client schedule
- Visualizes listings on an interactive map
- Runs automated background searches on a configurable interval

## Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11 + Flask |
| Scheduling | APScheduler (background jobs) |
| MLS data | HomeHarvest (Redfin / Zillow / Realtor.com) |
| Mapping | Nominatim geocoding + OpenStreetMap |
| Deployment | Docker + Docker Compose |

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/jemplayer82/Property-Search.git
cd Property-Search
docker compose up -d
```

The dashboard is available at **http://\<your-host\>:5050**.

### Without Docker

```bash
git clone https://github.com/jemplayer82/Property-Search.git
cd Property-Search
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Configuration

### Search Filters — `config.json`

```json
{
  "location": "Dripping Springs, TX",
  "site": "realtor.com",
  "filters": {
    "min_price": 500000,
    "max_price": 700000,
    "min_beds": 4,
    "min_baths": 2,
    "property_types": ["house"],
    "distance": 10.0,
    "max_hoa_per_month": null,
    "min_sqft": null,
    "max_sqft": null,
    "max_days_on_market": null,
    "status": ["for sale"],
    "max_age": null,
    "min_age": null
  }
}
```

#### Filter Reference

| Parameter | Type | Description |
|-----------|------|-------------|
| `min_price` / `max_price` | int | Price range in dollars |
| `min_beds` | int | Minimum bedrooms |
| `min_baths` | int | Minimum bathrooms |
| `min_sqft` / `max_sqft` | int | Square footage range |
| `max_age` / `min_age` | int | Home age in years |
| `distance` | float | Search radius in miles from the location |
| `property_types` | array | `house`, `condo`, `townhouse`, `multi-family`, `land`, `mobile` |
| `status` | array | `for sale`, `sold`, `pending` |
| `max_hoa_per_month` | int | Maximum monthly HOA fee (optional) |
| `max_days_on_market` | int | Maximum days listed (optional) |

### Email Notifications — `notifications.json`

```json
{
  "enabled": true,
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 587,
  "smtp_user": "your-email@gmail.com",
  "smtp_pass": "your-app-password",
  "email": "recipient@example.com"
}
```

For Gmail, use an [app-specific password](https://support.google.com/accounts/answer/185833).

## Usage

### Web Dashboard

Open `http://<your-host>:5050` in your browser.

| Page | Purpose |
|------|---------|
| Dashboard | Recent searches and new listings |
| Clients | Add and manage client cards with individual filters |
| Settings | Configure search filters and email notifications |
| Map | Visualize listings on an interactive map |

### Command Line

Run a one-off search:

```bash
python search.py
```

The script loads `config.json`, fetches listings, identifies new ones, appends them to `results/listings.csv`, and prints the results.

### Scheduled Searches

The web app runs searches automatically in the background via APScheduler. Configure the schedule from the Settings page or via the REST API.

## Output Files

| File | Description |
|------|-------------|
| `results/listings.csv` | All discovered listings (tab-separated) |
| `results/seen_listings.json` | Listing IDs already found — prevents duplicates |
| `app.log` | Application and task execution logs |

## Useful Commands

```bash
# View logs
docker compose logs -f

# Restart the service
./restart.sh

# Stop
docker compose down
```
