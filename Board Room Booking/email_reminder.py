# =============================================================================
# email_reminder.py — Email Sender (Confirmations + Reminders)
# =============================================================================
# Two types of emails are sent:
#   1. Booking Confirmation — immediately after a new booking is created
#   2. Meeting Reminder     — 30 minutes before a meeting starts (configurable)
#
# Both Gmail and Outlook / Office 365 are supported.
# Set credentials in config.py — not here.
# =============================================================================

import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config

logger = logging.getLogger(__name__)


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
    
    # Add organiser's email to CC if attendee emails exist (so organiser is CC'd on their own meeting sent to attendees)
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
# Internal SMTP helper — shared by both email types
# ---------------------------------------------------------------------------

def _send_via_smtp(msg: MIMEMultipart) -> bool:
    """
    Send an already-composed MIMEMultipart message via SMTP.
    Supports STARTTLS (Gmail, Outlook port 587) and SSL (port 465).
    Returns True on success, False on failure.
    """
    try:
        if config.SMTP_USE_TLS:
            # STARTTLS — works for Gmail (smtp.gmail.com:587)
            #             and Outlook (smtp.office365.com:587)
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT,
                              timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(
                    config.SMTP_FROM,
                    config.REMINDER_TO,
                    msg.as_string()
                )
        else:
            # SSL — port 465
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                                  timeout=15) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(
                    config.SMTP_FROM,
                    config.REMINDER_TO,
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
# Shared HTML email layout helper
# ---------------------------------------------------------------------------

def _build_booking_table(booking: dict) -> tuple[str, str]:
    """
    Return (plain_text, html_string) for a booking's key details.
    Used in both confirmation and reminder emails.
    """
    attendees = (booking.get("attendees") or "").strip()
    desc = (booking.get("description") or "").strip()
    meeting_mode = str(booking.get("meeting_mode", "") or "offline").strip().lower()
    meeting_link = str(booking.get("meeting_link", "") or "").strip()

    plain = (
        f"  Room      : {booking['room']}\n"
        f"  Meeting Mode: {meeting_mode.capitalize()}\n"
        f"  Title     : {booking['title']}\n"
        f"  Booked by : {booking['booked_by']}\n"
        + (f"  Attendees : {attendees}\n" if attendees else "")
        + (f"  Purpose   : {desc}\n" if desc else "")
        + f"  Date      : {booking['date']}\n"
        f"  Time      : {booking['start_time']} – {booking['end_time']}\n"
    )

    teams_details_plain = ""
    teams_details_html = ""

    if meeting_mode == "online" and meeting_link:
        parts = meeting_link.split("|")
        url = parts[0]
        mid = parts[1] if len(parts) > 1 else ""
        passcode = parts[2] if len(parts) > 2 else ""

        # Filter out placeholder values so they don't show up in the email
        if mid.strip().lower() == "meeting-join" or passcode.strip().lower() == "microsoft teams":
            mid = ""
            passcode = ""

        id_passcode_plain = f"  Meeting ID : {mid}\n  Passcode   : {passcode}\n" if mid else ""
        teams_details_plain = (
            f"\n💻 Microsoft Teams Meeting:\n"
            f"  Join Link  : {url}\n"
            + id_passcode_plain
        )

        id_passcode_html = f"""
              <div style="font-size:13px;color:#475569;line-height:1.5;font-family:Arial,sans-serif">
                <strong>Meeting ID:</strong> {mid} <br/>
                <strong>Passcode:</strong> {passcode}
              </div>
        """ if mid else ""

        teams_details_html = f"""
        <div style="margin-top:20px;padding:18px;background:#f0f4ff;
                    border:1px solid #dbeafe;border-radius:8px;text-align:center">
          <h3 style="margin:0 0 10px;font-size:15px;color:#1e40af;font-family:Arial,sans-serif">💻 Microsoft Teams Online Meeting</h3>
          <a href="{url}" target="_blank"
             style="display:inline-block;padding:10px 20px;background:#4f46e5;
                    color:#ffffff;text-decoration:none;border-radius:6px;
                    font-weight:600;font-size:14px;margin-bottom:12px;
                    box-shadow:0 2px 4px rgba(79,70,229,0.2)">
            Join Teams Meeting
          </a>
          {id_passcode_html}
        </div>
        """

    plain += teams_details_plain

    attendees_row = (
        f"""
        <tr>
          <td style="padding:10px 14px;font-weight:600;color:#555">Attendees</td>
          <td style="padding:10px 14px">{attendees}</td>
        </tr>"""
        if attendees
        else ""
    )

    desc_row = (
        f"""
        <tr style="background:#f4f4f8">
          <td style="padding:10px 14px;font-weight:600;color:#555">Purpose</td>
          <td style="padding:10px 14px">{desc}</td>
        </tr>"""
        if desc
        else ""
    )

    html = f"""
      <table cellpadding="8" cellspacing="0"
             style="border-collapse:collapse;width:100%;max-width:480px;
                    font-size:14px;color:#333">
        <tr style="background:#f4f4f8">
          <td style="padding:10px 14px;font-weight:600;color:#555;width:110px">Room</td>
          <td style="padding:10px 14px;font-weight:700;color:#1a1a2e">{booking['room']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;font-weight:600;color:#555">Meeting Mode</td>
          <td style="padding:10px 14px;font-weight:600;color:#1a1a2e">{meeting_mode.capitalize()}</td>
        </tr>
        <tr style="background:#f4f4f8">
          <td style="padding:10px 14px;font-weight:600;color:#555">Title</td>
          <td style="padding:10px 14px">{booking['title']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;font-weight:600;color:#555">Booked by</td>
          <td style="padding:10px 14px">{booking['booked_by']}</td>
        </tr>
        {attendees_row}
        {desc_row}
        <tr style="background:#f4f4f8">
          <td style="padding:10px 14px;font-weight:600;color:#555">Date</td>
          <td style="padding:10px 14px">{booking['date']}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;font-weight:600;color:#555">Time</td>
          <td style="padding:10px 14px">
            {booking['start_time']} – {booking['end_time']}
          </td>
        </tr>
      </table>
      {teams_details_html}
    """
    return plain, html


# ---------------------------------------------------------------------------
# 1. Booking Confirmation Email
# ---------------------------------------------------------------------------

def send_confirmation(booking: dict) -> bool:
    """
    Send an immediate confirmation email right after a booking is created.
    Returns True on success, False on failure.
    EMAIL_ENABLED in config.py must be True, otherwise this is a no-op.
    """
    if not config.EMAIL_ENABLED:
        logger.info(
            "[Email] EMAIL_ENABLED=False — skipping confirmation for booking %s",
            booking.get("id")
        )
        return False

    plain_table, html_table = _build_booking_table(booking)

    # ----- Plain text -----
    plain = (
        f"✅ Booking Confirmed\n"
        f"-------------------\n"
        f"{plain_table}\n"
        f"Your booking is confirmed. You will receive a reminder "
        f"{config.REMINDER_MINUTES_BEFORE} minutes before the meeting.\n"
    )

    # ----- HTML -----
    html = f"""
    <html>
    <body style="font-family:Arial,Helvetica,sans-serif;background:#f9f9f9;
                 margin:0;padding:0">
      <div style="max-width:520px;margin:32px auto;background:#fff;
                  border-radius:12px;overflow:hidden;
                  box-shadow:0 4px 20px rgba(0,0,0,.08)">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#6366f1,#4f52e0);
                    padding:28px 32px">
          <h1 style="margin:0;font-size:22px;color:#fff">✅ Booking Confirmed</h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,.8);font-size:14px">
            Your meeting room has been reserved.
          </p>
        </div>
        <!-- Body -->
        <div style="padding:28px 32px">
          {html_table}
          <p style="margin-top:20px;font-size:13px;color:#888">
            You will receive a reminder email
            <strong>{config.REMINDER_MINUTES_BEFORE} minutes</strong>
            before the meeting starts.
          </p>
        </div>
        <!-- Footer -->
        <div style="padding:16px 32px;background:#f4f4f8;
                    font-size:12px;color:#aaa;text-align:center">
          Meeting Management System System
        </div>
      </div>
    </body>
    </html>
    """

    recipients = _get_recipients(booking)
    cc_list = _get_cc_recipients(booking)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"✅ Confirmed: {booking['title']} — {booking['room']} "
        f"on {booking['date']} at {booking['start_time']}"
    )
    organiser_name = booking.get("booked_by", "").strip()
    organiser_email = (booking.get("email") or "").strip()
    msg["From"] = config.SMTP_FROM
    if organiser_email:
        if organiser_name:
            msg["Reply-To"] = f'"{organiser_name}" <{organiser_email}>'
        else:
            msg["Reply-To"] = organiser_email

    msg["To"]   = ", ".join(recipients)
    msg["Cc"]   = ", ".join(cc_list)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    envelope_recipients = list(recipients)
    for cc_addr in cc_list:
        if cc_addr not in envelope_recipients:
            envelope_recipients.append(cc_addr)

    try:
        if config.SMTP_USE_TLS:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_USER, envelope_recipients, msg.as_string())
        else:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_USER, envelope_recipients, msg.as_string())
        logger.info("[Email] Confirmation sent to %s (CC: %s) for booking %s", recipients, cc_list, booking.get("id"))
        return True
    except Exception as exc:
        logger.error("[Email] Failed to send confirmation to %s (CC: %s): %s", recipients, cc_list, exc)
        return False


