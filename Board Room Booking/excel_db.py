# =============================================================================
# excel_db.py — Excel "Database" Layer
# =============================================================================
# All reads and writes to bookings.xlsx go through this file.
# A file lock (via the 'filelock' package) wraps every read-then-write so that:
#   - Concurrent HTTP requests can't corrupt the file.
#   - The overlap check + write is atomic (no race condition).
#   - The scheduler's reminder writes don't clash with user bookings.
# =============================================================================
 
import os
import uuid
import shutil
from datetime import datetime, date, time
 
import openpyxl
# pyrefly: ignore [missing-import]
from filelock import FileLock, Timeout
 
import config
 
# ---------------------------------------------------------------------------
# Lock helper
# ---------------------------------------------------------------------------
# Acquire this lock before reading AND before writing.  Use it as a context
# manager:  with _lock():  ...
# ---------------------------------------------------------------------------
_file_lock = FileLock(config.LOCK_PATH, timeout=10)   # wait up to 10 s
 
 
def _lock():
    """Return the FileLock context manager."""
    return _file_lock
 
 
# ---------------------------------------------------------------------------
# Sheet & workbook helpers
# ---------------------------------------------------------------------------
 
BOOKINGS_SHEET    = "Bookings"
ROOMS_SHEET       = "Rooms"
REMINDER_SHEET    = "ReminderLog"
USERS_SHEET       = "Users"
 
BOOKINGS_HEADERS  = ["id", "room", "date", "start_time", "end_time",
                      "title", "booked_by", "email", "attendees", "attendee_emails", "meeting_mode", "meeting_link", "cc_emails", "description", "created_at", "status"]
ROOMS_HEADERS     = ["room_name", "color", "capacity", "floor", "teams_link"]
REMINDER_HEADERS  = ["booking_id", "reminder_sent_at"]
USERS_HEADERS     = ["username", "email", "pin", "role", "created_at"]
 
 
def _ensure_data_dirs():
    """Create data/ and data/backups/ if they don't exist."""
    os.makedirs(config.DATA_DIR,   exist_ok=True)
    os.makedirs(config.BACKUP_DIR, exist_ok=True)
 
 
