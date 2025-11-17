# NatMEG-BIDSifier Implementation Summary

## Overview
Complete implementation of a 5-step BIDS conversion workflow with Electron desktop application wrapper.

## Architecture

### 5-Step Workflow
1. **Configuration** - Load/edit YAML config with essential BIDS settings
2. **Analyse** - Generate conversion table without executing conversion (dry-run mode)
3. **Editor** - Review and modify conversion mappings in interactive table
4. **Execute** - Run actual BIDS conversion based on edited table
5. **Report** - Summary statistics and quality metrics

### File Structure
```
electron/
├── package.json          # Electron app config, dependencies, build scripts
├── main.js              # Main process: IPC handlers, Python subprocess, menus
├── preload.js           # Security bridge: exposes safe APIs to renderer
├── index.html           # Main UI: 5-step sidebar navigation
├── app.js               # Frontend controller: state management, workflow logic
├── bids_viewer.html     # TSV table editor (embedded in Editor step)
├── README.md            # Development documentation
└── ELECTRON_QUICKSTART.md  # User guide
```

### Key Technologies
- **Electron 28.0.0**: Desktop app framework
- **js-yaml 4.1.0**: YAML config parsing
- **Python subprocess**: Executes bidsify.py with config
- **IPC (Inter-Process Communication)**: Secure main ↔ renderer messaging
- **Professional Color Scheme**: #860052 (magenta), #98C9A3 (mint green), #000000 (black)

## Implementation Details

### Step 1: Configuration
**File**: `index.html` (config view), `app.js` (config functions)

**Features**:
- Form-based config editing (Project, Paths, BIDS Metadata, Conversion Settings)
- Load/Save YAML config files via native dialogs
- Load default config from `default_config.yml`
- Validation for required fields (Project Name, Raw Path, BIDS Path)
- Auto-collect form data into config object

**Form Fields**:
- Project Name*, CIR ID
- Raw Data Path*, BIDS Output Path*
- Authors, License, Description
- Conversion Table File, Overwrite Existing

### Step 2: Analyse Data Structure
**File**: `index.html` (analyse view), `app.js` (runAnalysis function), `bidsify.py` (dry_run mode)

**Features**:
- Runs `bidsify.py` with `dry_run: true` flag
- Scans raw data directory structure
- Generates `bids_conversion.tsv` without file conversion
- Progress bar with real-time console output
- Enables "Next: Editor" button on success

**Implementation**:
- `app.js`: Sets `config.RUN.dry_run = true` before calling bidsify
- `bidsify.py`: New dry-run mode checks flag and only calls `update_conversion_table()`
- Console output parsed for progress tracking

**Dry-Run Mode** (bidsify.py modification):
```python
dry_run = config.get('RUN', {}).get('dry_run', False)
if dry_run:
    print("Running in DRY-RUN mode: generating conversion table only")
    df, conversion_file = update_conversion_table(config)
    df.to_csv(conversion_file, sep='\t', index=False)
    print(f"Conversion table saved to: {conversion_file}")
    return True
```

### Step 3: Editor
**File**: `index.html` (editor view), `bids_viewer.html` (embedded iframe)

**Features**:
- Embeds existing `bids_viewer.html` in iframe
- Interactive TSV table editing (task, run, description, status)
- Search, filter, sort functionality
- Auto-status change to "run" for modified rows
- Professional styling with research colors

**Navigation**:
- Back to Analyse step (re-run analysis if needed)
- Next to Execute step (proceed with conversion)

### Step 4: Execute
**File**: `index.html` (execute view), `app.js` (runBidsification function)

**Features**:
- Warning box: Files will be converted according to BIDS spec
- Runs `bidsify.py` with full config (no dry_run flag)
- Progress bar with real-time console output
- Success state enables "Next: Report" button

**Execution Flow**:
- Collect config from form
- Call `electronAPI.runBidsify(config, progressCallback)`
- Main process spawns Python subprocess
- Capture stdout/stderr for progress and errors
- Update UI with progress percentage and console lines

### Step 5: Report
**File**: `index.html` (report view), `app.js` (generateReport, exportReport functions)

