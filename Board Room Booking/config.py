# =============================================================================
# config.py — Meeting Management System App Configuration
# =============================================================================
# Edit this file to change rooms, working hours, email settings, etc.
# No Python knowledge required for most changes below.
# =============================================================================

import os

# --- Rooms -------------------------------------------------------------------
# Add or remove rooms here. Each room has a name and a display color.
# Colors are in hex format (#RRGGBB).
ROOMS = [
    {"name": "Multazim - CEO Conference Room",  "color": "#6366f1", "floor":3, "teams_link": ""},   # Indigo
    {"name": "Muzdalifa - Ideation Room",   "color": "#10b981", "floor":3, "teams_link": ""},   # Emerald
    {"name": "Arafah - Ideation Room",  "color": "#f59e0b", "floor":3, "teams_link": ""},   # Golden
    {"name": "Mina - Ideation Room", "color": "#7faf52", "floor":3, "teams_link": ""},   # Grape
    {"name": "Ghulam Rasool Khan - Hall",  "color": "#32d2dd", "floor":3, "teams_link": ""},   # Cyan  
    {"name": "Dar-E-Arqam - Conference Room",  "color": "#ff0000", "floor":3, "teams_link": ""},   # Red    

    {"name": "Shaik Ahmed - Conference Room",  "color": "#6366f1", "floor":4, "teams_link": ""},   # Indigo
    {"name": "Nayeem - Discussion Room",   "color": "#10b981", "floor":4, "teams_link": ""},   # Emerald
    {"name": "Fazal - Discussion Room",  "color": "#f59e0b", "floor":4, "teams_link": ""},   # Golden

    {"name": "Mohammed Yousuf Hussain - Training Room",  "color": "#32d2dd", "floor":5, "teams_link": ""},   # Cyan  
    {"name": "AL-Ansar(Audit) - Conference Room",  "color": "#ff0000", "floor":5, "teams_link": ""},   # Red  

    # Online virtual rooms
    {"name": "BADAR - CHAIRMAN'S OFFICE",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "QUBA   - VICE CHAIRPERSON'S OFFICE",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "AQSA  - MANAGING DIRECTOR'S OFFICE",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "HUDAIBIA - MANAGING DIRECTOR'S OFFICE",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "Work Station -1",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "Work Station -2",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "Work Station -3",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
    {"name": "Work Station -4",  "color": "#4338ca", "floor": "Online", "teams_link": ""},
]

# --- Working Hours -----------------------------------------------------------
# These are used for display only (the app doesn't block bookings outside them).
WORK_HOUR_START = 8    # 8 AM
WORK_HOUR_END   = 20   # 8 PM

# --- Excel File --------------------------------------------------------------
# Path to the Excel file used as the database.
# The file and its parent folder are created automatically on first run.
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
EXCEL_PATH  = os.path.join(DATA_DIR, "bookings.xlsx")

# Daily backup copies are kept here (one file per day).
BACKUP_DIR  = os.path.join(DATA_DIR, "backups")

# Lock file used to prevent simultaneous writes to the Excel file.
LOCK_PATH   = os.path.join(DATA_DIR, "bookings.lock")

# --- Reminder Settings -------------------------------------------------------
# How many minutes BEFORE a meeting the reminder email is sent.
REMINDER_MINUTES_BEFORE = 30

# How often (in seconds) the background worker checks for upcoming reminders.
# 300 = check every 5 minutes (clean logs)
# 1800 = check every 30 minutes
SCHEDULER_INTERVAL_SECONDS = 300

# --- Time Zone ---------------------------------------------------------------
# All booking times and scheduler checks use the SERVER'S local clock.
# Make sure the machine running this app is set to the correct local timezone.
# Example: on Windows, set it via Settings → Time & Language → Date & Time.
# If you need to force a timezone, set the TZ environment variable before
# starting the app:  set TZ=Asia/Kolkata  (on Windows, use the system setting)

# --- Email / SMTP ------------------------------------------------------------
# Two types of emails are sent:
#   1. CONFIRMATION — immediately after a booking is created
#   2. REMINDER     — REMINDER_MINUTES_BEFORE minutes before the meeting starts
#
# Set EMAIL_ENABLED = True and fill in the SMTP fields to activate both.
#
# ── Gmail setup ──────────────────────────────────────────────────────────────
#   1. Enable 2-Step Verification at myaccount.google.com → Security
#   2. Go to myaccount.google.com → Security → App Passwords
#   3. Create an App Password for "Mail" and paste it as SMTP_PASSWORD below
#   4. Use your Gmail address for SMTP_USER and SMTP_FROM
#
#   SMTP_HOST     = "smtp.gmail.com"
#   SMTP_PORT     = 587
#   SMTP_USE_TLS  = True
#
# ── Outlook / Office 365 setup ───────────────────────────────────────────────
#   SMTP_HOST     = "smtp.office365.com"
#   SMTP_PORT     = 587
#   SMTP_USE_TLS  = True
#   SMTP_USER     = "you@yourdomain.com"
#   SMTP_PASSWORD = "your-outlook-password"
#   SMTP_FROM     = "you@yourdomain.com"
#
# ── Other providers (SSL on port 465) ────────────────────────────────────────
#   SMTP_PORT     = 465
#   SMTP_USE_TLS  = False   (uses SSL instead of STARTTLS)
# =============================================================================

EMAIL_ENABLED   = True
SMTP_HOST       = "smtp.office365.com"
SMTP_PORT       = 587
SMTP_USE_TLS    = True
SMTP_USER       = "assetmgmt@mseducation.academy"
SMTP_PASSWORD   = "ljqpwwwrqpgpjbgz"
SMTP_FROM       = "PMS System <assetmgmt@mseducation.academy>"

REMINDER_TO     = ["assetmgmt@mseducation.academy"]
 
# --- Flask Server ------------------------------------------------------------
FLASK_HOST  = "0.0.0.0"   # 0.0.0.0 = accessible from other devices on the same network
FLASK_PORT  = 4000
# Set DEBUG = False in production.
# WARNING: DEBUG = True causes Flask to reload, which starts the scheduler twice.
# The code in app.py already guards against this, but keep DEBUG = False
# when deploying.
FLASK_DEBUG = False

# --- Authentication ----------------------------------------------------------
# To prevent unauthorized users from booking or cancelling rooms,
# they must provide these credentials.
ADMIN_USERNAME = "admin" 
ADMIN_PASSWORD = "crbs"  
