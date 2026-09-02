import { state } from './state.js';
import { esc, showToast } from './utils.js';
import { loadAgenda } from './calendar.js';
import { loadStatus } from './rooms.js';

export function openEdit(bookingId) {
  state.editId = bookingId;

  fetch(`/api/bookings/${bookingId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;
      const b = data.booking;
      document.getElementById('edit-booking-info').innerHTML =
        `<b>${esc(b.title)}</b><br/>${esc(b.room)} &bull; ${b.date} &bull; Booked by <b>${esc(b.booked_by)}</b>`;

      document.getElementById('edit-start').value = b.start_time;
      document.getElementById('edit-end').value = b.end_time;
      document.getElementById('edit-attendees').value = b.attendees || '';
      document.getElementById('edit-attendees-emails').value = b.attendee_emails || '';
      document.getElementById('edit-mode').value = b.meeting_mode || 'offline';
      document.getElementById('edit-cc-emails').value = b.cc_emails || '';
      let desc = b.description || '';
      let venue = '';
      if (desc.startsWith('Venue: ')) {
        const parts = desc.split('\n\n');
        venue = parts[0].substring(7).trim();
        desc = parts.slice(1).join('\n\n').trim();
      }
      document.getElementById('edit-description').value = desc;

      setTimeout(() => {
        ['edit-attendees-emails', 'edit-cc-emails', 'edit-description'].forEach(id => {
          const el = document.getElementById(id);
          if (el) el.dispatchEvent(new Event('input'));
        });
      }, 50);

      const sel = document.getElementById('edit-room');
      sel.innerHTML = '';
      
      const floors = [...new Set(state.rooms.map(r => r.floor))].sort((a, b) => {
        if (a === 'Online') return 1;
        if (b === 'Online') return -1;
        return a - b;
      });
      
      const mode = b.meeting_mode || 'offline';
      
      floors.forEach(f => {
        if (mode !== 'online' && f === 'Online') return;

        const grp = document.createElement('optgroup');
        grp.label = f === 'Online' ? 'Online Rooms' : `Floor ${f}`;
        state.rooms.filter(r => r.floor === f).forEach(r => {
          const opt = document.createElement('option');
          opt.value = r.name;
          opt.textContent = r.name;
          if (r.name === b.room) opt.selected = true;
          grp.appendChild(opt);
        });
        sel.appendChild(grp);
      });
      
      const editVenueGroup = document.getElementById('edit-venue-group');
      if (editVenueGroup) {
        if (mode === 'online') {
          editVenueGroup.classList.remove('hidden');
        } else {
          editVenueGroup.classList.add('hidden');
        }
      }
      
      const editVenueEl = document.getElementById('edit-venue');
      if (editVenueEl) editVenueEl.value = venue;
    });

  document.getElementById('edit-username').value = '';
  document.getElementById('edit-password').value = '';
  document.getElementById('edit-error').classList.add('hidden');
  document.getElementById('edit-modal').classList.remove('hidden');
  setTimeout(() => document.getElementById('edit-username').focus(), 100);
}

export function closeEdit() {
  document.getElementById('edit-modal').classList.add('hidden');
  state.editId = null;
}

export function onEditMeetingModeChange() {
  const mode = document.getElementById('edit-mode').value;
  const sel = document.getElementById('edit-room');
  const prevValue = sel.value;
  
  sel.innerHTML = '';
  
  const floors = [...new Set(state.rooms.map(r => r.floor))].sort((a, b) => {
    if (a === 'Online') return 1;
    if (b === 'Online') return -1;
    return a - b;
  });
  
  floors.forEach(f => {
    if (mode !== 'online' && f === 'Online') return;

    const grp = document.createElement('optgroup');
    grp.label = f === 'Online' ? 'Online Rooms' : `Floor ${f}`;
    state.rooms.filter(r => r.floor === f).forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = r.name;
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  });
  
  if (prevValue && sel.querySelector(`option[value="${prevValue}"]`)) {
    sel.value = prevValue;
  }
  
  const editVenueGroup = document.getElementById('edit-venue-group');
  if (editVenueGroup) {
    if (mode === 'online') {
      editVenueGroup.classList.remove('hidden');
    } else {
      editVenueGroup.classList.add('hidden');
    }
  }
}

export async function confirmEdit() {
  if (!state.editId) return;
  const uname = document.getElementById('edit-username').value.trim();
  const pwd = document.getElementById('edit-password').value;
  const errEl = document.getElementById('edit-error');
  const btn = document.getElementById('edit-confirm-btn');
  const label = btn.querySelector('.btn-label');
  const spinner = btn.querySelector('.btn-spinner');

  errEl.classList.add('hidden');

  if (!uname || !pwd) {
    errEl.textContent = 'Please enter username and PIN.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  label.classList.add('hidden');
  spinner.classList.remove('hidden');

  let desc = document.getElementById('edit-description').value.trim();
  const editVenueEl = document.getElementById('edit-venue');
  const mode = document.getElementById('edit-mode').value;
  if (mode === 'online' && editVenueEl && editVenueEl.value.trim()) {
      desc = `Venue: ${editVenueEl.value.trim()}\n\n${desc}`.trim();
  }

  const payload = {
    username: uname,
    password: pwd,
    room: document.getElementById('edit-room').value,
    meeting_mode: mode,
    start_time: document.getElementById('edit-start').value,
    end_time: document.getElementById('edit-end').value,
    attendees: document.getElementById('edit-attendees').value.trim(),
    attendee_emails: document.getElementById('edit-attendees-emails').value.trim(),
    cc_emails: document.getElementById('edit-cc-emails').value.trim(),
    description: desc,
  };

  try {
    const res = await fetch(`/api/bookings/${state.editId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
      showToast('✅ Booking updated successfully.', 'success');
      closeEdit();
      loadAgenda();
      loadStatus();
    } else {
      errEl.textContent = data.error || 'Update failed.';
      errEl.classList.remove('hidden');
    }
  } catch (_) {
    errEl.textContent = 'Network error — please try again.';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    label.classList.remove('hidden');
    spinner.classList.add('hidden');
  }
}

