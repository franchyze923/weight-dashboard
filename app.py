from flask import Flask, render_template
import requests
import datetime
import json
import time
import os
import shutil
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

TOKEN_DIR = "/app/tokens"
TOKEN_FILE = os.path.join(TOKEN_DIR, "tokens.json")
SECRET_TOKEN_PATH = "/app/readonly-tokens/tokens.json"

# ✅ Create token dir if needed
os.makedirs(TOKEN_DIR, exist_ok=True)

# ✅ Copy secret only if tokens.json doesn't already exist
if not os.path.exists(TOKEN_FILE):
    shutil.copy(SECRET_TOKEN_PATH, TOKEN_FILE)

app = Flask(__name__)

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]

def load_tokens():
    app.logger.info("📥 Loading tokens from file...")
    if not os.path.exists(TOKEN_FILE):
        raise Exception(f"Token file '{TOKEN_FILE}' not found")
    with open(TOKEN_FILE) as f:
        tokens = json.load(f)
    expires = datetime.datetime.fromtimestamp(tokens["expires_at"], tz=ET)
    app.logger.info(f"✅ Access token loaded: {tokens['access_token'][:10]}... (expires at {expires})")
    return tokens

def save_tokens(tokens):
    app.logger.info("💾 Saving new tokens to file...")
    app.logger.info(f"🔐 New access token: {tokens['access_token'][:10]}... (valid for {int(tokens['expires_at'] - time.time())} seconds)")
    app.logger.info(f"🔁 New refresh token: {tokens['refresh_token'][:10]}...")
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)

def refresh_if_needed():
    app.logger.info("🔁 Called refresh_if_needed()")
    tokens = load_tokens()
    now = time.time()

    if now < tokens["expires_at"]:
        app.logger.info("✅ Access token is still valid. No refresh needed.")
        return tokens["access_token"]

    app.logger.warning("⚠️  Access token expired — refreshing...")

    r = requests.post("https://wbsapi.withings.net/v2/oauth2", data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"]
    })

    response = r.json()
    if response.get("status") != 0:
        app.logger.error("❌ Token refresh failed. API response:")
        app.logger.error(response)
        raise Exception("Token refresh failed")

    body = response["body"]
    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    expires_at = now + body["expires_in"]

    new_tokens = {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_at": expires_at
    }

    save_tokens(new_tokens)
    return new_access

def get_weight_data():
    access_token = refresh_if_needed()

    r = requests.get("https://wbsapi.withings.net/measure", params={
        "action": "getmeas",
        "meastype": 1,
        "category": 1,
        "access_token": access_token
    })

    response = r.json()
    if response.get("status") != 0 or "measuregrps" not in response.get("body", {}):
        app.logger.error("❌ Failed to retrieve weight data. API response:")
        app.logger.error(response)
        return []

    data = response["body"]["measuregrps"]
    weights = []
    for g in data:
        for m in g["measures"]:
            if m["type"] == 1:  # weight
                timestamp = datetime.datetime.fromtimestamp(g["date"], tz=ET)
                weight = m["value"] * (10 ** m["unit"]) * 2.20462  # kg to lbs
                weights.append({"date": timestamp.date(), "datetime": timestamp, "weight": weight})
    return sorted(weights, key=lambda x: x["datetime"], reverse=True)

@app.route("/")
def index():
    weights = get_weight_data()
    today = datetime.datetime.now(tz=ET).date()
    today_weight = next((w for w in weights if w["date"] == today), None)
    latest_weight = weights[0] if weights else None
    weight_change = None
    if len(weights) >= 2 and latest_weight:
        prev_weight = weights[1]["weight"]
        weight_change = round(latest_weight["weight"] - prev_weight, 2)

    recent_weights = weights[:50]
    return render_template(
        "index.html",
        today_weight=today_weight,
        latest_weight=latest_weight,
        recent_weights=recent_weights,
        weight_change=weight_change
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")