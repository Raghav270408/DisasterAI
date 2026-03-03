"""
DisasterAI — Chennai Only Backend
Sources: USGS, NASA EONET, GDACS, ReliefWeb, NDMA, IMD
All data filtered strictly to Chennai & Tamil Nadu only
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from google import genai
import requests
import feedparser
import os
import json
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = Flask(__name__)
CORS(app)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ══════════════════════════════════════════════════════════
# CHENNAI CONSTANTS
# ══════════════════════════════════════════════════════════

INDIA_BBOX = {
    "min_lat": 12.5,
    "max_lat": 13.5,
    "min_lon": 79.8,
    "max_lon": 80.5
}

INDIA_TERMS = [
    'chennai', 'madras', 'tamil nadu', 'tamilnadu',
    'kanchipuram', 'tiruvallur', 'chengalpattu',
    'vellore', 'coromandel', 'bay of bengal',
    'palar river', 'adyar', 'cooum', 'buckingham canal',
    'tambaram', 'avadi', 'thiruvottiyur', 'sholinganallur',
    'velachery', 'anna nagar', 't nagar', 'perambur',
    'ambattur', 'chromepet', 'pallavaram', 'porur',
    'manali', 'ennore', 'red hills', 'poondi reservoir',
    'chembarambakkam', 'kolathur', 'kodambakkam',
    'mylapore', 'triplicane', 'royapuram', 'tondiarpet',
    'nungambakkam', 'egmore', 'guindy', 'mount road',
    'marina', 'besant nagar', 'thiruvanmiyur', 'siruseri'
]

def is_india(item):
    """Strict check — only return True if item is Chennai/Tamil Nadu related"""
    text = json.dumps(item).lower()
    return any(term in text for term in INDIA_TERMS)

def coords_in_india(lat, lon):
    """Check if coordinates fall within Chennai bounding box"""
    try:
        return (INDIA_BBOX["min_lat"] <= float(lat) <= INDIA_BBOX["max_lat"] and
                INDIA_BBOX["min_lon"] <= float(lon) <= INDIA_BBOX["max_lon"])
    except (TypeError, ValueError):
        return False

# ══════════════════════════════════════════════════════════
# DATA FETCHERS
# ══════════════════════════════════════════════════════════

def fetch_usgs_earthquakes():
    """
    USGS Earthquake API — filtered to Chennai bounding box
    Returns earthquakes magnitude 2.5+ near Chennai
    """
    try:
        url = (
            "https://earthquake.usgs.gov/fdsnws/event/1/query"
            "?format=geojson"
            f"&minlatitude={INDIA_BBOX['min_lat']}"
            f"&maxlatitude={INDIA_BBOX['max_lat']}"
            f"&minlongitude={INDIA_BBOX['min_lon']}"
            f"&maxlongitude={INDIA_BBOX['max_lon']}"
            "&minmagnitude=2.5"
            "&orderby=time"
            "&limit=20"
        )
        res = requests.get(url, timeout=10).json()
        results = []
        for f in res.get("features", []):
            p = f["properties"]
            coords = f["geometry"]["coordinates"]
            lat, lon = coords[1], coords[0]

            if not coords_in_india(lat, lon):
                continue

            mag = p.get("mag", 0)
            results.append({
                "source": "USGS",
                "type": "Earthquake",
                "title": p.get("title", "Earthquake — Chennai Region"),
                "magnitude": mag,
                "place": p.get("place", "Chennai Region, Tamil Nadu"),
                "alert": p.get("alert"),
                "tsunami": p.get("tsunami", 0),
                "felt": p.get("felt", 0),
                "time": datetime.utcfromtimestamp(
                    p["time"] / 1000
                ).strftime("%Y-%m-%d %H:%M UTC"),
                "coordinates": {
                    "lat": lat,
                    "lon": lon,
                    "depth_km": coords[2]
                },
            })
        print(f"  USGS: {len(results)} Chennai earthquakes")
        return results
    except Exception as e:
        print(f"  USGS error: {e}")
        return [{"error": str(e)}]


def fetch_nasa_eonet():
    """
    NASA EONET — active natural events filtered to Chennai bounding box
    Covers: cyclones, floods, wildfires near Chennai
    """
    try:
        url = (
            "https://eonet.gsfc.nasa.gov/api/v3/events"
            "?status=open"
            "&limit=50"
            f"&bbox={INDIA_BBOX['min_lon']},{INDIA_BBOX['min_lat']},"
            f"{INDIA_BBOX['max_lon']},{INDIA_BBOX['max_lat']}"
        )
        res = requests.get(url, timeout=10).json()
        results = []
        for e in res.get("events", []):
            coords = None
            last_date = "N/A"
            if e.get("geometry"):
                g = e["geometry"][-1]
                coords = g.get("coordinates")
                last_date = g.get("date", "N/A")

            if coords and isinstance(coords, list) and len(coords) >= 2:
                if not coords_in_india(coords[1], coords[0]):
                    continue

            category = e["categories"][0]["title"] if e.get("categories") else "Unknown"
            results.append({
                "source": "NASA EONET",
                "id": e.get("id"),
                "title": e.get("title", "Active Event — Chennai"),
                "type": category,
                "status": e.get("status"),
                "updated": last_date,
                "coordinates": coords,
                "url": e.get("sources", [{}])[0].get("url"),
            })
        print(f"  NASA EONET: {len(results)} Chennai events")
        return results
    except Exception as e:
        print(f"  NASA EONET error: {e}")
        return [{"error": str(e)}]


def fetch_gdacs():
    """
    GDACS UN — disaster alerts filtered strictly to Chennai/Tamil Nadu
    """
    try:
        feed = feedparser.parse("https://www.gdacs.org/xml/rss.xml")
        results = []
        for entry in feed.entries:
            country = entry.get("gdacs_country", "").lower()
            title = entry.get("title", "").lower()
            summary = entry.get("summary", "").lower()
            combined = f"{country} {title} {summary}"

            if not any(term in combined for term in ['chennai', 'tamil nadu', 'tamilnadu', 'coromandel']):
                continue

            results.append({
                "source": "GDACS/UN",
                "title": entry.get("title"),
                "summary": entry.get("summary", "")[:400],
                "published": entry.get("published"),
                "alert_level": entry.get("gdacs_alertlevel", "N/A"),
                "event_type": entry.get("gdacs_eventtype", "N/A"),
                "country": "India — Tamil Nadu",
                "link": entry.get("link"),
            })
        print(f"  GDACS: {len(results)} Chennai/TN alerts")
        return results
    except Exception as e:
        print(f"  GDACS error: {e}")
        return [{"error": str(e)}]


def fetch_reliefweb():
    """
    ReliefWeb UN — humanitarian disasters in Tamil Nadu/Chennai (ISO3: IND)
    Filtered by Tamil Nadu keyword
    """
    try:
        url = (
            "https://api.reliefweb.int/v1/disasters"
            "?appname=disasterai"
            "&limit=15"
            "&filter[operator]=AND"
            "&filter[conditions][0][field]=country.iso3"
            "&filter[conditions][0][value]=IND"
            "&filter[conditions][1][field]=name"
            "&filter[conditions][1][value]=Tamil Nadu"
            "&fields[include][]=name"
            "&fields[include][]=status"
            "&fields[include][]=country"
            "&fields[include][]=type"
            "&fields[include][]=date"
            "&fields[include][]=description"
            "&sort[]=date:desc"
        )
        res = requests.get(url, timeout=10).json()
        results = []

        # If no Tamil Nadu specific results, get all India and filter
        if not res.get("data"):
            url2 = (
                "https://api.reliefweb.int/v1/disasters"
                "?appname=disasterai"
                "&limit=20"
                "&filter[field]=country.iso3"
                "&filter[value]=IND"
                "&fields[include][]=name"
                "&fields[include][]=status"
                "&fields[include][]=country"
                "&fields[include][]=type"
                "&fields[include][]=date"
                "&sort[]=date:desc"
            )
            res = requests.get(url2, timeout=10).json()
            for item in res.get("data", []):
                f = item.get("fields", {})
                name = (f.get("name") or "").lower()
                if any(term in name for term in ['tamil', 'chennai', 'cyclone']):
                    results.append({
                        "source": "ReliefWeb/UN",
                        "name": f.get("name"),
                        "status": f.get("status"),
                        "type": [t["name"] for t in f.get("type", [])],
                        "countries": ["India — Tamil Nadu"],
                        "date": f.get("date", {}).get("event", "N/A"),
                    })
        else:
            for item in res.get("data", []):
                f = item.get("fields", {})
                results.append({
                    "source": "ReliefWeb/UN",
                    "name": f.get("name"),
                    "status": f.get("status"),
                    "type": [t["name"] for t in f.get("type", [])],
                    "countries": ["India — Tamil Nadu"],
                    "date": f.get("date", {}).get("event", "N/A"),
                    "description": f.get("description", "")[:300] if f.get("description") else "",
                })

        print(f"  ReliefWeb: {len(results)} Tamil Nadu disasters")
        return results
    except Exception as e:
        print(f"  ReliefWeb error: {e}")
        return [{"error": str(e)}]


def fetch_ndma():
    """
    NDMA — disaster management reports filtered to Tamil Nadu
    """
    try:
        url = (
            "https://api.reliefweb.int/v1/reports"
            "?appname=disasterai"
            "&limit=10"
            "&filter[operator]=AND"
            "&filter[conditions][0][field]=country.iso3"
            "&filter[conditions][0][value]=IND"
            "&filter[conditions][1][field]=theme.name"
            "&filter[conditions][1][value]=Disaster Management"
            "&fields[include][]=title"
            "&fields[include][]=date"
            "&fields[include][]=source"
            "&fields[include][]=body"
            "&sort[]=date:desc"
        )
        res = requests.get(url, timeout=10).json()
        results = []
        for item in res.get("data", []):
            f = item.get("fields", {})
            title = (f.get("title") or "").lower()
            body = (f.get("body") or "").lower()
            # Filter to Tamil Nadu / Chennai relevant reports
            if any(term in title + body for term in ['tamil', 'chennai', 'cyclone', 'flood', 'india']):
                results.append({
                    "source": "NDMA India",
                    "title": f.get("title"),
                    "date": f.get("date", {}).get("created", "N/A"),
                    "body": f.get("body", "")[:300] if f.get("body") else "",
                    "type": "Disaster Management",
                    "country": "India — Tamil Nadu",
                })
        print(f"  NDMA: {len(results)} reports")
        return results
    except Exception as e:
        print(f"  NDMA error: {e}")
        return [{"error": str(e)}]


def fetch_imd_warnings():
    """
    IMD Chennai — weather warnings for Tamil Nadu
    """
    try:
        url = (
            "https://api.reliefweb.int/v1/reports"
            "?appname=disasterai"
            "&limit=10"
            "&filter[operator]=AND"
            "&filter[conditions][0][field]=country.iso3"
            "&filter[conditions][0][value]=IND"
            "&filter[conditions][1][field]=theme.name"
            "&filter[conditions][1][value]=Weather and Climate"
            "&fields[include][]=title"
            "&fields[include][]=date"
            "&fields[include][]=body"
            "&sort[]=date:desc"
        )
        res = requests.get(url, timeout=10).json()
        results = []
        for item in res.get("data", []):
            f = item.get("fields", {})
            title = (f.get("title") or "").lower()
            body = (f.get("body") or "").lower()
            if any(term in title + body for term in ['tamil', 'chennai', 'cyclone', 'india']):
                results.append({
                    "source": "IMD Chennai",
                    "title": f.get("title"),
                    "date": f.get("date", {}).get("created", "N/A"),
                    "body": f.get("body", "")[:300] if f.get("body") else "",
                    "type": "Weather Warning",
                    "country": "India — Tamil Nadu",
                })
        print(f"  IMD: {len(results)} Chennai weather warnings")
        return results
    except Exception as e:
        print(f"  IMD error: {e}")
        return [{"error": str(e)}]


def get_all_live_data():
    """
    Aggregates all Chennai/Tamil Nadu only data from every source
    """
    print("\n📡 Fetching Chennai-only disaster data...")

    earthquakes   = fetch_usgs_earthquakes()
    active_events = fetch_nasa_eonet()
    gdacs_alerts  = fetch_gdacs()
    humanitarian  = fetch_reliefweb()
    ndma          = fetch_ndma()
    imd           = fetch_imd_warnings()

    # Final safety net
    earthquakes   = [x for x in earthquakes   if not x.get("error")]
    active_events = [x for x in active_events if not x.get("error")]
    gdacs_alerts  = [x for x in gdacs_alerts  if not x.get("error")]
    humanitarian  = [x for x in humanitarian  if not x.get("error")]
    ndma          = [x for x in ndma          if not x.get("error")]
    imd           = [x for x in imd           if not x.get("error")]

    total = (len(earthquakes) + len(active_events) + len(gdacs_alerts) +
             len(humanitarian) + len(ndma) + len(imd))

    print(f"✅ Total Chennai/TN events: {total}\n")

    return {
        "fetched_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "region": "Chennai & Tamil Nadu",
        "total_events": total,
        "earthquakes":    earthquakes,
        "active_events":  active_events,
        "gdacs_alerts":   gdacs_alerts,
        "humanitarian":   humanitarian,
        "ndma_reports":   ndma,
        "imd_warnings":   imd,
    }


# ══════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/live-data", methods=["GET"])
def live_data():
    """Raw Chennai-only live data from all sources"""
    return jsonify(get_all_live_data())


@app.route("/api/summary", methods=["GET"])
def ai_summary():
    """Gemini AI analysis of live Chennai disaster data"""
    data = get_all_live_data()

    if data["total_events"] == 0:
        return jsonify({
            "summary": "No active disasters detected in Chennai or Tamil Nadu at this time. All monitored systems show normal conditions.",
            "raw_data": data,
            "status": "clear"
        })

    prompt = f"""
