
from flask import Flask, render_template, request, jsonify, Response
import sqlite3, heapq, math
from datetime import datetime
from html import escape
from pathlib import Path

app = Flask(__name__)
DB = Path("greenpulse.db")

# Fixed road-network nodes placed on a real city area.
# Route generation is constrained to these road nodes.
NODES = {
    "amb_north": {"name":"North Ambulance Base","lat":51.4696,"lng":7.0048,"type":"station","vehicle_type":"ambulance"},
    "amb_south": {"name":"South Ambulance Base","lat":51.4395,"lng":7.0118,"type":"station","vehicle_type":"ambulance"},
    "fire_west": {"name":"West Fire Station","lat":51.4545,"lng":6.9850,"type":"station","vehicle_type":"fire_truck"},
    "police_east": {"name":"East Police Station","lat":51.4594,"lng":7.0372,"type":"station","vehicle_type":"police"},
    "hospital": {"name":"Central Hospital","lat":51.4358,"lng":7.0069,"type":"hospital"},

    "j1":{"name":"J1 North West","lat":51.4665,"lng":6.9970,"type":"junction","traffic":"low"},
    "j2":{"name":"J2 North Center","lat":51.4662,"lng":7.0105,"type":"junction","traffic":"medium"},
    "j3":{"name":"J3 North East","lat":51.4654,"lng":7.0240,"type":"junction","traffic":"medium"},
    "j4":{"name":"J4 East Gate","lat":51.4640,"lng":7.0360,"type":"junction","traffic":"heavy"},

    "j5":{"name":"J5 West Market","lat":51.4568,"lng":6.9965,"type":"junction","traffic":"medium"},
    "j6":{"name":"J6 Central Cross","lat":51.4566,"lng":7.0106,"type":"junction","traffic":"heavy"},
    "j7":{"name":"J7 Business Cross","lat":51.4564,"lng":7.0241,"type":"junction","traffic":"heavy"},
    "j8":{"name":"J8 Hospital Road","lat":51.4560,"lng":7.0363,"type":"junction","traffic":"medium"},

    "j9":{"name":"J9 West Park","lat":51.4480,"lng":6.9967,"type":"junction","traffic":"low"},
    "j10":{"name":"J10 City Center","lat":51.4478,"lng":7.0107,"type":"junction","traffic":"heavy"},
    "j11":{"name":"J11 Mall Road","lat":51.4476,"lng":7.0241,"type":"junction","traffic":"medium"},
    "j12":{"name":"J12 East Ring","lat":51.4472,"lng":7.0361,"type":"junction","traffic":"heavy"},

    "j13":{"name":"J13 South West","lat":51.4398,"lng":6.9970,"type":"junction","traffic":"medium"},
    "j14":{"name":"J14 South Center","lat":51.4396,"lng":7.0108,"type":"junction","traffic":"low"},
    "j15":{"name":"J15 Industrial Road","lat":51.4395,"lng":7.0240,"type":"junction","traffic":"medium"},
    "j16":{"name":"J16 Fire Corridor","lat":51.4392,"lng":7.0360,"type":"junction","traffic":"heavy"},
}

GRAPH = {
    "amb_north":{"j1":0.8,"j2":0.9},
    "amb_south":{"j13":0.8,"j14":0.9},
    "fire_west":{"j5":0.9,"j9":1.0},
    "police_east":{"j4":0.9,"j8":1.0},
    "hospital":{"j14":0.8,"j10":1.0},

    "j1":{"amb_north":0.8,"j2":1.0,"j5":1.0},
    "j2":{"amb_north":0.9,"j1":1.0,"j3":1.0,"j6":1.0},
    "j3":{"j2":1.0,"j4":1.0,"j7":1.0},
    "j4":{"j3":1.0,"j8":1.0,"police_east":0.9},

    "j5":{"fire_west":0.9,"j1":1.0,"j6":1.0,"j9":1.0},
    "j6":{"j2":1.0,"j5":1.0,"j7":1.0,"j10":1.0},
    "j7":{"j3":1.0,"j6":1.0,"j8":1.0,"j11":1.0},
    "j8":{"j4":1.0,"j7":1.0,"j12":1.0,"police_east":1.0},

    "j9":{"fire_west":1.0,"j5":1.0,"j10":1.0,"j13":1.0},
    "j10":{"j6":1.0,"j9":1.0,"j11":1.0,"j14":1.0,"hospital":1.0},
    "j11":{"j7":1.0,"j10":1.0,"j12":1.0,"j15":1.0},
    "j12":{"j8":1.0,"j11":1.0,"j16":1.0},

    "j13":{"j9":1.0,"j14":1.0,"amb_south":0.8},
    "j14":{"j10":1.0,"j13":1.0,"j15":1.0,"amb_south":0.9,"hospital":0.8},
    "j15":{"j11":1.0,"j14":1.0,"j16":1.0},
    "j16":{"j12":1.0,"j15":1.0}
}

