const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Config management
  loadDefaultConfig: () => ipcRenderer.invoke('load-default-config'),
  loadConfig: () => ipcRenderer.invoke('load-config'),
  saveConfig: (config) => ipcRenderer.invoke('save-config', config),
  
  // BIDSify execution
  runBidsify: (config, onlyTable, progressCallback) => {
    // Set up progress listener
    ipcRenderer.on('bidsify-progress', (event, data) => {
      if (progressCallback) progressCallback(data);
    });
    
    return ipcRenderer.invoke('run-bidsify', config, onlyTable);
  },
  
  // File operations
  loadConversionTable: (path) => ipcRenderer.invoke('load-conversion-table', path),
  readFile: (path) => ipcRenderer.invoke('read-file', path),
  openFile: () => ipcRenderer.invoke('open-file-dialog'),
  saveFile: (filePath, content) => ipcRenderer.invoke('save-file', { filePath, content }),
  saveFileDialog: (defaultPath, content) => ipcRenderer.invoke('save-file-dialog', { defaultPath, content }),
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  selectFile: () => ipcRenderer.invoke('select-file'),
  
  // Menu triggers
  onTriggerFileOpen: (callback) => ipcRenderer.on('trigger-file-open', callback),
  onTriggerSave: (callback) => ipcRenderer.on('trigger-save', callback),
  onTriggerLoadConfig: (callback) => ipcRenderer.on('trigger-load-config', callback),
  onTriggerSaveConfig: (callback) => ipcRenderer.on('trigger-save-config', callback)
});
