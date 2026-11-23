// The only bridge between the panel and the app: read the daemon's port and token, say whether
// the panel is open (so clicks pass through while it is closed), and hear when the corner changes.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('nodApp', {
  config: () => ipcRenderer.invoke('nod:config'),
  setExpanded: (open) => ipcRenderer.send('nod:expanded', !!open),
  onCorner: (fn) => ipcRenderer.on('corner', (_e, corner) => fn(corner)),
});
