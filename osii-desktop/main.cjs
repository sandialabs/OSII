'use strict';
const { app, BrowserWindow, dialog, ipcMain, Menu, session, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const { RuntimeClient, validRuntimeSession } = require('./runtime-client.cjs');

const welcomeUrl = pathToFileURL(path.join(__dirname, 'welcome.html')).href;
let window;
let runtime;
let active;
let stopping = false;
let allowExit = false;
let dataDirectory;

app.setName('OSII Standalone');
if (process.platform === 'win32') app.setAppUserModelId('org.osii.standalone');
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.focus(); } });
  app.on('window-all-closed', () => app.quit());
  app.on('before-quit', event => {
    if (allowExit) return;
    event.preventDefault();
    if (stopping) return;
    stopping = true;
    if (window && !window.isDestroyed()) window.setTitle('OSII — stopping safely…');
    Promise.resolve(runtime?.shutdown()).finally(() => { allowExit = true; app.exit(0); });
  });
  app.whenReady().then(start).catch(error => {
    dialog.showErrorBox('OSII could not start', error.message);
    app.quit();
  });
}

function verifyWelcome(event) {
  if (event.sender !== window?.webContents || event.senderFrame?.url !== welcomeUrl) {
    throw new Error('This operation belongs to the OSII library chooser.');
  }
}

function status(message) {
  if (window && !window.isDestroyed() && window.webContents.getURL() === welcomeUrl) {
    window.webContents.send('desktop:status', message);
  }
}

async function exportDiagnostics() {
  const selected = await dialog.showSaveDialog(window, {
    title: 'Export OSII diagnostics', defaultPath: 'OSII-diagnostics.json',
    filters: [{ name: 'Diagnostics', extensions: ['json'] }],
  });
  if (selected.canceled || !selected.filePath) return;
  const lifecycle = [];
  for (const filename of ['lifecycle.jsonl.3', 'lifecycle.jsonl.2', 'lifecycle.jsonl.1', 'lifecycle.jsonl']) {
    try {
      const content = await fs.readFile(path.join(dataDirectory, 'logs', filename), 'utf8');
      for (const line of content.trim().split('\n')) {
        try {
          const record = JSON.parse(line);
          // Construct fresh allowlisted records; never copy arbitrary logs.
          lifecycle.push({ time: record.time, service: record.service, event: record.event,
            ...(Number.isInteger(record.exit_code) ? { exit_code: record.exit_code } : {}) });
        } catch { /* Ignore a partially written final line. */ }
      }
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  await fs.writeFile(selected.filePath, JSON.stringify({ version: app.getVersion(), platform: process.platform,
    architecture: process.arch, lifecycle }, null, 2) + '\n', { mode: 0o600 });
}

async function showChooser() {
  if (stopping) return;
  if (active) await runtime.request('close_library');
  active = undefined;
  window.setTitle('OSII Standalone');
  await window.loadURL(welcomeUrl);
}

function installMenu() {
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Library', submenu: [
      { label: 'Choose library…', click: () => showChooser().catch(showError) },
      { type: 'separator' }, { role: 'quit' },
    ] },
    { label: 'Edit', submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' },
      { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'selectAll' }] },
    { label: 'View', submenu: [{ role: 'reload' }, { role: 'resetZoom' }, { role: 'zoomIn' }, { role: 'zoomOut' }, { role: 'togglefullscreen' }] },
    { label: 'Help', submenu: [
      { label: 'Export diagnostics…', click: () => exportDiagnostics().catch(showError) },
      { label: 'Open logs folder', click: () => shell.openPath(path.join(dataDirectory, 'logs')) },
      { label: 'About OSII', click: () => dialog.showMessageBox(window, { type: 'info', title: 'OSII Standalone',
        message: `OSII Standalone ${app.getVersion()}`, detail: 'Common document extraction, full-page OCR and keyword search work offline. AI uses an optional model connection. Updates are installed using a new OSII installer.' }) },
    ] },
  ]));
}

function showError(error) {
  if (!stopping) dialog.showMessageBox(window, { type: 'error', title: 'OSII', message: String(error.message ?? error) });
}

