"""
Unified Pipeline Tracking System for NatMEG Processing

A comprehensive tracking system that follows files through the entire MEG processing
pipeline from raw acquisition through BIDS conversion to final analysis. Integrates
all existing logging systems and provides unified HTML reporting.

Features:
- Centralized file lifecycle tracking across all pipeline stages
- Real-time HTML report generation with interactive filtering
- Integration with existing logging systems (copy_results.json, bids_conversion.tsv)
- Stage-based progress tracking with timestamps and metadata
- Automatic conflict detection and status validation
- Extensible architecture for additional pipeline stages

Author: Andreas Gerhardsson
"""

import json
import pandas as pd
import os
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import sqlite3
from contextlib import contextmanager
import time

from utils import log, get_logger, extract_info_from_filename

# Pipeline Stage Definitions
class PipelineStage(Enum):
    """Enumeration of all pipeline processing stages."""
    RAW_ACQUISITION = "raw_acquisition"
    RAW_COPY = "raw_copy"
    BIDSIFICATION = "bidsification"  
    MAXFILTER = "maxfilter"
    PREPROCESSING = "preprocessing"
    ANALYSIS = "analysis"
    VALIDATION = "validation"
    REPORTING = "reporting"
    ARCHIVED = "archived"

class FileStatus(Enum):
    """File processing status within each stage."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    REQUIRES_ATTENTION = "requires_attention"

@dataclass
class FileRecord:
    """Complete file record tracking all pipeline information."""
    file_id: str  # Unique identifier (hash of original path + subject + session + task)
    original_path: str  # Source file path
    current_path: Optional[str]  # Current file location
    bids_path: Optional[str]  # BIDS standardized path
    
    # File metadata
    participant: str
    session: str
    task: str
    acquisition: str
    datatype: str
    processing: List[str]
    description: List[str]
    
    # Pipeline tracking
    current_stage: PipelineStage
    stage_history: Dict[str, Dict]  # Stage -> {status, timestamp, details}
    
    # File properties
    file_size: int
    checksum: Optional[str]
    created_timestamp: datetime
    last_modified: datetime
    
    # Processing metadata
    conversion_details: Optional[Dict] = None
    processing_parameters: Optional[Dict] = None
    validation_results: Optional[Dict] = None
    error_log: List[str] = None
    
    def __post_init__(self):
        """Initialize default values."""
        if self.error_log is None:
            self.error_log = []
        if self.stage_history is None:
            self.stage_history = {}

class PipelineTracker:
    """
    Centralized pipeline tracking system.
    
    Manages file lifecycle tracking across all pipeline stages, integrates
    with existing logging systems, and provides unified reporting capabilities.
    """
    
    def __init__(self, project_root: str, config: Optional[Dict] = None):
        """
        Initialize pipeline tracker.
        
        Args:
            project_root (str): Root directory of the project
            config (dict, optional): Configuration dictionary
        """
        self.project_root = Path(project_root)
        self.config = config or {}
        
        # Setup tracking directories
        self.tracking_dir = self.project_root / 'pipeline_tracking'
        self.tracking_dir.mkdir(exist_ok=True)
        
        # Database file for SQLite storage
        self.db_path = self.tracking_dir / 'pipeline_tracker.db'
        
        # Initialize database
        self._init_database()
        
        # Logger setup
        self.logger = get_logger('PipelineTracker')
        
        # File record cache
        self._file_cache = {}
        self._cache_dirty = False
    
    def _init_database(self):
        """Initialize SQLite database for persistent storage."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS file_records (
                    file_id TEXT PRIMARY KEY,
                    original_path TEXT NOT NULL,
                    current_path TEXT,
                    bids_path TEXT,
                    participant TEXT NOT NULL,
                    session TEXT NOT NULL,
                    task TEXT NOT NULL,
                    acquisition TEXT,
                    datatype TEXT,
                    processing TEXT,  -- JSON string
                    description TEXT,  -- JSON string
                    current_stage TEXT NOT NULL,
                    stage_history TEXT,  -- JSON string
                    file_size INTEGER,
                    checksum TEXT,
                    created_timestamp TEXT,
                    last_modified TEXT,
                    conversion_details TEXT,  -- JSON string
                    processing_parameters TEXT,  -- JSON string
                    validation_results TEXT,  -- JSON string
                    error_log TEXT,  -- JSON string
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_participant_session 
                ON file_records (participant, session)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_current_stage 
                ON file_records (current_stage)
            ''')
            
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_task 
                ON file_records (task)
            ''')
    
    def _generate_file_id(self, file_path: str, metadata: Dict) -> str:
        """Generate unique file ID based on path and metadata."""
        identifier = f"{file_path}_{metadata.get('participant', '')}_{metadata.get('session', '')}_{metadata.get('task', '')}"
        return hashlib.md5(identifier.encode()).hexdigest()[:16]
    
    def find_file_by_path(self, file_path: str, metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Find existing file record by path, trying different metadata combinations.
        
        Args:
            file_path (str): Path to the file
            metadata (dict, optional): Metadata to help with lookup
            
        Returns:
            str: File ID if found, None otherwise
        """
        metadata = metadata or {}
        
        # Try with current metadata first
        test_id = self._generate_file_id(file_path, metadata)
        if self._load_record(test_id):
            return test_id
            
        # Try with minimal metadata variations
        for test_metadata in [
            {},  # Empty metadata
            {'participant': metadata.get('participant', ''), 'session': '', 'task': ''},  # Partial
            {'participant': '', 'session': '', 'task': ''}  # All empty strings
        ]:
            test_id = self._generate_file_id(file_path, test_metadata)
            if self._load_record(test_id):
                return test_id
                
        return None

    def register_file(self, file_path: str, stage: PipelineStage, 
                     status: FileStatus = FileStatus.PENDING, 
                     metadata: Optional[Dict] = None) -> str:
        """
        Register a new file in the pipeline tracking system.
        
        Args:
            file_path (str): Path to the file
            stage (PipelineStage): Initial pipeline stage
            status (FileStatus): Initial status
            metadata (dict, optional): Additional metadata
            
        Returns:
            str: File ID for tracking
        """
        try:
            # Extract file information
            file_info = extract_info_from_filename(file_path)
            
            # Get file stats
            file_stat = os.stat(file_path) if os.path.exists(file_path) else None
            
            # Generate unique ID
            file_id = self._generate_file_id(file_path, file_info)
            
            # Create file record
            record = FileRecord(
                file_id=file_id,
                original_path=file_path,
                current_path=file_path,
                bids_path=None,
                participant=file_info.get('participant', ''),
                session=metadata.get('session', ''),
                task=file_info.get('task', ''),
                acquisition=metadata.get('acquisition', ''),
                datatype=metadata.get('datatype', 'meg'),
                processing=file_info.get('processing', []),
                description=file_info.get('description', []),
                current_stage=stage,
                stage_history={},
                file_size=file_stat.st_size if file_stat else 0,
                checksum=None,
                created_timestamp=datetime.now(timezone.utc),
                last_modified=datetime.fromtimestamp(file_stat.st_mtime, timezone.utc) if file_stat else datetime.now(timezone.utc)
            )
            
            # Add initial stage to history directly (before saving)
            stage_entry = {
                'status': status.value,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'metadata': metadata or {}
            }
            record.stage_history[stage.value] = stage_entry
            
            # Save to database first
            self._save_record(record)
            
            # Now update stage history (this will work since record is in DB)
            # self.update_file_stage(file_id, stage, status, metadata)
            
            self.logger.info(f"Registered file {file_path} with ID {file_id} at stage {stage.value}")
            return file_id
            
        except Exception as e:
            self.logger.error(f"Failed to register file {file_path}: {e}")
            raise
    
    def update_file_stage(self, file_id: str, stage: PipelineStage, 
                         status: FileStatus, metadata: Optional[Dict] = None) -> bool:
        """
        Update file stage and status.
        
        Args:
            file_id (str): File identifier
            stage (PipelineStage): New pipeline stage
            status (FileStatus): New status
            metadata (dict, optional): Additional stage metadata
            
        Returns:
            bool: Success status
        """
        try:
            record = self._load_record(file_id)
            if not record:
                self.logger.warning(f"File {file_id} not found for stage update")
                return False
            
            # Update current stage
            record.current_stage = stage
            record.last_modified = datetime.now(timezone.utc)
            
            # Add to stage history
            stage_entry = {
                'status': status.value,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'metadata': metadata or {}
            }
            
            if record.stage_history is None:
                record.stage_history = {}
                
            record.stage_history[stage.value] = stage_entry
            
            # Save updated record
            self._save_record(record)
            
            self.logger.info(f"Updated file {file_id} to stage {stage.value} with status {status.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update stage for {file_id}: {e}")
            return False
    
    def update_file_path(self, file_id: str, new_path: str, path_type: str = 'current') -> bool:
        """
        Update file path information.
        
        Args:
            file_id (str): File identifier
            new_path (str): New file path
            path_type (str): Type of path ('current' or 'bids')
            
        Returns:
            bool: Success status
        """
        try:
            record = self._load_record(file_id)
            if not record:
                return False
            
            if path_type == 'current':
                record.current_path = new_path
            elif path_type == 'bids':
                record.bids_path = new_path
            
            record.last_modified = datetime.now(timezone.utc)
            
            self._save_record(record)
            
            self.logger.info(f"Updated {path_type} path for {file_id}: {new_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update path for {file_id}: {e}")
            return False
    
    def get_file_status(self, file_id: str) -> Optional[Dict]:
        """
        Get current status of a file.
        
        Args:
            file_id (str): File identifier
            
        Returns:
            dict: File status information or None
        """
        record = self._load_record(file_id)
        if not record:
            return None
            
        return {
            'file_id': file_id,
            'current_stage': record.current_stage.value,
            'stage_history': record.stage_history,
            'current_path': record.current_path,
            'bids_path': record.bids_path,
            'last_modified': record.last_modified.isoformat()
        }
    
    def get_files_by_stage(self, stage: PipelineStage) -> List[Dict]:
        """
        Get all files in a specific pipeline stage.
        
        Args:
            stage (PipelineStage): Pipeline stage to filter by
            
        Returns:
            list: List of file records
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM file_records WHERE current_stage = ?',
                (stage.value,)
            )
            
            results = []
            for row in cursor.fetchall():
                record_dict = dict(row)
                # Parse JSON fields
                for json_field in ['processing', 'description', 'stage_history', 
                                 'conversion_details', 'processing_parameters', 
                                 'validation_results', 'error_log']:
                    if record_dict[json_field]:
                        try:
                            record_dict[json_field] = json.loads(record_dict[json_field])
                        except json.JSONDecodeError:
                            record_dict[json_field] = None
                
                results.append(record_dict)
            
            return results
    
    def get_participant_summary(self, participant: str) -> Dict:
        """
        Get processing summary for a specific participant.
        
        Args:
            participant (str): Participant ID
            
        Returns:
            dict: Summary statistics and file information
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Get all files for participant
            cursor = conn.execute(
                'SELECT * FROM file_records WHERE participant = ?',
                (participant,)
            )
            
            files = cursor.fetchall()
            
            # Calculate statistics
            stage_counts = {}
            total_files = len(files)
            
            for file_record in files:
                stage = file_record['current_stage']
                stage_counts[stage] = stage_counts.get(stage, 0) + 1
            
            return {
                'participant': participant,
                'total_files': total_files,
                'stage_distribution': stage_counts,
                'files': [dict(f) for f in files]
            }
    
    def import_legacy_data(self):
        """
        Import data from existing logging systems.
        
        Reads copy_results.json and bids_conversion.tsv to populate
        the unified tracking system with historical data.
        """
        self.logger.info("Importing legacy pipeline data...")
        
        # Import copy results
        self._import_copy_results()
        
        # Import BIDS conversion data  
        self._import_bids_conversion_data()
        
        self.logger.info("Legacy data import completed")
    
    def _import_copy_results(self):
        """Import data from copy_results.json."""
        copy_results_path = self.project_root / 'log' / 'copy_results.json'
        
        if not copy_results_path.exists():
            self.logger.warning("copy_results.json not found, skipping import")
            return
        
        try:
            with open(copy_results_path, 'r') as f:
                copy_data = json.load(f)
            
            for entry in copy_data:
                original_file = entry.get('Original File')
                new_files = entry.get('New file(s)')
                
                if not original_file:
                    continue
                
                # Handle both single files and lists (split files)
                if isinstance(new_files, list):
                    current_path = new_files[0] if new_files else original_file
                else:
                    current_path = new_files or original_file
                
                # Register file if it doesn't exist
                if os.path.exists(original_file):
                    file_id = self.register_file(
                        original_file, 
                        PipelineStage.RAW_COPY,
                        FileStatus.COMPLETED,
                        {
                            'copy_date': entry.get('Copy Date'),
                            'copy_time': entry.get('Copy Time'),
                            'transfer_status': entry.get('Transfer status')
                        }
                    )
                    
                    # Update current path
                    if current_path != original_file:
                        self.update_file_path(file_id, current_path, 'current')
                        
        except Exception as e:
            self.logger.error(f"Failed to import copy results: {e}")
    
    def _import_bids_conversion_data(self):
        """Import data from bids_conversion.tsv."""
        conversion_files = list((self.project_root / 'BIDS' / 'conversion_logs').glob('*.tsv'))
        
        if not conversion_files:
            self.logger.warning("No BIDS conversion files found, skipping import")
            return
        
        # Use the most recent conversion file
        latest_conversion = max(conversion_files, key=lambda x: x.stat().st_mtime)
        
        try:
            df = pd.read_csv(latest_conversion, sep='\t', dtype=str)
            
            for _, row in df.iterrows():
                raw_path = os.path.join(row['raw_path'], row['raw_name'])
                bids_path = os.path.join(row['bids_path'], row['bids_name'])
                
                if os.path.exists(raw_path):
                    # Register or update file
                    file_id = self.register_file(
                        raw_path,
                        PipelineStage.BIDSIFICATION,
                        FileStatus.COMPLETED if row['run_conversion'] == 'no' else FileStatus.PENDING,
                        {
                            'session': row['session_to'],
                            'acquisition': row['acquisition'],
                            'datatype': row['datatype'],
                            'task_flag': row.get('task_flag', 'ok')
                        }
                    )
                    
                    # Update BIDS path
                    if os.path.exists(bids_path):
                        self.update_file_path(file_id, bids_path, 'bids')
                        
        except Exception as e:
            self.logger.error(f"Failed to import BIDS conversion data: {e}")
    
    def _save_record(self, record: FileRecord):
        """Save file record to database."""
        with sqlite3.connect(self.db_path) as conn:
            # Convert lists and dicts to JSON strings
            processing_json = json.dumps(record.processing) if record.processing else None
            description_json = json.dumps(record.description) if record.description else None
            stage_history_json = json.dumps(record.stage_history) if record.stage_history else None
            conversion_details_json = json.dumps(record.conversion_details) if record.conversion_details else None
            processing_parameters_json = json.dumps(record.processing_parameters) if record.processing_parameters else None
            validation_results_json = json.dumps(record.validation_results) if record.validation_results else None
            error_log_json = json.dumps(record.error_log) if record.error_log else None
            
            conn.execute('''
                INSERT OR REPLACE INTO file_records (
                    file_id, original_path, current_path, bids_path,
                    participant, session, task, acquisition, datatype,
                    processing, description, current_stage, stage_history,
                    file_size, checksum, created_timestamp, last_modified,
                    conversion_details, processing_parameters, validation_results, error_log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.file_id, record.original_path, record.current_path, record.bids_path,
                record.participant, record.session, record.task, record.acquisition, record.datatype,
                processing_json, description_json, record.current_stage.value, stage_history_json,
                record.file_size, record.checksum, 
                record.created_timestamp.isoformat(), record.last_modified.isoformat(),
                conversion_details_json, processing_parameters_json, validation_results_json, error_log_json
            ))
    
    def _load_record(self, file_id: str) -> Optional[FileRecord]:
        """Load file record from database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                'SELECT * FROM file_records WHERE file_id = ?', 
                (file_id,)
            )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Parse JSON fields
            processing = json.loads(row['processing']) if row['processing'] else []
            description = json.loads(row['description']) if row['description'] else []
            stage_history = json.loads(row['stage_history']) if row['stage_history'] else {}
            conversion_details = json.loads(row['conversion_details']) if row['conversion_details'] else None
            processing_parameters = json.loads(row['processing_parameters']) if row['processing_parameters'] else None
            validation_results = json.loads(row['validation_results']) if row['validation_results'] else None
            error_log = json.loads(row['error_log']) if row['error_log'] else []
            
            return FileRecord(
                file_id=row['file_id'],
                original_path=row['original_path'],
                current_path=row['current_path'],
                bids_path=row['bids_path'],
                participant=row['participant'],
                session=row['session'],
                task=row['task'],
                acquisition=row['acquisition'],
                datatype=row['datatype'],
                processing=processing,
                description=description,
                current_stage=PipelineStage(row['current_stage']),
                stage_history=stage_history,
                file_size=row['file_size'],
                checksum=row['checksum'],
                created_timestamp=datetime.fromisoformat(row['created_timestamp']),
                last_modified=datetime.fromisoformat(row['last_modified']),
                conversion_details=conversion_details,
                processing_parameters=processing_parameters,
                validation_results=validation_results,
                error_log=error_log
            )
    
    def generate_summary_report(self) -> Dict:
        """
        Generate comprehensive pipeline summary report.
        
        Returns:
            dict: Complete pipeline statistics and status
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Overall statistics
            total_files = conn.execute('SELECT COUNT(*) as count FROM file_records').fetchone()['count']
            
            # Stage distribution
            stage_dist = {}
            for stage in PipelineStage:
                count = conn.execute(
                    'SELECT COUNT(*) as count FROM file_records WHERE current_stage = ?',
                    (stage.value,)
                ).fetchone()['count']
                stage_dist[stage.value] = count
            
            # Participant summary
            participants = conn.execute(
                'SELECT DISTINCT participant FROM file_records ORDER BY participant'
            ).fetchall()
            
            participant_summaries = []
            for p in participants:
                participant_id = p['participant']
                summary = self.get_participant_summary(participant_id)
                participant_summaries.append(summary)
            
            # Recent activity (last 24 hours)
            recent_cutoff = (datetime.now(timezone.utc) - pd.Timedelta(hours=24)).isoformat()
            recent_files = conn.execute(
                'SELECT COUNT(*) as count FROM file_records WHERE last_modified > ?',
                (recent_cutoff,)
            ).fetchone()['count']
            
            return {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'total_files': total_files,
                'stage_distribution': stage_dist,
                'participants': participant_summaries,
                'recent_activity': recent_files,
                'project_root': str(self.project_root)
            }

# Utility functions for integration with existing scripts
def get_project_tracker(project_root: str, config: Optional[Dict] = None) -> PipelineTracker:
    """
    Get or create a pipeline tracker for a project.
    
    Args:
        project_root (str): Project root directory
        config (dict, optional): Configuration dictionary
        
    Returns:
        PipelineTracker: Tracker instance
    """
    return PipelineTracker(project_root, config)

def track_file_operation(tracker: PipelineTracker, operation: str, 
                        file_path: str, result: bool, metadata: Optional[Dict] = None):
    """
    Helper function to track file operations from existing scripts.
    
    Args:
        tracker (PipelineTracker): Tracker instance
        operation (str): Operation type ('copy', 'bidsify', 'maxfilter', etc.)
        file_path (str): File path being operated on
        result (bool): Success status of operation
        metadata (dict, optional): Additional operation metadata
    """
    # Map operations to pipeline stages
    stage_mapping = {
        'copy': PipelineStage.RAW_COPY,
        'bidsify': PipelineStage.BIDSIFICATION,
        'maxfilter': PipelineStage.MAXFILTER,
        'preprocessing': PipelineStage.PREPROCESSING,
        'analysis': PipelineStage.ANALYSIS,
        'validation': PipelineStage.VALIDATION
    }
    
    stage = stage_mapping.get(operation, PipelineStage.RAW_COPY)
    status = FileStatus.COMPLETED if result else FileStatus.FAILED
    metadata = metadata or {}
    
    # Try to find existing file with different metadata combinations
    file_id = tracker.find_file_by_path(file_path, metadata)
    
    try:
        if file_id:
            # Update existing file
            success = tracker.update_file_stage(file_id, stage, status, metadata)
            if success:
                tracker.logger.info(f"Updated {operation} operation for {file_path}: {'success' if result else 'failed'}")
            else:
                tracker.logger.warning(f"Failed to update {operation} operation for {file_path}")
        else:
            # Register new file
            file_id = tracker.register_file(file_path, stage, status, metadata)
            tracker.logger.info(f"Registered new file for {operation} operation on {file_path}: {'success' if result else 'failed'}")
    except Exception as e:
        tracker.logger.error(f"Failed to track operation for {file_path}: {e}")