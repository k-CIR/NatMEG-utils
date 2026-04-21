#!/usr/bin/env python3
"""
File Tracker Module
Tracks files through the pipeline: copy → preprocess → sync → delete
Uses SQLite for project-level and central tracking databases.
"""

import sqlite3
import hashlib
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Union
from glob import glob
import yaml
import argparse

TRACKER_DIR = Path.home() / '.natmeg'
CENTRAL_DB = TRACKER_DIR / 'file_tracker.db'

STATUS_PENDING_COPY = 'pending_copy'
STATUS_COPIED = 'copied'
STATUS_PREPROCESSING = 'preprocessing'
STATUS_PREPROCESSED = 'preprocessed'
STATUS_SYNCING = 'syncing'
STATUS_SYNCED = 'synced'
STATUS_READY_TO_DELETE = 'ready_to_delete'
STATUS_DELETED = 'deleted'

VALID_STATUSES = [
    STATUS_PENDING_COPY,
    STATUS_COPIED,
    STATUS_PREPROCESSING,
    STATUS_PREPROCESSED,
    STATUS_SYNCING,
    STATUS_SYNCED,
    STATUS_READY_TO_DELETE,
    STATUS_DELETED,
]

STAGES = [
    'copied',
    'preprocessed',
    'synced',
    'deleted',
]


