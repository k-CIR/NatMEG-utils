#!/bin/bash
# Build standalone Python executables for bidsify.py using PyInstaller

set -e

echo "Building standalone Python executable..."

# Install PyInstaller if not already installed
pip install pyinstaller

# Create spec file for better control
cat > bidsify.spec <<EOF
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['../bidsify.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('../utils.py', '.'),
        ('../default_config.yml', '.'),
    ],
    hiddenimports=[
        'mne',
        'mne_bids',
        'pandas',
        'numpy',
        'scipy',
        'matplotlib',
        'yaml',
        'tqdm',
        'bids_validator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='bidsify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
EOF

# Build the executable
pyinstaller --clean bidsify.spec

# Move executable to resources folder
mkdir -p resources/python
mv dist/bidsify resources/python/

echo "Python executable built successfully: resources/python/bidsify"
