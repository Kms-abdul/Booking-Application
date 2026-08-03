import { state, roomColor } from './state.js';
import { fetchWithAbort } from './api.js';
import { esc, escAttr, todayISO } from './utils.js';
import { updateDoorFocus, showTab } from './ui.js';

const STATUS_LABEL = {
  vacant: 'Available',
  engaged: 'In progress',
  soon: 'Starting soon',
  closed: 'Closed',
};

const DOM = {
  track: null,
  dots: null
};

export async function loadRooms() {
  try {
    const data = await fetchWithAbort('/api/rooms', {}, 'rooms');
    if (data && data.ok) state.rooms = data.rooms;
  } catch (_) { }
}

export async function loadStatus() {
  if (!DOM.track) {
    DOM.track = document.getElementById('hallway-track');
    DOM.dots = document.getElementById('hallway-dots');
  }
  try {
    const data = await fetchWithAbort('/api/status', {}, 'status');
    if (data && data.aborted) return;
    if (!data.ok) throw new Error(data.error);
    
    state.statusByRoom = {};
    data.status.forEach(r => { state.statusByRoom[r.room] = r; });
    state.lastStatusList = data.status;
    renderHallway(_filterStatusByFloor(data.status, state.activeCorridorFloor));
  } catch (err) {
    if (DOM.track) {
      DOM.track.innerHTML = `<p class="empty-state">⚠️ Could not load room status.<br><small>${esc(err.message)}</small></p>`;
    }
  }
}

function _filterStatusByFloor(statusList, floor) {
  if (floor === 'all') return statusList;
  return statusList.filter(r => {
    const room = state.rooms.find(rm => rm.name === r.room);
    return room && String(room.floor) === String(floor);
  });
}

function getDoorHTML(room) {
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
  
  const stateHash = engaged ? `engaged-${cur?.id}` : `vacant-${nxt?.id || 'none'}`;

  return `
    <div class="door" data-room="${escAttr(room.room)}" data-status="${statusKey}" data-state-hash="${stateHash}" style="--room-color:${color}" onclick="openRoomPanel('${escAttr(room.room)}')">
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
}

export function renderHallway(statusList) {
  if (!DOM.track) return;

  if (!statusList.length) {
    DOM.track.innerHTML = '<p class="empty-state">No rooms configured.</p>';
    DOM.dots.innerHTML = '';
    return;
  }

  const currentDoors = Array.from(DOM.track.querySelectorAll('.door'));
  const needsFullRebuild = currentDoors.length !== statusList.length || 
                           currentDoors.some((door, idx) => door.dataset.room !== statusList[idx].room);

  if (needsFullRebuild) {
    DOM.track.innerHTML = statusList.map(room => getDoorHTML(room)).join('');
    DOM.dots.innerHTML = statusList.map((_, i) => `<span class="hallway-dot" data-i="${i}"></span>`).join('');
    
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
  } else {
    statusList.forEach((room, idx) => {
      const door = currentDoors[idx];
      const engaged = room.status === 'engaged';
      const cur = room.current_booking;
      const nxt = room.next_booking;
      const stateHash = engaged ? `engaged-${cur?.id}` : `vacant-${nxt?.id || 'none'}`;
      
      if (door.dataset.stateHash !== stateHash) {
        door.outerHTML = getDoorHTML(room);
      }
    });
  }
}

export function renderFloorTabs() {
  const floors = [...new Set(state.rooms.map(r => r.floor).filter(Boolean))].sort((a, b) => a - b);

  const sub = document.getElementById('entry-subtitle');
  if (sub && floors.length) {
    sub.textContent = `Floors ${floors.join(' · ')} — walk the corridor and see what's free.`;
  }

  const corrContainer = document.getElementById('corridor-floor-tabs');
  if (corrContainer) {
    let html = `<button class="floor-tab active" data-floor="all" onclick="setCorridorFloor('all')">All Floors</button>`;
    floors.forEach(f => {
      const suffix = f === 1 ? 'st' : f === 2 ? 'nd' : f === 3 ? 'rd' : 'th';
      html += `<button class="floor-tab" data-floor="${f}" onclick="setCorridorFloor('${f}')">${f}<sup>${suffix}</sup> Floor</button>`;
    });
    corrContainer.innerHTML = html;
  }

  const agendaContainer = document.getElementById('agenda-floor-tabs');
  if (agendaContainer) {
    let html = `<button class="floor-tab active" data-floor="all" onclick="setAgendaFloor('all')">All</button>`;
    floors.forEach(f => {
      html += `<button class="floor-tab" data-floor="${f}" onclick="setAgendaFloor('${f}')">${f}F</button>`;
    });
    agendaContainer.innerHTML = html;
  }
}

function _setFloorTab(containerId, floor) {
  document.querySelectorAll(`#${containerId} .floor-tab`).forEach(btn => {
    btn.classList.toggle('active', btn.dataset.floor === floor);
  });
}

export function setCorridorFloor(floor) {
  state.activeCorridorFloor = floor;
  _setFloorTab('corridor-floor-tabs', floor);
  renderHallway(_filterStatusByFloor(state.lastStatusList, floor));
}

export async function openRoomPanel(roomName) {
  state.activeRoomPanel = roomName;
  const panel = document.getElementById('room-panel');
  const body = document.getElementById('room-panel-body');
  const status = state.statusByRoom[roomName];
  const color = roomColor(roomName);
  const engaged = status && status.status === 'engaged';

  const roomObj = state.rooms.find(r => r.name === roomName);
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
          ${status.current_booking.description ? `<br/>📝 <b>Purpose:</b> ${esc(status.current_booking.description)}` : ''}
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

export async function loadRoomTimeline(roomName) {
  const el = document.getElementById('rp-timeline');
  try {
    const params = new URLSearchParams({ date: todayISO(), room: roomName });
    const data = await fetchWithAbort(`/api/bookings?${params}`, {}, `timeline-${roomName}`);
    if (data && data.aborted) return;
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
      const descHTML = b.description ? `<div style="font-size: 11px; color: var(--text-mute); margin-top: 4px; font-style: italic;">📝 <b>Purpose:</b> ${esc(b.description)}</div>` : '';
      return `
        <div class="rp-timeline-item" style="flex-direction: column; align-items: flex-start; gap: 4px;">
          <div style="display: flex; align-items: center; width: 100%; justify-content: space-between; gap: 10px;">
            <span class="rp-timeline-time">${b.start_time} – ${b.end_time}</span>
            ${modeHTML}
          </div>
          <div class="rp-timeline-title" style="font-size: 0.86rem; font-weight: 500;">
            ${esc(b.title)} <span style="font-weight: normal; font-size: 0.78rem; color: var(--text-mute);">by ${esc(b.booked_by)}</span>
          </div>
          ${descHTML}
        </div>`;
    }).join('');
  } catch (err) {
    el.innerHTML = `<p class="empty-state" style="padding:16px 0">⚠️ ${esc(err.message)}</p>`;
  }
}

export function closeRoomPanel() {
  document.getElementById('room-panel').classList.add('hidden');
  document.body.style.overflow = '';
  state.activeRoomPanel = null;
}

export function goBookRoom(roomName) {
  closeRoomPanel();
  showTab('book');
  const sel = document.getElementById('book-room');
  if (sel && roomName) sel.value = roomName;
}
