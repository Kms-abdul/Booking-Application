# Meeting Management System — Setup & Run Guide

A lightweight, installable web app for booking board meeting rooms.
No database, no login — just Python + an Excel file.

---

## Quick Start (Windows)

```bash
# 1. Open a terminal in this folder
# 2. Install dependencies (one time only)
pip install -r requirements.txt

# 3. Start the app
python app.py
```

Open your browser at: **http://localhost:4000**

---

## Configuration

All settings are in **`config.py`** — open it in Notepad and edit:

| Setting | What it does |
|---|---|
| `ROOMS` | Add/remove/rename rooms and their colors |
| `REMINDER_MINUTES_BEFORE` | How many minutes before a meeting to send the email reminder |
| `EMAIL_ENABLED` | Set to `True` to activate email reminders |
| `SMTP_*` settings | Your email server details (see comments in config.py) |
| `FLASK_PORT` | Change the port if 4000 is in use |

---

## Data File

The Excel file **`data/bookings.xlsx`** is created automatically on first run.
- It has three sheets: **Bookings**, **Rooms**, **ReminderLog**
- You can open it in Excel to view or manually edit data
- ⚠️ **Do not have it open in Excel while the server is running** — this will cause a write error

Daily backups are saved in `data/backups/bookings_YYYY-MM-DD.xlsx`.

---

## Email Reminders

1. Open `config.py`
2. Set `EMAIL_ENABLED = True`
3. Fill in `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, and `REMINDER_TO`
4. **Gmail**: Use an [App Password](https://myaccount.google.com/apppasswords), not your login password

---

## Installing as a Mobile App (PWA)

The app can be installed on phones and desktops like a native app:

**Android / Chrome**:
1. Open the app in Chrome
2. Tap the three-dot menu → "Add to Home Screen" / "Install app"

**Desktop Chrome**:
1. Look for the install icon (⊕) in the address bar
2. Click → "Install"

> **Note**: PWA install requires either `localhost` or HTTPS.
> If you want it installable from other devices on your Wi-Fi network,
> use a tool like [Caddy](https://caddyserver.com/) or [ngrok](https://ngrok.com/)
> to add HTTPS. See the plan document for details.

---

## Accessing from Other Devices on the Same Network

The server binds to `0.0.0.0` by default, so any device on the same Wi-Fi can use it.
Find your PC's local IP address:

```
ipconfig   # look for "IPv4 Address", e.g. 192.168.1.10
```

Then open `http://192.168.1.10:4000` on any phone or tablet.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| Port already in use | Change `FLASK_PORT` in config.py |
| Excel file locked | Close the file in Excel, then restart the server |
| Emails not sending | Check SMTP settings and ensure `EMAIL_ENABLED = True` |
| PWA install not appearing | Ensure you're on `localhost` or HTTPS |
