import { todayISO, esc } from './utils.js';
import { loadStatus } from './rooms.js';
import { loadAgenda } from './calendar.js';

export function showTab(tab) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.remove('active');
    b.setAttribute('aria-selected', 'false');
  });
  document.querySelectorAll('.drawer-nav-item, .desktop-nav-item').forEach(b => {
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

  const desktopBtn = document.getElementById(`desktop-tab-${tab}`);
  if (desktopBtn) {
    desktopBtn.classList.add('active');
  }

  if (tab === 'corridor') loadStatus();
  if (tab === 'agenda') loadAgenda();

  if (tab === 'book') {
    showBookNotification();
  } else {
    closeBookNotification();
  }
}

export function enterFloor() {
  const veil = document.getElementById('entry-veil');
  if(veil) veil.classList.add('entered');
  showTab('about');
}

export function showBookNotification() {
  const popup = document.getElementById('book-notification-popup');
  if (popup) {
    popup.classList.add('show');
    popup.classList.add('blink-active');
  }
}

export function closeBookNotification(event) {
  if (event) event.stopPropagation();
  const popup = document.getElementById('book-notification-popup');
  if (popup) {
    popup.classList.remove('show');
    popup.classList.remove('blink-active');
  }
}

export function openSideDrawer() {
  const drawer = document.getElementById('side-nav-drawer');
  if (drawer) {
    drawer.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
}

export function closeSideDrawer() {
  const drawer = document.getElementById('side-nav-drawer');
  if (drawer) {
    drawer.classList.add('hidden');
    document.body.style.overflow = '';
  }
}

export function selectDrawerTab(tab) {
  showTab(tab);
  closeSideDrawer();
}

export function startClock() {
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

export function initDateDefaults() {
  const today = todayISO();
  const agendaDate = document.getElementById('agenda-date');
  const bookDate = document.getElementById('book-date');
  if (agendaDate) agendaDate.value = today;
  if (bookDate) bookDate.value = today;
}

export function initFormTextareas() {
  const ids = ['book-attendees-emails', 'book-cc-emails', 'book-description', 'edit-attendees-emails', 'edit-cc-emails', 'edit-description'];
  ids.forEach(setupAutoResizeTextarea);
  
  ['book-attendees-emails', 'book-cc-emails', 'edit-attendees-emails', 'edit-cc-emails'].forEach(setupEmailDefaultDomain);
}

function setupAutoResizeTextarea(id) {
  const el = document.getElementById(id);
  if (!el) return;

  function resize() {
    el.style.height = 'auto';
    el.style.height = el.scrollHeight + 'px';
  }

  el.addEventListener('input', resize);
  el.addEventListener('focus', resize);
}

function setupEmailDefaultDomain(id) {
  const el = document.getElementById(id);
  if (!el) return;

  const domain = '@mseducation.academy';

  el.addEventListener('focus', () => {
    if (!el.value.trim()) {
      el.value = domain;
      setTimeout(() => el.setSelectionRange(0, 0), 0);
    }
  });

  el.addEventListener('blur', () => {
    if (el.value.trim() === domain || el.value.trim() === '') {
      el.value = '';
      el.style.height = '44px';
    }
  });

  el.addEventListener('input', () => {
    if (el.value === '') return;
    const val = el.value;
    const cursor = el.selectionStart;
    const lastChar = val.charAt(cursor - 1);
    
    if (lastChar === ',' || lastChar === ';') {
      const textBefore = val.slice(0, cursor - 1).trim();
      const textAfter = val.slice(cursor).trim();
      const emailsBefore = textBefore.split(/[,;]/);
      const lastEmail = emailsBefore[emailsBefore.length - 1].trim();

      if (lastEmail && !lastEmail.includes('@')) {
        emailsBefore[emailsBefore.length - 1] = lastEmail + domain;
      }

      const newTextBefore = emailsBefore.join(', ') + ', ';
      const newTextAfter = textAfter || domain;
      
      el.value = newTextBefore + newTextAfter;
      const targetCursor = newTextBefore.length;
      el.setSelectionRange(targetCursor, targetCursor);
    }
  });

  el.addEventListener('paste', () => {
    setTimeout(() => {
      const val = el.value;
      const parts = val.split(/[,;]/);
      const formatted = parts.map(part => {
        const trimmed = part.trim();
        if (trimmed && !trimmed.includes('@')) {
          return trimmed + domain;
        }
        return trimmed;
      }).filter(Boolean).join(', ');
      
      el.value = formatted;
      el.dispatchEvent(new Event('input'));
    }, 0);
  });
}

export function showFieldError(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

let _hallwayScrollRAF = null;
export function onHallwayScroll() {
  if (_hallwayScrollRAF) return;
  _hallwayScrollRAF = requestAnimationFrame(() => {
    updateDoorFocus();
    _hallwayScrollRAF = null;
  });
}

export function updateDoorFocus() {
  const track = document.getElementById('hallway-track');
  if (!track) return;
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

    const rotate = ((doorCenter - center) / trackRect.width) * 34;
    const scale = 1 - norm * 0.16;
    const z = -norm * 90;
    door.style.transform = `translateZ(${z}px) rotateY(${-rotate}deg) scale(${scale})`;
    door.classList.toggle('is-center', norm < 0.18);

    if (dist < closestDist) { closestDist = dist; closestIdx = i; }
  });

  document.querySelectorAll('.hallway-dot').forEach((dot, i) => dot.classList.toggle('active', i === closestIdx));
}

export function scrollHallway(dir) {
  const track = document.getElementById('hallway-track');
  if (!track) return;
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
