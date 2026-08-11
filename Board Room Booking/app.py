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

@app.route("/api/verify-user", methods=["POST"])
def api_verify_user():
    """Verify user/admin credentials before opening booking form."""
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    pin = data.get("password")  # The frontend sends "password"
    user = excel_db.verify_user(username, pin)
    if user:
        return jsonify({
            "ok": True, 
            "role": user.get("role", "user"), 
            "email": user.get("email", "")
        })
    return jsonify({"ok": False, "error": "Invalid username or PIN"}), 401


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

    user = excel_db.verify_user(data.get("username"), data.get("password"))
    if not user:
        return jsonify({"ok": False, "error": "Invalid username or PIN"}), 401

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
            description     = (data.get("description") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        logger.exception("POST /api/bookings failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

    if conflict:
        if conflict.get("conflict_type") == "attendee":
            err_msg = (
                f"Attendee '{conflict['conflict_email']}' is already in another meeting from "
                f"{conflict['conflict_start']} to {conflict['conflict_end']} "
                f"by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            )
        else:
            err_msg = (
                f"'{data['room']}' is already booked from "
                f"{conflict['conflict_start']} to {conflict['conflict_end']} "
                f"by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            )
        return jsonify({
            "ok":       False,
            "error":    err_msg,
            "conflict": conflict,
        }), 409

    logger.info("New booking: %s in %s on %s", booking["title"],
                booking["room"], booking["date"])

    # Send confirmation email asynchronously (non-blocking to prevent HTTP latency)
    import threading
    threading.Thread(
        target=email_reminder.send_confirmation,
        args=(booking,),
        daemon=True
    ).start()

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

    user = excel_db.verify_user(data.get("username"), data.get("password"))
    if not user:
        return jsonify({"ok": False, "error": "Invalid username or PIN"}), 401

    # Collect only the editable fields that were actually provided
    updates = {}
    for field in ("room", "start_time", "end_time", "attendees", "attendee_emails", "meeting_mode", "cc_emails", "description"):
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
        if conflict.get("conflict_type") == "attendee":
            err_msg = (
                f"Attendee '{conflict['conflict_email']}' is already in another meeting from "
                f"{conflict['conflict_start']} to {conflict['conflict_end']} "
                f"by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            )
        else:
            room = conflict.get("conflict_room") or updates.get("room", "") or (booking.get("room") if booking else "")
            err_msg = (
                f"'{room}' is already booked from {conflict['conflict_start']} "
                f"to {conflict['conflict_end']} by {conflict['conflict_booked_by']} "
                f"({conflict['conflict_title']})."
            )
        return jsonify({
            "ok": False,
            "error": err_msg,
            "conflict": conflict,
        }), 409

    logger.info("Booking %s edited by admin: %s", booking_id, list(updates.keys()))
    return jsonify({"ok": True, "booking": booking})


@app.route("/api/bookings/<booking_id>", methods=["DELETE"])
def api_cancel_booking(booking_id):
    """
    Cancel a booking.
    Requires JSON body: { "username": "<name>", "password": "<pin>" }
    The user's email must match the booking's email, unless they are an admin.
    """
    data         = request.get_json(silent=True) or {}

    user = excel_db.verify_user(data.get("username"), data.get("password"))
    if not user:
        return jsonify({"ok": False, "error": "Invalid username or PIN"}), 401

    try:
        existing = excel_db.get_booking_by_id(booking_id)
        if existing is None:
            return jsonify({"ok": False, "error": "Booking not found"}), 404

        if existing["status"] == "cancelled":
            return jsonify({"ok": False, "error": "Already cancelled"}), 409

        # Ownership guard — check email match or admin role
        is_admin = user.get("role") == "admin"
        user_email = user.get("email", "").strip().lower()
        booking_email = existing.get("email", "").strip().lower()

        if not is_admin and (not user_email or user_email != booking_email):
            return jsonify({
                "ok": False,
                "error": "You can only cancel meetings that you booked (email mismatch)."
            }), 403

        cancelled = excel_db.cancel_booking(booking_id)
        if cancelled is None:
            return jsonify({"ok": False, "error": "Could not cancel booking"}), 500

        # Send cancellation email asynchronously (non-blocking)
        import threading
        threading.Thread(
            target=email_reminder.send_cancellation,
            args=(cancelled, user.get("username")),
            daemon=True
        ).start()

        logger.info("Booking %s cancelled by user %s", booking_id, user.get("username"))
        return jsonify({"ok": True, "booking": cancelled})

    except Exception as exc:
        logger.exception("DELETE /api/bookings/%s failed", booking_id)
        return jsonify({"ok": False, "error": str(exc)}), 500

# ---------------------------------------------------------------------------
# API — User Management & Forgot PIN
# ---------------------------------------------------------------------------

def _is_admin(username, pin):
    u = excel_db.verify_user(username, pin)
    return u is not None and u.get("role") == "admin"

@app.route("/api/users", methods=["GET"])
def api_get_users():
    admin_user = request.args.get("username")
    admin_pin = request.args.get("pin")
    if not _is_admin(admin_user, admin_pin):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    users = excel_db.get_users()
    # Mask PINs except for the returned data
    clean_users = [{"username": u.get("username"), "email": u.get("email"), "role": u.get("role")} for u in users]
    return jsonify({"ok": True, "users": clean_users})

@app.route("/api/users", methods=["POST"])
def api_create_user():
    data = request.get_json(silent=True) or {}
    if not _is_admin(data.get("admin_username"), data.get("admin_password")):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    pin = (data.get("pin") or "").strip()
    role = (data.get("role") or "user").strip()

    if not username or not pin:
        return jsonify({"ok": False, "error": "Username and PIN are required"}), 400

    success, err = excel_db.add_user(username, email, pin, role)
    if not success:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True}), 201

@app.route("/api/users/<username>", methods=["DELETE"])
def api_delete_user(username):
    data = request.get_json(silent=True) or {}
    if not _is_admin(data.get("admin_username"), data.get("admin_password")):
        return jsonify({"ok": False, "error": "Admin access required"}), 403
    
    if excel_db.delete_user(username):
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "User not found"}), 404

@app.route("/api/forgot-pin", methods=["POST"])
def api_forgot_pin():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    user = excel_db.get_user_by_username(username)
    if not user:
        return jsonify({"ok": False, "error": "User not found"}), 404
    
    email = user.get("email")
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "No valid email address on file for this user"}), 400
    
    # Send email with PIN
    import email_reminder
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your MMS Board Room Booking PIN"
    msg["From"] = config.SMTP_FROM
    msg["To"] = email
    
    plain = f"Hello {username},\n\nYour PIN is: {user.get('pin')}\n\nPlease keep this secure."
    html = f"<p>Hello <b>{username}</b>,</p><p>Your PIN is: <b>{user.get('pin')}</b></p><p>Please keep this secure.</p>"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    
    sent = email_reminder._send_via_smtp(msg)
    if sent:
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "Failed to send email. Please contact administrator."}), 500

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
    # threaded=True: Allows Flask to serve multiple concurrent requests,
    # relying on filelock and caching to keep Excel safe and fast.
    app.run(
        host    = config.FLASK_HOST,
        port    = config.FLASK_PORT,
        debug   = config.FLASK_DEBUG,
        threaded= True,        # ← multi-threaded to prevent latency
        use_reloader = config.FLASK_DEBUG,
    )