VEHICLES = [
    {"id":"AMB-101","name":"Ambulance 101","vehicle_type":"ambulance","node_id":"amb_north","status":"available"},
    {"id":"AMB-202","name":"Ambulance 202","vehicle_type":"ambulance","node_id":"amb_south","status":"available"},
    {"id":"FIRE-11","name":"Fire Truck 11","vehicle_type":"fire_truck","node_id":"fire_west","status":"available"},
    {"id":"POL-7","name":"Police Car 7","vehicle_type":"police","node_id":"police_east","status":"available"},
]

NEED = {"medical":"ambulance","accident":"ambulance","fire":"fire_truck","police":"police","rescue":"ambulance"}
PRIORITY = {"fire":5,"rescue":4,"medical":4,"accident":3,"police":2}
SEVERITY_SCORE = {"low":10,"medium":20,"high":30,"critical":45}
SEVERITY_LABEL = {"low":"Low","medium":"Medium","high":"High","critical":"Critical"}
HOSPITALS = {
    "Central Hospital": {"beds": 5, "icu": 2, "status": "Available", "node_id": "hospital"}
}
PRE_CLEAR = {"low":3,"medium":6,"heavy":10}
TRAFFIC_FACTOR = {"low":1.0,"medium":1.22,"heavy":1.55}

def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = get_db()
    cur = c.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS vehicles(id TEXT PRIMARY KEY,name TEXT,vehicle_type TEXT,node_id TEXT,status TEXT)")
    cur.execute("""CREATE TABLE IF NOT EXISTS emergencies(
        id INTEGER PRIMARY KEY AUTOINCREMENT, emergency_type TEXT, severity TEXT DEFAULT 'high', priority INTEGER, priority_score INTEGER DEFAULT 0,
        spot_name TEXT, spot_lat REAL, spot_lng REAL, snap_node TEXT,
        vehicle_id TEXT, route TEXT, eta_seconds INTEGER, status TEXT, created_at TEXT, completed_at TEXT
    )""")
    cur.execute("CREATE TABLE IF NOT EXISTS event_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, emergency_id INTEGER, event_type TEXT, message TEXT, created_at TEXT)")
    cur.execute("""CREATE TABLE IF NOT EXISTS emergency_queue(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emergency_type TEXT,
        severity TEXT DEFAULT 'high',
        priority INTEGER,
        priority_score INTEGER DEFAULT 0,
        spot_name TEXT,
        spot_lat REAL,
        spot_lng REAL,
        status TEXT,
        created_at TEXT
    )""")
    for table, cols in {
        "emergencies": [
            ("severity", "TEXT DEFAULT 'high'"),
            ("priority_score", "INTEGER DEFAULT 0"),
            ("completed_at", "TEXT")
        ],
        "emergency_queue": [
            ("severity", "TEXT DEFAULT 'high'"),
            ("priority_score", "INTEGER DEFAULT 0")
        ]
    }.items():
        existing = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        for name, typ in cols:
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    if cur.execute("SELECT COUNT(*) c FROM vehicles").fetchone()["c"] == 0:
        for v in VEHICLES:
            cur.execute("INSERT INTO vehicles VALUES(?,?,?,?,?)", (v["id"],v["name"],v["vehicle_type"],v["node_id"],v["status"]))
    c.commit()
    c.close()

def log(eid, typ, msg):
    c = get_db()
    c.execute("INSERT INTO event_logs(emergency_id,event_type,message,created_at) VALUES(?,?,?,?)",
              (eid, typ, msg, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    c.commit()
    c.close()

def haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))

def nearest_junction(lat, lng):
    ids = [k for k,v in NODES.items() if v["type"] == "junction"]
    return min(ids, key=lambda k: haversine(lat,lng,NODES[k]["lat"],NODES[k]["lng"]))

