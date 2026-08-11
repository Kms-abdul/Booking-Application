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

export async function verifyUser() {
  const username = document.getElementById('book-username').value.trim();
  const password = document.getElementById('book-password').value;
  const errorEl = document.getElementById('form-error');
  const btn = document.getElementById('admin-verify-btn');
  const label = btn ? btn.querySelector('.btn-label') : null;
  const spinner = btn ? btn.querySelector('.btn-spinner') : null;

  if (errorEl) errorEl.classList.add('hidden');

  if (!username || !password) {
    showFieldError(errorEl, 'Please enter username and PIN.');
    return;
  }

  if (btn) btn.disabled = true;
  if (label) label.classList.add('hidden');
  if (spinner) spinner.classList.remove('hidden');

  try {
    const res = await fetch('/api/verify-user', {
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
    
    // Store role and credentials on the form dataset so we can use them
    const form = document.getElementById('booking-form');
    form.dataset.role = data.role;
    form.dataset.username = username;
    form.dataset.password = password;

    const emailEl = document.getElementById('book-email');
    if (emailEl) {
      if (data.email) {
        emailEl.value = data.email;
        emailEl.readOnly = true;
        emailEl.style.backgroundColor = '#f3f4f6';
      } else {
        emailEl.value = '';
        emailEl.readOnly = false;
        emailEl.style.backgroundColor = '';
      }
    }

    if (data.role === 'admin') {
      document.getElementById('admin-dashboard-btn').classList.remove('hidden');
    } else {
      document.getElementById('admin-dashboard-btn').classList.add('hidden');
    }

    showToast('✅ User verified. You can now submit the booking.', 'success');
  } catch (err) {
    showFieldError(errorEl, 'Unable to verify user — please try again.');
  } finally {
    if (btn) btn.disabled = false;
    if (label) label.classList.remove('hidden');
    if (spinner) spinner.classList.add('hidden');
  }
}

export async function forgotPin() {
  const username = document.getElementById('book-username').value.trim();
  if (!username) {
    showToast('Please enter your username first.', 'error');
    return;
  }
  
  showToast('Sending PIN...', 'info');
  try {
    const res = await fetch('/api/forgot-pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username }),
    });
    const data = await res.json();
    if (data.ok) {
      showToast('PIN has been sent to your email.', 'success');
    } else {
      showToast(data.error || 'Failed to send PIN.', 'error');
    }
  } catch (err) {
    showToast('Network error while requesting PIN.', 'error');
  }
}

export function openAdminPanel() {
  document.getElementById('admin-panel-modal').classList.remove('hidden');
  loadAdminUsers();
}

export function closeAdminPanel() {
  document.getElementById('admin-panel-modal').classList.add('hidden');
  document.getElementById('admin-panel-error').classList.add('hidden');
}

export async function loadAdminUsers() {
  const list = document.getElementById('admin-users-list');
  list.innerHTML = 'Loading...';
  
  const form = document.getElementById('booking-form');
  const username = form.dataset.username;
  const password = form.dataset.password;
  
  try {
    const res = await fetch(`/api/users?username=${encodeURIComponent(username)}&pin=${encodeURIComponent(password)}`);
    const data = await res.json();
    
    if (data.ok) {
      if (data.users.length === 0) {
        list.innerHTML = 'No users found.';
        return;
      }
      list.innerHTML = data.users.map(u => `
        <div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border);">
          <span><b>${u.username}</b> (${u.email || 'No email'}) - <i>${u.role}</i></span>
          ${u.username !== username ? `<button onclick="deleteUser('${u.username}')" style="color: red; background: none; border: none; cursor: pointer;">Delete</button>` : ''}
        </div>
      `).join('');
    } else {
      list.innerHTML = `<span style="color:red">${data.error}</span>`;
    }
  } catch (err) {
    list.innerHTML = `<span style="color:red">Error loading users</span>`;
  }
}

export async function createUser() {
  const errorEl = document.getElementById('admin-panel-error');
  errorEl.classList.add('hidden');
  
  const form = document.getElementById('booking-form');
  const admin_username = form.dataset.username;
  const admin_password = form.dataset.password;
  
  const username = document.getElementById('new-user-username').value.trim();
  const email = document.getElementById('new-user-email').value.trim();
  const pin = document.getElementById('new-user-pin').value.trim();
  
  if (!username || !pin) {
    errorEl.textContent = 'Username and PIN are required.';
    errorEl.classList.remove('hidden');
    return;
  }
  
  try {
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ admin_username, admin_password, username, email, pin, role: 'user' }),
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById('new-user-username').value = '';
      document.getElementById('new-user-email').value = '';
      document.getElementById('new-user-pin').value = '';
      showToast('User added successfully', 'success');
      loadAdminUsers();
    } else {
      errorEl.textContent = data.error;
      errorEl.classList.remove('hidden');
    }
  } catch (err) {
    errorEl.textContent = 'Network error.';
    errorEl.classList.remove('hidden');
  }
}

export async function deleteUser(usernameToDelete) {
  if (!confirm(`Are you sure you want to delete ${usernameToDelete}?`)) return;
  
  const form = document.getElementById('booking-form');
  const admin_username = form.dataset.username;
  const admin_password = form.dataset.password;
  
  try {
    const res = await fetch(`/api/users/${encodeURIComponent(usernameToDelete)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ admin_username, admin_password }),
    });
    const data = await res.json();
    if (data.ok) {
      showToast('User deleted', 'success');
      loadAdminUsers();
    } else {
      showToast(data.error, 'error');
    }
  } catch (err) {
    showToast('Network error.', 'error');
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
