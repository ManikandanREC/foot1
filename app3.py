from flask import Flask, jsonify, render_template, make_response
from flask_cors import CORS
import threading
import random
import time
from datetime import datetime
import json
import os

# thread lock for safe access
lock = threading.Lock()

# --- Configuration ---
TOTAL_PEOPLE = 1000  # fixed total campus population
UPDATE_INTERVAL = 5  # seconds

ZONES = {
    "Block A": [f"Classroom-{i}" for i in range(1, 16)],
    "Block B": [f"Classroom-{i}" for i in range(1, 16)],
    "Block C": [f"Classroom-{i}" for i in range(1, 16)],
    "Block D": [f"Classroom-{i}" for i in range(1, 16)],
    "Canteen": [f"Canteen-{i}" for i in range(1, 6)],
    "Dorm-1": [f"Dorm1-WiFi-{i}" for i in range(1, 11)],
    "Dorm-2": [f"Dorm2-WiFi-{i}" for i in range(1, 16)],
}

app = Flask(__name__)
CORS(app)

# Initialize distribution
base_each = TOTAL_PEOPLE // len(ZONES)
zone_people = {zone: base_each for zone in ZONES}
remainder = TOTAL_PEOPLE - base_each * len(ZONES)
zones_list = list(ZONES.keys())
for i in range(remainder):
    zone_people[zones_list[i % len(zones_list)]] += 1

device_data = {}  # {device_id: {zone, foot_count, timestamp}}

# --- Simulation logic ---
def simulate_data():
    """Background loop: move people around and update device_data."""
    global zone_people, device_data
    zones = list(ZONES.keys())

    while True:
        # choose hot zone uniformly
        hot_zone = random.choice(zones)

        # movement events
        for _ in range(random.randint(20, 50)):
            # read populations under lock for consistency
            with lock:
                populations = [zone_people.get(z, 0) for z in zones]

            if sum(populations) == 0:
                from_zone = random.choice(zones)
            else:
                from_zone = random.choices(zones, weights=populations, k=1)[0]

            # choose to_zone biased toward hot_zone but not equal to from_zone
            weights = []
            for z in zones:
                w = 1
                if z == hot_zone:
                    w += 3
                if z == from_zone:
                    w = 0
                weights.append(w)

            if sum(weights) == 0:
                to_zone = random.choice([z for z in zones if z != from_zone])
            else:
                to_zone = random.choices(zones, weights=weights, k=1)[0]

            # perform move safely
            with lock:
                if zone_people.get(from_zone, 0) > 0:
                    max_possible = min(50, zone_people[from_zone])
                    move = random.randint(1, max_possible)
                    move = min(move, zone_people[from_zone])
                    zone_people[from_zone] -= move
                    zone_people[to_zone] += move

        # update devices
        with lock:
            for zone, devices in ZONES.items():
                num_devices = max(1, len(devices))
                base = zone_people.get(zone, 0) // num_devices
                remainder_local = zone_people.get(zone, 0) - base * num_devices
                for idx, device in enumerate(devices):
                    extra = 1 if idx < remainder_local else 0
                    device_data[device] = {
                        "zone": zone,
                        "foot_count": max(0, base + extra + random.randint(-3, 3)),
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    }

        with lock:
            total_now = sum(zone_people.values())
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Total: {total_now} | Hot Zone: {hot_zone}")

        time.sleep(UPDATE_INTERVAL)


# --- Flask routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_data")
def get_data():
    # produce a single atomic snapshot under lock
    with lock:
        snapshot = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "zones": [{"zone": zone, "total_foot_count": zone_people.get(zone, 0)} for zone in ZONES],
            # optionally include devices if you need them:
            # "devices": device_data.copy()
        }
    response = make_response(json.dumps(snapshot))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    # debugging log — uncomment if you want to inspect timing
    # print(f"GET /get_data -> {snapshot['timestamp']} totals: {[z['total_foot_count'] for z in snapshot['zones']]}")
    return response



# --- Simulator startup helper (start on import unless disabled) ---
_simulator_started = False

def start_simulator_background():
    global _simulator_started
    if _simulator_started:
        return
    _simulator_started = True
    t = threading.Thread(target=simulate_data, daemon=True)
    t.start()

# If environment variable DISABLE_SIM is set to "1", we won't start simulator automatically.
if os.environ.get("DISABLE_SIM", "") != "1":
    # Start simulator on import (works for gunicorn import-based startup)
    start_simulator_background()

# Allow running directly for local dev as well:
if __name__ == "__main__":
    # If user runs `python app3.py` we want to start Flask too.
    # Simulator already started above (unless DISABLE_SIM=1).
    app.run(host="0.0.0.0", port=5000, debug=False)
