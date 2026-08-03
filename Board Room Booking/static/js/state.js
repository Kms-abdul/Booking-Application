export const state = {
  rooms: [],
  statusByRoom: {},
  lastStatusList: [],
  activeCorridorFloor: 'all',
  activeAgendaFloor: 'all',
  activeAgendaCategory: 'online',
  activeRoomPanel: null,
  cancelId: null,
  editId: null
};

export function roomColor(roomName) {
  const r = state.rooms.find(r => r.name === roomName);
  return r ? r.color : '#c9a468';
}
