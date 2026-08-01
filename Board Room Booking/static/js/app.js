// =============================================================================
// app.js — The Floor: corridor walkthrough booking frontend
// Talks to the same backend API as before — only the presentation changed.
// =============================================================================

'use strict';

// ── State ──────────────────────────────────────────────────────────────────

let _rooms = [];
let _statusByRoom = {};
let _cancelId = null;
let _activeRoomPanel = null;
let _activeCorridorFloor = 'all';   // 'all' | '3' | '4' | '5'
let _activeAgendaFloor = 'all';   // 'all' | '3' | '4' | '5'
let _activeAgendaCategory = 'online'; // 'online' | 'offline'
let _lastStatusList = [];           // full unfiltered status list

const STATUS_COLOR = {
  vacant: 'var(--ok)',
  engaged: 'var(--busy)',
  soon: 'var(--soon)',
  closed: 'var(--closed)',
};
const STATUS_LABEL = {
  vacant: 'Available',
  engaged: 'In progress',
  soon: 'Starting soon',
  closed: 'Closed',
};

// ── Bootstrap ──────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initDateDefaults();
  loadRooms().then(() => {
    renderFloorTabs();
    loadStatus();
    loadAgenda();
    populateBookForm();
  });
  startClock();
  setInterval(loadStatus, 60_000);

  document.getElementById('hallway-track').addEventListener('scroll', onHallwayScroll, { passive: true });
});

function enterFloor() {
  document.getElementById('entry-veil').classList.add('entered');
  showTab('about');
}
// Auto-dismiss the entry veil shortly after load in case the user just scrolls.
setTimeout(() => {
  const veil = document.getElementById('entry-veil');
  if (veil) veil.classList.add('entered');
}, 4500);

// ── Tab Navigation ─────────────────────────────────────────────────────────

function showTab(tab) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });
  document.querySelectorAll('.drawer-nav-item').forEach(b => {
    b.classList.remove('active');
  });

  const viewEl = document.getElementById(`view-${tab}`);
  if (viewEl) viewEl.classList.add('active');

  const btn = document.getElementById(`tab-${tab}`);
  if (btn) {
    btn.classList.add('active');
    btn.setAttribute('aria-selected', 'true');
  }

  const drawerBtn = document.getElementById(`drawer-tab-${tab}`);
  if (drawerBtn) {
    drawerBtn.classList.add('active');
  }

  if (tab === 'corridor') loadStatus();
  if (tab === 'agenda') loadAgenda();
}