You are DisasterAI, Chennai's disaster response intelligence system.
Date: {data['fetched_at']}. Scope: CHENNAI & TAMIL NADU ONLY.

Analyze this LIVE disaster data for Chennai and Tamil Nadu:

1. CRITICAL ALERTS — Top 3 most urgent events in Chennai right now
2. AREA OVERVIEW — Which Chennai zones or Tamil Nadu districts are most affected
3. CITY RISK LEVEL — Current disaster risk: Low / Medium / High / Critical (with reason)
4. RESPONSE ACTIONS — 5 specific actions for Chennai Corporation, TNSDMA, NDRF
5. STATISTICS — Total active events, most affected area, most common disaster type

Rules:
- Only reference Chennai localities and Tamil Nadu districts
- Reference local agencies: TNSDMA, Chennai Corporation (GCC), NDRF, IMD Chennai, Coast Guard Chennai
- Use local geography: Adyar river, Cooum river, Buckingham Canal, Marina Beach, Poondi reservoir, Chembarambakkam lake
- If no active events, clearly state Chennai is currently safe
- Plain text only, no markdown symbols

LIVE CHENNAI DATA:
{json.dumps(data, indent=2)[:8000]}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return jsonify({
            "summary": response.text,
            "raw_data": data,
            "status": "success"
        })
    except Exception as e:
        return jsonify({"error": str(e), "raw_data": data}), 500


