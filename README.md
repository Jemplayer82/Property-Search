# 🏠 Property Search

> A powerful MLS property listing search tool with both CLI and web interface. Automatically discovers new real estate listings from major property databases, filters by your criteria, and tracks them over time.

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Features](#-features) • [Installation](#-installation) • [Configuration](#-configuration) • [Usage](#-usage) • [Troubleshooting](#-troubleshooting)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔍 **Multi-source Scraping** | Fetches from Redfin, Zillow, and Realtor.com via [HomeHarvest](https://github.com/ZacharyHampton/HomeHarvest) |
| 🎯 **Advanced Filtering** | Price, beds, baths, sqft, property type, location radius, age, and more |
| 🚫 **Duplicate Detection** | Automatically tracks seen listings to identify only new properties |
| 📊 **CSV Export** | Maintains a persistent CSV log of all discoveries |
| 🖥️ **Web Dashboard** | User-friendly Flask interface with real-time search |
| 📧 **Email Alerts** | Send new listing notifications to multiple recipients |
| ⏰ **Scheduled Searches** | Run automated searches on a configurable schedule |
| 🗺️ **Map View** | Visualize listings on an interactive map |
| 👥 **Multi-Client** | Manage different searches for different clients |
| 📝 **Logging** | Comprehensive logs for debugging and monitoring |

## 📋 Requirements

- **Python** 3.11+
- **Flask** — Web framework
- **APScheduler** — Scheduled background jobs
- **pandas** — Data processing
- **HomeHarvest** — MLS scraping library
- **gunicorn** — Production-grade server

## 🚀 Installation

### Step 1: Clone the Repository
```bash
git clone https://github.com/yourusername/property-search.git
cd property-search
```

### Step 2: Set Up Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install flask apscheduler homeharvest pandas gunicorn
```

## ⚙️ Configuration

### 🔧 config.json — Search Settings

The main configuration file controls all search parameters:

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
    "max_hoa_per_month": null,
    "min_sqft": null,
    "max_sqft": null,
    "max_days_on_market": null,
    "status": ["for sale"],
    "max_age": null,
    "min_age": null,
    "distance": 10.0
  },
  "output": {
    "results_dir": "results",
    "seen_listings_file": "seen_listings.json",
    "csv_filename": "listings.csv",
    "print_new_only": true
  }
}
```

#### Filter Parameters

| Parameter | Type | Description |
|:----------|:----:|:-----------|
| `min_price` / `max_price` | `int` | Price range in dollars |
| `min_beds` | `int` | Minimum number of bedrooms |
| `min_baths` | `int` | Minimum number of bathrooms |
| `property_types` | `array` | `house`, `condo`, `townhouse`, `multi-family`, `land`, `mobile` |
| `status` | `array` | `for sale`, `sold`, `pending` |
| `min_sqft` / `max_sqft` | `int` | Square footage range |
| `max_age` / `min_age` | `int` | Building age in years |
| `distance` | `float` | Search radius in miles |
| `max_hoa_per_month` | `int` | Maximum HOA fees *(optional)* |
| `max_days_on_market` | `int` | Maximum days on market *(optional)* |

---

### 👥 clients.json — Multi-Client Support

Store configurations for multiple clients:

```json
{
  "clients": [
    {
      "name": "Client Name",
      "email": "client@example.com",
      "config": "path/to/config.json"
    }
  ]
}
```

---

### 📧 notifications.json — Email Alerts

Configure email notifications for new listings:

```json
{
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "sender_email": "your-email@gmail.com",
  "sender_password": "your-app-password",
  "recipients": ["recipient@example.com"]
}
```

> 💡 **Tip:** For Gmail, use an [app-specific password](https://support.google.com/accounts/answer/185833)

## 💻 Usage

### 📍 Command Line

Run a single search:

```bash
python search.py
```

**What happens:**
1. ✅ Loads search criteria from `config.json`
2. 🔍 Fetches listings from the specified location
3. 🆕 Identifies new listings (not seen before)
4. 💾 Appends to `results/listings.csv`
5. 📋 Updates `results/seen_listings.json`
6. 🖨️ Prints results to console

---

### 🌐 Web Interface

**Development Server:**
```bash
python app.py
```
Access at: `http://localhost:5000`

**Production Server:**
```bash
gunicorn -w 1 -b 0.0.0.0:5050 app:app
```
Access at: `http://localhost:5050`

#### 🎨 Dashboard Features

| Feature | Purpose |
|---------|---------|
| 📊 **Dashboard** | View recent searches and new listings |
| 🔎 **Search** | Run manual searches with real-time results |
| 👥 **Clients** | Manage multiple client configurations |
| ⚙️ **Settings** | Configure filters and notifications |
| 🗺️ **Map** | Visualize listings on interactive map |
| 📜 **History** | Browse previously found listings |

---

### ⏰ Automated Scheduled Searches

Searches run automatically via APScheduler. Configure intervals:
- Via web dashboard
- Via REST API
- Via `config.json`

## 📂 Output Files

### 📊 `results/listings.csv`
Tab-separated CSV with all discovered listings:

```csv
id,address,city,state,zip,price,beds,baths,sqft,property_type,year_built,days_on_market,list_date,url,photo,latitude,longitude,fetched_at
```

✨ Only new listings are appended each run

### 📋 `results/seen_listings.json`
Tracks all listing IDs to prevent duplicate alerts:

```json
["mls_id_1", "mls_id_2", "mls_id_3"]
```

### 📝 `app.log`
Application logs with Flask and task execution details

## 📁 Project Structure

```
property-search/
├── 🐍 app.py                      Flask web application
├── 🔍 search.py                   Core search logic
├── ⚙️  config.json                Search configuration
├── 👥 clients.json                Client configurations
├── 📧 notifications.json          Email settings
├── 🔄 restart.sh                  Service restart script
├── 📦 requirements.txt            Python dependencies
│
├── templates/
│   ├── 📄 base.html              Base template
│   ├── 📊 index.html             Dashboard
│   ├── 👥 clients.html           Client management
│   ├── 📝 client_form.html       Add/edit client
│   ├── 🗺️  map.html              Map view
│   └── ⚙️  settings.html         Settings page
│
├── static/
│   └── 🎨 style.css              Styling
│
└── results/
    ├── 📊 listings.csv            All discovered listings
    └── 📋 seen_listings.json      Tracking file
```

## 🛠️ Development

### Test the Search
```bash
python -c "from search import fetch_listings; import json; cfg = json.load(open('config.json')); listings = fetch_listings(cfg); print(f'Found {len(listings)} listings')"
```

### View Live Logs
```bash
tail -f app.log
```

### Restart Service
```bash
./restart.sh
```

---

## 🆘 Troubleshooting

### ❌ No Results Found

- [ ] Verify location spelling in `config.json`
- [ ] Check if filters are too restrictive
- [ ] Update HomeHarvest: `pip install --upgrade homeharvest`

### ❌ Email Notifications Not Working

- [ ] Verify SMTP credentials in `notifications.json`
- [ ] Use [app-specific password](https://support.google.com/accounts/answer/185833) for Gmail
- [ ] Check `app.log` for SMTP errors

### ❌ Missing Dependencies

```bash
pip install -r requirements.txt
```

Or manually:
```bash
pip install homeharvest pandas flask apscheduler gunicorn
```

---

## ⚡ Performance Tips

| Tip | Benefit |
|-----|---------|
| Adjust `distance` | Balance coverage vs. result count |
| Use narrow filters | Reduce API calls |
| Schedule off-peak | Avoid rate limiting |
| Set `print_new_only: true` | Reduce log clutter |

---

## 📜 License

MIT License — Feel free to use for personal or commercial projects.

---

## 💬 Support

Need help? Try these steps:

1. 📖 Check the **Troubleshooting** section above
2. 📝 Review `app.log` for error messages
3. ✅ Verify all config files are valid JSON
4. 🌐 Ensure stable internet connection

---

## 🚀 Future Enhancements

- [ ] Support for additional MLS sources
- [ ] Advanced filtering UI improvements
- [ ] Property comparison tools
- [ ] Market analysis and trend tracking
- [ ] Webhook integrations
- [ ] Mobile app

---

<div align="center">

Made with ❤️ for real estate professionals

[⬆ back to top](#-property-search)

</div>