function openSideDrawer() {
  const drawer = document.getElementById('side-nav-drawer');
  if (drawer) {
    drawer.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

function closeSideDrawer() {
  const drawer = document.getElementById('side-nav-drawer');
  if (drawer) {
    drawer.classList.add('hidden');
    document.body.style.overflow = '';
  }
}

function selectDrawerTab(tab) {
  showTab(tab);
  closeSideDrawer();
}

// ── Clock ──────────────────────────────────────────────────────────────────

function startClock() {
  const el = document.getElementById('status-time');
  const drawerEl = document.getElementById('drawer-time');
  function tick() {
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (el) el.textContent = timeStr;
    if (drawerEl) drawerEl.textContent = timeStr;
  }
  tick();
  setInterval(tick, 1000);
}

// ── Date defaults ──────────────────────────────────────────────────────────

function initDateDefaults() {
  const today = todayISO();
  document.getElementById('agenda-date').value = today;
  document.getElementById('book-date').value = today;
}
function todayISO() { return new Date().toISOString().slice(0, 10); }

function agendaShiftDay(delta) {
  const input = document.getElementById('agenda-date');
  const d = new Date(input.value + 'T00:00:00');
  d.setDate(d.getDate() + delta);
  input.value = d.toISOString().slice(0, 10);
  loadAgenda();
}

// ── Rooms ───────────────────────────────────────────────────────────────────

async function loadRooms() {
  try {
    const res = await fetch('/api/rooms');
    const data = await res.json();
    if (data.ok) _rooms = data.rooms;
  } catch (_) { /* UI still works with an empty room list */ }
}

function roomColor(roomName) {
  const r = _rooms.find(r => r.name === roomName);
  return r ? r.color : '#c9a468';
}

// ── CORRIDOR / STATUS ────────────────────────────────────────────────────────

async function loadStatus() {
  const track = document.getElementById('hallway-track');
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    _statusByRoom = {};
    data.status.forEach(r => { _statusByRoom[r.room] = r; });
    _lastStatusList = data.status;
    renderHallway(_filterStatusByFloor(data.status, _activeCorridorFloor));
  } catch (err) {
    track.innerHTML = `<p class="empty-state">⚠️ Could not load room status.<br><small>${esc(err.message)}</small></p>`;
  }
}

function renderHallway(statusList) {
  const track = document.getElementById('hallway-track');
  const dots = document.getElementById('hallway-dots');

  if (!statusList.length) {
    track.innerHTML = '<p class="empty-state">No rooms configured.</p>';
    dots.innerHTML = '';
    return;
  }

  track.innerHTML = statusList.map(room => {
    const engaged = room.status === 'engaged';
    const cur = room.current_booking;
    const nxt = room.next_booking;
    const color = room.color || '#c9a468';
    const statusKey = engaged ? 'engaged' : 'vacant';

    let interiorHTML;
    if (engaged && cur) {
      const attendeesList = (cur.attendees ? cur.attendees.split(',') : []).map(a => a.trim()).filter(Boolean);
      const namesToShow = attendeesList.length ? attendeesList : [cur.booked_by];
      interiorHTML = `
        <div class="door-attendees-section">
          <div class="door-attendees-label">👥 Attendees:</div>
          <div class="door-attendees-list">${namesToShow.map(name => `<span class="door-attendee-chip">${esc(name)}</span>`).join('')}</div>
        </div>
        <div class="door-table-container">
          <div class="door-chair top-left">🪑</div>
          <div class="door-chair top-right">🪑</div>
          <div class="door-chair mid-left">🪑</div>
          <div class="door-table"></div>
          <div class="door-chair mid-right">🪑</div>
          <div class="door-chair bot-left">🪑</div>
          <div class="door-chair bot-right">🪑</div>
          <div class="door-screen">📺 Screen</div>
        </div>
        <div class="door-meeting-title">${esc(cur.title)}</div>
        <div class="door-meeting-time">🕐 ${cur.start_time}–${cur.end_time}</div>`;
    } else {
      interiorHTML = `
        <div class="door-table-container">
          <div class="door-chair top-left">🪑</div>
          <div class="door-chair top-right">🪑</div>
          <div class="door-chair mid-left">🪑</div>
          <div class="door-table"></div>
          <div class="door-chair mid-right">🪑</div>
          <div class="door-chair bot-left">🪑</div>
          <div class="door-chair bot-right">🪑</div>
          <div class="door-screen">📺 Screen</div>
        </div>
        <div class="door-vacant-note">Room is Free</div>
        ${nxt ? `<div class="door-next-note">Next: ${esc(nxt.title)} · ${nxt.start_time}</div>` : `<div class="door-next-note">Nothing booked today</div>`}`;
    }

    return `
      <div class="door" data-room="${esc(room.room)}" data-status="${statusKey}" style="--room-color:${color}" onclick="openRoomPanel('${escAttr(room.room)}')">
        <div class="door-frame">
          <span class="door-led ${engaged ? 'pulse' : ''}"></span>
          <div class="door-plaque">
            <div class="door-name">${esc(room.room)}</div>
            <div class="door-floor-badge" style="font-size: 0.65rem; color: var(--text-dim); margin-top: 1px; letter-spacing: 0.05em; font-weight: 500;">FLOOR ${room.floor}</div>
            <span class="door-status-label" style="margin-top: 4px;">${STATUS_LABEL[statusKey]}</span>
          </div>
          <div class="door-interior">${interiorHTML}</div>
        </div>
      </div>`;
  }).join('');

  dots.innerHTML = statusList.map((_, i) => `<span class="hallway-dot" data-i="${i}"></span>`).join('');

  // let layout settle, then mark the centered door + wire dot clicks
  requestAnimationFrame(() => {
    updateDoorFocus();
    document.querySelectorAll('.hallway-dot').forEach(dot => {
      dot.addEventListener('click', () => {
        const doors = document.querySelectorAll('.door');
        const target = doors[+dot.dataset.i];
        if (target) target.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      });
    });
  });
}

function initialsFromAttendees(attendeesStr, bookedBy) {
  const names = (attendeesStr ? attendeesStr.split(',') : []).map(a => a.trim()).filter(Boolean);
  const all = names.length ? names : (bookedBy ? [bookedBy] : []);
  return all.slice(0, 4).map(n => n.trim().charAt(0).toUpperCase());
}

let _hallwayScrollRAF = null;
function onHallwayScroll() {
  if (_hallwayScrollRAF) return;
  _hallwayScrollRAF = requestAnimationFrame(() => {
    updateDoorFocus();
    _hallwayScrollRAF = null;
  });
}

function updateDoorFocus() {
  const track = document.getElementById('hallway-track');
  const doors = Array.from(track.querySelectorAll('.door'));
  if (!doors.length) return;
  const trackRect = track.getBoundingClientRect();
  const center = trackRect.left + trackRect.width / 2;

  let closestIdx = 0, closestDist = Infinity;
  doors.forEach((door, i) => {
    const r = door.getBoundingClientRect();
    const doorCenter = r.left + r.width / 2;
    const dist = Math.abs(doorCenter - center);
    const norm = Math.min(dist / (trackRect.width / 2), 1);

    // Perspective: doors near center are frontal & bright; off-center doors
    // tilt away and recede, as if seen while walking past them.
    const rotate = ((doorCenter - center) / trackRect.width) * 34;
    const scale = 1 - norm * 0.16;
    const z = -norm * 90;
    door.style.transform = `translateZ(${z}px) rotateY(${-rotate}deg) scale(${scale})`;
    door.classList.toggle('is-center', norm < 0.18);

    if (dist < closestDist) { closestDist = dist; closestIdx = i; }
  });

  document.querySelectorAll('.hallway-dot').forEach((dot, i) => dot.classList.toggle('active', i === closestIdx));
}

function scrollHallway(dir) {
  const track = document.getElementById('hallway-track');
  const doors = Array.from(track.querySelectorAll('.door'));
  if (!doors.length) return;
  const trackRect = track.getBoundingClientRect();
  const center = trackRect.left + trackRect.width / 2;
  let idx = 0, best = Infinity;
  doors.forEach((d, i) => {
    const r = d.getBoundingClientRect();
    const dist = Math.abs((r.left + r.width / 2) - center);
    if (dist < best) { best = dist; idx = i; }
  });
  const targetIdx = Math.max(0, Math.min(doors.length - 1, idx + dir));
  doors[targetIdx].scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
}

// ── ROOM DETAIL PANEL ─────────────────────────────────────────────────────

async function openRoomPanel(roomName) {
  _activeRoomPanel = roomName;
  const panel = document.getElementById('room-panel');
  const body = document.getElementById('room-panel-body');
  const status = _statusByRoom[roomName];
  const color = roomColor(roomName);
  const engaged = status && status.status === 'engaged';

  const roomObj = _rooms.find(r => r.name === roomName);
  const floorNum = roomObj ? roomObj.floor : '';

  body.innerHTML = `
    <p class="rp-eyebrow" style="--room-color:${color}">${engaged ? 'In progress' : 'Available now'} &bull; Floor ${floorNum}</p>
    <h2 class="rp-title" id="room-panel-title">${esc(roomName)}</h2>
    <div class="rp-status-row">
      <span class="rp-led" style="--room-color:${color}"></span>
      <span class="rp-status-text">${engaged ? 'Occupied right now' : 'Free to book'}</span>
    </div>
    ${engaged && status.current_booking ? `
      <div class="rp-now" style="--room-color:${color}">
        <div class="rp-now-label">Happening now</div>
        <div class="rp-now-title">${esc(status.current_booking.title)}</div>
        <div class="rp-now-meta">
          👤 ${esc(status.current_booking.booked_by)}<br/>
          🕐 ${status.current_booking.start_time}–${status.current_booking.end_time}
        </div>
        ${status.current_booking.meeting_mode === 'online' && status.current_booking.meeting_link ? (() => {
          const parts = status.current_booking.meeting_link.split('|');
          const url = parts[0];
          let mid = parts[1] || '';
          let passcode = parts[2] || '';
          if (mid.toLowerCase().trim() === 'meeting-join' || passcode.toLowerCase().trim() === 'microsoft teams') {
            mid = '';
            passcode = '';
          }
          const idPasscodeHTML = mid ? `<div style="color:#475569">ID: <b>${esc(mid)}</b> &bull; Passcode: <b>${esc(passcode)}</b></div>` : '';
          return `
            <div class="rp-now-teams" style="margin-top:12px; padding:10px; background:#f0f4ff; border-radius:6px; font-size:12px; border:1px solid #dbeafe">
              <a href="${escAttr(url)}" target="_blank" style="display:inline-flex; align-items:center; gap:6px; padding:6px 12px; background:#4f46e5; color:#fff; text-decoration:none; border-radius:6px; font-weight:600; font-size:11px; margin-bottom:6px">💻 Join Teams</a>
              ${idPasscodeHTML}
            </div>
          `;
        })() : ''}
      </div>` : ''}
    <p class="rp-section-label">Today's timeline</p>
    <div id="rp-timeline" class="rp-timeline"><p class="empty-state" style="padding:20px 0">Loading…</p></div>
    <button class="rp-cta" onclick="goBookRoom('${escAttr(roomName)}')">Book this room</button>
  `;

  panel.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  loadRoomTimeline(roomName);
}

async function loadRoomTimeline(roomName) {
  const el = document.getElementById('rp-timeline');
  try {
    const params = new URLSearchParams({ date: todayISO(), room: roomName });
    const res = await fetch(`/api/bookings?${params}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    if (!data.bookings.length) {
      el.innerHTML = `<p class="empty-state" style="padding:16px 0">No bookings today — wide open.</p>`;
      return;
    }
    el.innerHTML = data.bookings.map(b => {
      const modeHTML = b.meeting_mode === 'online' && b.meeting_link ? (() => {
        const parts = b.meeting_link.split('|');
        const url = parts[0];
        return ` <a href="${escAttr(url)}" target="_blank" style="display:inline-flex; align-items:center; padding:2px 6px; font-size:10px; font-weight:600; background:#e0e7ff; color:#4338ca; border-radius:4px; text-decoration:none; margin-left:6px">💻 Join Teams</a>`;
      })() : '';
      return `
        <div class="rp-timeline-item">
          <span class="rp-timeline-time">${b.start_time}</span>
          <span class="rp-timeline-title">${esc(b.title)}${modeHTML}</span>
        </div>`;
    }).join('');
  } catch (err) {
    el.innerHTML = `<p class="empty-state" style="padding:16px 0">⚠️ ${esc(err.message)}</p>`;
  }
}

function closeRoomPanel() {
  document.getElementById('room-panel').classList.add('hidden');
  document.body.style.overflow = '';
  _activeRoomPanel = null;
}

function goBookRoom(roomName) {
  closeRoomPanel();
  showTab('book');
  const sel = document.getElementById('book-room');
  if (sel && roomName) sel.value = roomName;
}

// ── FLOOR FILTERING ──────────────────────────────────────────────────────────

function renderFloorTabs() {
  const floors = [...new Set(_rooms.map(r => r.floor).filter(Boolean))].sort((a, b) => a - b);

  // Update entry subtitle dynamically
  const sub = document.getElementById('entry-subtitle');
  if (sub && floors.length) {
    sub.textContent = `Floors ${floors.join(' · ')} — walk the corridor and see what's free.`;
  }

  // Render Corridor floor tabs
  const corrContainer = document.getElementById('corridor-floor-tabs');
  if (corrContainer) {
    let html = `<button class="floor-tab active" data-floor="all" onclick="setCorridorFloor('all')">All Floors</button>`;
    floors.forEach(f => {
      const suffix = f === 1 ? 'st' : f === 2 ? 'nd' : f === 3 ? 'rd' : 'th';
      html += `<button class="floor-tab" data-floor="${f}" onclick="setCorridorFloor('${f}')">${f}<sup>${suffix}</sup> Floor</button>`;
    });
    corrContainer.innerHTML = html;
  }

  // Render Agenda floor tabs
  const agendaContainer = document.getElementById('agenda-floor-tabs');
  if (agendaContainer) {
    let html = `<button class="floor-tab active" data-floor="all" onclick="setAgendaFloor('all')">All</button>`;
    floors.forEach(f => {
      html += `<button class="floor-tab" data-floor="${f}" onclick="setAgendaFloor('${f}')">${f}F</button>`;
    });
    agendaContainer.innerHTML = html;
  }
}

function _filterStatusByFloor(statusList, floor) {
  if (floor === 'all') return statusList;
  return statusList.filter(r => {
    const room = _rooms.find(rm => rm.name === r.room);
    return room && String(room.floor) === String(floor);
  });
}

function _setFloorTab(containerId, floor) {
  document.querySelectorAll(`#${containerId} .floor-tab`).forEach(btn => {
    btn.classList.toggle('active', btn.dataset.floor === floor);
  });
}

function setCorridorFloor(floor) {
  _activeCorridorFloor = floor;
  _setFloorTab('corridor-floor-tabs', floor);
  renderHallway(_filterStatusByFloor(_lastStatusList, floor));
}

function setAgendaFloor(floor) {
  _activeAgendaFloor = floor;
  _setFloorTab('agenda-floor-tabs', floor);
  // Rebuild the room dropdown to show only rooms on that floor
  _rebuildAgendaRoomFilter(floor);
  // Reset room selection and reload
  document.getElementById('agenda-room-filter').value = '';
  loadAgenda();
}

function _rebuildAgendaRoomFilter(floor) {
  const sel = document.getElementById('agenda-room-filter');
  sel.innerHTML = '<option value="">All rooms</option>';

  const filtered = floor === 'all' ? _rooms : _rooms.filter(r => String(r.floor) === String(floor));

  if (floor === 'all') {
    // Group by floor using optgroups
    const floors = [...new Set(_rooms.map(r => r.floor))].sort((a, b) => a - b);
    floors.forEach(f => {
      const grp = document.createElement('optgroup');
      grp.label = `Floor ${f}`;
      _rooms.filter(r => r.floor === f).forEach(r => {
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

// ── AGENDA ──────────────────────────────────────────────────────────────────

async function loadAgenda() {
  const date = document.getElementById('agenda-date').value;
  const room = document.getElementById('agenda-room-filter').value;
  const list = document.getElementById('agenda-list');

  list.innerHTML = '<p class="empty-state">Loading…</p>';

  // Build room dropdown on first run
  const filterEl = document.getElementById('agenda-room-filter');
  if (filterEl.options.length <= 1 && _rooms.length) {
    _rebuildAgendaRoomFilter(_activeAgendaFloor);
  }

  try {
    const params = new URLSearchParams({ date });
    // If a specific room is chosen, filter server-side; otherwise fetch all & filter client-side by floor
    if (room) params.set('room', room);
    const res = await fetch(`/api/bookings?${params}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);

    let bookings = data.bookings;
    // If no specific room selected but a floor is active, filter by floor client-side
    if (!room && _activeAgendaFloor !== 'all') {
      const floorRooms = new Set(_rooms.filter(r => String(r.floor) === String(_activeAgendaFloor)).map(r => r.name));
      bookings = bookings.filter(b => floorRooms.has(b.room));
    }

    // Filter by online/offline category client-side
    bookings = bookings.filter(b => b.meeting_mode === _activeAgendaCategory);

    renderAgenda(bookings, date);
  } catch (err) {
    list.innerHTML = `<p class="empty-state">⚠️ ${esc(err.message)}</p>`;
  }
}

function setAgendaCategory(category) {
  _activeAgendaCategory = category;
  document.querySelectorAll('.category-tab').forEach(btn => {
    btn.classList.toggle('active', btn.id === `category-tab-${category}`);
  });
  loadAgenda();
}

function renderAgenda(bookings, date) {
  const list = document.getElementById('agenda-list');
  const isToday = date === todayISO();
  const now = new Date();

  if (!bookings.length) {
    const label = isToday ? 'today' : `on ${formatDateDisplay(date)}`;
    const catLabel = _activeAgendaCategory === 'online' ? 'online' : 'offline';
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

    const roomObj = _rooms.find(r => r.name === b.room);
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
          ${onlineHTML}
        </div>
        <div onclick="event.stopPropagation()">${actionHTML}</div>
      </div>`;
  }).join('');
}

function formatDateDisplay(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

// ── BOOKING FORM ─────────────────────────────────────────────────────────────

function populateBookForm() {
  const sel = document.getElementById('book-room');
  sel.innerHTML = ''; // Clear default option

  // Group by floor using optgroups
  const floors = [...new Set(_rooms.map(r => r.floor))].sort((a, b) => a - b);
  floors.forEach(f => {
    const grp = document.createElement('optgroup');
    grp.label = `Floor ${f}`;
    _rooms.filter(r => r.floor === f).forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.name;
      opt.textContent = r.name;
      grp.appendChild(opt);
    });
    sel.appendChild(grp);
  });
}

async function verifyAdmin() {
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

async function submitBooking(e) {
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

function showFieldError(el, msg) {
  el.textContent = msg;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── EDIT MODAL ────────────────────────────────────────────────────────────────

let _editId = null;

function openEdit(bookingId) {
  _editId = bookingId;

  // Pre-populate form from live data
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

      // Populate room dropdown grouped by floor
      const sel = document.getElementById('edit-room');
      sel.innerHTML = '';
      const floors = [...new Set(_rooms.map(r => r.floor))].sort((a, b) => a - b);
      floors.forEach(f => {
        const grp = document.createElement('optgroup');
        grp.label = `Floor ${f}`;
        _rooms.filter(r => r.floor === f).forEach(r => {
          const opt = document.createElement('option');
          opt.value = r.name;
          opt.textContent = r.name;
          if (r.name === b.room) opt.selected = true;
          grp.appendChild(opt);
        });
        sel.appendChild(grp);
      });
    });

  document.getElementById('edit-username').value = '';
  document.getElementById('edit-password').value = '';
  document.getElementById('edit-error').classList.add('hidden');
  document.getElementById('edit-modal').classList.remove('hidden');
  setTimeout(() => document.getElementById('edit-username').focus(), 100);
}

function closeEdit() {
  document.getElementById('edit-modal').classList.add('hidden');
  _editId = null;
}

async function confirmEdit() {
  if (!_editId) return;
  const uname = document.getElementById('edit-username').value.trim();
  const pwd = document.getElementById('edit-password').value;
  const errEl = document.getElementById('edit-error');
  const btn = document.getElementById('edit-confirm-btn');
  const label = btn.querySelector('.btn-label');
  const spinner = btn.querySelector('.btn-spinner');

  errEl.classList.add('hidden');

  if (!uname || !pwd) {
    errEl.textContent = 'Please enter admin username and password.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  label.classList.add('hidden');
  spinner.classList.remove('hidden');

  const payload = {
    username: uname,
    password: pwd,
    room: document.getElementById('edit-room').value,
    meeting_mode: document.getElementById('edit-mode').value,
    start_time: document.getElementById('edit-start').value,
    end_time: document.getElementById('edit-end').value,
    attendees: document.getElementById('edit-attendees').value.trim(),
    attendee_emails: document.getElementById('edit-attendees-emails').value.trim(),
    cc_emails: document.getElementById('edit-cc-emails').value.trim(),
  };

  try {
    const res = await fetch(`/api/bookings/${_editId}`, {
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

// ── CANCEL MODAL ─────────────────────────────────────────────────────────────

function openCancel(bookingId) {
  _cancelId = bookingId;

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

  document.getElementById('cancel-name-input').value = '';
  document.getElementById('cancel-username-input').value = '';
  document.getElementById('cancel-password-input').value = '';
  document.getElementById('cancel-error').classList.add('hidden');
  document.getElementById('cancel-modal').classList.remove('hidden');
  setTimeout(() => document.getElementById('cancel-name-input').focus(), 100);
}

function closeCancel() {
  document.getElementById('cancel-modal').classList.add('hidden');
  _cancelId = null;
}

async function confirmCancel() {
  if (!_cancelId) return;
  const name = document.getElementById('cancel-name-input').value.trim();
  const uname = document.getElementById('cancel-username-input').value.trim();
  const pwd = document.getElementById('cancel-password-input').value;
  const errEl = document.getElementById('cancel-error');
  const btn = document.getElementById('cancel-confirm-btn');

  if (!name || !uname || !pwd) {
    errEl.textContent = 'Please enter name, username, and password.';
    errEl.classList.remove('hidden');
    return;
  }

  btn.disabled = true;
  errEl.classList.add('hidden');

  try {
    const res = await fetch(`/api/bookings/${_cancelId}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cancelled_by: name, username: uname, password: pwd }),
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

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('cancel-modal').addEventListener('click', function (e) {
    if (e.target === this) closeCancel();
  });
  document.getElementById('edit-modal').addEventListener('click', function (e) {
    if (e.target === this) closeEdit();
  });
});

// ── TOAST ────────────────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(message, type = 'info', durationMs = 4000) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `toast ${type}`;
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), durationMs);
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function escAttr(str) {
  return esc(str).replace(/'/g, '&#39;');
}