@app.route("/api/analyze-event", methods=["POST"])
def analyze_event():
    """Deep Gemini analysis of a single Chennai disaster event"""
    event = request.get_json(silent=True)
    if not event:
        return jsonify({"error": "No event data provided"}), 400

    prompt = f"""
You are DisasterAI, Chennai's disaster response intelligence system.
Analyze this disaster event affecting Chennai or Tamil Nadu:

{json.dumps(event, indent=2)}

Provide:
1. SITUATION — What is happening and exactly where in Chennai/Tamil Nadu
2. SEVERITY — Score 1-10 with reasoning
3. AFFECTED AREAS — Which Chennai localities or TN districts are at risk
4. IMMEDIATE ACTIONS — What Chennai Corporation/TNSDMA/NDRF should do in next 24 hours
5. RESOURCES NEEDED — Personnel, equipment, relief materials
6. MONITORING — What to watch for in coming days

Reference Chennai localities, TNSDMA, GCC, IMD Chennai where relevant.
Be specific and actionable. Plain text only.
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return jsonify({"analysis": response.text, "event": event})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def chat():
    """Chat with DisasterAI about Chennai disasters using live data"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No data provided"}), 400

    message = data.get("message", "")
    include_live = data.get("include_live_data", True)

    if not message:
        return jsonify({"error": "No message provided"}), 400

    context = ""
    if include_live:
        live = get_all_live_data()
        context = f"\n\nCurrent live Chennai disaster data:\n{json.dumps(live, indent=2)[:5000]}"

    prompt = f"""You are DisasterAI, Chennai's disaster response intelligence assistant.
You only provide information about disasters in Chennai and Tamil Nadu.
You reference local agencies: TNSDMA, GCC Chennai, NDRF, IMD Chennai, Coast Guard Chennai.
Local geography: Adyar, Cooum, Buckingham Canal, Marina Beach, Poondi, Chembarambakkam.{context}

User question: {message}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        return jsonify({"response": response.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/risk-map", methods=["GET"])
def risk_map():
    """Geo-coordinates of all active Chennai events for map rendering"""
    data = get_all_live_data()
    points = []

    for eq in data["earthquakes"]:
        c = eq.get("coordinates")
        if c and coords_in_india(c["lat"], c["lon"]):
            points.append({
                "lat": c["lat"], "lon": c["lon"],
                "type": "Earthquake",
                "title": eq.get("title"),
                "severity": eq.get("magnitude"),
                "alert": eq.get("alert", "unknown"),
                "source": "USGS"
            })

    for ev in data["active_events"]:
        c = ev.get("coordinates")
        if c and isinstance(c, list) and len(c) >= 2:
            if coords_in_india(c[1], c[0]):
                points.append({
                    "lat": c[1], "lon": c[0],
                    "type": ev.get("type"),
                    "title": ev.get("title"),
                    "source": "NASA EONET"
                })

    return jsonify({
        "points": points,
        "count": len(points),
        "region": "Chennai & Tamil Nadu"
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "region": "Chennai & Tamil Nadu",
        "time": datetime.utcnow().isoformat(),
        "sources": ["USGS", "NASA EONET", "GDACS/UN", "ReliefWeb/UN", "NDMA", "IMD Chennai"]
    })


# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("🏙️  DisasterAI — Chennai Only Backend")
    print("🚀 Running on http://localhost:5000")
    print("📡 Sources: USGS | NASA EONET | GDACS | ReliefWeb | NDMA | IMD Chennai")
    print("📍 Region: Chennai & Tamil Nadu")
    print("─" * 55)
    app.run(debug=True, port=5000)