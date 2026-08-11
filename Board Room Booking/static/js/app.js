import * as ui from './ui.js';
import * as rooms from './rooms.js';
import * as calendar from './calendar.js';
import * as booking from './booking.js';
import * as modal from './modal.js';

window.enterFloor = ui.enterFloor;
window.openSideDrawer = ui.openSideDrawer;
window.closeSideDrawer = ui.closeSideDrawer;
window.selectDrawerTab = ui.selectDrawerTab;
window.closeBookNotification = ui.closeBookNotification;
window.scrollHallway = ui.scrollHallway;

window.setCorridorFloor = rooms.setCorridorFloor;
window.openRoomPanel = rooms.openRoomPanel;
window.closeRoomPanel = rooms.closeRoomPanel;
window.goBookRoom = rooms.goBookRoom;

window.loadAgenda = calendar.loadAgenda;
window.setAgendaCategory = calendar.setAgendaCategory;
window.setAgendaFloor = calendar.setAgendaFloor;

window.verifyUser = booking.verifyUser;
window.submitBooking = booking.submitBooking;
window.forgotPin = booking.forgotPin;
window.openAdminPanel = booking.openAdminPanel;
window.closeAdminPanel = booking.closeAdminPanel;
window.createUser = booking.createUser;
window.deleteUser = booking.deleteUser;
window.openEdit = modal.openEdit;
window.closeEdit = modal.closeEdit;
window.confirmEdit = modal.confirmEdit;

window.openCancel = modal.openCancel;
window.closeCancel = modal.closeCancel;
window.confirmCancel = modal.confirmCancel;

document.addEventListener('DOMContentLoaded', () => {
  ui.initDateDefaults();
  rooms.loadRooms().then(() => {
    rooms.renderFloorTabs();
    rooms.loadStatus();
    calendar.loadAgenda();
    booking.populateBookForm();
  });
  ui.startClock();
  
  // Single polling loop utilizing AbortController
  setInterval(() => {
    rooms.loadStatus();
  }, 60_000);

  const track = document.getElementById('hallway-track');
  if (track) {
    track.addEventListener('scroll', ui.onHallwayScroll, { passive: true });
  }
  
  ui.initFormTextareas();
  modal.initModalListeners();
});