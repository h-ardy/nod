// Nod Dot: a tiny dot in a corner of the screen that opens into a review panel when you hold your Nod key.
//
// One transparent, always-on-top window sits in the chosen corner. While the panel is closed the window
// lets every click pass through to whatever is underneath, so the dot never gets in the way. The panel
// itself never approves anything: it only shows the request. Answers come from the key.
const { app, BrowserWindow, Tray, Menu, ipcMain, screen, nativeImage } = require('electron');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const CORNERS = { 'top-right': 'Top right', 'bottom-right': 'Bottom right', 'bottom-left': 'Bottom left', 'top-left': 'Top left' };
const MARGIN = 12;

let win = null;
let tray = null;
let keyWin = null;
let settings = { corner: 'top-right', practiceKey: true };
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

// ---- practice key: an on-screen Nod for when no real key is around.
// It only works with a daemon started as `nod daemon --sim 1`, so it can never press a real key.
function createKeyWindow() {
  if (keyWin) { keyWin.show(); keyWin.focus(); return; }
  const wa = screen.getPrimaryDisplay().workArea;
  const w = 760, h = 560;
  const saved = settings.keyBounds;
  keyWin = new BrowserWindow({
    width: w, height: h, minWidth: 620, minHeight: 500,
    x: saved ? saved.x : Math.round(wa.x + (wa.width - w) / 2),
    y: saved ? saved.y : Math.round(wa.y + (wa.height - h) / 2),
    title: 'Practice key',
    backgroundColor: '#0F100E',
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    autoHideMenuBar: true,
    fullscreenable: false,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload-key.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  keyWin.loadFile(path.join(__dirname, 'renderer', 'key.html'));
  keyWin.once('ready-to-show', () => keyWin.show());
  keyWin.webContents.on('will-navigate', (e) => e.preventDefault());
  keyWin.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  keyWin.on('close', () => { const b = keyWin.getBounds(); settings.keyBounds = { x: b.x, y: b.y }; saveSettings(); });
  keyWin.on('closed', () => { keyWin = null; });
}

function daemonCall(method, route, body, timeoutMs = 10000) {
  const { port, token } = nodConfig();
  return new Promise((resolve) => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({
      host: '127.0.0.1', port, path: route, method, timeout: timeoutMs,
      headers: { 'Content-Type': 'application/json', 'X-Nod-Token': token, ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}) },
    }, (res) => {
      let out = '';
      res.on('data', (c) => { out += c; });
      res.on('end', () => { try { resolve({ status: res.statusCode, ...JSON.parse(out) }); } catch (e) { resolve({ status: res.statusCode, error: 'bad reply' }); } });
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', (e) => resolve({ status: 0, error: e.message }));
    if (data) req.write(data);
    req.end();
  });
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
    { label: 'Practice key', type: 'checkbox', checked: !!keyWin,
      click: (item) => { settings.practiceKey = item.checked; saveSettings(); if (item.checked) createKeyWindow(); else if (keyWin) keyWin.close(); } },
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
    if (settings.practiceKey) createKeyWindow();
    screen.on('display-metrics-changed', () => win && win.setBounds(bounds()));
    screen.on('display-added', () => win && win.setBounds(bounds()));
    screen.on('display-removed', () => win && win.setBounds(bounds()));
  });
  app.on('window-all-closed', () => { /* the dot window stays; closing the practice key is fine */ });
}

ipcMain.handle('nod:config', () => ({ ...nodConfig(), corner: settings.corner, platform: process.platform }));
// Closed: every click passes through. Open: the panel takes the mouse so you can scroll the details.
ipcMain.on('nod:expanded', (_e, open) => {
  if (!win) return;
  win.setIgnoreMouseEvents(!open, { forward: true });
});

// Practice key. Sending waits for the answer (like a real agent would) and reports it back.
ipcMain.handle('key:config', () => { const c = nodConfig(); return { port: c.port, token: c.token }; });
ipcMain.handle('key:press', (_e, kind) => daemonCall('POST', '/v1/sim/press', { lane: 0, kind: ['tap', 'double', 'hold'].includes(kind) ? kind : 'tap' }));
ipcMain.on('key:send', async (e, req) => {
  const body = {
    source: String(req.source || '*').slice(0, 32), l1: String(req.l1 || '').slice(0, 200), l2: String(req.l2 || '').slice(0, 400),
    l3: String(req.l3 || '').slice(0, 200), risky: !!req.risky, detail: String(req.detail || '').slice(0, 20000), why: String(req.why || '').slice(0, 600),
    wait: 600,
  };
  const res = await daemonCall('POST', '/v1/ask', body, 620000);
  if (!e.sender.isDestroyed()) e.sender.send('key:answer', { tag: req.tag, decision: res.decision || 'unavailable', error: res.error || '' });
});
