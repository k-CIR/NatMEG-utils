const { app, BrowserWindow, dialog, ipcMain, Menu } = require('electron');
const path = require('path');
const fs = require('fs').promises;
const fsSync = require('fs');
const { spawn } = require('child_process');
const yaml = require('js-yaml');

let mainWindow;
let pythonProcess = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 800,
    backgroundColor: '#f8f8f8',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: path.join(__dirname, 'assets', 'icon.png')
  });

  // Load the new pipeline interface
  mainWindow.loadFile(path.join(__dirname, 'index.html'));

  // Create application menu
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'Load Configuration...',
          accelerator: 'CmdOrCtrl+O',
          click: () => {
            mainWindow.webContents.send('trigger-load-config');
          }
        },
        {
          label: 'Save Configuration',
          accelerator: 'CmdOrCtrl+S',
          click: () => {
            mainWindow.webContents.send('trigger-save-config');
          }
        },
        { type: 'separator' },
        { role: 'quit' }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About NatMEG-BIDSifier',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About NatMEG-BIDSifier',
              message: 'NatMEG-BIDSifier v1.0.0',
              detail: 'BIDS Conversion Tool for MEG Data\n\nDeveloped at NatMEG, Karolinska Institutet',
              buttons: ['OK']
            });
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools();
  }
}

// Handle file open dialog
ipcMain.handle('open-file-dialog', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'TSV Files', extensions: ['tsv'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (result.canceled) {
    return null;
  }

  const filePath = result.filePaths[0];
  const content = await fs.readFile(filePath, 'utf-8');
  
  return {
    path: filePath,
    name: path.basename(filePath),
    content: content
  };
});

// Handle directory selection
ipcMain.handle('select-directory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result;
});

// Handle file selection
ipcMain.handle('select-file', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Calibration/Crosstalk Files', extensions: ['dat', 'fif'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });
  return result;
});