def _init_workbook():
    """
    Create bookings.xlsx with the three sheets and seed the Rooms sheet
    from config.ROOMS.  Only called when the file doesn't exist yet.
    """
    wb = openpyxl.Workbook()
 
    # --- Bookings sheet ---
    ws_b = wb.active
    ws_b.title = BOOKINGS_SHEET
    ws_b.append(BOOKINGS_HEADERS)
 
    # --- Rooms sheet ---
    ws_r = wb.create_sheet(ROOMS_SHEET)
    ws_r.append(ROOMS_HEADERS)
    for room in config.ROOMS:
        ws_r.append([room["name"], room["color"], "", room.get("floor", 0), room.get("teams_link", "")])
 
    # --- ReminderLog sheet ---
    ws_rl = wb.create_sheet(REMINDER_SHEET)
    ws_rl.append(REMINDER_HEADERS)
    
    # --- Users sheet ---
    ws_u = wb.create_sheet(USERS_SHEET)
    ws_u.append(USERS_HEADERS)
    # Add a default admin
    ws_u.append([config.ADMIN_USERNAME, "admin@example.com", config.ADMIN_PASSWORD, "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
 
    wb.save(config.EXCEL_PATH)
 
 
def _load_wb():
    """Load and return the workbook.  Must be called inside the file lock."""
    return openpyxl.load_workbook(config.EXCEL_PATH)
 
 
def _save_wb(wb):
    """Save workbook and immediately create a daily backup if needed."""
    wb.save(config.EXCEL_PATH)
    _maybe_backup()
 
 
import logging
 
logger = logging.getLogger(__name__)
 
def _maybe_backup():
    """
    Copy bookings.xlsx to data/backups/bookings_YYYY-MM-DD.xlsx on every save.
    This ensures today's backup file always contains all latest bookings.
    """
    today_str   = date.today().isoformat()
    backup_path = os.path.join(config.BACKUP_DIR, f"bookings_{today_str}.xlsx")
    try:
        shutil.copy2(config.EXCEL_PATH, backup_path)
        logger.info("[Backup] Daily backup updated at: %s", backup_path)
    except Exception as exc:
        logger.error("[Backup] Failed to update backup: %s", exc)
 
 
def _rows_as_dicts(ws):
    """Convert worksheet rows to list of dicts, using the first row as keys."""
    headers = [cell.value for cell in ws[1]]
    result  = []
    for row in ws.iter_rows(min_row=2):
        if any(cell.value is not None for cell in row):          # skip fully empty rows
            row_values = []
            for cell in row:
                if cell.hyperlink and cell.hyperlink.target:
                    val_str = str(cell.value or "")
                    if "|" in val_str:
                        parts = [p.strip() for p in val_str.split("|")]
                        combined = "|".join([cell.hyperlink.target] + parts[1:])
                        row_values.append(combined)
                    else:
                        row_values.append(cell.hyperlink.target)
                else:
                    row_values.append(cell.value)
            result.append(dict(zip(headers, row_values)))
    return result
 
 
def _str_to_time(value):
    """
    Parse HH:MM or HH:MM:SS string (or datetime.time object) → datetime.time.
    openpyxl sometimes returns time objects directly from cells.
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None
 
 
def _str_to_date(value):
    """Parse YYYY-MM-DD string or date/datetime object → datetime.date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
 
 
# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
 
def ensure_db():
    """
    Called once at startup.  Creates the Excel file if it doesn't exist.
    Safe to call repeatedly — adds missing columns if upgrading schema.
    """
    _ensure_data_dirs()
    if not os.path.exists(config.EXCEL_PATH):
        _init_workbook()
    else:
        with _lock():
            wb = _load_wb()
            ws = wb[BOOKINGS_SHEET]
            headers = [cell.value for cell in ws[1]]
            
            # Ensure "attendees" column exists
            if "attendees" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="attendees")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="attendees")
                headers = [cell.value for cell in ws[1]] # refresh headers
                
            # Ensure "attendee_emails" column exists
            if "attendee_emails" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="attendee_emails")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="attendee_emails")
                _save_wb(wb)
                headers = [cell.value for cell in ws[1]] # refresh headers

            # Ensure "meeting_mode" column exists
            if "meeting_mode" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="meeting_mode")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="meeting_mode")
                _save_wb(wb)
                headers = [cell.value for cell in ws[1]]

            # Ensure "meeting_link" column exists
            if "meeting_link" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="meeting_link")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="meeting_link")
                _save_wb(wb)
                headers = [cell.value for cell in ws[1]]

            # Ensure "cc_emails" column exists
            if "cc_emails" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="cc_emails")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="cc_emails")
                _save_wb(wb)
                headers = [cell.value for cell in ws[1]]

            # Ensure "description" column exists
            if "description" not in headers:
                idx = next((headers.index(k) + 1 for k in ["created_at", "create", "status"] if k in headers), None)
                if idx is not None:
                    ws.insert_cols(idx)
                    ws.cell(row=1, column=idx, value="description")
                else:
                    ws.cell(row=1, column=len(headers) + 1, value="description")
                _save_wb(wb)
                headers = [cell.value for cell in ws[1]]
           
            # Ensure "floor" column exists in Rooms sheet
            ws_r = wb[ROOMS_SHEET]
            r_headers = [cell.value for cell in ws_r[1]]
            if "floor" not in r_headers:
                ws_r.cell(row=1, column=len(r_headers) + 1, value="floor")
                _save_wb(wb)
                r_headers = [cell.value for cell in ws_r[1]]
                
            # Ensure "teams_link" column exists in Rooms sheet
            if "teams_link" not in r_headers:
                if None in r_headers:
                    idx = r_headers.index(None) + 1
                    ws_r.cell(row=1, column=idx, value="teams_link")
                else:
                    ws_r.cell(row=1, column=len(r_headers) + 1, value="teams_link")
                _save_wb(wb)
                
            # Ensure Users sheet exists
            if USERS_SHEET not in wb.sheetnames:
                ws_u = wb.create_sheet(USERS_SHEET)
                ws_u.append(USERS_HEADERS)
                ws_u.append([config.ADMIN_USERNAME, "admin@example.com", config.ADMIN_PASSWORD, "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                _save_wb(wb)
 
 
# --- Rooms ------------------------------------------------------------------
 
def get_rooms():
    """
    Return list of rooms from the Rooms sheet.
    Falls back to config.ROOMS if the sheet is empty, so the app always
    has a valid room list even on first run.
    """
    with _lock():
        wb  = _load_wb()
        ws  = wb[ROOMS_SHEET]
        rows = _rows_as_dicts(ws)
 
    rooms = [
        {
            "name":     r["room_name"],
            "color":    r.get("color") or "#6366f1",
            "capacity": r.get("capacity") or "",
            "floor":    int(r["floor"]) if r.get("floor") is not None and str(r["floor"]).strip().isdigit() else 0,
            "teams_link": r.get("teams_link") or "",
        }
        for r in rows if r.get("room_name")
    ]
    if not rooms:
        rooms = config.ROOMS
 
    # Merge floor info from config.ROOMS (fallback/override if floor not in Excel or is 0)
    _floor_map = {r["name"]: r.get("floor", 0) for r in config.ROOMS}
    for room in rooms:
        if room.get("floor") == 0:
            room["floor"] = _floor_map.get(room["name"], 0)
 
    return rooms
 
 
# --- Bookings ---------------------------------------------------------------
 
def get_bookings(filter_date=None, filter_room=None):
    """
    Return active bookings, optionally filtered by date (str YYYY-MM-DD)
    and/or room name.
    """
    with _lock():
        wb   = _load_wb()
        ws   = wb[BOOKINGS_SHEET]
        rows = _rows_as_dicts(ws)
 
    result = []
    for r in rows:
        if r.get("status") != "active":
            continue
        if filter_room and r.get("room") != filter_room:
            continue
        if filter_date:
            row_date = _str_to_date(r.get("date"))
            if row_date is None or row_date.isoformat() != filter_date:
                continue
        result.append(_serialize_booking(r))
 
    # Sort chronologically
    result.sort(key=lambda b: (b["date"], b["start_time"]))
    return result
 
 
def get_booking_by_id(booking_id):
    """Return a single booking dict by id, or None if not found."""
    with _lock():
        wb   = _load_wb()
        ws   = wb[BOOKINGS_SHEET]
        rows = _rows_as_dicts(ws)
 
    for r in rows:
        if str(r.get("id")) == str(booking_id):
            return _serialize_booking(r)
    return None
 
 
def _serialize_booking(row):
    """Normalize a raw row dict into clean string fields for JSON output."""
    d = _str_to_date(row.get("date"))
    s = _str_to_time(row.get("start_time"))
    e = _str_to_time(row.get("end_time"))
    return {
        "id":         str(row.get("id", "") or ""),
        "room":       str(row.get("room", "") or ""),
        "date":       d.isoformat() if d else "",
        "start_time": s.strftime("%H:%M") if s else "",
        "end_time":   e.strftime("%H:%M") if e else "",
        "title":      str(row.get("title", "") or ""),
        "booked_by":  str(row.get("booked_by", "") or ""),
        "email":      str(row.get("email", "") or ""),
        "attendees":  str(row.get("attendees", "") or ""),
        "attendee_emails": str(row.get("attendee_emails", "") or ""),
        "meeting_mode": str(row.get("meeting_mode", "") or "offline"),
        "meeting_link": str(row.get("meeting_link", "") or ""),
        "cc_emails":    str(row.get("cc_emails", "") or ""),
        "description":  str(row.get("description", "") or ""),
        "created_at": str(row.get("created_at", "") or ""),
        "status":     str(row.get("status", "") or ""),
    }
 
 
def _times_overlap(s1, e1, s2, e2):
    """Return True if time interval [s1,e1) overlaps [s2,e2)."""
    return s1 < e2 and e1 > s2
 
 
def _parse_emails(emails_str):
    if not emails_str:
        return set()
    emails = set()
    for p in str(emails_str).replace(";", ",").split(","):
        email_part = p.strip()
        if "<" in email_part and ">" in email_part:
            email_part = email_part.split("<")[-1].split(">")[0].strip()
        if email_part and "@" in email_part:
            emails.add(email_part.lower())
    return emails


def add_booking(room, booking_date, start_time_str, end_time_str, 
                title, booked_by, email="", attendees="", attendee_emails="",
                meeting_mode="offline", meeting_link="", cc_emails="", description=""):
    """
    Atomically check for conflicts and write a new booking.
    Returns (booking_dict, None) on success.
    Returns (None, conflict_dict) if the slot is already taken.
    Raises ValueError for bad input.
    """
    # --- Validate inputs (server-side) ---
    try:
        b_date = datetime.strptime(booking_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Invalid date format. Use YYYY-MM-DD.")
 
    try:
        b_start = datetime.strptime(start_time_str, "%H:%M").time()
        b_end   = datetime.strptime(end_time_str,   "%H:%M").time()
    except ValueError:
        raise ValueError("Invalid time format. Use HH:MM.")
 
    if b_start >= b_end:
        raise ValueError("Start time must be before end time.")
    if not title.strip():
        raise ValueError("Meeting title cannot be empty.")
    if not booked_by.strip():
        raise ValueError("Booked-by name cannot be empty.")
    if not room.strip():
        raise ValueError("Room cannot be empty.")
 
    # --- Atomic check-then-write (whole block under the lock) ---
    with _lock():
        wb      = _load_wb()
        ws_b    = wb[BOOKINGS_SHEET]
        rows    = _rows_as_dicts(ws_b)
 
        # Check for overlaps
        for r in rows:
            if r.get("status") != "active":
                continue
            row_date = _str_to_date(r.get("date"))
            if row_date != b_date:
                continue
            rs = _str_to_time(r.get("start_time"))
            re = _str_to_time(r.get("end_time"))
            if not (rs and re and _times_overlap(b_start, b_end, rs, re)):
                continue

            # Case A: Room overlap
            if r.get("room") == room:
                return None, {
                    "conflict_type": "room",
                    "conflict_title":      str(r.get("title", "")),
                    "conflict_booked_by":  str(r.get("booked_by", "")),
                    "conflict_start":      rs.strftime("%H:%M"),
                    "conflict_end":        re.strftime("%H:%M"),
                }

            # Case B: Attendee overlap
            existing_emails = _parse_emails(r.get("attendee_emails"))
            new_emails = _parse_emails(attendee_emails)
            common_emails = existing_emails.intersection(new_emails)
            if common_emails:
                return None, {
                    "conflict_type": "attendee",
                    "conflict_email": list(common_emails)[0],
                    "conflict_title":      str(r.get("title", "")),
                    "conflict_booked_by":  str(r.get("booked_by", "")),
                    "conflict_start":      rs.strftime("%H:%M"),
                    "conflict_end":        re.strftime("%H:%M"),
                }
 
        # No conflict — write the new row
        new_id  = str(uuid.uuid4())
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        import random
        import string
        m_mode = (meeting_mode or "offline").strip().lower()
        m_link = (meeting_link or "").strip()

        if m_mode == "online" and not m_link:
            # Check if there is a room-specific teams_link in the database
            rooms_list = get_rooms()
            sel_rm = next((r for r in rooms_list if r["name"] == room.strip()), None)
            room_link = sel_rm.get("teams_link", "").strip() if sel_rm else ""
            
            use_dynamic = True
            if room_link:
                parts = [p.strip() for p in room_link.split("|")]
                if parts[0].startswith("http://") or parts[0].startswith("https://"):
                    m_link = room_link
                    use_dynamic = False

            if use_dynamic:
                import base64
                raw_uuid = str(uuid.uuid4())
                meeting_uuid = base64.b64encode(raw_uuid.encode('utf-8')).decode('utf-8').replace('=', '')
                join_url = f"https://teams.microsoft.com/l/meetup-join/19%3ameeting_{meeting_uuid}%40thread.v2/0?context=%7b%22Tid%22%3a%22mseducation.academy%22%7d"
                
                if room_link:
                    parts = [p.strip() for p in room_link.split("|")]
                    meeting_id = parts[1] if len(parts) > 1 else f"{random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}"
                    passcode = parts[2] if len(parts) > 2 else "".join(random.choices(string.ascii_letters + string.digits, k=6))
                else:
                    meeting_id = f"{random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}"
                    passcode = "".join(random.choices(string.ascii_letters + string.digits, k=6))
                
                m_link = f"{join_url}|{meeting_id}|{passcode}"
        elif m_mode != "online":
            m_link = ""

        headers = [c.value for c in ws_b[1]]
        row_dict = {
            "id": new_id,
            "room": room.strip(),
            "date": b_date.isoformat(),
            "start_time": b_start.strftime("%H:%M"),
            "end_time": b_end.strftime("%H:%M"),
            "title": title.strip(),
            "booked_by": booked_by.strip(),
            "email": email.strip(),
            "attendees": attendees.strip(),
            "attendee_emails": attendee_emails.strip(),
            "meeting_mode": m_mode,
            "meeting_link": m_link,
            "cc_emails": cc_emails.strip(),
            "description": description.strip(),
            "created_at": now_str,
            "status": "active",
        }
        ws_b.append([row_dict.get(h, "") for h in headers])
        _save_wb(wb)

    return {
        "id":         new_id,
        "room":       room.strip(),
        "date":       b_date.isoformat(),
        "start_time": b_start.strftime("%H:%M"),
        "end_time":   b_end.strftime("%H:%M"),
        "title":      title.strip(),
        "booked_by":  booked_by.strip(),
        "email":      email.strip(),
        "attendees":  attendees.strip(),
        "attendee_emails": attendee_emails.strip(),
        "meeting_mode": m_mode,
        "meeting_link": m_link,
        "cc_emails": cc_emails.strip(),
        "description": description.strip(),
        "created_at": now_str,
        "status":     "active",
    }, None
 
 
def update_booking(booking_id, updates):
    """
    Partially update an active booking (room, start_time, end_time, attendees).
    Checks conflicts (skipping self) before writing.
    Returns (updated_booking_dict, None) on success.
    Returns (None, conflict_dict)  if the new slot is taken.
    Returns (None, None)           if booking_id not found.
    Raises ValueError for bad input.
    """
    new_room  = updates.get('room')
    new_start = updates.get('start_time')
    new_end   = updates.get('end_time')
    new_att   = updates.get('attendees')
    new_att_emails = updates.get('attendee_emails')
    new_meeting_mode = updates.get('meeting_mode')
    new_cc_emails = updates.get('cc_emails')
    new_desc = updates.get('description')
 
    with _lock():
        wb      = _load_wb()
        ws      = wb[BOOKINGS_SHEET]
        headers = [c.value for c in ws[1]]
        col     = {h: i for i, h in enumerate(headers)}
 
        # Find target row
        target_row  = None
        target_data = None
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value) == str(booking_id):
                target_data = {h: row[col[h]].value for h in headers}
                target_row  = row
                break
 
        if target_row is None:
            return None, None
        if str(target_data.get('status', '')) != 'active':
            raise ValueError('Booking is not active and cannot be edited.')
 
        # Resolve final values
        final_room  = new_room  or str(target_data.get('room',  '') or '')
        final_start = new_start or str(target_data.get('start_time', '') or '')
        final_end   = new_end   or str(target_data.get('end_time',   '') or '')
        final_att_emails = new_att_emails if new_att_emails is not None else str(target_data.get('attendee_emails', '') or '')
 
        b_date  = _str_to_date(target_data.get('date'))
        b_start = _str_to_time(final_start)
        b_end   = _str_to_time(final_end)
 
        if b_start is None or b_end is None:
            raise ValueError('Invalid time format. Use HH:MM.')
        if b_start >= b_end:
            raise ValueError('End time must be after start time.')
 
        # Conflict check — skip self
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value) == str(booking_id):
                continue
            rd = {h: row[col[h]].value for h in headers}
            if str(rd.get('status', '')) != 'active':
                continue
            row_date = _str_to_date(rd.get('date'))
            if row_date != b_date:
                continue
            rs = _str_to_time(rd.get('start_time'))
            re = _str_to_time(rd.get('end_time'))
            if not (rs and re and _times_overlap(b_start, b_end, rs, re)):
                continue
 
            # Case A: Room overlap
            if str(rd.get('room', '')) == final_room:
                return None, {
                    "conflict_type": "room",
                    "conflict_room": final_room,
                    'conflict_title':     str(rd.get('title', '')),
                    'conflict_booked_by': str(rd.get('booked_by', '')),
                    'conflict_start':     rs.strftime('%H:%M'),
                    'conflict_end':       re.strftime('%H:%M'),
                }
 
            # Case B: Attendee overlap
            existing_emails = _parse_emails(rd.get('attendee_emails'))
            new_emails = _parse_emails(final_att_emails)
            common_emails = existing_emails.intersection(new_emails)
            if common_emails:
                return None, {
                    "conflict_type": "attendee",
                    "conflict_email": list(common_emails)[0],
                    'conflict_title':     str(rd.get('title', '')),
                    'conflict_booked_by': str(rd.get('booked_by', '')),
                    'conflict_start':     rs.strftime('%H:%M'),
                    'conflict_end':       re.strftime('%H:%M'),
                }
 
        # Apply updates in-place (only touch changed fields)
        if new_room  is not None: target_row[col['room']].value       = final_room
        if new_start is not None: target_row[col['start_time']].value = b_start.strftime('%H:%M')
        if new_end   is not None: target_row[col['end_time']].value   = b_end.strftime('%H:%M')
        if new_att   is not None: target_row[col['attendees']].value  = new_att.strip()
        if new_att_emails is not None: target_row[col['attendee_emails']].value = new_att_emails.strip()
        if new_cc_emails is not None: target_row[col['cc_emails']].value = new_cc_emails.strip()
        if new_desc is not None: target_row[col['description']].value = new_desc.strip()

        if new_meeting_mode is not None:
            old_mode = str(target_data.get('meeting_mode', '') or '').strip().lower()
            old_link = str(target_data.get('meeting_link', '') or '').strip()
            new_mode_clean = new_meeting_mode.strip().lower()

            target_row[col['meeting_mode']].value = new_mode_clean
            if new_mode_clean == "online":
                if not old_link or old_mode != "online":
                    current_room = target_row[col['room']].value or ''
                    rooms_list = get_rooms()
                    sel_rm = next((r for r in rooms_list if r["name"] == current_room.strip()), None)
                    room_link = sel_rm.get("teams_link", "").strip() if sel_rm else ""
                    
                    use_dynamic = True
                    if room_link:
                        parts = [p.strip() for p in room_link.split("|")]
                        if parts[0].startswith("http://") or parts[0].startswith("https://"):
                            target_row[col['meeting_link']].value = room_link
                            use_dynamic = False

                    if use_dynamic:
                        import random
                        import string
                        import base64
                        raw_uuid = str(uuid.uuid4())
                        meeting_uuid = base64.b64encode(raw_uuid.encode('utf-8')).decode('utf-8').replace('=', '')
                        join_url = f"https://teams.microsoft.com/l/meetup-join/19%3ameeting_{meeting_uuid}%40thread.v2/0?context=%7b%22Tid%22%3a%22mseducation.academy%22%7d"
                        
                        if room_link:
                            parts = [p.strip() for p in room_link.split("|")]
                            meeting_id = parts[1] if len(parts) > 1 else f"{random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}"
                            passcode = parts[2] if len(parts) > 2 else "".join(random.choices(string.ascii_letters + string.digits, k=6))
                        else:
                            meeting_id = f"{random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)} {random.randint(100,999)}"
                            passcode = "".join(random.choices(string.ascii_letters + string.digits, k=6))
                        
                        target_row[col['meeting_link']].value = f"{join_url}|{meeting_id}|{passcode}"
            else:
                target_row[col['meeting_link']].value = ""
 
        _save_wb(wb)
 
        updated = {h: target_row[col[h]].value for h in headers}
        return _serialize_booking(updated), None
 
 
def cancel_booking(booking_id):
    """
    Set status to 'cancelled' for the given booking id.
    Returns the cancelled booking dict, or None if not found.
    """
    with _lock():
        wb   = _load_wb()
        ws   = wb[BOOKINGS_SHEET]
        headers = [c.value for c in ws[1]]
        status_col = headers.index("status") + 1   # 1-indexed
 
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value) == str(booking_id):
                if row[status_col - 1].value == "cancelled":
                    return None   # already cancelled
                row[status_col - 1].value = "cancelled"
                booking_data = {h: row[i].value for i, h in enumerate(headers)}
                _save_wb(wb)
                return _serialize_booking(booking_data)
    return None
 
 
