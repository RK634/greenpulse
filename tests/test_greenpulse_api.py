"""Basic AI-style automated tests for the GreenPulse Flask website.
Run from project root: python tests/test_greenpulse_api.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as greenpulse  # noqa: E402

TEST_DB = ROOT / "greenpulse_ai_test.db"
greenpulse.DB = TEST_DB


def reset_database():
    if TEST_DB.exists():
        TEST_DB.unlink()
    greenpulse.init_db()


def assert_status(response, expected, label):
    assert response.status_code == expected, f"{label}: expected {expected}, got {response.status_code}; body={response.get_data(as_text=True)[:300]}"


def main():
    reset_database()
    client = greenpulse.app.test_client()

    checks = []

    r = client.get("/")
    assert_status(r, 200, "Homepage loads")
    checks.append("Homepage loads")

    for route in ["/api/map", "/api/vehicles", "/api/events", "/api/queue", "/api/dashboard"]:
        r = client.get(route)
        assert_status(r, 200, f"{route} works")
        assert r.is_json, f"{route} did not return JSON"
        checks.append(f"{route} works")

    r = client.post("/api/emergency", json={"emergency_type": "medical", "severity": "critical", "lat": 51.4480, "lng": 7.0320, "spot_name": "AI test emergency"})
    assert_status(r, 200, "Create medical emergency")
    data = r.get_json()
    assert "emergency_id" in data, f"Emergency response missing emergency_id: {data}"
    assert data["route"], "Emergency route is empty"
    assert data["severity"] == "critical"
    assert data["priority_score"] >= data["priority"]
    checks.append("Create medical emergency")

    r = client.post("/api/complete", json={"emergency_id": data["emergency_id"]})
    assert_status(r, 200, "Complete emergency")
    checks.append("Complete emergency")

    # Queue behavior: only 2 ambulances exist, so third medical case should queue.
    client.post("/api/reset", json={})
    client.post("/api/emergency", json={"emergency_type": "medical", "lat": 51.4480, "lng": 7.0320})
    client.post("/api/emergency", json={"emergency_type": "medical", "lat": 51.4490, "lng": 7.0320})
    r = client.post("/api/emergency", json={"emergency_type": "medical", "lat": 51.4500, "lng": 7.0320})
    assert_status(r, 200, "Third ambulance request queues")
    assert r.get_json().get("queued") is True, f"Third ambulance request should queue: {r.get_json()}"
    checks.append("Queue logic works")

    # Negative tests should return 400, not 500.
    bad_cases = [
        ({"emergency_type": "invalid", "lat": 51.45, "lng": 7.01}, "Invalid emergency type"),
        ({"emergency_type": "medical", "lat": "bad", "lng": 7.01}, "Bad latitude"),
        ({"emergency_type": "medical"}, "Missing coordinates"),
        ({"emergency_type": "medical", "lat": 999, "lng": 999}, "Out-of-range coordinates"),
        ({"emergency_type": "medical", "severity": "extreme", "lat": 51.45, "lng": 7.01}, "Invalid severity"),
    ]
    for payload, label in bad_cases:
        r = client.post("/api/emergency", json=payload)
        assert_status(r, 400, label)
    checks.append("Invalid input validation works")

    r = client.post("/api/complete", json={"emergency_id": 999999})
    assert_status(r, 404, "Completing missing emergency returns 404")
    checks.append("404 handling works")

    # Fleet rule: only 2 ambulances, 1 police car, and 1 fire truck.
    client.post('/api/reset')
    vehicles = client.get('/api/vehicles').get_json()
    assert len(vehicles) == 4, f"Expected exactly 4 emergency vehicles, got {len(vehicles)}"
    assert sum(1 for v in vehicles if v['vehicle_type'] == 'ambulance') == 2
    assert sum(1 for v in vehicles if v['vehicle_type'] == 'police') == 1
    assert sum(1 for v in vehicles if v['vehicle_type'] == 'fire_truck') == 1
    checks.append("Fleet count rule works")

    # Dashboard and operator controls are available.
    r = client.get('/api/dashboard')
    assert_status(r, 200, "Dashboard endpoint works")
    dashboard = r.get_json()
    assert 'metrics' in dashboard and 'iot' in dashboard and 'junctions' in dashboard
    checks.append("Dashboard analytics endpoint works")

    r = client.get('/api/report')
    assert_status(r, 200, "Report endpoint works")
    assert 'GreenPulse Emergency Traffic Control Report' in r.get_data(as_text=True)
    assert '<table>' in r.get_data(as_text=True)
    checks.append("Readable HTML report endpoint works")

    r = client.post('/api/vehicle/status', json={'vehicle_id':'AMB-101','status':'maintenance'})
    assert_status(r, 200, "Vehicle maintenance status works")
    r = client.post('/api/vehicle/status', json={'vehicle_id':'AMB-101','status':'available'})
    assert_status(r, 200, "Vehicle available status works")
    checks.append("Vehicle status management works")

    # Frontend priority rules are present in the browser script.
    script = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')
    assert 'Same junction + same direction = shared green corridor' in script
    assert 'Different direction = conflict, so priority decides who passes first' in script
    assert 'already green, emergency passes' in script
    assert 'EMERGENCY_SEGMENT_MS' in script
    assert 'trackIotHealthChanges' in script
    assert 'clearJunctionTraffic' in script
    assert 'normalTrafficVehicles' in script
    assert 'normal vehicles wait so the corridor stays clear' in script
    assert 'Busy city traffic' in script
    html = (ROOT / 'templates' / 'index.html').read_text(encoding='utf-8')
    hidden_labels = ['AI Recommendation Panel', 'Conflict Detection', 'Simulation Controls', 'Priority & Severity Rules', 'Hospital Capacity', 'Database Logs', 'GreenPulse Satellite Final', 'Live Junction Status Table', 'IoT Device Health']
    for label in hidden_labels:
        assert label not in html, f"Hidden dashboard label is still visible: {label}"
    assert 'Emergency Activity Timeline' in html
    checks.append("Internal priority, signal-clearance, and normal-traffic logic remain while unnecessary panels stay hidden")

    print("✅ All GreenPulse automated tests passed:")
    for c in checks:
        print(" -", c)


if __name__ == "__main__":
    main()
