const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  openFile: () => ipcRenderer.invoke('open-file-dialog'),
  saveFile: (filePath, content) => ipcRenderer.invoke('save-file', { filePath, content }),
  saveFileDialog: (defaultPath, content) => ipcRenderer.invoke('save-file-dialog', { defaultPath, content }),
  onTriggerFileOpen: (callback) => ipcRenderer.on('trigger-file-open', callback),
  onTriggerSave: (callback) => ipcRenderer.on('trigger-save', callback)
});
