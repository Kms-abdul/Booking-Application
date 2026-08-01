# =============================================================================
# app.py — Flask Application + Scheduler
# =============================================================================
# Run with:  python app.py
# API is served on http://localhost:4000
# =============================================================================

import os
import logging
from datetime import datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
## pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler

import config
import excel_db
import email_reminder

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
    template_folder="templates",
)
CORS(app)   # Allow requests from any origin (useful during local development)

# ---------------------------------------------------------------------------
# Ensure the Excel DB exists before the first request
# ---------------------------------------------------------------------------
excel_db.ensure_db()

# ---------------------------------------------------------------------------
# Serve the single-page frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("templates", "index.html")

# manifest and service worker must be served from the app root for PWA install
@app.route("/manifest.json")
def manifest():
    response = send_from_directory("static", "manifest.json")
    response.headers["Content-Type"] = "application/manifest+json"
    return response

@app.route("/sw.js")
def service_worker():
    response = send_from_directory("static", "sw.js")
    # Required header so the browser trusts this as a service worker
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

# Icons served at root path so manifest can reference /icon-192.png etc.
@app.route("/icon-192.png")
def icon_192():
    return send_from_directory("static/icons", "icon-192.png")

@app.route("/icon-512.png")
def icon_512():
    return send_from_directory("static/icons", "icon-512.png")


# ---------------------------------------------------------------------------
# API — Rooms
# ---------------------------------------------------------------------------