**Features**:
- Summary statistics cards (Files Converted, Subjects, Sessions, Errors)
- Detailed report with project info and console output
- Export report as HTML file via native save dialog
- "Start Over" button resets workflow to Step 1

**Report Generation**:
- Parse console output for statistics (regex matching)
- Display project metadata from config
- Include full console output in scrollable pre block
- Generate standalone HTML report for export

## Python Integration

### Main Process (main.js)
**IPC Handlers**:
- `load-default-config`: Read and parse `default_config.yml`
- `load-config`: Native file dialog → read YAML → return config
- `save-config`: Native file dialog → dump YAML → write file
- `run-bidsify`: Create temp config → spawn Python → capture output → cleanup
- `load-conversion-table`: Read TSV file from path

**Python Subprocess**:
```javascript
const pythonProcess = spawn('python3', ['bidsify.py', '--config', tempConfigPath]);
pythonProcess.stdout.on('data', (data) => {
    // Parse progress, send to renderer
    event.sender.send('bidsify-progress', { line, progress });
});
pythonProcess.on('close', (code) => {
    // Cleanup temp file, resolve promise
});
```

**Progress Tracking**:
- Heuristic parsing of stdout for keywords (processing, converting, completed)
- Calculate percentage based on output patterns
- Send real-time updates to renderer via IPC

### Preload Script (preload.js)
**Exposed APIs** (via contextBridge):
- `loadDefaultConfig()`: Promise<config>
- `loadConfig()`: Promise<{config, path}>
- `saveConfig(config)`: Promise<{success, error?}>
- `runBidsify(config, progressCallback)`: Promise<{success, error?}>
- `loadConversionTable(path)`: Promise<fileData>
- `onTriggerLoadConfig(callback)`: Menu event listener
- `onTriggerSaveConfig(callback)`: Menu event listener

## UI/UX Design

### Sidebar Navigation
**Structure**:
- 220px fixed width, #860052 background
- 5 numbered step items with active/completed states
- 28px circular step numbers
- Flex layout with step label