# --- Reminder Log -----------------------------------------------------------
 
def get_reminded_ids():
    """Return a set of booking_ids that already had a reminder sent."""
    with _lock():
        wb   = _load_wb()
        ws   = wb[REMINDER_SHEET]
        rows = _rows_as_dicts(ws)
    return {str(r["booking_id"]) for r in rows if r.get("booking_id")}
 
 
def log_reminder(booking_id):
    """Record that a reminder was sent for booking_id."""
    with _lock():
        wb  = _load_wb()
        ws  = wb[REMINDER_SHEET]
        ws.append([str(booking_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        _save_wb(wb)
 
 
# --- Today's Status ---------------------------------------------------------
 
def get_today_status():
    """
    Return a list of {room, status, current_booking, next_booking} dicts
    for the current moment, one entry per room.
      status = "engaged" | "vacant"
    """
    now        = datetime.now()
    today_str  = now.date().isoformat()
    now_time   = now.time().replace(second=0, microsecond=0)
 
    bookings   = get_bookings(filter_date=today_str)
    rooms      = get_rooms()
 
    status_list = []
    for room in rooms:
        room_name = room["name"]
        room_bks  = [b for b in bookings if b["room"] == room_name]
 
        current   = None
        upcoming  = None
 
        for b in room_bks:
            s = _str_to_time(b["start_time"])
            e = _str_to_time(b["end_time"])
            if s <= now_time < e:
                current = b
            elif s > now_time:
                if upcoming is None or s < _str_to_time(upcoming["start_time"]):
                    upcoming = b
 
        status_list.append({
            "room":            room_name,
            "color":           room["color"],
            "floor":           room.get("floor", 0),
            "status":          "engaged" if current else "vacant",
            "current_booking": current,
            "next_booking":    upcoming,
        })
 
    return status_list

# --- Users ------------------------------------------------------------------
 
def get_users():
    """Return list of all users."""
    with _lock():
        wb  = _load_wb()
        ws  = wb[USERS_SHEET]
        rows = _rows_as_dicts(ws)
    return rows

def verify_user(username, pin):
    """Return user dict if credentials match, else None."""
    users = get_users()
    for u in users:
        if str(u.get("username")).lower() == str(username).lower() and str(u.get("pin")) == str(pin):
            return u
    # Fallback to config admin
    if username == config.ADMIN_USERNAME and pin == config.ADMIN_PASSWORD:
        return {"username": config.ADMIN_USERNAME, "role": "admin"}
    return None

def add_user(username, email, pin, role="user"):
    with _lock():
        wb = _load_wb()
        ws = wb[USERS_SHEET]
        # Check if user exists
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value).lower() == str(username).lower():
                return False, "Username already exists"
        
        ws.append([username, email, pin, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        _save_wb(wb)
    return True, None

def reset_pin(username, new_pin):
    with _lock():
        wb = _load_wb()
        ws = wb[USERS_SHEET]
        for row in ws.iter_rows(min_row=2):
            if str(row[0].value).lower() == str(username).lower():
                row[2].value = new_pin
                _save_wb(wb)
                return True
    return False

def get_user_by_username(username):
    users = get_users()
    for u in users:
        if str(u.get("username")).lower() == str(username).lower():
            return u
    return None

def delete_user(username):
    with _lock():
        wb = _load_wb()
        ws = wb[USERS_SHEET]
        for i, row in enumerate(ws.iter_rows(min_row=2)):
            if str(row[0].value).lower() == str(username).lower():
                ws.delete_rows(i + 2)
                _save_wb(wb)
                return True
    return False