# ---------------------------------------------------------------------------
# 2. Meeting Reminder Email (30 minutes before)
# ---------------------------------------------------------------------------

def send_reminder(booking: dict) -> bool:
    """
    Send a reminder email N minutes before a meeting (N = REMINDER_MINUTES_BEFORE).
    Returns True on success, False on failure.
    EMAIL_ENABLED in config.py must be True, otherwise this is a no-op.
    """
    if not config.EMAIL_ENABLED:
        logger.info(
            "[Email] EMAIL_ENABLED=False — skipping reminder for booking %s",
            booking.get("id")
        )
        return False

    plain_table, html_table = _build_booking_table(booking)
    mins = config.REMINDER_MINUTES_BEFORE

    # ----- Plain text -----
    plain = (
        f"⏰ Meeting Reminder — Starting in {mins} Minutes\n"
        f"------------------------------------------------\n"
        f"{plain_table}\n"
        f"Please make your way to the room now.\n"
    )

    # ----- HTML -----
    html = f"""
    <html>
    <body style="font-family:Arial,Helvetica,sans-serif;background:#f9f9f9;
                 margin:0;padding:0">
      <div style="max-width:520px;margin:32px auto;background:#fff;
                  border-radius:12px;overflow:hidden;
                  box-shadow:0 4px 20px rgba(0,0,0,.08)">
        <!-- Header -->
        <div style="background:linear-gradient(135deg,#f59e0b,#d97706);
                    padding:28px 32px">
          <h1 style="margin:0;font-size:22px;color:#fff">
            ⏰ Starting in {mins} Minutes
          </h1>
          <p style="margin:6px 0 0;color:rgba(255,255,255,.85);font-size:14px">
            Your meeting is about to begin — please head to the room.
          </p>
        </div>
        <!-- Body -->
        <div style="padding:28px 32px">
          {html_table}
          <div style="margin-top:20px;padding:14px 18px;
                      background:#fff8ec;border-left:4px solid #f59e0b;
                      border-radius:6px;font-size:14px;color:#92400e">
            🚀 <strong>Please make your way to {booking['room']} now.</strong>
          </div>
        </div>
        <!-- Footer -->
        <div style="padding:16px 32px;background:#f4f4f8;
                    font-size:12px;color:#aaa;text-align:center">
          Meeting Management System System
        </div>
      </div>
    </body>
    </html>
    """

    recipients = _get_recipients(booking)
    cc_list = _get_cc_recipients(booking)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"⏰ Reminder ({mins} min): {booking['title']} — "
        f"{booking['room']} at {booking['start_time']}"
    )
    organiser_name = booking.get("booked_by", "").strip()
    organiser_email = (booking.get("email") or "").strip()
    msg["From"] = config.SMTP_FROM
    if organiser_email:
        if organiser_name:
            msg["Reply-To"] = f'"{organiser_name}" <{organiser_email}>'
        else:
            msg["Reply-To"] = organiser_email

    msg["To"]   = ", ".join(recipients)
    msg["Cc"]   = ", ".join(cc_list)
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))

    envelope_recipients = list(recipients)
    for cc_addr in cc_list:
        if cc_addr not in envelope_recipients:
            envelope_recipients.append(cc_addr)

    try:
        if config.SMTP_USE_TLS:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_USER, envelope_recipients, msg.as_string())
        else:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.SMTP_USER, envelope_recipients, msg.as_string())
        logger.info("[Email] Reminder sent to %s (CC: %s) for booking %s", recipients, cc_list, booking.get("id"))
        return True
    except Exception as exc:
        logger.error("[Email] Failed to send reminder to %s (CC: %s): %s", recipients, cc_list, exc)
        return False
