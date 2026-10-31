"""Face check-in: Flask backend.

The browser (face-api.js) detects the face, checks for a blink (liveness) and
turns the face into a 128-number embedding. Only that embedding is sent here;
no photos are stored. This server matches embeddings and records attendance.
"""
import hmac
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from functools import wraps

import numpy as np
from flask import Flask, g, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)  # where attendance.db lives (must be persistent when hosted)
DB_PATH = os.path.join(DATA_DIR, "attendance.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")      # change this!
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # change this!
MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.55"))  # lower = stricter

# Hosting servers often run on UTC. Use the office's time zone so check-in times
# and the "once per day" cut-off (midnight) are correct. Change with TIMEZONE env var.
try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Kolkata"))
except Exception:  # tz database missing (e.g. Windows without tzdata)
    TZ = timezone(timedelta(hours=5, minutes=30))

app = Flask(__name__, static_folder="static", static_url_path="")


# ---------- database ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            embeddings TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            day TEXT NOT NULL,
            check_in_time TEXT NOT NULL,
            distance REAL,
            UNIQUE(employee_id, day)
        );
        """
    )
    db.commit()
    db.close()


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_ok = hmac.compare_digest(request.headers.get("X-Admin-User", "").encode(), ADMIN_USERNAME.encode())
        pw_ok = hmac.compare_digest(request.headers.get("X-Admin-Password", "").encode(), ADMIN_PASSWORD.encode())
        if not (user_ok and pw_ok):
            return jsonify(error="Wrong admin ID or password"), 401
        return fn(*args, **kwargs)

    return wrapper


def valid_descriptor(d):
    return (
        isinstance(d, list)
        and len(d) == 128
        and all(isinstance(x, (int, float)) for x in d)
    )


# ---------- pages ----------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------- API ----------
@app.post("/api/enroll")
def enroll():
    data = request.get_json(silent=True) or {}
    emp_code = str(data.get("emp_code", "")).strip()
    name = str(data.get("name", "")).strip()
    add_samples = bool(data.get("add_samples"))
    descriptors = data.get("descriptors", [])
    registration_mode = data.get("registration_mode", "face")
    if not emp_code or (not name and not add_samples):
        return jsonify(error="Employee ID and name are required"), 400
    if registration_mode == "no-face":
        descriptors = []
    elif len(descriptors) < 3 or not all(valid_descriptor(d) for d in descriptors):
        return jsonify(error="Need at least 3 valid face samples"), 400

    db = get_db()
    if add_samples:
        # e.g. enrolled without glasses earlier, now adding samples with glasses
        row = db.execute(
            "SELECT id, name, embeddings FROM employees WHERE emp_code=?", (emp_code,)
        ).fetchone()
        if not row:
            return jsonify(error=f"No employee with ID '{emp_code}' to add samples to"), 404
        combined = (json.loads(row["embeddings"]) + descriptors)[-30:]
        db.execute("UPDATE employees SET embeddings=? WHERE id=?", (json.dumps(combined), row["id"]))
        db.commit()
        return jsonify(ok=True, message=f"Added {len(descriptors)} more samples for {row['name']}")

    try:
        db.execute(
            "INSERT INTO employees (emp_code, name, embeddings, created_at) VALUES (?,?,?,?)",
            (emp_code, name, json.dumps(descriptors), datetime.now(TZ).isoformat(timespec="seconds")),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error=f"Employee ID '{emp_code}' is already enrolled. Tick 'Add more samples' to add to it."), 409
    return jsonify(ok=True, message=(f"{name} registered without face" if registration_mode == "no-face" else f"{name} enrolled"))


@app.post("/api/checkin")
def checkin():
    data = request.get_json(silent=True) or {}
    probe = data.get("descriptor")
    if not valid_descriptor(probe):
        return jsonify(status="error", message="Invalid face data"), 400
    probe = np.array(probe, dtype=np.float32)

    db = get_db()
    rows = db.execute("SELECT id, emp_code, name, embeddings FROM employees").fetchall()
    best, best_dist = None, 9.9
    for r in rows:
        stored = json.loads(r["embeddings"])
        if not stored:  # employee registered without face cannot be matched by face
            continue
        enrolled = np.array(stored, dtype=np.float32)
        dist = float(np.min(np.linalg.norm(enrolled - probe, axis=1)))
        if dist < best_dist:
            best, best_dist = r, dist

    if best is None or best_dist > MATCH_THRESHOLD:
        return jsonify(status="no_match", message="Face not recognised. Please try again or contact admin."), 404

    now = datetime.now(TZ)
    day, t = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    existing = db.execute(
        "SELECT check_in_time FROM attendance WHERE employee_id=? AND day=?", (best["id"], day)
    ).fetchone()
    if existing:
        return jsonify(
            status="already",
            name=best["name"],
            emp_code=best["emp_code"],
            time=existing["check_in_time"],
            message=f"{best['name']} already checked in today at {existing['check_in_time']}",
        )

    db.execute(
        "INSERT INTO attendance (employee_id, day, check_in_time, distance) VALUES (?,?,?,?)",
        (best["id"], day, t, round(best_dist, 4)),
    )
    db.commit()
    return jsonify(
        status="ok",
        name=best["name"],
        emp_code=best["emp_code"],
        time=t,
        message=f"Welcome, {best['name']}! Checked in at {t}",
    )


@app.get("/api/attendance")
@admin_required
def attendance():
    day = request.args.get("day") or datetime.now(TZ).strftime("%Y-%m-%d")
    rows = get_db().execute(
        """SELECT e.emp_code, e.name, a.day, a.check_in_time
           FROM attendance a JOIN employees e ON e.id = a.employee_id
           WHERE a.day = ? ORDER BY a.check_in_time""",
        (day,),
    ).fetchall()
    return jsonify(day=day, records=[dict(r) for r in rows])


@app.get("/api/employees")
@admin_required
def employees():
    rows = get_db().execute(
        "SELECT emp_code, name, created_at FROM employees ORDER BY name"
    ).fetchall()
    return jsonify(employees=[dict(r) for r in rows])


@app.delete("/api/employees/<emp_code>")
@admin_required
def delete_employee(emp_code):
    db = get_db()
    row = db.execute("SELECT id FROM employees WHERE emp_code=?", (emp_code,)).fetchone()
    if not row:
        return jsonify(error="Not found"), 404
    db.execute("DELETE FROM attendance WHERE employee_id=?", (row["id"],))
    db.execute("DELETE FROM employees WHERE id=?", (row["id"],))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/export.csv")
@admin_required
def export_csv():
    day = request.args.get("day") or datetime.now(TZ).strftime("%Y-%m-%d")
    rows = get_db().execute(
        """SELECT e.emp_code, e.name, a.day, a.check_in_time
           FROM attendance a JOIN employees e ON e.id = a.employee_id
           WHERE a.day = ? ORDER BY a.check_in_time""",
        (day,),
    ).fetchall()
    lines = ["emp_code,name,date,check_in_time"] + [
        f'{r["emp_code"]},"{r["name"]}",{r["day"]},{r["check_in_time"]}' for r in rows
    ]
    return ("\n".join(lines), 200, {"Content-Type": "text/csv"})


init_db()  # also runs when a hosting service imports this file

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    if "--https" in sys.argv:
        # Phones only allow camera access over HTTPS (localhost is exempt).
        app.run(host="0.0.0.0", port=port, ssl_context="adhoc")
    else:
        app.run(host="0.0.0.0", port=port)
