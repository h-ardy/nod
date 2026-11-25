// Bridge for the practice key window: send a made-up request, press the on-screen key, hear the answer.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nodKey', {
  config: () => ipcRenderer.invoke('key:config'),
  press: (kind) => ipcRenderer.invoke('key:press', kind),
  send: (req) => ipcRenderer.send('key:send', req),
  onAnswer: (fn) => ipcRenderer.on('key:answer', (_e, a) => fn(a)),
});