def build_graph_with_spot(lat, lng):
    g = {k: dict(v) for k,v in GRAPH.items()}
    snap = nearest_junction(lat, lng)
    dist = max(0.25, haversine(lat, lng, NODES[snap]["lat"], NODES[snap]["lng"]))
    g["custom_spot"] = {snap: round(dist,2)}
    g.setdefault(snap, {})["custom_spot"] = round(dist,2)
    return g, snap

def shortest_path(g, start, goal):
    q = [(0, start, [])]
    seen = set()
    while q:
        d,n,p = heapq.heappop(q)
        if n in seen: continue
        seen.add(n)
        p = p + [n]
        if n == goal: return p,d
        for nb,w in g.get(n,{}).items():
            if nb not in seen:
                heapq.heappush(q,(d+w,nb,p))
    return [], math.inf

def eta_seconds(route, dist):
    factor = 1.0
    for nid in route:
        n = NODES.get(nid)
        if n and n.get("type") == "junction":
            factor += (TRAFFIC_FACTOR[n.get("traffic","medium")] - 1) * 0.12
    return max(30, int(dist * 28 * factor))

def priority_score(etype, severity="high"):
    return PRIORITY.get(etype, 1) * 10 + SEVERITY_SCORE.get(severity, SEVERITY_SCORE["high"])

def fmt_seconds(sec):
    sec = int(sec or 0)
    return f"{sec//60}m {sec%60}s" if sec >= 60 else f"{sec}s"

def payload(route, spot_lat, spot_lng, spot_name):
    out = []
    for nid in route:
        if nid == "custom_spot":
            out.append({"id":"custom_spot","name":spot_name,"lat":spot_lat,"lng":spot_lng,"type":"spot","traffic":"none","pre_clear_seconds":0})
        else:
            n = NODES[nid]
            out.append({"id":nid,"name":n["name"],"lat":n["lat"],"lng":n["lng"],"type":n["type"],"traffic":n.get("traffic","none"),
                        "pre_clear_seconds": PRE_CLEAR.get(n.get("traffic","medium"),0) if n["type"]=="junction" else 0})
    return out

def hospital_return_payload(snap_node, spot_lat, spot_lng, spot_name):
    # Ambulance return path: emergency spot -> nearest road junction -> hospital.
    g = {k: dict(v) for k, v in GRAPH.items()}
    g["custom_spot"] = {snap_node: 0.25}
    g.setdefault(snap_node, {})["custom_spot"] = 0.25

    route, _ = shortest_path(g, "custom_spot", "hospital")
    if not route:
        return []

    return payload(route, spot_lat, spot_lng, spot_name)


def find_vehicle(etype, lat, lng):
    required = NEED[etype]
    g, snap = build_graph_with_spot(lat, lng)
    c = get_db()
    rows = c.execute("SELECT * FROM vehicles WHERE vehicle_type=? AND status='available'", (required,)).fetchall()
    c.close()
    candidates = []
    for v in rows:
        r,d = shortest_path(g, v["node_id"], "custom_spot")
        if r:
            e = eta_seconds(r,d)
            candidates.append({"id":v["id"],"name":v["name"],"vehicle_type":v["vehicle_type"],"route":r,"distance":round(d,2),"eta_seconds":e,"eta_minutes":round(e/60,1),"snap":snap})
    return sorted(candidates, key=lambda x:x["eta_seconds"])[0] if candidates else None


