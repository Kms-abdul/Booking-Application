# =============================================================================
# email_reminder.py — Email Sender (Confirmations, Reminders & Cancellations)
# =============================================================================
# Three types of emails are sent:
#   1. Booking Confirmation — immediately after a new booking is created
#   2. Meeting Reminder     — 15 minutes before a meeting starts (configurable)
#   3. Meeting Cancellation — when a booking is cancelled
#
# Both Gmail and Outlook / Office 365 are supported.
# Set credentials in config.py — not here.
# =============================================================================

import smtplib
import logging
from datetime import datetime, date, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def _format_date(date_val) -> str:
    """Format date to DD/MM/YYYY."""
    if not date_val:
        return ""
    if hasattr(date_val, "strftime"):
        return date_val.strftime("%d/%m/%Y")
    val_str = str(date_val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(val_str, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return val_str


def _format_time_12h(time_val) -> str:
    """Format time string (e.g. '14:00') to 12-hour clock (e.g. '2:00 PM')."""
    if not time_val:
        return ""
    if hasattr(time_val, "strftime"):
        formatted = time_val.strftime("%I:%M %p")
        return formatted.lstrip("0") if formatted.startswith("0") else formatted
    val_str = str(time_val).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(val_str, fmt).time()
            formatted = t.strftime("%I:%M %p")
            return formatted.lstrip("0") if formatted.startswith("0") else formatted
        except ValueError:
            continue
    return val_str


def _get_room_display(room_name: str, include_floor: bool = True) -> str:
    """Format room name with floor suffix if available, e.g. 'Multazim – CEO Conference Room (3rd Floor)'."""
    room_str = (room_name or "").strip()
    if not room_str or not include_floor:
        return room_str

    if "floor" in room_str.lower():
        return room_str

    r_info = None
    try:
        import excel_db
        rooms = excel_db.get_rooms()
        r_info = next((r for r in rooms if r["name"].strip().lower() == room_str.lower()), None)
    except Exception:
        pass

    if not r_info:
        r_info = next((r for r in config.ROOMS if r["name"].strip().lower() == room_str.lower()), None)

    if r_info and r_info.get("floor"):
        floor_val = r_info.get("floor")
        floor_str = str(floor_val).strip()
        if floor_str.isdigit() and int(floor_str) > 0:
            f_num = int(floor_str)
            if f_num == 1:
                suffix = "1st Floor"
            elif f_num == 2:
                suffix = "2nd Floor"
            elif f_num == 3:
                suffix = "3rd Floor"
            else:
                suffix = f"{f_num}th Floor"
            return f"{room_str} ({suffix})"
    return room_str


def _extract_venue_and_purpose(booking: dict) -> tuple[str, str]:
    """Extract venue and purpose from booking description."""
    raw_desc = (booking.get("description") or "").strip()
    venue = (booking.get("venue") or "").strip()
    purpose = raw_desc

    if raw_desc.startswith("Venue:"):
        parts = raw_desc.split("\n\n", 1)
        extracted_venue = parts[0][6:].strip()
        if not venue:
            venue = extracted_venue
        if len(parts) > 1:
            purpose = parts[1].strip()
        else:
            purpose = ""

    return venue, purpose


def _get_teams_link_details(booking: dict) -> tuple[str, str, str]:
    """Return (join_url, meeting_id, passcode) for online meetings."""
    link_str = (booking.get("meeting_link") or "").strip()

    if not link_str:
        room_name = (booking.get("room") or "").strip()
        try:
            import excel_db
            rooms = excel_db.get_rooms()
            sel_rm = next((r for r in rooms if r["name"].strip().lower() == room_name.lower()), None)
            if sel_rm and sel_rm.get("teams_link"):
                link_str = sel_rm.get("teams_link").strip()
        except Exception:
            pass

        if not link_str:
            sel_rm = next((r for r in config.ROOMS if r["name"].strip().lower() == room_name.lower()), None)
            if sel_rm and sel_rm.get("teams_link"):
                link_str = sel_rm.get("teams_link").strip()

    if not link_str:
        return "", "", ""

    parts = [p.strip() for p in link_str.split("|")]
    url = parts[0]
    mid = parts[1] if len(parts) > 1 else ""
    passcode = parts[2] if len(parts) > 2 else ""

    if mid.strip().lower() == "meeting-join" or passcode.strip().lower() == "microsoft teams":
        mid = ""
        passcode = ""

    return url, mid, passcode


# ---------------------------------------------------------------------------
# Recipient Helpers
# ---------------------------------------------------------------------------

def _get_recipients(booking: dict) -> list[str]:
    """
    Get recipient email list (TO field).
    Includes all attendee emails parsed from the booking.
    Falls back to the organiser's email (or config.REMINDER_TO) if no attendee emails are found.
    """
    recipients = []

    # Attendee emails
    att_emails_str = (booking.get("attendee_emails") or "").strip()
    if att_emails_str:
        for p in att_emails_str.replace(";", ",").split(","):
            email_part = p.strip()
            if "<" in email_part and ">" in email_part:
                email_part = email_part.split("<")[-1].split(">")[0].strip()
            if email_part and "@" in email_part and email_part not in recipients:
                recipients.append(email_part)

    # Fallback to organiser email if no attendees
    if not recipients:
        user_email = (booking.get("email") or "").strip()
        if user_email and "@" in user_email:
            recipients.append(user_email)

    # Ultimate fallback
    if not recipients:
        recipients = [r for r in config.REMINDER_TO if r and r != "team@example.com"]

    return recipients


def _get_cc_recipients(booking: dict) -> list[str]:
    """
    Get CC email list.
    Includes the default CC "kareemulla@mseducation.academy",
    the organiser's email (if attendee emails exist),
    and any custom CC emails parsed from booking.
    """
    cc_list = ["kareemulla@mseducation.academy"]

    # Add organiser's email to CC if attendee emails exist
    att_emails_str = (booking.get("attendee_emails") or "").strip()
    user_email = (booking.get("email") or "").strip()
    if att_emails_str and user_email and "@" in user_email:
        if user_email not in cc_list:
            cc_list.append(user_email)

    # Custom CC emails entered by user
    custom_cc = (booking.get("cc_emails") or "").strip()
    if custom_cc:
        for p in custom_cc.replace(";", ",").split(","):
            email_part = p.strip()
            if "<" in email_part and ">" in email_part:
                email_part = email_part.split("<")[-1].split(">")[0].strip()
            if email_part and "@" in email_part and email_part not in cc_list:
                cc_list.append(email_part)

    return cc_list


# ---------------------------------------------------------------------------
# Internal SMTP helper
# ---------------------------------------------------------------------------

def _send_via_smtp(msg: MIMEMultipart, envelope_recipients=None) -> bool:
    """
    Send an already-composed MIMEMultipart message via SMTP.
    Supports STARTTLS (Gmail, Outlook port 587) and SSL (port 465).
    Returns True on success, False on failure.
    """
    if not envelope_recipients:
        envelope_recipients = [msg["To"]]

    try:
        if config.SMTP_USE_TLS:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(
                    config.SMTP_USER,
                    envelope_recipients,
                    msg.as_string()
                )
        else:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(
                    config.SMTP_USER,
                    envelope_recipients,
                    msg.as_string()
                )
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "[Email] Authentication failed. Check SMTP_USER / SMTP_PASSWORD in config.py. "
            "For Gmail, use an App Password (not your login password)."
        )
        return False
    except smtplib.SMTPException as exc:
        logger.error("[Email] SMTP error: %s", exc)
        return False
    except Exception as exc:
        logger.error("[Email] Unexpected error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# HTML Helpers
# ---------------------------------------------------------------------------

def _render_teams_block_html(url: str, mid: str = "", passcode: str = "") -> str:
    """Generate HTML block for Microsoft Teams join link."""
    if not url:
        return ""

    id_passcode_html = ""
    if mid:
        pass_snippet = f"<br/><strong>Passcode:</strong> {passcode}" if passcode else ""
        id_passcode_html = f"""
        <div style="font-size:13px;color:#475569;margin-top:10px;line-height:1.5;font-family:Arial,sans-serif">
          <strong>Meeting ID:</strong> {mid} {pass_snippet}
        </div>
        """

    return f"""
    <div style="margin-top:24px;padding:20px;background:#f0f4ff;
                border:1px solid #dbeafe;border-radius:10px;text-align:center">
      <h3 style="margin:0 0 12px;font-size:15px;color:#1e40af;font-family:Arial,sans-serif;font-weight:700">
        💻 Microsoft Teams Online Meeting
      </h3>
      <a href="{url}" target="_blank"
         style="display:inline-block;padding:11px 24px;background:#4f46e5;
                color:#ffffff;text-decoration:none;border-radius:6px;
                font-weight:600;font-size:14px;box-shadow:0 2px 4px rgba(79,70,229,0.25)">
        Join Teams Meeting
      </a>
      {id_passcode_html}
    </div>
    """


def _render_details_table_html(rows: list[tuple[str, str]]) -> str:
    """Render a clean key-value table in HTML."""
    rows_html = ""
    for i, (label, val) in enumerate(rows):
        bg = "#f8fafc" if i % 2 == 0 else "#ffffff"
        rows_html += f"""
        <tr style="background:{bg};border-bottom:1px solid #e2e8f0;">
          <td style="padding:10px 14px;font-weight:600;color:#475569;width:150px;vertical-align:top;">{label}</td>
          <td style="padding:10px 14px;color:#1e293b;font-weight:500;">{val}</td>
        </tr>
        """
    return f"""
    <table cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;width:100%;font-size:14px;
                  border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
      {rows_html}
    </table>
    """


# ---------------------------------------------------------------------------
# 1. Booking Confirmation Email
# ---------------------------------------------------------------------------

def send_confirmation(booking: dict) -> bool:
    """
    Send an immediate confirmation email right after a booking is created.
    Returns True on success, False on failure.
    """
    if not config.EMAIL_ENABLED:
        logger.info(
            "[Email] EMAIL_ENABLED=False — skipping confirmation for booking %s",
            booking.get("id")
        )
        return False

    meeting_mode_raw = str(booking.get("meeting_mode", "") or "offline").strip().lower()
    is_online = (meeting_mode_raw == "online")
    meeting_mode_display = "Online" if is_online else "Offline"

    room_display = _get_room_display(booking.get("room", ""), include_floor=True)
    title = (booking.get("title") or "").strip()
    organizer = (booking.get("booked_by") or "").strip()
    formatted_date = _format_date(booking.get("date"))
    start_12h = _format_time_12h(booking.get("start_time"))
    end_12h = _format_time_12h(booking.get("end_time"))
    time_display = f"{start_12h} – {end_12h} (12 hour clock)" if start_12h and end_12h else f"{start_12h} – {end_12h}"

    venue, purpose = _extract_venue_and_purpose(booking)
    attendees = (booking.get("attendees") or "").strip()
    teams_url, mid, passcode = _get_teams_link_details(booking)

    # ----- Plain text -----
    plain_lines = [
        "✅ Meeting Confirmed",
        "Please find the meeting details as below:",
        f"Room: {room_display}",
        f"Meeting Mode: {meeting_mode_display}",
        f"Title: {title}",
        f"Meeting Organizer: {organizer}",
        f"Date: {formatted_date}",
        f"Time: {time_display}",
    ]
    if is_online and venue:
        plain_lines.append(f"Attendees Venue (Only for Online meeting): {venue}")
    if attendees:
        plain_lines.append(f"Attendees: {attendees}")
    if purpose:
        plain_lines.append(f"Purpose: {purpose}")

    if is_online and teams_url:
        plain_lines.append("")
        plain_lines.append("💻 Microsoft Teams Online Meeting")
        plain_lines.append(f"[Join Teams Meeting]({teams_url})")
        if mid:
            plain_lines.append(f"Meeting ID: {mid}")
        if passcode:
            plain_lines.append(f"Passcode: {passcode}")

    plain = "\n".join(plain_lines) + "\n"

    # ----- HTML Table Rows -----
    table_rows = [
        ("Room", room_display),
        ("Meeting Mode", meeting_mode_display),
        ("Title", title),
        ("Meeting Organizer", organizer),
        ("Date", formatted_date),
        ("Time", time_display),
    ]
    if is_online and venue:
        table_rows.append(("Attendees Venue (Only for Online meeting)", venue))
    if attendees:
        table_rows.append(("Attendees", attendees))
    if purpose:
        table_rows.append(("Purpose", purpose))

    table_html = _render_details_table_html(table_rows)
    teams_html = _render_teams_block_html(teams_url, mid, passcode) if (is_online and teams_url) else ""

    # ----- HTML -----
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Meeting Confirmed</title>
    </head>
    <body style="font-family:Arial,Helvetica,sans-serif;background:#f8fafc;margin:0;padding:24px 0;">
      <div style="max-width:540px;margin:0 auto;background:#ffffff;border-radius:12px;
                  overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);border:1px solid #e2e8f0;">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#4f46e5,#4338ca);padding:26px 30px;">
          <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:700;">✅ Meeting Confirmed</h1>
          <p style="margin:6px 0 0;color:#e0e7ff;font-size:14px;">
            Please find the meeting details as below:
          </p>
        </div>
        <!-- Body -->
        <div style="padding:26px 30px;">
          {table_html}
          {teams_html}
        </div>
        <!-- Footer -->
        <div style="padding:16px 30px;background:#f8fafc;font-size:12px;color:#94a3b8;
                    text-align:center;border-top:1px solid #e2e8f0;">
          Meeting Management System
        </div>
      </div>
    </body>
    </html>
    """

    recipients = _get_recipients(booking)
    cc_list = _get_cc_recipients(booking)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"✅ Meeting Confirmed: {title} — {formatted_date} at {start_12h}"
    organiser_name = organizer
    organiser_email = (booking.get("email") or "").strip()
    msg["From"] = config.SMTP_FROM
    if organiser_email:
        if organiser_name:
            msg["Reply-To"] = f'"{organiser_name}" <{organiser_email}>'
        else:
            msg["Reply-To"] = organiser_email

    msg["To"] = ", ".join(recipients)
    msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    envelope_recipients = list(recipients)
    for cc_addr in cc_list:
        if cc_addr not in envelope_recipients:
            envelope_recipients.append(cc_addr)

    success = _send_via_smtp(msg, envelope_recipients)
    if success:
        logger.info("[Email] Confirmation sent to %s (CC: %s) for booking %s", recipients, cc_list, booking.get("id"))
    else:
        logger.error("[Email] Failed to send confirmation to %s (CC: %s)", recipients, cc_list)
    return success


# ---------------------------------------------------------------------------
# 2. Meeting Reminder Email (15 minutes before)
# ---------------------------------------------------------------------------

def send_reminder(booking: dict) -> bool:
    """
    Send a reminder email N minutes before a meeting (N = REMINDER_MINUTES_BEFORE).
    Differentiates between Online and Offline meeting drafts.
    Returns True on success, False on failure.
    """
    if not config.EMAIL_ENABLED:
        logger.info(
            "[Email] EMAIL_ENABLED=False — skipping reminder for booking %s",
            booking.get("id")
        )
        return False

    mins = config.REMINDER_MINUTES_BEFORE
    meeting_mode_raw = str(booking.get("meeting_mode", "") or "offline").strip().lower()
    is_online = (meeting_mode_raw == "online")
    meeting_mode_display = "Online" if is_online else "Offline"

    room_display = _get_room_display(booking.get("room", ""), include_floor=True)
    title = (booking.get("title") or "").strip()
    organizer = (booking.get("booked_by") or "").strip()
    formatted_date = _format_date(booking.get("date"))
    start_12h = _format_time_12h(booking.get("start_time"))
    end_12h = _format_time_12h(booking.get("end_time"))
    time_display = f"{start_12h} – {end_12h} (12 hour clock)" if is_online else f"{start_12h} – {end_12h}"

    venue, purpose = _extract_venue_and_purpose(booking)
    attendees = (booking.get("attendees") or "").strip()
    teams_url, mid, passcode = _get_teams_link_details(booking)

    if is_online:
        # ---------------- ONLINE REMINDER ----------------
        subject = f"⏰ Reminder !! (Online meeting): {title} starts in {mins} Minutes"

        plain_lines = [
            "⏰ Reminder !! (Online meeting)",
            f"Your meeting starts in {mins} Minutes",
            "",
            f"Title: {title}",
            f"Meeting Mode: {meeting_mode_display}",
            f"Meeting Organizer: {organizer}",
            f"Date: {formatted_date}",
            f"Time: {time_display}",
        ]
        if venue:
            plain_lines.append(f"Attendees Venue: {venue}")
        if attendees:
            plain_lines.append(f"Attendees: {attendees}")
        if purpose:
            plain_lines.append(f"Purpose: {purpose}")

        if teams_url:
            plain_lines.append("")
            plain_lines.append("💻 Microsoft Teams Online Meeting")
            plain_lines.append(f"[Join Teams Meeting]({teams_url})")
            if mid:
                plain_lines.append(f"Meeting ID: {mid}")
            if passcode:
                plain_lines.append(f"Passcode: {passcode}")

        plain = "\n".join(plain_lines) + "\n"

        table_rows = [
            ("Title", title),
            ("Meeting Mode", meeting_mode_display),
            ("Meeting Organizer", organizer),
            ("Date", formatted_date),
            ("Time", time_display),
        ]
        if venue:
            table_rows.append(("Attendees Venue", venue))
        if attendees:
            table_rows.append(("Attendees", attendees))
        if purpose:
            table_rows.append(("Purpose", purpose))

        table_html = _render_details_table_html(table_rows)
        teams_html = _render_teams_block_html(teams_url, mid, passcode) if teams_url else ""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>Meeting Reminder</title>
        </head>
        <body style="font-family:Arial,Helvetica,sans-serif;background:#f8fafc;margin:0;padding:24px 0;">
          <div style="max-width:540px;margin:0 auto;background:#ffffff;border-radius:12px;
                      overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);border:1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:26px 30px;">
              <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:700;">
                ⏰ Reminder !! (Online meeting)
              </h1>
              <p style="margin:6px 0 0;color:#fef3c7;font-size:15px;font-weight:600;">
                Your meeting starts in {mins} Minutes
              </p>
            </div>
            <!-- Body -->
            <div style="padding:26px 30px;">
              {table_html}
              {teams_html}
            </div>
            <!-- Footer -->
            <div style="padding:16px 30px;background:#f8fafc;font-size:12px;color:#94a3b8;
                        text-align:center;border-top:1px solid #e2e8f0;">
              Meeting Management System
            </div>
          </div>
        </body>
        </html>
        """

    else:
        # ---------------- OFFLINE REMINDER ----------------
        subject = f"⏰ Reminder !! (Offline meeting): {title} — {room_display} starts in {mins} Minutes"

        plain_lines = [
            "⏰ Reminder !! (Offline meeting)",
            "",
            f"Your meeting starts in {mins} Minutes",
            "",
            f"Room: {room_display}",
            f"Title: {title}",
            f"Meeting Mode: {meeting_mode_display}",
            f"Meeting Organizer: {organizer}",
            f"Date: {formatted_date}",
            f"Time: {time_display}",
        ]
        if attendees:
            plain_lines.append(f"Attendees: {attendees}")
        if purpose:
            plain_lines.append(f"Purpose: {purpose}")

        plain_lines.append("")
        plain_lines.append("Kindly ensure your presence before time.")
        plain = "\n".join(plain_lines) + "\n"

        table_rows = [
            ("Room", room_display),
            ("Title", title),
            ("Meeting Mode", meeting_mode_display),
            ("Meeting Organizer", organizer),
            ("Date", formatted_date),
            ("Time", time_display),
        ]
        if attendees:
            table_rows.append(("Attendees", attendees))
        if purpose:
            table_rows.append(("Purpose", purpose))

        table_html = _render_details_table_html(table_rows)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>Meeting Reminder</title>
        </head>
        <body style="font-family:Arial,Helvetica,sans-serif;background:#f8fafc;margin:0;padding:24px 0;">
          <div style="max-width:540px;margin:0 auto;background:#ffffff;border-radius:12px;
                      overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);border:1px solid #e2e8f0;">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#f59e0b,#d97706);padding:26px 30px;">
              <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:700;">
                ⏰ Reminder !! (Offline meeting)
              </h1>
              <p style="margin:6px 0 0;color:#fef3c7;font-size:15px;font-weight:600;">
                Your meeting starts in {mins} Minutes
              </p>
            </div>
            <!-- Body -->
            <div style="padding:26px 30px;">
              {table_html}
              <div style="margin-top:20px;padding:14px 18px;background:#fef3c7;
                          border-left:4px solid #f59e0b;border-radius:6px;font-size:14px;
                          color:#92400e;font-weight:600;">
                📍 Kindly ensure your presence before time.
              </div>
            </div>
            <!-- Footer -->
            <div style="padding:16px 30px;background:#f8fafc;font-size:12px;color:#94a3b8;
                        text-align:center;border-top:1px solid #e2e8f0;">
              Meeting Management System
            </div>
          </div>
        </body>
        </html>
        """

    recipients = _get_recipients(booking)
    cc_list = _get_cc_recipients(booking)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    organiser_name = organizer
    organiser_email = (booking.get("email") or "").strip()
    msg["From"] = config.SMTP_FROM
    if organiser_email:
        if organiser_name:
            msg["Reply-To"] = f'"{organiser_name}" <{organiser_email}>'
        else:
            msg["Reply-To"] = organiser_email

    msg["To"] = ", ".join(recipients)
    msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    envelope_recipients = list(recipients)
    for cc_addr in cc_list:
        if cc_addr not in envelope_recipients:
            envelope_recipients.append(cc_addr)

    success = _send_via_smtp(msg, envelope_recipients)
    if success:
        logger.info("[Email] Reminder sent to %s (CC: %s) for booking %s", recipients, cc_list, booking.get("id"))
    else:
        logger.error("[Email] Failed to send reminder to %s (CC: %s)", recipients, cc_list)
    return success


# ---------------------------------------------------------------------------
# 3. Cancellation Email
# ---------------------------------------------------------------------------

def send_cancellation(booking: dict, cancelled_by: str = "") -> bool:
    """
    Send an email notifying attendees that a meeting has been cancelled.
    Returns True on success, False on failure.
    """
    if not config.EMAIL_ENABLED:
        logger.info(
            "[Email] EMAIL_ENABLED=False — skipping cancellation email for booking %s",
            booking.get("id")
        )
        return False

    meeting_mode_raw = str(booking.get("meeting_mode", "") or "offline").strip().lower()
    is_online = (meeting_mode_raw == "online")
    mode_text = "online" if is_online else "offline"
    meeting_mode_display = "Online" if is_online else "Offline"

    room_display = _get_room_display(booking.get("room", ""), include_floor=True)
    title = (booking.get("title") or "").strip()
    organizer = (booking.get("booked_by") or "").strip()
    formatted_date = _format_date(booking.get("date"))
    start_12h = _format_time_12h(booking.get("start_time"))
    end_12h = _format_time_12h(booking.get("end_time"))
    time_display = f"{start_12h} – {end_12h}"

    cancellation_actor = cancelled_by if cancelled_by else organizer
    venue, purpose = _extract_venue_and_purpose(booking)
    attendees = (booking.get("attendees") or "").strip()

    # Cancel message as per draft
    cancel_notice = (
        f"This is to inform you that {mode_text} meeting scheduled for {formatted_date} "
        f"at {start_12h} has been cancelled by the organizer ({cancellation_actor})."
    )

    # ----- Plain text -----
    plain_lines = [
        "🚫 Meeting Cancelled",
        "",
        cancel_notice,
        "",
        f"Room: {room_display}",
        f"Meeting Mode: {meeting_mode_display}",
        f"Title: {title}",
        f"Meeting Organizer: {organizer}",
        f"Date: {formatted_date}",
        f"Time: {time_display}",
    ]
    if is_online and venue:
        plain_lines.append(f"Attendees Venue: {venue}")
    if attendees:
        plain_lines.append(f"Attendees: {attendees}")
    if purpose:
        plain_lines.append(f"Purpose: {purpose}")

    plain = "\n".join(plain_lines) + "\n"

    # ----- HTML Table Rows -----
    table_rows = [
        ("Room", room_display),
        ("Meeting Mode", meeting_mode_display),
        ("Title", title),
        ("Meeting Organizer", organizer),
        ("Date", formatted_date),
        ("Time", time_display),
    ]
    if is_online and venue:
        table_rows.append(("Attendees Venue", venue))
    if attendees:
        table_rows.append(("Attendees", attendees))
    if purpose:
        table_rows.append(("Purpose", purpose))

    table_html = _render_details_table_html(table_rows)

    # ----- HTML -----
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Meeting Cancelled</title>
    </head>
    <body style="font-family:Arial,Helvetica,sans-serif;background:#f8fafc;margin:0;padding:24px 0;">
      <div style="max-width:540px;margin:0 auto;background:#ffffff;border-radius:12px;
                  overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);border:1px solid #e2e8f0;">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#ef4444,#dc2626);padding:26px 30px;">
          <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:700;">🚫 Meeting Cancelled</h1>
        </div>
        <!-- Body -->
        <div style="padding:26px 30px;">
          <div style="margin-bottom:22px;padding:14px 18px;background:#fef2f2;
                      border-left:4px solid #ef4444;border-radius:6px;font-size:14px;
                      color:#991b1b;line-height:1.5;">
            This is to inform you that <b>{mode_text}</b> meeting scheduled for <b>{formatted_date}</b>
            at <b>{start_12h}</b> has been cancelled by the organizer (<b>{cancellation_actor}</b>).
          </div>
          {table_html}
        </div>
        <!-- Footer -->
        <div style="padding:16px 30px;background:#f8fafc;font-size:12px;color:#94a3b8;
                    text-align:center;border-top:1px solid #e2e8f0;">
          Meeting Management System
        </div>
      </div>
    </body>
    </html>
    """

    recipients = _get_recipients(booking)
    cc_list = _get_cc_recipients(booking)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚫 Cancelled: {title} scheduled for {formatted_date} at {start_12h}"
    organiser_name = organizer
    organiser_email = (booking.get("email") or "").strip()
    msg["From"] = config.SMTP_FROM
    if organiser_email:
        if organiser_name:
            msg["Reply-To"] = f'"{organiser_name}" <{organiser_email}>'
        else:
            msg["Reply-To"] = organiser_email

    msg["To"] = ", ".join(recipients)
    msg["Cc"] = ", ".join(cc_list)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    envelope_recipients = list(recipients)
    for cc_addr in cc_list:
        if cc_addr not in envelope_recipients:
            envelope_recipients.append(cc_addr)

    success = _send_via_smtp(msg, envelope_recipients)
    if success:
        logger.info("[Email] Cancellation sent to %s (CC: %s) for booking %s", recipients, cc_list, booking.get("id"))
    else:
        logger.error("[Email] Failed to send cancellation to %s (CC: %s)", recipients, cc_list)
    return success