@app.route("/api/rooms", methods=["GET"])
def api_get_rooms():
    """Return the list of rooms defined in the Rooms sheet."""
    try:
        rooms = excel_db.get_rooms()
        return jsonify({"ok": True, "rooms": rooms})
    except Exception as exc:
        logger.exception("GET /api/rooms failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

# ---------------------------------------------------------------------------
# API — Today's Status
# ---------------------------------------------------------------------------

@app.route("/api/status", methods=["GET"])
def api_get_status():
    """
    Return live status for every room right now:
      { room, color, status, current_booking, next_booking }
    """
    try:
        status = excel_db.get_today_status()
        return jsonify({"ok": True, "status": status})
    except Exception as exc:
        logger.exception("GET /api/status failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

# ---------------------------------------------------------------------------
# API — Bookings
# ---------------------------------------------------------------------------

@app.route("/api/bookings", methods=["GET"])
def api_get_bookings():
    """
    Query params:
      date=YYYY-MM-DD   (optional, defaults to today)
      room=<room_name>  (optional, for filtering)
    """
    filter_date = request.args.get("date") or datetime.now().date().isoformat()
    filter_room = request.args.get("room") or None
    try:
        bookings = excel_db.get_bookings(
            filter_date=filter_date,
            filter_room=filter_room
        )
        return jsonify({"ok": True, "bookings": bookings, "date": filter_date})
    except Exception as exc:
        logger.exception("GET /api/bookings failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/bookings/<booking_id>", methods=["GET"])
def api_get_booking(booking_id):
    """Return a single booking by ID."""
    try:
        booking = excel_db.get_booking_by_id(booking_id)
        if booking is None:
            return jsonify({"ok": False, "error": "Booking not found"}), 404
        return jsonify({"ok": True, "booking": booking})
    except Exception as exc:
        logger.exception("GET /api/bookings/%s failed", booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500


# ---------------------------------------------------------------------------
# API — Admin Validation
# ---------------------------------------------------------------------------

@app.route("/api/verify-admin", methods=["POST"])
def api_verify_admin():
    """Verify admin credentials before opening booking form."""
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Invalid admin username or password"}), 401


@app.route("/api/bookings", methods=["POST"])
def api_create_booking():
    """
    Body (JSON):
      { room, date, start_time, end_time, title, booked_by }

    Returns:
      201  { ok: true, booking: {...} }
      409  { ok: false, error: "...", conflict: {...} }   ← double-booking
      400  { ok: false, error: "..." }                    ← bad input
    """
    data = request.get_json(silent=True) or {}

    if data.get("username") != config.ADMIN_USERNAME or data.get("password") != config.ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401

    required = ["room", "date", "start_time", "end_time", "title", "booked_by"]
    missing  = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({
            "ok": False,
            "error": f"Missing fields: {', '.join(missing)}"
        }), 400

    try:
        booking, conflict = excel_db.add_booking(
            room            = data["room"].strip(),
            booking_date    = data["date"].strip(),
            start_time_str  = data["start_time"].strip(),
            end_time_str    = data["end_time"].strip(),
            title           = data["title"].strip(),
            booked_by       = data["booked_by"].strip(),
            email           = (data.get("email") or "").strip(),
            attendees       = (data.get("attendees") or "").strip(),
            attendee_emails = (data.get("attendee_emails") or "").strip(),
            meeting_mode    = (data.get("meeting_mode") or "offline").strip(),
            cc_emails       = (data.get("cc_emails") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("POST /api/bookings failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    if conflict:
        return jsonify({
            "ok":       False,
            "error":    (
                f"'{data['room']}' is already booked from "
                f"{conflict['conflict_start']} to {conflict['conflict_end']} "
                f"by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            ),
            "conflict": conflict,
        }), 409

    logger.info("New booking: %s in %s on %s", booking["title"],
                booking["room"], booking["date"])

    # Send confirmation email immediately (non-blocking — failure is logged, not raised)
    try:
        email_reminder.send_confirmation(booking)
    except Exception as exc:
        logger.warning("[Email] Confirmation email failed (non-fatal): %s", exc)

    return jsonify({"ok": True, "booking": booking}), 201


# ---------------------------------------------------------------------------
# API — Edit Booking (admin only)
# ---------------------------------------------------------------------------

@app.route("/api/bookings/<booking_id>", methods=["PATCH"])
def api_edit_booking(booking_id):
    """
    Edit an active booking.
    Body (JSON): { username, password, room?, start_time?, end_time?, attendees? }
    Only provided fields are updated; missing fields keep their original values.
    Returns 200  { ok: true, booking: {...} }
            409  { ok: false, error, conflict } on double-booking
            400 / 401 / 404 on bad input
    """
    data = request.get_json(silent=True) or {}

    if data.get("username") != config.ADMIN_USERNAME or data.get("password") != config.ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid admin credentials"}), 401

    # Collect only the editable fields that were actually provided
    updates = {}
    for field in ("room", "start_time", "end_time", "attendees", "attendee_emails", "meeting_mode", "cc_emails"):
        if field in data and data[field] is not None:
            updates[field] = data[field]

    if not updates:
        return jsonify({"ok": False, "error": "No editable fields provided."}), 400

    try:
        booking, conflict = excel_db.update_booking(booking_id, updates)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("PATCH /api/bookings/%s failed", booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

    if booking is None and conflict is None:
        return jsonify({"ok": False, "error": "Booking not found."}), 404

    if conflict:
        room = updates.get("room", "")
        return jsonify({
            "ok": False,
            "error": (
                f"'{room}' is already booked from {conflict['conflict_start']} "
                f"to {conflict['conflict_end']} by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            ),
            "conflict": conflict,
        }), 409

    logger.info("Booking %s edited by admin: %s", booking_id, list(updates.keys()))
    return jsonify({"ok": True, "booking": booking})


@app.route("/api/bookings/<booking_id>", methods=["DELETE"])
def api_cancel_booking(booking_id):
    """
    Cancel a booking.
    Requires JSON body: { "cancelled_by": "<name>" }
    The name must match booked_by (case-insensitive) for ownership check.
    """
    data         = request.get_json(silent=True) or {}
    cancelled_by = (data.get("cancelled_by") or "").strip()

    if data.get("username") != config.ADMIN_USERNAME or data.get("password") != config.ADMIN_PASSWORD:
        return jsonify({"ok": False, "error": "Invalid username or password"}), 401

    try:
        # Fetch the booking first to check name
        existing = excel_db.get_booking_by_id(booking_id)
        if existing is None:
            return jsonify({"ok": False, "error": "Booking not found"}), 404

        # Ownership guard — soft check (no login, just name match)
        if existing["status"] == "cancelled":
            return jsonify({"ok": False, "error": "Already cancelled"}), 409

        if cancelled_by.lower() != existing["booked_by"].lower():
            return jsonify({
                "ok": False,
                "error": (
                    "Name doesn't match the original booker. "
                    f"Enter '{existing['booked_by']}' to confirm cancellation."
                )
            }), 403

        cancelled = excel_db.cancel_booking(booking_id)
        if cancelled is None:
            return jsonify({"ok": False, "error": "Could not cancel booking"}), 500

        logger.info("Booking %s cancelled by %s", booking_id, cancelled_by)
        return jsonify({"ok": True, "booking": cancelled})

    except Exception as exc:
        logger.exception("DELETE /api/bookings/%s failed", booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

# ---------------------------------------------------------------------------
# Reminder Scheduler Job
# ---------------------------------------------------------------------------

def _reminder_job():
    """
    Runs every SCHEDULER_INTERVAL_SECONDS seconds.
    Finds bookings whose start time is between NOW and NOW + REMINDER_MINUTES_BEFORE
    that haven't had a reminder sent yet, and sends email reminders.

    Example: REMINDER_MINUTES_BEFORE=30 → if a meeting starts at 10:00,
    the reminder fires anywhere between 09:30 and 10:00 (whichever check runs first).
    """
    now       = datetime.now()
    today_str = now.date().isoformat()

    # The reminder window: [now, now + REMINDER_MINUTES_BEFORE]
    window_end = now + timedelta(minutes=config.REMINDER_MINUTES_BEFORE)

    try:
        bookings     = excel_db.get_bookings(filter_date=today_str)
        reminded_ids = excel_db.get_reminded_ids()
    except Exception as exc:
        logger.error("[Scheduler] Failed to load bookings/reminders: %s", exc)
        return

    for booking in bookings:
        # Skip if reminder already sent
        if booking["id"] in reminded_ids:
            continue

        try:
            start_dt = datetime.combine(
                now.date(),
                datetime.strptime(booking["start_time"], "%H:%M").time()
            )
        except ValueError:
            continue

        # Fire reminder if meeting starts within the next REMINDER_MINUTES_BEFORE minutes
        # (and hasn't started yet — don't remind after the fact)
        if now <= start_dt <= window_end:
            sent = email_reminder.send_reminder(booking)
            if sent:
                try:
                    excel_db.log_reminder(booking["id"])
                except Exception as exc:
                    logger.error("[Scheduler] Failed to log reminder: %s", exc)


# ---------------------------------------------------------------------------
# Start scheduler — guarded against Flask debug-mode double-start
# ---------------------------------------------------------------------------
# When DEBUG=True, Flask uses a reloader that forks a second process.
# The guard below ensures the scheduler only starts in the main worker process,
# preventing duplicate reminder emails.
# ---------------------------------------------------------------------------

def _start_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _reminder_job,
        trigger="interval",
        seconds=config.SCHEDULER_INTERVAL_SECONDS,
        id="reminder_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[Scheduler] Reminder job started — checking every %ds, "
        "window=%d min before start.",
        config.SCHEDULER_INTERVAL_SECONDS,
        config.REMINDER_MINUTES_BEFORE,
    )
    return scheduler


_scheduler = None

# Only start in the reloader's main process, not in the monitoring subprocess.
if not config.FLASK_DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _scheduler = _start_scheduler()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info(
        "Starting Meeting Management System app at http://%s:%d",
        config.FLASK_HOST, config.FLASK_PORT
    )
    # threaded=False: all requests are serialised, which eliminates any
    # remaining Excel concurrency risk.  For a small office app this is fine.
    app.run(
        host    = config.FLASK_HOST,
        port    = config.FLASK_PORT,
        debug   = config.FLASK_DEBUG,
        threaded= False,       # ← single-threaded; safe for Excel file writes
        use_reloader = config.FLASK_DEBUG,
    )