// Handle file save
ipcMain.handle('save-file', async (event, { filePath, content }) => {
  try {
    await fs.writeFile(filePath, content, 'utf-8');
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// Handle save-as dialog
ipcMain.handle('save-file-dialog', async (event, { defaultPath, content }) => {
  const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultPath,
    filters: [
      { name: 'TSV Files', extensions: ['tsv'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (result.canceled) {
    return { success: false, canceled: true };
  }

  try {
    await fs.writeFile(result.filePath, content, 'utf-8');
    return { success: true, filePath: result.filePath };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// Clean up on quit
app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});

// ========== IPC Handlers for Pipeline ==========

// Load default config
ipcMain.handle('load-default-config', async () => {
  try {
    const configPath = path.join(__dirname, 'default_bids_config.yml');
    const content = await fs.readFile(configPath, 'utf-8');
    const config = yaml.load(content);
    return config;
  } catch (error) {
    console.error('Error loading default config:', error);
    return null;
  }
});

// Load config file
ipcMain.handle('load-config', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'YAML Config', extensions: ['yml', 'yaml'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  });

  if (result.canceled) {
    return null;
  }

  try {
    const filePath = result.filePaths[0];
    const content = await fs.readFile(filePath, 'utf-8');
    const config = yaml.load(content);
    return { config, path: filePath };
  } catch (error) {
    return { error: error.message };
  }
});

// Save config file
ipcMain.handle('save-config', async (event, config) => {
const result = await dialog.showSaveDialog(mainWindow, {
    defaultPath: path.join(app.getPath('documents'), 'bids_config.yml'),
    filters: [
        { name: 'YAML Config', extensions: ['yml', 'yaml'] },
        { name: 'All Files', extensions: ['*'] }
    ]
});

  if (result.canceled) {
    return { success: false, canceled: true };
  }

  try {
    const yamlContent = yaml.dump(config, { lineWidth: -1 });
    await fs.writeFile(result.filePath, yamlContent, 'utf-8');
    return { success: true, filePath: result.filePath };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// Helper function to find bundled or system Python
function getPythonExecutable() {
  const isDev = !app.isPackaged;
  
  if (isDev) {
    // Development: Check for virtual environment, fall back to system Python
    const venvPath = path.join(__dirname, 'resources', 'python_env');
    const venvPython = process.platform === 'win32' 
      ? path.join(venvPath, 'Scripts', 'python.exe')
      : path.join(venvPath, 'bin', 'python3');
    
    if (fsSync.existsSync(venvPath)) {
      return venvPython;
    }
    return process.platform === 'win32' ? 'python' : 'python3';
  } else {
    // Production: Use bundled Python executable or virtual environment
    const resourcesPath = process.resourcesPath || path.join(__dirname, 'resources');
    
    // Option 1: PyInstaller standalone executable
    const standalonePath = path.join(resourcesPath, 'python', 'bidsify');
    if (fsSync.existsSync(standalonePath)) {
      return standalonePath;
    }
    
    // Option 2: Virtual environment
    const venvPython = process.platform === 'win32'
      ? path.join(resourcesPath, 'python_env', 'Scripts', 'python.exe')
      : path.join(resourcesPath, 'python_env', 'bin', 'python3');
    
    if (fsSync.existsSync(venvPython)) {
      return venvPython;
    }
    
    // Fallback to system Python
    return process.platform === 'win32' ? 'python' : 'python3';
  }
}

// Run bidsify.py with config
ipcMain.handle('run-bidsify', async (event, config, onlyTable = false) => {
  return new Promise((resolve) => {
    try {
      // Create temporary config file
      const tempConfigPath = path.join(app.getPath('temp'), 'natmeg_config_temp.yml');
      const yamlContent = yaml.dump(config, { lineWidth: -1 });
      fs.writeFile(tempConfigPath, yamlContent, 'utf-8').then(() => {
        
        // Find Python executable and bidsify.py
        const pythonExe = getPythonExecutable();
        const isDev = !app.isPackaged;
        const bidsifyPath = isDev 
          ? path.join(__dirname, '..', 'bidsify.py')
          : path.join(process.resourcesPath || __dirname, 'bidsify.py');
        
        // Build command arguments
        const args = [bidsifyPath, '--config', tempConfigPath];
        if (onlyTable) {
          args.splice(1, 0, '--only-table'); // Insert --only-table after bidsifyPath
        }
        
        // Spawn Python process
        pythonProcess = spawn(pythonExe, args);
        
        let output = '';
        let errorOutput = '';
        
        // Capture stdout
        pythonProcess.stdout.on('data', (data) => {
          const text = data.toString();
          output += text;
          
          // Send progress updates to renderer
          mainWindow.webContents.send('bidsify-progress', {
            line: text,
            progress: calculateProgress(output)
          });
        });
        
        // Capture stderr
        pythonProcess.stderr.on('data', (data) => {
          const text = data.toString();
          errorOutput += text;
          
          mainWindow.webContents.send('bidsify-progress', {
            line: text,
            type: 'error'
          });
        });
        
        // Handle process completion
        pythonProcess.on('close', (code) => {
          pythonProcess = null;
          
          // Clean up temp file
          fs.unlink(tempConfigPath).catch(() => {});
          
          if (code === 0) {
            // Determine the conversion table path
            const conversionFile = config.BIDS?.Conversion_file || 'bids_conversion.tsv';
            const conversionTablePath = path.join(config.Project.BIDS, 'conversion_logs', conversionFile);
            
            resolve({ 
              success: true, 
              output: output,
              conversionTablePath: conversionTablePath
            });
          } else {
            resolve({ 
              success: false, 
              error: errorOutput || `Process exited with code ${code}`,
              output: output
            });
          }
        });
        
        pythonProcess.on('error', (error) => {
          pythonProcess = null;
          resolve({ success: false, error: error.message });
        });
        
      }).catch(error => {
        resolve({ success: false, error: error.message });
      });
      
    } catch (error) {
      resolve({ success: false, error: error.message });
    }
  });
});

// Calculate progress from output (simple heuristic)
function calculateProgress(output) {
  // Look for common progress indicators
  if (output.includes('Creating dataset description')) return 10;
  if (output.includes('Scanning files')) return 20;
  if (output.includes('Building conversion table')) return 40;
  if (output.includes('Converting files')) return 60;
  if (output.includes('Writing sidecars')) return 80;
  if (output.includes('Complete') || output.includes('Finished')) return 100;
  return 30; // Default progress
}

// Read file content
ipcMain.handle('read-file', async (event, filePath) => {
  try {
    const content = await fs.readFile(filePath, 'utf-8');
    return content;
  } catch (error) {
    console.error('Error reading file:', error);
    throw error;
  }
});

// Load conversion table
ipcMain.handle('load-conversion-table', async (event, tsvPath) => {
  try {
    const content = await fs.readFile(tsvPath, 'utf-8');
    return {
      path: tsvPath,
      name: path.basename(tsvPath),
      content: content
    };
  } catch (error) {
    console.error('Error loading conversion table:', error);
    return null;
  }
});
