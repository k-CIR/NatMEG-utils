# Bundling Python Dependencies with NatMEG-BIDSifier

The Electron app needs Python and its dependencies bundled for distribution. Here are two approaches:

## Approach 1: Virtual Environment (Recommended for Development)

This creates a self-contained Python environment that travels with the app.

### Setup

```bash
cd electron
chmod +x setup_python_env.sh
./setup_python_env.sh
```

This will:
- Create `resources/python_env/` with Python interpreter
- Install all dependencies from `requirements.txt`
- Be automatically detected by the app

### Building

```bash
npm run build
```

The virtual environment in `resources/` will be packaged with the app.

**Pros:**
- Simple setup
- Easy to update dependencies
- Smaller than full PyInstaller bundle

**Cons:**
- Platform-specific (must build on target platform)
- Larger than standalone executable

## Approach 2: PyInstaller Standalone Executable

This creates a single executable file with Python and all dependencies embedded.

### Setup

```bash
cd electron
chmod +x build_python.sh
./build_python.sh
```

This will:
- Install PyInstaller
- Build standalone `bidsify` executable
- Place it in `resources/python/bidsify`

### Building

```bash
npm run build
```

The standalone executable will be packaged with the app.

**Pros:**
- Single file, no external Python needed
- Faster startup
- Cross-compilation possible with some work

**Cons:**
- Larger initial build
- Must rebuild for each platform
- More complex debugging

## Platform-Specific Builds

### macOS
```bash
./setup_python_env.sh
npm run build:mac
```

### Windows (on Windows machine)
```bash
setup_python_env.sh
npm run build:win
```

### Linux
```bash
./setup_python_env.sh
npm run build:linux
```

## Development Mode

In development, the app will:
1. First check for `resources/python_env/`
2. Fall back to system Python if not found

Run with:
```bash
npm start
```

## File Structure

```
electron/
├── resources/
│   ├── python_env/          # Virtual environment (Approach 1)
│   │   ├── bin/python3
│   │   └── lib/...
│   └── python/              # Standalone executable (Approach 2)
│       └── bidsify
├── setup_python_env.sh      # Setup script for Approach 1
├── build_python.sh          # Build script for Approach 2
└── main.js                  # Auto-detects bundled Python
```

## Distribution

The built app will include:
- Python interpreter (in virtual env or standalone)
- All Python dependencies
- `bidsify.py` and `utils.py`
- Configuration files

Users won't need to install Python or any dependencies manually.

## Troubleshooting

### "ModuleNotFoundError" in packaged app
- Rebuild the Python environment: `./setup_python_env.sh`
- Check that `resources/` is included in the build

### Different behavior in dev vs. production
- Test the packaged app: `npm run build && open dist/mac/NatMEG-BIDSifier.app`
- Check console logs for Python path being used

### Large app size
- Use PyInstaller approach for smaller size
- Consider excluding unnecessary packages from `requirements.txt`
