import { state } from './state.js';
import { showToast } from './utils.js';
import { showFieldError, initDateDefaults, showTab } from './ui.js';
import { loadStatus } from './rooms.js';

export function populateBookForm() {
  const sel = document.getElementById('book-room');
  sel.innerHTML = ''; 

  const floors = [...new Set(state.rooms.map(r => r.floor))].sort((a, b) => a - b);
  floors.forEach(f => {
    const grp = document.createElement('optgroup');
    grp.label = `Floor ${f}`;
    state.rooms.filter(r => r.floor === f).forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = r.name;
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  });
}

export async function verifyAdmin() {
  const username = document.getElementById('book-username').value.trim();
  const password = document.getElementById('book-password').value;
  const errorEl = document.getElementById('form-error');
  const btn = document.getElementById('admin-verify-btn');
  const label = btn ? btn.querySelector('.btn-label') : null;
  const spinner = btn ? btn.querySelector('.btn-spinner') : null;

  if (errorEl) errorEl.classList.add('hidden');

  if (!username || !password) {
    showFieldError(errorEl, 'Please enter admin username and password.');
    return;
  }

  if (btn) btn.disabled = true;
  if (label) label.classList.add('hidden');
  if (spinner) spinner.classList.remove('hidden');

  try {
    const res = await fetch('/api/verify-admin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();

    if (!data.ok) {
      showFieldError(errorEl, data.error || 'Verification failed.');
      return;
    }

    document.getElementById('booking-form').classList.remove('hidden');
    document.getElementById('admin-login-section').classList.add('hidden');
    showToast('✅ Admin verified. You can now submit the booking.', 'success');
  } catch (err) {
    showFieldError(errorEl, 'Unable to verify admin — please try again.');
  } finally {
    if (btn) btn.disabled = false;
    if (label) label.classList.remove('hidden');
    if (spinner) spinner.classList.add('hidden');
  }
}

export async function submitBooking(e) {
  e.preventDefault();
  const errorEl = document.getElementById('form-error');
  const btn = document.getElementById('book-submit');
  const label = btn ? btn.querySelector('.btn-label') : null;
  const spinner = btn ? btn.querySelector('.btn-spinner') : null;

  if (errorEl) errorEl.classList.add('hidden');

  const emailEl = document.getElementById('book-email');
  const attEl = document.getElementById('book-attendees');
  const attEmailsEl = document.getElementById('book-attendees-emails');
  const modeEl = document.getElementById('book-mode');
  const ccEmailsEl = document.getElementById('book-cc-emails');
  const username = document.getElementById('book-username').value.trim();
  const password = document.getElementById('book-password').value;

  const payload = {
    room: document.getElementById('book-room').value,
    meeting_mode: (modeEl ? modeEl.value : 'offline'),
    title: document.getElementById('book-title').value.trim(),
    booked_by: document.getElementById('book-name').value.trim(),
    attendees: (attEl ? attEl.value : '').trim(),
    attendee_emails: (attEmailsEl ? attEmailsEl.value : '').trim(),
    cc_emails: (ccEmailsEl ? ccEmailsEl.value : '').trim(),
    email: (emailEl ? emailEl.value : '').trim(),
    date: document.getElementById('book-date').value,
    start_time: document.getElementById('book-start').value,
    end_time: document.getElementById('book-end').value,
    username: username,
    password: password,
    description: (document.getElementById('book-description') ? document.getElementById('book-description').value : '').trim(),
  };

  if (!payload.room) return showFieldError(errorEl, 'Please select a room.');
  if (!payload.title) return showFieldError(errorEl, 'Meeting title is required.');
  if (!payload.booked_by) return showFieldError(errorEl, 'Your name is required.');
  if (!payload.email) return showFieldError(errorEl, 'Organiser\'s email is required.');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)) {
    return showFieldError(errorEl, 'Please enter a valid organiser email address.');
  }
  if (!payload.date) return showFieldError(errorEl, 'Date is required.');
  if (!payload.start_time) return showFieldError(errorEl, 'Start time is required.');
  if (!payload.end_time) return showFieldError(errorEl, 'End time is required.');
  if (payload.start_time >= payload.end_time) {
    return showFieldError(errorEl, 'End time must be after start time.');
  }

  if (btn) btn.disabled = true;
  if (label) label.classList.add('hidden');
  if (spinner) spinner.classList.remove('hidden');

  try {
    const res = await fetch('/api/bookings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
      showToast(`✅ Booked! ${payload.room} on ${payload.date} from ${payload.start_time}–${payload.end_time}`, 'success');
      document.getElementById('booking-form').reset();
      document.querySelectorAll('#booking-form textarea').forEach(textarea => {
        textarea.style.height = '44px';
      });
      document.getElementById('book-username').value = '';
      document.getElementById('book-password').value = '';
      document.getElementById('booking-form').classList.add('hidden');
      document.getElementById('admin-login-section').classList.remove('hidden');
      initDateDefaults();
      showTab('corridor');
      loadStatus();
    } else {
      showFieldError(errorEl, data.error || 'Booking failed.');
    }
  } catch (err) {
    showFieldError(errorEl, 'Network error — please try again.');
  } finally {
    if (btn) btn.disabled = false;
    if (label) label.classList.remove('hidden');
    if (spinner) spinner.classList.add('hidden');
  }
}
