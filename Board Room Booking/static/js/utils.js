export function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

export function escAttr(str) {
  return esc(str).replace(/'/g, '&#39;');
}

export function formatDateDisplay(iso) {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

export function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

let _toastTimer = null;
export function showToast(message, type = 'info', durationMs = 4000) {
  const el = document.getElementById('toast');
  if(!el) return;
  el.textContent = message;
  el.className = `toast ${type}`;
  void el.offsetWidth;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), durationMs);
}
