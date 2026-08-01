import os
import sys
from datetime import datetime, date

# Add the directory to the path so we can import local modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import excel_db
import email_reminder

def send_future_emails():
    print("Loading active future bookings...")
    bookings = excel_db.get_bookings()
    today_dt = date.today()
    now_str = datetime.now().strftime("%H:%M")
    
    future_bookings = []
    for b in bookings:
        if b.get("status") != "active":
            continue
        try:
            b_date = datetime.strptime(b["date"], "%Y-%m-%d").date()
        except Exception:
            continue
            
        # Is it in the future?
        if b_date > today_dt:
            future_bookings.append(b)
        elif b_date == today_dt:
            if b["end_time"] >= now_str:
                future_bookings.append(b)
                
    if not future_bookings:
        print("No future bookings found.")
        return
        
    print(f"Found {len(future_bookings)} future bookings.")
    print("Sending confirmation emails for these bookings...")
    for b in future_bookings:
        try:
            success = email_reminder.send_confirmation(b)
            title_clean = b['title'].encode('ascii', 'ignore').decode('ascii')
            room_clean = b['room'].encode('ascii', 'ignore').decode('ascii')
            if success:
                print(f"[SUCCESS] Sent confirmation email for booking '{title_clean}' ({room_clean})")
            else:
                print(f"[FAILED] Failed to send confirmation email for booking '{title_clean}' ({room_clean})")
        except Exception as e:
            print(f"[ERROR] Exception sending email: {e}")

if __name__ == '__main__':
    send_future_emails()
