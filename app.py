from flask import Flask, render_template
import requests
import datetime
import json
import time
import os

app = Flask(__name__)

CLIENT_ID = "YOUR_CLIENT_ID"
CLIENT_SECRET = "YOUR_CLIENT_SECRET"
TOKEN_FILE = "tokens.json"

def load_tokens():
    print("📥 Loading tokens from file...")
    if not os.path.exists(TOKEN_FILE):
        raise Exception(f"Token file '{TOKEN_FILE}' not found")
    with open(TOKEN_FILE) as f:
        tokens = json.load(f)
    print(f"✅ Access token loaded: {tokens['access_token'][:10]}... (expires at {datetime.datetime.fromtimestamp(tokens['expires_at'])})")
    return tokens

def save_tokens(tokens):
    print(f"💾 Saving new tokens to file...")
    print(f"🔐 New access token: {tokens['access_token'][:10]}... (valid for {int(tokens['expires_at'] - time.time())} seconds)")
    print(f"🔁 New refresh token: {tokens['refresh_token'][:10]}...")
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)

def refresh_if_needed():
    tokens = load_tokens()
    now = time.time()
    if now < tokens["expires_at"]:
        print("✅ Access token is still valid. No refresh needed.")
        return tokens["access_token"]

    print("⚠️  Access token expired — refreshing...")

    r = requests.post("https://wbsapi.withings.net/v2/oauth2", data={
        "action": "refresh_token",
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": tokens["refresh_token"]
    })

    response = r.json()
    if response["status"] != 0:
        print("❌ Token refresh failed. API response:")
        print(response)
        raise Exception("Token refresh failed")

    body = response["body"]
    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    expires_at = now + body["expires_in"]

    tokens = {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_at": expires_at
    }
    save_tokens(tokens)
    return new_access


def get_weight_data():
    access_token = refresh_if_needed()

    r = requests.get("https://wbsapi.withings.net/measure", params={
        "action": "getmeas",
        "meastype": 1,
        "category": 1,
        "access_token": access_token
    })

    data = r.json()["body"]["measuregrps"]
    weights = []
    for g in data:
        for m in g["measures"]:
            if m["type"] == 1:  # weight
                timestamp = datetime.datetime.fromtimestamp(g["date"])
                weight = m["value"] * (10 ** m["unit"]) * 2.20462  # convert to lbs
                weights.append({"date": timestamp.date(), "datetime": timestamp, "weight": weight})
    return sorted(weights, key=lambda x: x["datetime"], reverse=True)


@app.route("/")
def index():
    weights = get_weight_data()
    today = datetime.date.today()
    today_weight = next((w for w in weights if w["date"] == today), None)
    latest_weight = weights[0] if weights else None
    recent_weights = weights[:50]
    return render_template(
        "index.html",
        today_weight=today_weight,
        latest_weight=latest_weight,
        recent_weights=recent_weights
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