class FileTracker:
    """Central file tracking system using SQLite"""

    def __init__(self, project_config: Optional[Union[str, Dict]] = None, project_root: Optional[str] = None):
        self.project_config = project_config
        self.project_name = None
        self.project_root = None
        self.project_db = None

        if project_config:
            self._init_from_config(project_config, project_root)

    def _init_from_config(self, config: Union[str, Dict], project_root: Optional[str] = None):
        """Initialize from config file or dict"""
        if isinstance(config, str):
            with open(config, 'r') as f:
                if config.endswith('.json'):
                    cfg = json.load(f)
                else:
                    cfg = yaml.safe_load(f)
        else:
            cfg = config

        proj = cfg.get('Project', {})
        self.project_name = proj.get('Name', 'unknown')
        root = project_root or proj.get('Root', '.')
        self.project_root = os.path.join(root, self.project_name)

        logs_dir = os.path.join(self.project_root, 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        self.project_db = os.path.join(logs_dir, 'file_tracker.db')

        self._ensure_central_db()
        self._init_project_db()

    def _ensure_central_db(self):
        """Ensure central DB exists"""
        TRACKER_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(CENTRAL_DB)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
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
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER REFERENCES files(id),
                    operation TEXT,
                    server TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER,
                    details TEXT
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def _init_project_db(self):
        """Initialize project-level database"""
        if not self.project_db:
            raise ValueError("Project DB not initialized. Provide project_config.")

        conn = sqlite3.connect(self.project_db)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
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
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER REFERENCES files(id),
                    operation TEXT,
                    server TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    success INTEGER,
                    details TEXT
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self, db_path: str = None) -> sqlite3.Connection:
        """Get database connection"""
        path = db_path or self.project_db
        if not path:
            raise ValueError("No database path specified")
        return sqlite3.connect(path)

    def register_file(self, source_path: str, project_path: str,
                     compute_hash: bool = True) -> int:
        """Register a file in the tracker. Returns file_id."""
        original_hash = None
        if compute_hash and os.path.exists(source_path):
            original_hash = self.compute_hash(source_path)

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO files
                (source_path, project_name, project_path, original_hash, current_hash, status, stage_timestamps, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                source_path,
                self.project_name,
                project_path,
                original_hash,
                original_hash,
                STATUS_PENDING_COPY,
                json.dumps({}),
                datetime.now().isoformat()
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def register_files_batch(self, file_pairs: List[tuple], compute_hash: bool = True) -> int:
        """Register multiple files. file_pairs = [(source, project), ...]"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            count = 0
            for source_path, project_path in file_pairs:
                original_hash = None
                if compute_hash and os.path.exists(source_path):
                    original_hash = self.compute_hash(source_path)

                cursor.execute('''
                    INSERT OR REPLACE INTO files
                    (source_path, project_name, project_path, original_hash, current_hash, status, stage_timestamps, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    source_path,
                    self.project_name,
                    project_path,
                    original_hash,
                    original_hash,
                    STATUS_PENDING_COPY,
                    json.dumps({}),
                    datetime.now().isoformat()
                ))
                count += 1
            conn.commit()
            return count
        finally:
            conn.close()

    def update_status(self, file_id: int, new_status: str,
                     error_log: Optional[str] = None,
                     compute_hash: bool = False) -> bool:
        """Update file status. Optionally compute new hash."""
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}")

        conn = self._get_conn()
        try:
            cursor = conn.cursor()

            current_hash = None
            if compute_hash:
                cursor.execute('SELECT project_path FROM files WHERE id = ?', (file_id,))
                row = cursor.fetchone()
                if row and os.path.exists(row[0]):
                    current_hash = self.compute_hash(row[0])

            timestamps = {}
            cursor.execute('SELECT stage_timestamps FROM files WHERE id = ?', (file_id,))
            row = cursor.fetchone()
            if row and row[0]:
                timestamps = json.loads(row[0])

            timestamps[new_status] = datetime.now().isoformat()

            cursor.execute('''
                UPDATE files
                SET status = ?, stage_timestamps = ?, current_hash = ?,
                    error_log = ?, updated_at = ?
                WHERE id = ?
            ''', (
                new_status,
                json.dumps(timestamps),
                current_hash,
                error_log,
                datetime.now().isoformat(),
                file_id
            ))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_status_by_path(self, project_path: str, new_status: str,
                             error_log: Optional[str] = None,
                             compute_hash: bool = False) -> bool:
        """Update status by project path"""
        file_id = self.find_file_by_project_path(project_path)
        if file_id:
            return self.update_status(file_id, new_status, error_log, compute_hash)
        return False

    def compute_hash(self, file_path: str) -> Optional[str]:
        """Compute SHA256 hash of a file"""
        if not os.path.exists(file_path):
            return None

        sha256 = hashlib.sha256()
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception:
            return None

    def verify_hash(self, file_id: int) -> Dict:
        """Verify that current hash matches original"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT source_path, project_path, original_hash, current_hash, status
                FROM files WHERE id = ?
            ''', (file_id,))
            row = cursor.fetchone()
            if not row:
                return {'verified': False, 'reason': 'File not found'}

            source_path, project_path, orig_hash, curr_hash, status = row

            if not os.path.exists(project_path):
                return {'verified': False, 'reason': 'Project file missing', 'status': status}

            actual_hash = self.compute_hash(project_path)

            if orig_hash and actual_hash != orig_hash:
                return {
                    'verified': False,
                    'reason': 'Hash mismatch',
                    'original': orig_hash,
                    'current': actual_hash,
                    'status': status
                }

            return {
                'verified': True,
                'original': orig_hash,
                'current': actual_hash,
                'status': status
            }
        finally:
            conn.close()

    def find_file(self, source_path: str) -> Optional[Dict]:
        """Find file by source path"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, source_path, project_path, status, original_hash, current_hash
                FROM files
                WHERE source_path = ? AND project_name = ?
            ''', (source_path, self.project_name))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'source_path': row[1],
                    'project_path': row[2],
                    'status': row[3],
                    'original_hash': row[4],
                    'current_hash': row[5]
                }
            return None
        finally:
            conn.close()

    def find_file_by_project_path(self, project_path: str) -> Optional[int]:
        """Find file ID by project path"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM files WHERE project_path = ? AND project_name = ?',
                         (project_path, self.project_name))
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def find_file_by_id(self, file_id: int) -> Optional[Dict]:
        """Find file by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, source_path, project_path, status, original_hash, current_hash, stage_timestamps
                FROM files WHERE id = ?
            ''', (file_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'source_path': row[1],
                    'project_path': row[2],
                    'status': row[3],
                    'original_hash': row[4],
                    'current_hash': row[5],
                    'stage_timestamps': json.loads(row[6]) if row[6] else {}
                }
            return None
        finally:
            conn.close()

    def get_status_summary(self) -> Dict:
        """Get count of files by status for current project"""
        if not self.project_name:
            return {}

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status, COUNT(*) as count
                FROM files
                WHERE project_name = ?
                GROUP BY status
            ''', (self.project_name,))
            return dict(cursor.fetchall())
        finally:
            conn.close()

    def get_files_by_status(self, status: str) -> List[Dict]:
        """Get all files with given status"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, source_path, project_path, status, original_hash, current_hash
                FROM files
                WHERE status = ? AND project_name = ?
                ORDER BY source_path
            ''', (status, self.project_name))
            return [
                {
                    'id': row[0],
                    'source_path': row[1],
                    'project_path': row[2],
                    'status': row[3],
                    'original_hash': row[4],
                    'current_hash': row[5]
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_all_files(self) -> List[Dict]:
        """Get all tracked files for project"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, source_path, project_path, status, original_hash, current_hash, stage_timestamps
                FROM files
                WHERE project_name = ?
                ORDER BY source_path
            ''', (self.project_name,))
            return [
                {
                    'id': row[0],
                    'source_path': row[1],
                    'project_path': row[2],
                    'status': row[3],
                    'original_hash': row[4],
                    'current_hash': row[5],
                    'stage_timestamps': json.loads(row[6]) if row[6] else {}
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def mark_ready_to_delete(self, file_ids: List[int]) -> int:
        """Mark files as ready for deletion after sync verification"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            count = 0
            for file_id in file_ids:
                cursor.execute('''
                    UPDATE files
                    SET status = ?, updated_at = ?
                    WHERE id = ? AND status = ?
                ''', (STATUS_READY_TO_DELETE, datetime.now().isoformat(),
                      file_id, STATUS_SYNCED))
                count += cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def mark_deleted(self, file_ids: List[int]) -> int:
        """Mark files as deleted (only allowed from ready_to_delete)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            count = 0
            for file_id in file_ids:
                cursor.execute('''
                    UPDATE files
                    SET status = ?, updated_at = ?
                    WHERE id = ? AND status = ?
                ''', (STATUS_DELETED, datetime.now().isoformat(),
                      file_id, STATUS_READY_TO_DELETE))
                count += cursor.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def safe_to_delete(self, file_id: int) -> bool:
        """Check if file is safe to delete (must be ready_to_delete)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT status FROM files WHERE id = ?', (file_id,))
            row = cursor.fetchone()
            return row and row[0] == STATUS_READY_TO_DELETE
        finally:
            conn.close()

    def sync_to_central(self) -> Dict:
        """Push project DB records to central DB"""
        if not self.project_name:
            return {'success': False, 'reason': 'No project configured'}

        project_conn = self._get_conn(self.project_db)
        try:
            project_conn.row_factory = sqlite3.Row
            cursor = project_conn.cursor()
            cursor.execute('SELECT * FROM files WHERE project_name = ?', (self.project_name,))
            files = cursor.fetchall()
        finally:
            project_conn.close()

        central_conn = self._get_conn(str(CENTRAL_DB))
        try:
            central_cursor = central_conn.cursor()
            count = 0
            for file in files:
                central_cursor.execute('''
                    INSERT OR REPLACE INTO files
                    (source_path, project_name, project_path, original_hash, current_hash,
                     status, stage_timestamps, error_log, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file['source_path'], file['project_name'], file['project_path'],
                    file['original_hash'], file['current_hash'], file['status'],
                    file['stage_timestamps'], file['error_log'],
                    file['created_at'], file['updated_at']
                ))
                count += 1
            central_conn.commit()
            return {'success': True, 'synced': count}
        finally:
            central_conn.close()

    def sync_from_central(self) -> Dict:
        """Pull from central DB to project DB (central is source of truth)"""
        if not self.project_name:
            return {'success': False, 'reason': 'No project configured'}

        central_conn = self._get_conn(str(CENTRAL_DB))
        try:
            central_conn.row_factory = sqlite3.Row
            cursor = central_conn.cursor()
            cursor.execute('SELECT * FROM files WHERE project_name = ?', (self.project_name,))
            files = cursor.fetchall()
        finally:
            central_conn.close()

        if not files:
            return {'success': True, 'synced': 0, 'message': 'No files in central DB'}

        project_conn = self._get_conn(self.project_db)
        try:
            project_cursor = project_conn.cursor()
            count = 0
            for file in files:
                project_cursor.execute('''
                    INSERT OR REPLACE INTO files
                    (source_path, project_name, project_path, original_hash, current_hash,
                     status, stage_timestamps, error_log, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file['source_path'], file['project_name'], file['project_path'],
                    file['original_hash'], file['current_hash'], file['status'],
                    file['stage_timestamps'], file['error_log'],
                    file['created_at'], file['updated_at']
                ))
                count += 1
            project_conn.commit()
            return {'success': True, 'synced': count}
        finally:
            project_conn.close()

    def log_sync_operation(self, file_id: int, operation: str, server: str,
                          success: bool, details: str = None):
        """Log a sync operation"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sync_log (file_id, operation, server, success, details)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_id, operation, server, 1 if success else 0, details))
            conn.commit()
        finally:
            conn.close()

    def get_global_summary(self) -> Dict:
        """Get summary across all projects in central DB"""
        conn = self._get_conn(str(CENTRAL_DB))
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT project_name, status, COUNT(*) as count
                FROM files
                GROUP BY project_name, status
                ORDER BY project_name, status
            ''')
            results = cursor.fetchall()
            summary = {}
            for project_name, status, count in results:
                if project_name not in summary:
                    summary[project_name] = {}
                summary[project_name][status] = count
            return summary
        finally:
            conn.close()

    def delete_orphans(self, dry_run: bool = True) -> Dict:
        """Delete local files not in DB or not ready_to_delete"""
        if not self.project_root:
            return {'success': False, 'reason': 'No project root'}

        ready_files = self.get_files_by_status(STATUS_READY_TO_DELETE)

        deleted = []
        errors = []

        for file_info in ready_files:
            project_path = file_info['project_path']
            if os.path.exists(project_path):
                if dry_run:
                    deleted.append(project_path)
                else:
                    try:
                        os.remove(project_path)
                        self.mark_deleted([file_info['id']])
                        deleted.append(project_path)
                    except Exception as e:
                        errors.append({'file': project_path, 'error': str(e)})

        return {
            'success': True,
            'dry_run': dry_run,
            'deleted': deleted,
            'errors': errors
        }

    def import_from_copy_results(self, copy_results_path: str) -> Dict:
        """Import files from legacy copy_results.json

        Args:
            copy_results_path: Path to copy_results.json file

        Returns:
            Dict with import results
        """
        if not os.path.exists(copy_results_path):
            return {'success': False, 'reason': f'File not found: {copy_results_path}'}

        with open(copy_results_path, 'r') as f:
            copy_results = json.load(f)

        imported = 0
        skipped = 0
        not_found = 0
        path_mappings = {}

        if self.project_root:
            path_mappings = {
                '/neuro/data/local': self.project_root,
                'neuro/data/local': self.project_root,
                '/neuro/data/sinuhe/opm/': '',
            }

        for entry in copy_results:
            original_file = entry.get('Original File')
            new_files = entry.get('New file(s)')

            if not original_file or not new_files:
                skipped += 1
                continue

            if isinstance(new_files, str):
                new_files = [new_files]

            for dest_file in new_files:
                resolved_path = dest_file

                for old_prefix, new_prefix in path_mappings.items():
                    if dest_file.startswith(old_prefix):
                        resolved_path = dest_file.replace(old_prefix, new_prefix, 1)
                        break

                if not os.path.exists(resolved_path):
                    not_found += 1
                    continue

                file_id = self.find_file_by_project_path(resolved_path)
                if file_id:
                    skipped += 1
                    continue

                original_hash = None
                try:
                    original_hash = self.compute_hash(resolved_path)
                except Exception:
                    pass

                conn = self._get_conn()
                try:
                    cursor = conn.cursor()
                    status = entry.get('status', 'copied')
                    if status not in VALID_STATUSES:
                        status = STATUS_COPIED

                    cursor.execute('''
                        INSERT INTO files
                        (source_path, project_name, project_path, original_hash, current_hash, status, stage_timestamps, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        original_file,
                        self.project_name,
                        resolved_path,
                        original_hash,
                        original_hash,
                        status,
                        json.dumps({'copied': entry.get('timestamp', '')}),
                        entry.get('timestamp', datetime.now().isoformat()),
                        datetime.now().isoformat()
                    ))
                    conn.commit()
                    imported += 1
                finally:
                    conn.close()

        return {
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'not_found': not_found,
            'source': copy_results_path
        }

    def import_from_bids_conversion(self, bids_conversion_path: str) -> Dict:
        """Import files from BIDS conversion log

        Args:
            bids_conversion_path: Path to bids_conversion.tsv file

        Returns:
            Dict with import results
        """
        if not os.path.exists(bids_conversion_path):
            return {'success': False, 'reason': f'File not found: {bids_conversion_path}'}

        imported = 0
        errors = []

        with open(bids_conversion_path, 'r') as f:
            lines = f.readlines()

        if not lines:
            return {'success': False, 'reason': 'Empty file'}

        headers = lines[0].strip().split('\t')

        for line in lines[1:]:
            if not line.strip():
                continue

            try:
                values = line.strip().split('\t')
                record = dict(zip(headers, values))

                source = record.get('Source', record.get('source', ''))
                destination = record.get('Destination', record.get('destination', ''))

                if not source or not destination:
                    continue

                file_id = self.find_file_by_project_path(destination)
                if file_id:
                    continue

                original_hash = None
                if os.path.exists(destination):
                    try:
                        original_hash = self.compute_hash(destination)
                    except Exception:
                        pass

                conn = self._get_conn()
                try:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO files
                        (source_path, project_name, project_path, original_hash, current_hash, status, stage_timestamps, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        source,
                        self.project_name,
                        destination,
                        original_hash,
                        original_hash,
                        STATUS_COPIED,
                        json.dumps({}),
                        datetime.now().isoformat(),
                        datetime.now().isoformat()
                    ))
                    conn.commit()
                    imported += 1
                except Exception as e:
                    errors.append({'file': destination, 'error': str(e)})
                finally:
                    conn.close()

            except Exception as e:
                errors.append({'line': line[:50], 'error': str(e)})

        return {
            'success': True,
            'imported': imported,
            'errors': errors[:10],
            'source': bids_conversion_path
        }

    def migrate_existing_project(self, root_path: str = None,
                                 assume_synced: bool = False,
                                 assume_copied: bool = True) -> Dict:
        """Migrate existing project files to tracker DB

        Scans a project directory and registers all files.

        Args:
            root_path: Project root (defaults to self.project_root)
            assume_synced: If True, mark all files as 'synced'
            assume_copied: If True, mark all files as 'copied' (default)
                          If False, mark as 'pending_copy'

        Returns:
            Dict with migration results
        """
        import glob as glob_module

        root = root_path or self.project_root
        if not root or not os.path.exists(root):
            return {'success': False, 'reason': f'Path does not exist: {root}'}

        file_pairs = []
        for dirpath, dirnames, filenames in os.walk(root):
            if 'logs' in dirpath or '__pycache__' in dirpath:
                continue
            for filename in filenames:
                if filename.startswith('.') or filename.endswith('.tmp'):
                    continue
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, root)
                file_pairs.append((rel_path, full_path))

        registered = self.register_files_batch(file_pairs, compute_hash=True)

        if assume_copied:
            for source, dest in file_pairs:
                file_id = self.find_file_by_project_path(dest)
                if file_id:
                    self.update_status(file_id, STATUS_COPIED, compute_hash=False)

        if assume_synced:
            for source, dest in file_pairs:
                file_id = self.find_file_by_project_path(dest)
                if file_id:
                    self.update_status(file_id, STATUS_SYNCED, compute_hash=False)

        return {
            'success': True,
            'files_found': len(file_pairs),
            'registered': registered,
            'assumed_status': 'synced' if assume_synced else ('copied' if assume_copied else 'pending_copy')
        }

    def scan_and_detect_status(self, root_path: str = None) -> Dict:
        """Scan project and detect file status based on existing state

        Analyzes files and determines appropriate status:
        - If file exists locally and no remote info: 'copied'
        - Could check remote server if configured

        Args:
            root_path: Project root (defaults to self.project_root)

        Returns:
            Dict with detected files and suggested status
        """
        root = root_path or self.project_root
        if not root or not os.path.exists(root):
            return {'success': False, 'reason': f'Path does not exist: {root}'}

        files = []
        for dirpath, dirnames, filenames in os.walk(root):
            if 'logs' in dirpath or '__pycache__' in dirpath:
                continue
            for filename in filenames:
                if filename.startswith('.') or filename.endswith('.tmp'):
                    continue
                full_path = os.path.join(dirpath, filename)
                rel_path = os.path.relpath(full_path, root)
                stat = os.stat(full_path)

                files.append({
                    'relative_path': rel_path,
                    'absolute_path': full_path,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'detected_status': STATUS_COPIED
                })

        return {
            'success': True,
            'files': files,
            'total': len(files)
        }


def init_tracker_from_config(config_path: str) -> FileTracker:
    """Helper to initialize tracker from config file"""
    return FileTracker(project_config=config_path)


def status_to_color(status: str) -> str:
    """Get color for status in reports"""
    colors = {
        STATUS_PENDING_COPY: 'gray',
        STATUS_COPIED: 'blue',
        STATUS_PREPROCESSING: 'yellow',
        STATUS_PREPROCESSED: 'cyan',
        STATUS_SYNCING: 'orange',
        STATUS_SYNCED: 'green',
        STATUS_READY_TO_DELETE: 'purple',
        STATUS_DELETED: 'red',
    }
    return colors.get(status, 'gray')


def main():
    """CLI for file tracker"""
    parser = argparse.ArgumentParser(description='File Tracker CLI')
    parser.add_argument('--config', '-c', help='Project configuration file')
    parser.add_argument('--central', action='store_true', help='Use central database')
    parser.add_argument('command', choices=['status', 'verify', 'sync-central',
                                               'sync-from-central', 'delete-ready', 'global-status'],
                       help='Command to execute')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    parser.add_argument('--file', '-f', help='Specific file path')

    args = parser.parse_args()

    if not args.config and args.command not in ['global-status']:
        print("Error: --config required for this command")
        return

    tracker = FileTracker(args.config) if args.config else None

    if args.command == 'status':
        summary = tracker.get_status_summary()
        print(f"\nProject: {tracker.project_name}")
        print(f"Project DB: {tracker.project_db}")
        print("\nStatus Summary:")
        for status, count in sorted(summary.items()):
            print(f"  {status}: {count}")

        print("\nAll tracked files:")
        for f in tracker.get_all_files():
            print(f"  [{f['status']}] {f['source_path']}")

    elif args.command == 'verify':
        if args.file:
            file_id = tracker.find_file_by_project_path(args.file)
            if file_id:
                result = tracker.verify_hash(file_id)
                print(json.dumps(result, indent=2))
            else:
                print(f"File not found: {args.file}")
        else:
            all_files = tracker.get_all_files()
            verified = 0
            failed = 0
            for f in all_files:
                result = tracker.verify_hash(f['id'])
                if result['verified']:
                    verified += 1
                else:
                    failed += 1
                    print(f"FAILED: {f['source_path']} - {result['reason']}")
            print(f"\nVerified: {verified}, Failed: {failed}")

    elif args.command == 'sync-central':
        result = tracker.sync_to_central()
        print(json.dumps(result, indent=2))

    elif args.command == 'sync-from-central':
        result = tracker.sync_from_central()
        print(json.dumps(result, indent=2))

    elif args.command == 'delete-ready':
        result = tracker.delete_orphans(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))

    elif args.command == 'global-status':
        if not CENTRAL_DB.exists():
            print("Central DB not initialized yet")
            return
        tracker = FileTracker()
        tracker.project_db = str(CENTRAL_DB)
        summary = tracker.get_global_summary()
        print("\nGlobal Status Summary:")
        for project, statuses in summary.items():
            print(f"\n{project}:")
            for status, count in sorted(statuses.items()):
                print(f"  {status}: {count}")


if __name__ == '__main__':
    main()
