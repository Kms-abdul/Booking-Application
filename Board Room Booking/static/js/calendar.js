import { state, roomColor } from './state.js';
import { fetchWithAbort } from './api.js';
import { esc, escAttr, formatDateDisplay, todayISO } from './utils.js';

export async function loadAgenda() {
  const date = document.getElementById('agenda-date').value;
  const room = document.getElementById('agenda-room-filter').value;
  const list = document.getElementById('agenda-list');

  list.innerHTML = '<p class="empty-state">Loading…</p>';

  const filterEl = document.getElementById('agenda-room-filter');
  if (filterEl.options.length <= 1 && state.rooms.length) {
    _rebuildAgendaRoomFilter(state.activeAgendaFloor);
  }

  try {
    const params = new URLSearchParams({ date });
    if (room) params.set('room', room);

    const data = await fetchWithAbort(`/api/bookings?${params}`, {}, 'agenda');
    if (data && data.aborted) return;
    if (!data.ok) throw new Error(data.error);

    let bookings = data.bookings;
    if (!room && state.activeAgendaFloor !== 'all') {
      const floorRooms = new Set(state.rooms.filter(r => String(r.floor) === String(state.activeAgendaFloor)).map(r => r.name));
      bookings = bookings.filter(b => floorRooms.has(b.room));
    }

    const emailQuery = (document.getElementById('agenda-email-filter')?.value || '').trim().toLowerCase();
    if (emailQuery) {
      bookings = bookings.filter(b => {
        const attendeeEmails = (b.attendee_emails || '').toLowerCase();
        const ccEmails = (b.cc_emails || '').toLowerCase();
        const bookerEmail = (b.email || '').toLowerCase();
        const attendees = (b.attendees || '').toLowerCase();
        return attendeeEmails.includes(emailQuery) ||
          ccEmails.includes(emailQuery) ||
          bookerEmail.includes(emailQuery) ||
          attendees.includes(emailQuery);
      });
    }

    bookings = bookings.filter(b => b.meeting_mode === state.activeAgendaCategory);

    renderAgenda(bookings, date);
  } catch (err) {
    list.innerHTML = `<p class="empty-state">⚠️ ${esc(err.message)}</p>`;
  }
}

export function setAgendaCategory(category) {
  state.activeAgendaCategory = category;
  document.querySelectorAll('.category-tab').forEach(btn => {
    btn.classList.toggle('active', btn.id === `category-tab-${category}`);
  });
  loadAgenda();
}

export function setAgendaFloor(floor) {
  state.activeAgendaFloor = floor;
  document.querySelectorAll(`#agenda-floor-tabs .floor-tab`).forEach(btn => {
    btn.classList.toggle('active', btn.dataset.floor === floor);
  });
  _rebuildAgendaRoomFilter(floor);
  document.getElementById('agenda-room-filter').value = '';
  loadAgenda();
}

function _rebuildAgendaRoomFilter(floor) {
  const sel = document.getElementById('agenda-room-filter');
  sel.innerHTML = '<option value="">All rooms</option>';

  const filtered = floor === 'all' ? state.rooms : state.rooms.filter(r => String(r.floor) === String(floor));

  if (floor === 'all') {
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
  } else {
    filtered.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = r.name;
      sel.appendChild(opt);
    });
  }
}

function renderAgenda(bookings, date) {
  const list = document.getElementById('agenda-list');
  const isToday = date === todayISO();
  const now = new Date();

  if (!bookings.length) {
    const label = isToday ? 'today' : `on ${formatDateDisplay(date)}`;
    const catLabel = state.activeAgendaCategory === 'online' ? 'online' : 'offline';
    list.innerHTML = `<div class="empty-state"><span class="empty-state-icon">📅</span>No ${catLabel} meetings ${label}.</div>`;
    return;
  }

  list.innerHTML = bookings.map(b => {
    const color = roomColor(b.room);
    const endDt = new Date(`${b.date}T${b.end_time}:00`);
    const isCompleted = endDt < now;

    const actionHTML = isCompleted
      ? `<span class="completed-badge">✓ Completed</span>`
      : `<div class="agenda-actions">
           <button class="edit-btn" onclick="openEdit('${escAttr(b.id)}')" title="Edit booking">✏️ Edit</button>
           <button class="cancel-btn" onclick="openCancel('${escAttr(b.id)}')" title="Cancel this booking">Cancel</button>
         </div>`;

    let attendeesHTML = '';
    if (b.attendees) {
      const names = b.attendees.split(',').map(a => a.trim()).filter(Boolean);
      if (names.length) {
        attendeesHTML = `<div class="attendees-list"><span class="attendees-label">👥 Attendees:</span>${names.map(n => `<span class="attendee-chip">${esc(n)}</span>`).join('')}</div>`;
      }
    }

    let onlineHTML = '';
    const modeBadge = b.meeting_mode === 'online'
      ? `<span class="mode-badge online" style="display:inline-flex; align-items:center; padding:2px 6px; font-size:11px; font-weight:600; background:#e0e7ff; color:#4338ca; border-radius:4px; margin-left:4px">💻 Online</span>`
      : `<span class="mode-badge offline" style="display:inline-flex; align-items:center; padding:2px 6px; font-size:11px; font-weight:600; background:#f1f5f9; color:#475569; border-radius:4px; margin-left:4px">🏢 Offline</span>`;

    if (b.meeting_mode === 'online' && b.meeting_link) {
      const parts = b.meeting_link.split('|');
      const url = parts[0];
      let mid = parts[1] || '';
      let passcode = parts[2] || '';
      if (mid.toLowerCase().trim() === 'meeting-join' || passcode.toLowerCase().trim() === 'microsoft teams') {
        mid = '';
        passcode = '';
      }
      const idPasscodeHTML = mid ? `<span style="font-size:11px; color:#64748b;">ID: <b>${esc(mid)}</b> &bull; Pass: <b>${esc(passcode)}</b></span>` : '';
      onlineHTML = `
        <div class="online-details" style="margin-top: 8px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <a href="${escAttr(url)}" target="_blank" class="join-teams-btn" style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:#4f46e5; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; font-size:12px; box-shadow:0 2px 4px rgba(79,70,229,0.15)">
            Join Teams Meeting
          </a>
          ${idPasscodeHTML}
        </div>
      `;
    }

    let descriptionHTML = '';
    if (b.description) {
      descriptionHTML = `<div class="agenda-description" style="margin-top: 6px; font-size: 0.82rem; color: var(--text-dim); line-height: 1.4;">📝 <b>Purpose:</b> ${esc(b.description)}</div>`;
    }

    const roomObj = state.rooms.find(r => r.name === b.room);
    const floorNum = roomObj ? roomObj.floor : '';

    return `
      <div class="agenda-item ${isCompleted ? 'completed' : ''}" style="--room-color:${color}; cursor: pointer;" onclick="openRoomPanel('${escAttr(b.room)}')">
        <div class="agenda-time">${b.start_time}<br/>–<br/>${b.end_time}</div>
        <div class="agenda-info">
          <div class="agenda-title">${esc(b.title)}</div>
          <div class="agenda-meta">
            <span class="agenda-room-chip" style="--room-color:${color}">${esc(b.room)} (Floor ${floorNum})</span>
            ${modeBadge}
            &nbsp;👤 ${esc(b.booked_by)}
          </div>
          ${attendeesHTML}
          ${descriptionHTML}
          ${onlineHTML}
        </div>
        <div onclick="event.stopPropagation()">${actionHTML}</div>
      </div>`;
  }).join('');
}
