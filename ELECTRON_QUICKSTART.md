# NatMEG-BIDSifier Setup & Quick Start

## 🚀 Quick Start (Development)

### 1. Run the Desktop App
```bash
./run-app.sh
```
OR
```bash
cd electron
npm start
```

### 2. Use the App
- Click **"📂 Open TSV File"** or press **Cmd+O** (Mac) / **Ctrl+O** (Windows/Linux)
- Browse and select your `bids_conversion.tsv` file
- Edit the table as needed
- Click **"💾 Save Changes"** or press **Cmd+S** / **Ctrl+S**
- File is automatically overwritten (no manual file replacement needed!)

## 📦 Building for Distribution

### Build for Your Platform
```bash
cd electron
npm run build:mac      # macOS only
npm run build:win      # Windows only  
npm run build:linux    # Linux only
npm run build          # All platforms
```

### Distribute
Built apps are in `electron/dist/`:
- **macOS**: `NatMEG-BIDSifier.dmg`
- **Windows**: `NatMEG-BIDSifier Setup.exe`
- **Linux**: `NatMEG-BIDSifier.AppImage`

Users can just double-click these - no Python/Node.js required!

## ✨ Features

### Current (v1.0)
- ✅ Native file dialogs
- ✅ Direct file overwriting
- ✅ Keyboard shortcuts
- ✅ Application menu
- ✅ All existing viewer features (filters, status changes, bulk operations)
- ✅ Professional UI with NatMEG colors

### Coming Soon (Optional)
- [ ] Drag & drop TSV files
- [ ] Recent files menu
- [ ] Auto-backup before saving
- [ ] Multi-file batch editing
- [ ] Integration with Python pipeline (run conversions from app)

## 🛠️ Development Tips

### Running in Dev Mode
The app loads `bids_viewer.html` from the parent directory. Changes to HTML/CSS/JS are reflected after reloading (View → Reload or Cmd+R).

### Debugging
Press **Cmd+Alt+I** (Mac) or **Ctrl+Shift+I** (Windows/Linux) to open DevTools.

### File Structure
```
NatMEG-utils/
├── bids_viewer.html          # Main viewer (works standalone & in Electron)
├── electron/
│   ├── main.js              # Electron main process
│   ├── preload.js           # Secure IPC bridge
│   ├── renderer.js          # Integration with viewer
│   └── package.json         # Build config
└── run-app.sh               # Quick launch script
```

## 🔄 Next Steps

1. **Test** the app: `./run-app.sh`
2. **Build** a distribution: `cd electron && npm run build:mac`
3. **Test** the built app in `electron/dist/`
4. **Merge** to main when ready: `git checkout dev && git merge feature/electron-app`

## 📝 Notes

- The app runs completely offline (no server needed)
- File paths are preserved for direct overwriting
- Modified rows automatically get status="run" on save (unless manually changed)
- All table features work identically to web version

Enjoy your new desktop app! 🎉
