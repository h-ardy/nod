// Nod Dot: a tiny dot in a corner of the screen that opens into a review panel when you hold your Nod key.
//
// One transparent, always-on-top window sits in the chosen corner. While the panel is closed the window
// lets every click pass through to whatever is underneath, so the dot never gets in the way. The panel
// itself never approves anything: it only shows the request. Answers come from the key.
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require('electron');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CORNERS = { 'top-right': 'Top right', 'bottom-right': 'Bottom right', 'bottom-left': 'Bottom left', 'top-left': 'Top left' };
const MARGIN = 12;

let win = null;
let tray = null;
let settings = { corner: 'top-right' };
const settingsPath = () => path.join(app.getPath('userData'), 'settings.json');

function loadSettings() {
  try { settings = { ...settings, ...JSON.parse(fs.readFileSync(settingsPath(), 'utf8')) }; } catch (e) { /* first run */ }
  if (!CORNERS[settings.corner]) settings.corner = 'top-right';
}
function saveSettings() {
  try { fs.mkdirSync(path.dirname(settingsPath()), { recursive: true }); fs.writeFileSync(settingsPath(), JSON.stringify(settings, null, 2)); } catch (e) { /* not fatal */ }
}

// Same place the Nod laptop app keeps its port and token (NOD_HOME, or ~/.nod)
function nodConfig() {
  const home = process.env.NOD_HOME || path.join(os.homedir(), '.nod');
  let port = 47823;
  let token = '';
  try { port = JSON.parse(fs.readFileSync(path.join(home, 'config.json'), 'utf8')).port || port; } catch (e) { /* defaults */ }
  try { token = fs.readFileSync(path.join(home, 'token'), 'utf8').trim(); } catch (e) { /* the daemon makes it on first run */ }
  return { port, token, home };
}

// The panel covers about a fifth of the screen: 44% of the width by 48% of the height of the work area.
function bounds() {
  const wa = screen.getPrimaryDisplay().workArea;
  const w = Math.round(Math.min(Math.max(wa.width * 0.44, 460), 900));
  const h = Math.round(Math.min(Math.max(wa.height * 0.48, 360), 720));
  const right = settings.corner.endsWith('right');
  const bottom = settings.corner.startsWith('bottom');
  return {
    x: right ? wa.x + wa.width - w - MARGIN : wa.x + MARGIN,
    y: bottom ? wa.y + wa.height - h - MARGIN : wa.y + MARGIN,
    width: w, height: h,
  };
}

function createWindow() {
  win = new BrowserWindow({
    ...bounds(),
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    focusable: false,              // never steals focus from what you're typing in
    alwaysOnTop: true,
    show: false,
    type: process.platform === 'darwin' ? 'panel' : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
    },
  });
  win.setAlwaysOnTop(true, 'screen-saver');
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.once('ready-to-show', () => win.showInactive());
  win.webContents.on('will-navigate', (e) => e.preventDefault());
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
}

function trayIcon() {
  const file = process.platform === 'darwin' ? 'trayTemplate.png' : 'tray.png';
  const img = nativeImage.createFromPath(path.join(__dirname, 'assets', file));
  if (process.platform === 'darwin') img.setTemplateImage(true);
  return img;
}

function buildMenu() {
  const login = app.getLoginItemSettings().openAtLogin;
  return Menu.buildFromTemplate([
    { label: 'Nod Dot', enabled: false },
    { type: 'separator' },
    { label: 'Corner', submenu: Object.entries(CORNERS).map(([id, label]) => ({
      label, type: 'radio', checked: settings.corner === id,
      click: () => { settings.corner = id; saveSettings(); win.setBounds(bounds()); win.webContents.send('corner', id); },
    })) },
    { label: 'Open at login', type: 'checkbox', checked: login,
      click: (item) => app.setLoginItemSettings({ openAtLogin: item.checked }) },
    { type: 'separator' },
    { label: 'Quit Nod Dot', click: () => app.quit() },
  ]);
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.whenReady().then(() => {
    if (process.platform === 'darwin' && app.dock) app.dock.hide();
    loadSettings();
    createWindow();
    tray = new Tray(trayIcon());
    tray.setToolTip('Nod Dot');
    tray.setContextMenu(buildMenu());
    tray.on('click', () => tray.popUpContextMenu(buildMenu()));
    screen.on('display-metrics-changed', () => win && win.setBounds(bounds()));
    screen.on('display-added', () => win && win.setBounds(bounds()));
    screen.on('display-removed', () => win && win.setBounds(bounds()));
  });
  app.on('window-all-closed', () => app.quit());
}

ipcMain.handle('nod:config', () => ({ ...nodConfig(), corner: settings.corner, platform: process.platform }));
// Closed: every click passes through. Open: the panel takes the mouse so you can scroll the details.
ipcMain.on('nod:expanded', (_e, open) => {
  if (!win) return;
  win.setIgnoreMouseEvents(!open, { forward: true });
});
