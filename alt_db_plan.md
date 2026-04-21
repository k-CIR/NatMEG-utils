---
# File Tracking System - Implementation Plan
## Overview
A robust file tracking system to ensure safe handling of files through the pipeline:
- Copy → Preprocess → Sync → Delete
- Centralized tracking with project-level and central databases
## Architecture
### Database Locations
project_A/logs/file_tracker.db  ← Project-level DB (auto-created)
project_B/logs/file_tracker.db
~/.natmeg/file_tracker.db       ← Central DB (source of truth)
### Database Sync
- Project DBs push to central DB after each stage
- Central DB can pull state to project DBs (source of truth)
- Bidirectional sync for recovery
### File Status States
| Status | Description |
|--------|-------------|
| `pending_copy` | File identified, waiting to copy |
| `copied` | Successfully copied to destination |
| `preprocessing` | Currently being preprocessed |
| `preprocessed` | Preprocessing complete |
| `syncing` | Currently being synced to server |
| `synced` | Successfully synced to server |
| `backed_up` | Successfully backed up |
| `ready_to_delete` | Verified synced, safe to delete |
| `deleted` | Removed from local storage |
## Schema
```sql
CREATE TABLE files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path TEXT NOT NULL,
    project_name TEXT NOT NULL,
    project_path TEXT NOT NULL,
    original_hash TEXT,
    current_hash TEXT,
    status TEXT DEFAULT 'pending_copy',
    stage_timestamps JSON,
    error_log TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_path, project_name, project_path)
);
CREATE TABLE sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER REFERENCES files(id),
    operation TEXT,
    server TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN,
    details TEXT
);
Implementation
1. New Module: file_tracker.py
Core Functions:
- init_tracker(project_config) - Initialize project DB
- register_file(source, dest, project) - Add file to tracking
- update_status(file_id, new_status) - Update file status
- verify_hash(file_id) - Verify file integrity
- get_project_status(project) - Get all files for project
- sync_to_central(project) - Push to central DB
- sync_from_central(project) - Pull from central DB
- get_files_by_status(status) - Query by status
- mark_ready_to_delete(file_ids) - Mark as safe to delete
- cleanup_deleted() - Remove deleted records
2. Integration: copy_to_cerberos.py
# Before copy
tracker.register_file(source, dest, project)
# After successful copy
tracker.update_status(file_id, 'copied')
# Compute and store hash
tracker.compute_hash(file_id)
3. Integration: opm_preprocess.py
# On preprocess start
tracker.update_status(file_id, 'preprocessing')
# On preprocess complete
tracker.update_status(file_id, 'preprocessed')
tracker.update_hash(file_id)
4. Integration: sync_to_cir.py
# BEFORE any delete - check DB
def safe_to_delete(file_path):
    record = tracker.find_file(file_path)
    return record and record['status'] == 'ready_to_delete'
# After successful sync
tracker.update_status(file_id, 'synced')
# Mark as safe to delete after verification
tracker.mark_ready_to_delete(file_ids)
# Only delete if safe
if safe_to_delete(file_path):
    os.remove(file_path)
5. New Pipeline Commands
# Track file status
seshat track status --config project.yml
# Verify file hashes
seshat track verify --config project.yml
# Sync to central DB
seshat track sync-central --config project.yml
# Sync from central DB
seshat track sync-from-central --config project.yml
# Delete files marked ready_to_delete
seshat track delete-ready --config project.yml [--dry-run]
# Global status across all projects
seshat track global-status
# Generate tracking report
seshat track report --config project.yml
6. Report Integration (render_report.py)
Extend to show:
- Files pending copy
- Files synced but not deleted
- Failed/error files
- Full history per file
Safety Rules
1. Never delete a file unless status is ready_to_delete
2. Verify sync success before marking ready_to_delete
3. Rollback on failure: If sync fails, status reverts to preprocessed
4. Hash verification: Compute hash at copy, verify before delete
5. Central backup: All operations logged to central DB

File: file_tracker.py - Structure
import sqlite3
import hashlib
import json
from pathlib import Path
from os.path import exists, getsize
from datetime import datetime
TRACKER_DIR = Path.home() / '.natmeg'
CENTRAL_DB = TRACKER_DIR / 'file_tracker.db'
class FileTracker:
    def __init__(self, project_config):
        self.project = project
        self.project_db = Path(project_logs) / 'file_tracker.db'
        
    def init(self):
        # Create tables in project DB
        # Create central DB if doesn't exist
        
    def register_file(self, source, dest):
        # Insert record with status='pending_copy'
        
    def update_status(self, file_id, new_status):
        # Update status, add timestamp
        
    def compute_hash(self, file_path):
        # SHA256 hash
        
    def verify_hash(self, file_id):
        # Compare current_hash with original
        
    def sync_to_central(self):
        # Push to central DB
        
    def sync_from_central(self):
        # Pull from central DB
        
    def get_status_summary(self, project):
        # Return counts by status
        
    def safe_to_delete(self, file_id):
        # Check status == 'ready_to_delete'
Testing
- Unit tests for hash computation
- Unit tests for status transitions
- Integration test with pipeline
- Verify delete safety rules
Migration Path
1. Create file_tracker.py
2. Add to pipeline, run in dry-run mode first
3. Enable tracking without delete
4. Enable delete with safety checks
5. Deprecate old copy_report.json
---