export function openCancel(bookingId) {
  state.cancelId = bookingId;

  fetch(`/api/bookings/${bookingId}`)
    .then(r => r.json())
    .then(data => {
      if (!data.ok) return;
      const b = data.booking;
      document.getElementById('cancel-booking-info').innerHTML = `
        <b>${esc(b.title)}</b><br/>
        ${esc(b.room)} &bull; ${b.date} &bull; ${b.start_time}–${b.end_time}<br/>
        Booked by: <b>${esc(b.booked_by)}</b>`;
    });

  document.getElementById('cancel-username-input').value = '';
  document.getElementById('cancel-password-input').value = '';
  document.getElementById('cancel-error').classList.add('hidden');
  document.getElementById('cancel-modal').classList.remove('hidden');
  setTimeout(() => document.getElementById('cancel-username-input').focus(), 100);
}

export function closeCancel() {
  document.getElementById('cancel-modal').classList.add('hidden');
  state.cancelId = null;
}

export async function confirmCancel() {
  if (!state.cancelId) return;
  const uname = document.getElementById('cancel-username-input').value.trim();
  const pwd = document.getElementById('cancel-password-input').value;
  const errEl = document.getElementById('cancel-error');
  const btn = document.getElementById('cancel-confirm-btn');

  if (!uname || !pwd) {
    errEl.textContent = 'Please enter username and PIN.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  errEl.classList.add('hidden');

  try {
    const res = await fetch(`/api/bookings/${state.cancelId}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uname, password: pwd }),
    });
    const data = await res.json();

    if (data.ok) {
      showToast('🗑️ Booking cancelled.', 'info');
      closeCancel();
      loadAgenda();
      loadStatus();
    } else {
      errEl.textContent = data.error || 'Cancellation failed.';
      errEl.classList.remove('hidden');
    }
  } catch (_) {
    errEl.textContent = 'Network error — please try again.';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
  }
}

export function initModalListeners() {
  const cancelModal = document.getElementById('cancel-modal');
  if (cancelModal) {
    cancelModal.addEventListener('click', function (e) {
      if (e.target === this) closeCancel();
    });
  }
  const editModal = document.getElementById('edit-modal');
  if (editModal) {
    editModal.addEventListener('click', function (e) {
      if (e.target === this) closeEdit();
    });
  }
}