**States**:
- `.active`: Green step number (#98C9A3), bold text
- `.completed`: Grayed text, checkmark icon (future enhancement)
- Hover: Opacity 0.8

### Content Views
**Layout**:
- Full height, 30px padding
- Only `.active` view displayed (flex column)
- Consistent h1, p.step-description styling
- Form sections with grid layout

**Components**:
- Info boxes: Background #f8f8f8, border-left accent
- Warning boxes: Background #fff3cd, border-left #ffd966
- Progress bars: 20px height, rounded, green gradient
- Console output: Dark theme (#1e1e1e bg, #d4d4d4 text), monospace
- Stat cards: White bg, shadow, centered text, large numbers

### Color Palette
- **Primary**: #860052 (magenta) - Headers, sidebar, secondary buttons
- **Success**: #98C9A3 (mint green) - Primary buttons, progress, stats
- **Text**: #000000 (black) - Main text
- **Secondary Text**: #666666 (gray) - Descriptions
- **Background**: #f8f8f8 (light gray) - Info boxes, alternating rows
- **Error**: #ff6b6b (red) - Error text, error stats

## State Management

### App State (app.js)
```javascript
let currentConfig = null;          // Current config object
let analysisComplete = false;      // Analysis step completed
let executionComplete = false;     // Execution step completed
```

**State Transitions**:
1. Config validated → `currentConfig` updated
2. Analysis success → `analysisComplete = true`, enable Editor button
3. Execution success → `executionComplete = true`, enable Report button
4. Reset workflow → Reset all state, hide progress elements

### Navigation State
- Active view tracked by `.active` class
- Completed steps tracked by data-step comparison
- Button enable/disable based on completion flags

## Error Handling

### Validation
- **Config validation**: Check required fields before proceeding
- **File existence**: Check paths in config before running
- **Python subprocess**: Capture stderr, display in console

### User Feedback
- **Alerts**: Success/error messages for config load/save
- **Console output**: Real-time Python output for debugging
- **Progress text**: Status messages above progress bar
- **Error styling**: Red text, error class in console

### Fallback Strategies
- **Missing config**: Load default_config.yml
- **Failed subprocess**: Display stderr, keep console open
- **Missing conversion table**: Generate new one in dry-run

## Build Configuration

### Package.json Scripts
```json
"start": "electron .",
"build": "electron-builder",
"build:mac": "electron-builder --mac",
"build:win": "electron-builder --win",
"build:linux": "electron-builder --linux"
```

### Electron-Builder Config
**Targets**:
- macOS: dmg, zip
- Windows: nsis (installer), portable
- Linux: AppImage, deb

**Included Files**:
- Main app files: main.js, preload.js, index.html, app.js, bids_viewer.html
- Python files: bidsify.py, utils.py, default_config.yml
- Assets: icons, README

## Testing Checklist

### Step 1: Configuration
- [ ] Load default config populates form
- [ ] Load custom config via file dialog
- [ ] Save config to custom location
- [ ] Validation blocks navigation with empty required fields
- [ ] Next button navigates to Analyse step

### Step 2: Analyse
- [ ] Run analysis spawns Python subprocess
- [ ] Progress bar updates during execution
- [ ] Console output displays real-time
- [ ] Conversion table generated in BIDS/conversion_logs/
- [ ] Next button enabled on success

### Step 3: Editor
- [ ] Iframe loads bids_viewer.html
- [ ] Table displays conversion mappings
- [ ] Editing fields updates status to "run"
- [ ] Save functionality works (if implemented)
- [ ] Navigation buttons work

### Step 4: Execute
- [ ] Warning message displays
- [ ] Run conversion spawns Python subprocess
- [ ] Progress tracking works
- [ ] Files converted to BIDS directory
- [ ] Next button enabled on success

### Step 5: Report
- [ ] Statistics display correctly
- [ ] Project metadata shown
- [ ] Console output included
- [ ] Export report creates HTML file
- [ ] Start Over resets workflow

## Future Enhancements

### Immediate
1. **Iframe communication**: Message passing between index.html and bids_viewer.html
2. **Better progress parsing**: Parse actual bidsify.py output for file counts
3. **Error recovery**: Retry mechanisms for failed conversions
4. **Validation**: Check Python installation, required packages

### Medium-term
1. **Quality metrics**: Parse BIDS validator output, display issues
2. **File preview**: Show sample converted files in Report step
3. **Batch processing**: Multiple projects in sequence
4. **Settings page**: Python path, default directories, theme

### Long-term
1. **Full pipeline**: Integrate maxfilter, add_hpi, etc.
2. **Cloud sync**: CIR synchronization from app
3. **Collaboration**: Share configs, conversion tables
4. **Plugin system**: Custom conversion logic

## Dependencies

### Node.js (package.json)
- electron: ^28.0.0
- electron-builder: ^24.9.0
- js-yaml: ^4.1.0

### Python (requirements.txt)
See main repository requirements.txt for full list:
- mne
- mne-bids
- pandas
- pyyaml
- etc.

## Running the Application

### Development
```bash
cd electron
npm install
npm start
```

### Building
```bash
# All platforms
npm run build

# Specific platform
npm run build:mac
npm run build:win
npm run build:linux
```

### Distribution
Built applications in `electron/dist/`:
- macOS: .dmg, .zip
- Windows: installer.exe, portable.exe
- Linux: .AppImage, .deb

## Known Issues

1. **Type errors in bidsify.py**: Python type hints cause Pylance warnings but don't affect runtime
2. **js-yaml already installed**: Was showing as needed but actually present
3. **Iframe isolation**: Editor iframe might need message passing for full integration
4. **Progress calculation**: Heuristic parsing, not based on actual file counts
5. **Report statistics**: Regex parsing may miss some output formats

## Git Workflow

**Branch**: `feature/electron-app`

**Key Commits**:
1. Initial Electron setup with basic structure
2. Python integration and IPC handlers
3. Config management with YAML support
4. 5-step workflow UI implementation
5. Dry-run mode added to bidsify.py
6. Complete app.js with all step handlers

**Next Steps**:
1. Test full workflow with real data
2. Fix any UI bugs
3. Merge to main branch after validation