def add_to_queue(etype, lat, lng, spot_name, severity="high"):
    priority = PRIORITY[etype]
    pscore = priority_score(etype, severity)
    c = get_db()
    cur = c.cursor()
    cur.execute("""INSERT INTO emergency_queue(
        emergency_type, severity, priority, priority_score, spot_name, spot_lat, spot_lng, status, created_at
    ) VALUES(?,?,?,?,?,?,?,?,?)""", (
        etype, severity, priority, pscore, spot_name, lat, lng, "waiting",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    qid = cur.lastrowid
    c.commit()
    c.close()
    log(None, "queue", f"No free {NEED[etype].replace('_', ' ')} available. Emergency added to queue #{qid}: {etype.title()} ({SEVERITY_LABEL.get(severity, severity)}) at {spot_name}.")
    return qid

def get_waiting_queue():
    c = get_db()
    rows = c.execute("""SELECT * FROM emergency_queue
                        WHERE status='waiting'
                        ORDER BY priority_score DESC, priority DESC, id ASC""").fetchall()
    c.close()
    return rows

def try_dispatch_queue_item(row):
    best = find_vehicle(row["emergency_type"], row["spot_lat"], row["spot_lng"])
    if not best:
        return None

    etype = row["emergency_type"]
    lat = row["spot_lat"]
    lng = row["spot_lng"]
    spot_name = row["spot_name"]
    priority = row["priority"]
    severity = row["severity"] if "severity" in row.keys() else "high"
    pscore = row["priority_score"] if "priority_score" in row.keys() and row["priority_score"] else priority_score(etype, severity)

    route_nodes = payload(best["route"], lat, lng, spot_name)

    c = get_db()
    cur = c.cursor()
    cur.execute("""INSERT INTO emergencies(
        emergency_type, severity, priority, priority_score, spot_name, spot_lat, spot_lng, snap_node,
        vehicle_id, route, eta_seconds, status, created_at
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        etype, severity, priority, pscore, spot_name, lat, lng, best["snap"],
        best["id"], ",".join(best["route"]), best["eta_seconds"],
        "active", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    eid = cur.lastrowid
    cur.execute("UPDATE vehicles SET status='busy' WHERE id=?", (best["id"],))
    cur.execute("UPDATE emergency_queue SET status='dispatched' WHERE id=?", (row["id"],))
    c.commit()
    c.close()

    log(eid, "queue_dispatch", f"Queued emergency #{row['id']} is now dispatched. {best['name']} assigned.")
    log(eid, "route", "Road-only route generated from queue: " + " → ".join([n["name"] for n in route_nodes]))

    return {
        "queued_from": row["id"],
        "emergency_id": eid,
        "priority": priority,
        "priority_score": pscore,
        "severity": severity,
        "emergency_type": etype,
        "vehicle": {
            "id": best["id"],
            "name": best["name"],
            "vehicle_type": best["vehicle_type"],
            "eta_seconds": best["eta_seconds"],
            "eta_minutes": best["eta_minutes"]
        },
        "spot": {
            "name": spot_name,
            "lat": lat,
            "lng": lng
        },
        "route": route_nodes,
        "hospital_return_route": hospital_return_payload(best["snap"], lat, lng, spot_name) if best["vehicle_type"] == "ambulance" else []
    }

def dispatch_available_queue_items():
    dispatched = []
    for row in get_waiting_queue():
        result = try_dispatch_queue_item(row)
        if result:
            dispatched.append(result)
    return dispatched

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/map")
def map_api():
    return jsonify({"nodes":NODES, "graph":GRAPH, "priority":PRIORITY, "severity":SEVERITY_SCORE, "hospitals":HOSPITALS})

@app.route("/api/vehicles")
def vehicles_api():
    c = get_db()
    rows = c.execute("SELECT * FROM vehicles ORDER BY id").fetchall()
    c.close()
    out = []
    for r in rows:
        n = NODES[r["node_id"]]
        item = dict(r)
        item["lat"] = n["lat"]; item["lng"] = n["lng"]; item["location_name"] = n["name"]
        out.append(item)
    return jsonify(out)

@app.route("/api/events")
def events_api():
    c = get_db()
    rows = c.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT 220").fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/emergency", methods=["POST"])
def emergency_api():
    data = request.get_json(silent=True) or {}
    etype = data.get("emergency_type")

    if etype not in NEED:
        return jsonify({"error":"Invalid emergency type"}), 400

    try:
        lat = float(data.get("lat"))
        lng = float(data.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error":"Latitude and longitude must be valid numbers"}), 400

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error":"Latitude or longitude is outside valid range"}), 400

    severity = (data.get("severity") or "high").lower()
    if severity not in SEVERITY_SCORE:
        return jsonify({"error":"Invalid severity level"}), 400

    spot_name = data.get("spot_name") or f"Selected Emergency ({lat:.4f}, {lng:.4f})"
    best = find_vehicle(etype, lat, lng)
    if not best:
        qid = add_to_queue(etype, lat, lng, spot_name, severity)
        return jsonify({
            "queued": True,
            "queue_id": qid,
            "message": f"No free suitable vehicle available. Emergency added to queue #{qid}."
        })
    route_nodes = payload(best["route"], lat, lng, spot_name)
    priority = PRIORITY[etype]
    pscore = priority_score(etype, severity)
    c = get_db()
    cur = c.cursor()
    cur.execute("""INSERT INTO emergencies(emergency_type,severity,priority,priority_score,spot_name,spot_lat,spot_lng,snap_node,vehicle_id,route,eta_seconds,status,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (etype,severity,priority,pscore,spot_name,lat,lng,best["snap"],best["id"],",".join(best["route"]),best["eta_seconds"],"active",datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    eid = cur.lastrowid
    cur.execute("UPDATE vehicles SET status='busy' WHERE id=?", (best["id"],))
    c.commit()
    c.close()
    log(eid,"request",f"{etype.title()} emergency ({SEVERITY_LABEL[severity]}) created from user-selected map point. Snapped to nearest road junction: {NODES[best['snap']]['name']}.")
    log(eid,"dispatch",f"{best['name']} selected as nearest free suitable vehicle by road-network ETA.")
    log(eid,"route","Road-only route generated: " + " → ".join([n["name"] for n in route_nodes]))
    return jsonify({"emergency_id":eid,"priority":priority,"priority_score":pscore,"severity":severity,"emergency_type":etype,
                    "vehicle":{"id":best["id"],"name":best["name"],"vehicle_type":best["vehicle_type"],"eta_seconds":best["eta_seconds"],"eta_minutes":best["eta_minutes"]},
                    "spot":{"name":spot_name,"lat":lat,"lng":lng},
                    "route":route_nodes,
                    "hospital_return_route": hospital_return_payload(best["snap"], lat, lng, spot_name) if best["vehicle_type"] == "ambulance" else []})

@app.route("/api/signal-log", methods=["POST"])
def signal_api():
    d = request.get_json(force=True)
    eid = d.get("emergency_id")
    j = d.get("junction_name","Junction")
    action = d.get("action")
    traffic = d.get("traffic","medium")
    sec = int(d.get("seconds",0))
    msgs = {
        "pre_clear": f"{j}: standard four-way signal override starts. {traffic} traffic gets {sec}s road-clear timing.",
        "green": f"{j}: emergency direction green; all cross directions red. Normal traffic waits.",
        "shared": f"{j}: same-route emergency shares green corridor.",
        "priority_wait": f"{j}: lower-priority emergency waits briefly for higher-priority route.",
        "passed": f"{j}: emergency vehicle passed without stopping.",
        "reset": f"{j}: signal returned to standard normal city cycle."
    }
    log(eid, "signal", msgs.get(action, f"{j}: {action}"))
    return jsonify({"message":"ok"})

@app.route("/api/complete", methods=["POST"])
def complete_api():
    eid = request.get_json(force=True).get("emergency_id")
    c = get_db()
    e = c.execute("SELECT * FROM emergencies WHERE id=?", (eid,)).fetchone()
    if not e:
        c.close()
        return jsonify({"error":"not found"}), 404
    c.execute("UPDATE emergencies SET status='completed', completed_at=? WHERE id=?", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), eid))
    vehicle = c.execute("SELECT * FROM vehicles WHERE id=?", (e["vehicle_id"],)).fetchone()
    final_node = "hospital" if vehicle and vehicle["vehicle_type"] == "ambulance" else e["snap_node"]
    c.execute("UPDATE vehicles SET status='available', node_id=? WHERE id=?", (final_node, e["vehicle_id"]))
    c.commit()
    c.close()
    log(eid,"complete","Emergency handling completed. If ambulance was assigned, patient transfer to hospital was completed before closing the case.")
    dispatched = dispatch_available_queue_items()
    return jsonify({"message":"complete", "dispatched_from_queue": dispatched})


@app.route("/api/queue")
def queue_api():
    rows = get_waiting_queue()
    return jsonify([dict(r) for r in rows])

@app.route("/api/queue/dispatch", methods=["POST"])
def queue_dispatch_api():
    dispatched = dispatch_available_queue_items()
    return jsonify({"dispatched": dispatched})


@app.route("/api/dashboard")
def dashboard_api():
    c = get_db()
    vehicles = [dict(r) for r in c.execute("SELECT * FROM vehicles ORDER BY id").fetchall()]
    active = [dict(r) for r in c.execute("SELECT * FROM emergencies WHERE status='active' ORDER BY priority_score DESC, id DESC").fetchall()]
    completed = [dict(r) for r in c.execute("SELECT * FROM emergencies WHERE status='completed' ORDER BY id DESC LIMIT 50").fetchall()]
    waiting = [dict(r) for r in c.execute("SELECT * FROM emergency_queue WHERE status='waiting' ORDER BY priority_score DESC, id ASC").fetchall()]
    counts = c.execute("SELECT emergency_type, COUNT(*) c FROM emergencies GROUP BY emergency_type").fetchall()
    logs = [dict(r) for r in c.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT 12").fetchall()]
    c.close()

    response_times = []
    for e in completed:
        try:
            if e.get("created_at") and e.get("completed_at"):
                st = datetime.strptime(e["created_at"], "%Y-%m-%d %H:%M:%S")
                en = datetime.strptime(e["completed_at"], "%Y-%m-%d %H:%M:%S")
                response_times.append(max(0, int((en-st).total_seconds())))
        except Exception:
            pass
    avg_response = int(sum(response_times)/len(response_times)) if response_times else 0
    total = len(active) + len(completed)
    busy = len([v for v in vehicles if v["status"] == "busy"])
    available = len([v for v in vehicles if v["status"] == "available"])
    by_type = {r["emergency_type"]: r["c"] for r in counts}

    junctions = []
    for jid, n in NODES.items():
        if n["type"] == "junction":
            junctions.append({
                "id": jid,
                "name": n["name"],
                "traffic": n.get("traffic", "medium"),
                "mode": "Normal Cycle",
                "override": "No",
                "active_vehicle": "None"
            })

    recommendation = "System is in normal monitoring mode. Waiting for a new emergency request."
    if active:
        top = active[0]
        recommendation = f"Continue green corridor for {top['vehicle_id']} because {top['emergency_type'].title()} has priority score {top.get('priority_score') or top.get('priority')}."
    elif waiting:
        top = waiting[0]
        recommendation = f"Queue priority: dispatch next available {NEED[top['emergency_type']].replace('_',' ')} for {top['emergency_type'].title()} ({top.get('severity','high')})."

    return jsonify({
        "metrics": {
            "total_emergencies": total,
            "active": len(active),
            "completed": len(completed),
            "waiting": len(waiting),
            "available_vehicles": available,
            "busy_vehicles": busy,
            "avg_response_seconds": avg_response,
            "avg_response_text": fmt_seconds(avg_response),
            "estimated_time_saved": fmt_seconds(max(0, avg_response // 2)) if avg_response else "Demo mode"
        },
        "active": active,
        "waiting": waiting,
        "vehicles": vehicles,
        "by_type": by_type,
        "junctions": junctions,
        "priority_rules": PRIORITY,
        "severity_rules": SEVERITY_SCORE,
        "hospitals": HOSPITALS,
        "recommendation": recommendation,
        "iot": [
            {"device":"ESP32-J1", "status":"Online", "last_update":"2 sec ago"},
            {"device":"RFID Reader", "status":"Active", "last_update":"3 sec ago"},
            {"device":"IR Sensor Pair", "status":"Active", "last_update":"1 sec ago"},
            {"device":"Signal Controller", "status":"Online", "last_update":"2 sec ago"}
        ],
        "timeline": logs
    })

@app.route("/api/report")
def report_api():
    c = get_db()
    emergencies = [dict(r) for r in c.execute("SELECT * FROM emergencies ORDER BY id DESC LIMIT 30").fetchall()]
    logs = [dict(r) for r in c.execute("SELECT * FROM event_logs ORDER BY id DESC LIMIT 120").fetchall()]
    vehicles = [dict(r) for r in c.execute("SELECT * FROM vehicles ORDER BY vehicle_type, id").fetchall()]
    c.close()

    completed = [e for e in emergencies if e.get("status") == "completed"]
    active = [e for e in emergencies if e.get("status") == "active"]
    avg_eta = int(sum((e.get("eta_seconds") or 0) for e in emergencies) / len(emergencies)) if emergencies else 0

    def safe(value):
        return escape(str(value if value is not None else "-"))

    emergency_rows = ""
    if emergencies:
        for e in emergencies:
            status = safe(e.get("status"))
            emergency_rows += (
                "<tr>"
                f"<td>#{safe(e.get('id'))}</td>"
                f"<td><strong>{safe(e.get('emergency_type', '')).title()}</strong></td>"
                f"<td>{safe(e.get('vehicle_id'))}</td>"
                f"<td><span class='pill {status}'>{status.title()}</span></td>"
                f"<td>{safe(e.get('eta_seconds'))} sec</td>"
                f"<td>{safe(e.get('created_at'))}</td>"
                f"<td>{safe(e.get('completed_at') or '-')}</td>"
                "</tr>"
            )
    else:
        emergency_rows = "<tr><td colspan='7' class='empty'>No emergency records yet. Run a demo scenario first.</td></tr>"

    timeline_rows = ""
    if logs:
        for l in logs:
            timeline_rows += (
                "<div class='timeline-item'>"
                f"<div class='timeline-time'>{safe(l.get('created_at'))}</div>"
                f"<div class='timeline-body'><strong>Emergency #{safe(l.get('emergency_id') or '-')} · {safe(l.get('event_type')).title()}</strong>"
                f"<p>{safe(l.get('message'))}</p></div>"
                "</div>"
            )
    else:
        timeline_rows = "<div class='empty'>No timeline logs yet.</div>"

    vehicle_rows = ""
    for v in vehicles:
        vstatus = safe(v.get("status"))
        vehicle_rows += (
            "<tr>"
            f"<td>{safe(v.get('name'))}</td>"
            f"<td>{safe(v.get('vehicle_type')).replace('_', ' ').title()}</td>"
            f"<td><span class='pill {vstatus}'>{vstatus.title()}</span></td>"
            f"<td>{safe(v.get('node_id'))}</td>"
            "</tr>"
        )


    generated = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    avg_eta_text = fmt_seconds(avg_eta) if avg_eta else "-"
    html = f"""<!DOCTYPE html>
<html lang='en'>
<head>
<meta charset='UTF-8' />
<meta name='viewport' content='width=device-width, initial-scale=1' />
<title>GreenPulse Emergency Report</title>
<style>
  :root {{ --bg:#07111f; --card:#101c2d; --muted:#89a2b7; --green:#20f49a; --blue:#54b7ff; --yellow:#ffd45a; --red:#ff4d64; }}
  body {{ margin:0; font-family: Arial, sans-serif; background:linear-gradient(135deg,#07111f,#0b1d2e); color:#edf7ff; }}
  .wrap {{ max-width:1180px; margin:auto; padding:28px; }}
  .hero {{ border:1px solid rgba(255,255,255,.12); background:linear-gradient(135deg,rgba(32,244,154,.13),rgba(84,183,255,.10)); border-radius:24px; padding:24px; margin-bottom:18px; }}
  h1 {{ margin:0 0 8px; font-size:30px; }} h2 {{ margin:0 0 14px; font-size:18px; }} p {{ color:#cfe2f0; line-height:1.5; }}
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:18px 0; }}
  .two {{ grid-template-columns:1fr 1fr; }} .card {{ background:rgba(16,28,45,.88); border:1px solid rgba(255,255,255,.10); border-radius:18px; padding:16px; }}
  .metric span {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; font-weight:700; }} .metric strong {{ display:block; margin-top:7px; font-size:24px; color:#fff; }}
  table {{ width:100%; border-collapse:collapse; }} th {{ text-align:left; color:#9eb7cb; text-transform:uppercase; font-size:11px; letter-spacing:.04em; border-bottom:1px solid rgba(255,255,255,.12); padding:10px; }}
  td {{ padding:12px 10px; border-bottom:1px solid rgba(255,255,255,.08); color:#e9f5ff; vertical-align:top; }} td span {{ color:#9eb7cb; font-size:12px; }}
  .pill {{ display:inline-block; padding:5px 9px; border-radius:999px; font-size:11px; font-weight:800; background:rgba(84,183,255,.16); color:#bfe4ff; }}
  .pill.completed,.pill.available {{ background:rgba(32,244,154,.14); color:#adffd9; }} .pill.active,.pill.busy {{ background:rgba(255,212,90,.15); color:#ffe9a0; }} .pill.waiting,.pill.offline {{ background:rgba(255,77,100,.15); color:#ffc0c8; }}
  .timeline {{ display:grid; gap:10px; }} .timeline-item {{ display:grid; grid-template-columns:170px 1fr; gap:14px; background:rgba(2,12,24,.44); border:1px solid rgba(255,255,255,.08); border-left:4px solid var(--blue); border-radius:14px; padding:12px; }}
  .timeline-time {{ color:#9eb7cb; font-size:12px; font-weight:700; }} .timeline-body p {{ margin:5px 0 0; }} .empty {{ color:#9eb7cb; padding:18px; }}
  .actions {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:16px; }} button, a.btn {{ border:0; border-radius:12px; padding:11px 14px; font-weight:800; cursor:pointer; text-decoration:none; color:#03130d; background:linear-gradient(135deg,var(--green),#00c77a); }}
  a.btn.secondary {{ color:#e9f5ff; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); }}
  @media print {{ body {{ background:white; color:#111; }} .wrap {{ max-width:none; padding:12px; }} .card,.hero {{ border:1px solid #ddd; background:white; color:#111; }} p,td,th,.timeline-time {{ color:#333; }} .actions {{ display:none; }} }}
  @media(max-width:900px) {{ .cards,.two {{ grid-template-columns:1fr; }} .timeline-item {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><div class='wrap'>
<section class='hero'><h1>GreenPulse Emergency Traffic Control Report</h1><p>Generated at: <strong>{generated}</strong></p><p>This report summarizes emergency requests, vehicle dispatch, fleet status, and the activity timeline for the green corridor demo.</p><div class='actions'><button onclick='window.print()'>Print / Save as PDF</button><a class='btn secondary' href='/'>Back to Dashboard</a></div></section>
<section class='cards'><div class='card metric'><span>Total Emergencies</span><strong>{len(emergencies)}</strong></div><div class='card metric'><span>Active</span><strong>{len(active)}</strong></div><div class='card metric'><span>Completed</span><strong>{len(completed)}</strong></div><div class='card metric'><span>Average ETA</span><strong>{avg_eta_text}</strong></div></section>
<section class='card'><h2>Emergency Summary</h2><table><thead><tr><th>ID</th><th>Type</th><th>Vehicle</th><th>Status</th><th>ETA</th><th>Created</th><th>Completed</th></tr></thead><tbody>{emergency_rows}</tbody></table></section>
<section class='card'><h2>Fleet Status</h2><table><thead><tr><th>Vehicle</th><th>Type</th><th>Status</th><th>Node</th></tr></thead><tbody>{vehicle_rows}</tbody></table></section>
<section class='card'><h2>Emergency Activity Timeline</h2><div class='timeline'>{timeline_rows}</div></section>
</div></body></html>"""
    return Response(html, mimetype="text/html")

@app.route("/api/hospital/capacity", methods=["POST"])
def hospital_capacity_api():
    data = request.get_json(silent=True) or {}
    name = data.get("hospital", "Central Hospital")
    if name not in HOSPITALS:
        return jsonify({"error": "Hospital not found"}), 404
    try:
        beds = int(data.get("beds", HOSPITALS[name]["beds"]))
        icu = int(data.get("icu", HOSPITALS[name]["icu"]))
    except (TypeError, ValueError):
        return jsonify({"error": "Beds and ICU must be valid numbers"}), 400
    if beds < 0 or icu < 0:
        return jsonify({"error": "Beds and ICU cannot be negative"}), 400
    HOSPITALS[name]["beds"] = beds
    HOSPITALS[name]["icu"] = icu
    HOSPITALS[name]["status"] = "Available" if beds > 0 else "Full"
    log(None, "hospital_capacity", f"{name} capacity updated: beds={beds}, ICU={icu}, status={HOSPITALS[name]['status']}.")
    return jsonify({"message": "updated", "hospital": name, "capacity": HOSPITALS[name]})

@app.route("/api/vehicle/status", methods=["POST"])
def vehicle_status_api():
    data = request.get_json(silent=True) or {}
    vid = data.get("vehicle_id")
    status = data.get("status")
    if status not in {"available", "maintenance", "offline"}:
        return jsonify({"error":"Invalid vehicle status"}), 400
    c = get_db()
    v = c.execute("SELECT * FROM vehicles WHERE id=?", (vid,)).fetchone()
    if not v:
        c.close()
        return jsonify({"error":"Vehicle not found"}), 404
    if v["status"] == "busy":
        c.close()
        return jsonify({"error":"Busy vehicle status cannot be changed during active emergency"}), 409
    c.execute("UPDATE vehicles SET status=? WHERE id=?", (status, vid))
    c.commit()
    c.close()
    log(None, "vehicle_status", f"{vid} marked as {status} by dashboard operator.")
    return jsonify({"message":"updated", "vehicle_id":vid, "status":status})

@app.route("/api/reset", methods=["POST"])
def reset_api():
    c = get_db()
    c.execute("DELETE FROM event_logs")
    c.execute("DELETE FROM emergencies")
    c.execute("DELETE FROM emergency_queue")
    c.execute("DELETE FROM vehicles")
    for v in VEHICLES:
        c.execute("INSERT INTO vehicles VALUES(?,?,?,?,?)",(v["id"],v["name"],v["vehicle_type"],v["node_id"],v["status"]))
    c.commit()
    c.close()
    return jsonify({"message":"reset"})

init_db()

if __name__ == "__main__":
    app.run(debug=True, threaded=True)