async function start() {
  dataDirectory = process.env.OSII_DESKTOP_DATA_DIR || (process.platform === 'win32'
    ? path.join(process.env.LOCALAPPDATA || path.join(app.getPath('home'), 'AppData', 'Local'), 'OSII')
    : path.join(app.getPath('appData'), 'OSII Standalone'));
  dataDirectory = path.resolve(dataDirectory);
  app.setPath('userData', path.join(dataDirectory, 'desktop'));
  await fs.mkdir(dataDirectory, { recursive: true });
  const browserSession = session.fromPartition('osii-' + crypto.randomUUID());
  await browserSession.setProxy({ mode: 'direct' }); // This session accesses only bundled/local content.
  browserSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  browserSession.setPermissionCheckHandler(() => false);
  browserSession.webRequest.onBeforeRequest({ urls: ['<all_urls>'] }, (details, callback) => {
    const target = new URL(details.url);
    const allowedFile = ['welcome.html', 'welcome.css', 'welcome.js'].some(name => details.url === pathToFileURL(path.join(__dirname, name)).href);
    const allowed = allowedFile || (active && target.origin === active.url) || ['data:', 'blob:', 'devtools:'].includes(target.protocol);
    callback({ cancel: !allowed });
  });
  browserSession.webRequest.onBeforeSendHeaders({ urls: ['http://127.0.0.1:*/*'] }, (details, callback) => {
    const headers = { ...details.requestHeaders };
    if (active && new URL(details.url).origin === active.url) headers.Authorization = 'Bearer ' + active.token;
    callback({ requestHeaders: headers });
  });
  window = new BrowserWindow({ width: 1320, height: 900, minWidth: 880, minHeight: 640, show: false,
    backgroundColor: '#f5f7f9', title: 'OSII Standalone',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), session: browserSession,
      nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true, spellcheck: false } });
  window.once('ready-to-show', () => window.show());
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.on('will-navigate', (event, url) => {
    if (url !== welcomeUrl && (!active || new URL(url).origin !== active.url)) event.preventDefault();
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    try { if (['https:', 'http:'].includes(new URL(url).protocol)) shell.openExternal(url).catch(showError); } catch { /* Reject other protocols. */ }
    return { action: 'deny' };
  });
  installMenu();

  let executable, args;
  if (app.isPackaged) {
    executable = path.join(process.resourcesPath, 'runtime', process.platform === 'win32' ? 'osii-runtime.exe' : 'osii-runtime');
    args = ['supervisor', '--data-dir', dataDirectory];
  } else {
    const root = path.resolve(__dirname, '..');
    executable = process.env.OSII_DESKTOP_PYTHON || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    args = [path.join(root, 'scripts', 'standalone_runtime.py'), 'supervisor', '--data-dir', dataDirectory];
  }
  const child = spawn(executable, args, { cwd: dataDirectory, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  // Consume startup stderr without recording potentially sensitive exception text.
  child.stderr.resume();
  runtime = new RuntimeClient(child);
  runtime.on('runtime-failed', error => {
    active = undefined;
    window.loadURL(welcomeUrl).then(() => status({ error })).catch(showError);
  });
  runtime.on('stopped', () => {
    active = undefined;
    if (!stopping) window.loadURL(welcomeUrl).then(() => status({ error: 'The OSII runtime stopped. Close and reopen OSII to recover queued work.' })).catch(showError);
  });
  registerCommands();
  await window.loadURL(welcomeUrl);
  await runtime.ready;
  status({ ready: true });
}

function registerCommands() {
  ipcMain.handle('desktop:profiles', async event => { verifyWelcome(event); return runtime.request('profiles'); });
  ipcMain.handle('desktop:choose-folder', async event => {
    verifyWelcome(event);
    const selected = await dialog.showOpenDialog(window, { properties: ['openDirectory'], title: 'Choose folder' });
    return selected.canceled ? '' : selected.filePaths[0];
  });
  ipcMain.handle('desktop:create-profile', async (event, fields) => {
    verifyWelcome(event);
    if (!fields || typeof fields !== 'object') throw new Error('Choose library folders first.');
    const profile = {};
    for (const name of ['name', 'source', 'library', 'config']) {
      if (fields[name] !== undefined && (typeof fields[name] !== 'string' || fields[name].length > 32768)) throw new Error('Invalid library folder');
      profile[name] = fields[name] ?? '';
    }
    profile.existing = fields.existing === true;
    return runtime.request('create_profile', { profile });
  });
  ipcMain.handle('desktop:open-profile', async (event, identifier) => {
    verifyWelcome(event);
    if (typeof identifier !== 'string' || identifier.length !== 36) throw new Error('Choose a saved library.');
    status({ starting: true });
    const selected = await runtime.request('open_profile', { profile_id: identifier });
    if (!validRuntimeSession(selected)) {
      await runtime.request('close_library');
      throw new Error('The bundled runtime returned an invalid local address.');
    }
    active = { ...selected, url: new URL(selected.url).origin };
    window.setTitle(`OSII — ${selected.profile.name}`);
    await window.loadURL(active.url);
    return { opened: true };
  });
  ipcMain.handle('desktop:information', event => { verifyWelcome(event); return { version: app.getVersion() }; });
  ipcMain.handle('desktop:diagnostics', async event => { verifyWelcome(event); await exportDiagnostics(); });
}
