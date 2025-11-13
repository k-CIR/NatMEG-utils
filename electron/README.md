# NatMEG-BIDSifier - Desktop Application

Desktop application for BIDS conversion of MEG data at NatMEG.

## Development

### Prerequisites
- Node.js (v18 or higher)
- npm

### Setup
```bash
cd electron
npm install
```

### Run in Development Mode
```bash
npm start
```

### Build for Distribution

**macOS:**
```bash
npm run build:mac
```

**Windows:**
```bash
npm run build:win
```

**Linux:**
```bash
npm run build:linux
```

**All Platforms:**
```bash
npm run build
```

Built applications will be in `electron/dist/`

## Features

- Native file dialogs for opening TSV files
- Direct file saving (overwrites original)
- Keyboard shortcuts (Cmd/Ctrl+O, Cmd/Ctrl+S)
- Application menu with standard controls
- Cross-platform support (macOS, Windows, Linux)

## Distribution

The built application is a standalone executable that can be distributed to users without requiring Python or Node.js installation.

### macOS
- `NatMEG-BIDSifier.dmg` - Drag and drop installer
- `NatMEG-BIDSifier-mac.zip` - Portable version

### Windows
- `NatMEG-BIDSifier Setup.exe` - Standard installer
- `NatMEG-BIDSifier.exe` - Portable version

### Linux
- `NatMEG-BIDSifier.AppImage` - Universal AppImage
- `natmeg-bidsifier.deb` - Debian package
