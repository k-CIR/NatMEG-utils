"""
File Processing Database Manager

A comprehensive script for tracking all file processing operations and saving
to a JSON database. Provides centralized logging of file transformations,
processing steps, and metadata across the NatMEG pipeline.

Author: GitHub Copilot
"""

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from glob import glob
import pandas as pd

# Default data paths
local_data = '/neuro/data/local'
sinuhe_data = '/neuro/data/sinuhe' 
kaptah_data = '/neuro/data/kaptah'


class FileProcessingDatabase:
    """
    Centralized database for tracking file processing operations.
    
    Features:
    - JSON-based storage for easy reading and writing
    - File integrity tracking with checksums
    - Processing step history and provenance
    - Search and query capabilities
    - Automatic backup and versioning
    """
    
    def __init__(self, db_path: str = "file_processing_database.json"):
        """
        Initialize the file processing database.
        
        Args:
            db_path (str): Path to the JSON database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_database()
    
    def _load_database(self):
        """Load existing database or create new one."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    self.data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self._init_empty_database()
        else:
            self._init_empty_database()
    
    def _init_empty_database(self):
        """Initialize empty database structure."""
        self.data = {
            "metadata": {
                "created": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "version": "1.0.0",
                "total_files": 0,
                "total_operations": 0
            },
            "files": {},
            "operations": [],
            "processing_chains": {}
        }
    
    def _save_database(self):
        """Save database to JSON file with backup."""
        # Create backup if database exists
        if self.db_path.exists():
            backup_path = self.db_path.with_suffix(f'.backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
            os.rename(self.db_path, backup_path)
        
        # Update metadata
        self.data["metadata"]["last_updated"] = datetime.now().isoformat()
        self.data["metadata"]["total_files"] = len(self.data["files"])
        self.data["metadata"]["total_operations"] = len(self.data["operations"])
        
        # Save database
        with open(self.db_path, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
    
    def _calculate_checksum(self, file_path: str) -> Optional[str]:
        """Calculate SHA256 checksum of file."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except (FileNotFoundError, PermissionError):
            return None
    
    def add_file(self, file_path: str, metadata: Optional[Dict] = None) -> str:
        """
        Add a file to the database.
        
        Args:
            file_path (str): Path to the file
            metadata (dict, optional): Additional metadata
            
        Returns:
            str: Unique file ID
        """
        file_path = str(Path(file_path).resolve())
        file_id = hashlib.md5(file_path.encode()).hexdigest()
        
        # Get file stats
        if os.path.exists(file_path):
            stat = os.stat(file_path)
            checksum = self._calculate_checksum(file_path)
            size = stat.st_size
            modified_time = datetime.fromtimestamp(stat.st_mtime).isoformat()
        else:
            checksum = None
            size = None
            modified_time = None
        
        file_record = {
            "file_id": file_id,
            "path": file_path,
            "filename": os.path.basename(file_path),
            "directory": os.path.dirname(file_path),
            "extension": Path(file_path).suffix,
            "size_bytes": size,
            "checksum": checksum,
            "created_in_db": datetime.now().isoformat(),
            "last_modified": modified_time,
            "exists": os.path.exists(file_path),
            "processing_history": [],
            "metadata": metadata or {}
        }
        
        self.data["files"][file_id] = file_record
        self._save_database()
        return file_id
    
    def log_operation(
        self,
        operation_type: str,
        input_files: List[str],
        output_files: List[str],
        process_name: str,
        parameters: Optional[Dict] = None,
        status: str = "completed",
        error_message: Optional[str] = None,
        duration_seconds: Optional[float] = None
    ) -> str:
        """
        Log a file processing operation.
        
        Args:
            operation_type (str): Type of operation (e.g., 'bidsify', 'maxfilter', 'hpi')
            input_files (List[str]): List of input file paths
            output_files (List[str]): List of output file paths  
            process_name (str): Name of the processing step
            parameters (dict, optional): Processing parameters used
            status (str): Operation status ('completed', 'failed', 'in_progress')
            error_message (str, optional): Error message if failed
            duration_seconds (float, optional): Processing duration
            
        Returns:
            str: Unique operation ID
        """
        operation_id = f"op_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.data['operations'])}"
        
        # Ensure input and output files are in database
        input_file_ids = []
        for file_path in input_files:
            if os.path.exists(file_path):
                file_id = self.add_file(file_path)
                input_file_ids.append(file_id)
        
        output_file_ids = []
        for file_path in output_files:
            file_id = self.add_file(file_path)
            output_file_ids.append(file_id)
        
        operation_record = {
            "operation_id": operation_id,
            "timestamp": datetime.now().isoformat(),
            "operation_type": operation_type,
            "process_name": process_name,
            "input_files": input_file_ids,
            "output_files": output_file_ids,
            "parameters": parameters or {},
            "status": status,
            "error_message": error_message,
            "duration_seconds": duration_seconds,
            "user": os.getenv("USER", "unknown"),
            "hostname": os.getenv("HOSTNAME", "unknown")
        }
        
        self.data["operations"].append(operation_record)
        
        # Update file processing history
        for file_id in output_file_ids:
            if file_id in self.data["files"]:
                self.data["files"][file_id]["processing_history"].append({
                    "operation_id": operation_id,
                    "timestamp": datetime.now().isoformat(),
                    "operation_type": operation_type,
                    "process_name": process_name
                })
        
        self._save_database()
        return operation_id
    
    def update_file_status(self, file_path: str, status: Dict[str, Any]):
        """Update file status and metadata."""
        file_id = hashlib.md5(str(Path(file_path).resolve()).encode()).hexdigest()
        
        if file_id in self.data["files"]:
            self.data["files"][file_id]["metadata"].update(status)
            self.data["files"][file_id]["last_updated"] = datetime.now().isoformat()
            self._save_database()
    
    def get_file_history(self, file_path: str) -> Optional[Dict]:
        """Get processing history for a file."""
        file_id = hashlib.md5(str(Path(file_path).resolve()).encode()).hexdigest()
        return self.data["files"].get(file_id)
    
    def search_files(self, **kwargs) -> List[Dict]:
        """
        Search files by criteria.
        
        Args:
            **kwargs: Search criteria (filename, extension, operation_type, etc.)
            
        Returns:
            List[Dict]: Matching file records
        """
        results = []
        
        for file_record in self.data["files"].values():
            match = True
            
            for key, value in kwargs.items():
                if key == "filename_contains":
                    if value.lower() not in file_record["filename"].lower():
                        match = False
                        break
                elif key == "extension":
                    if file_record["extension"] != value:
                        match = False
                        break
                elif key == "operation_type":
                    if not any(op["operation_type"] == value for op in file_record["processing_history"]):
                        match = False
                        break
                elif key == "exists":
                    if file_record["exists"] != value:
                        match = False
                        break
                elif key in file_record:
                    if file_record[key] != value:
                        match = False
                        break
            
            if match:
                results.append(file_record)
        
        return results
    
    def get_operations_summary(self) -> pd.DataFrame:
        """Get summary of all operations as DataFrame."""
        if not self.data["operations"]:
            return pd.DataFrame()
        
        operations_data = []
        for op in self.data["operations"]:
            operations_data.append({
                "operation_id": op["operation_id"],
                "timestamp": op["timestamp"],
                "operation_type": op["operation_type"],
                "process_name": op["process_name"],
                "num_inputs": len(op["input_files"]),
                "num_outputs": len(op["output_files"]),
                "status": op["status"],
                "duration_seconds": op.get("duration_seconds"),
                "user": op.get("user"),
                "hostname": op.get("hostname")
            })
        
        return pd.DataFrame(operations_data)
    
    def export_to_csv(self, output_dir: str = "."):
        """Export database contents to CSV files."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export files
        if self.data["files"]:
            files_data = []
            for file_record in self.data["files"].values():
                files_data.append({
                    "file_id": file_record["file_id"],
                    "path": file_record["path"],
                    "filename": file_record["filename"],
                    "directory": file_record["directory"],
                    "extension": file_record["extension"],
                    "size_bytes": file_record["size_bytes"],
                    "exists": file_record["exists"],
                    "created_in_db": file_record["created_in_db"],
                    "last_modified": file_record["last_modified"],
                    "num_operations": len(file_record["processing_history"])
                })
            
            files_df = pd.DataFrame(files_data)
            files_df.to_csv(output_dir / "files.csv", index=False)
        
        # Export operations
        operations_df = self.get_operations_summary()
        if not operations_df.empty:
            operations_df.to_csv(output_dir / "operations.csv", index=False)
    
    def cleanup_old_backups(self, keep_last_n: int = 10):
        """Remove old backup files, keeping only the most recent ones."""
        backup_pattern = str(self.db_path.with_suffix('.backup_*.json'))
        backup_files = sorted(glob(backup_pattern))
        
        if len(backup_files) > keep_last_n:
            for backup_file in backup_files[:-keep_last_n]:
                os.remove(backup_file)


# Convenience functions for integration with existing pipeline
def create_database(db_path: str = None) -> FileProcessingDatabase:
    """Create or load file processing database."""
    if db_path is None:
        db_path = os.path.join(local_data, "file_processing_database.json")
    
    return FileProcessingDatabase(db_path)


def log_file_processing(
    db: FileProcessingDatabase,
    operation_type: str,
    input_files: Union[str, List[str]],
    output_files: Union[str, List[str]] = None,
    process_name: str = None,
    **kwargs
) -> str:
    """
    Convenience function to log file processing operations.
    
    Args:
        db (FileProcessingDatabase): Database instance
        operation_type (str): Type of operation
        input_files (str or List[str]): Input file(s)
        output_files (str or List[str], optional): Output file(s)
        process_name (str, optional): Process name
        **kwargs: Additional parameters
        
    Returns:
        str: Operation ID
    """
    # Convert single files to lists
    if isinstance(input_files, str):
        input_files = [input_files]
    if isinstance(output_files, str):
        output_files = [output_files]
    elif output_files is None:
        output_files = []
    
    if process_name is None:
        process_name = operation_type
    
    return db.log_operation(
        operation_type=operation_type,
        input_files=input_files,
        output_files=output_files,
        process_name=process_name,
        **kwargs
    )


# Example usage and integration helper
def demonstrate_usage():
    """Demonstrate basic usage of the file processing database."""
    # Create database instance
    db = create_database()
    
    print(f"Database initialized at: {db.db_path}")
    print(f"Total files tracked: {db.data['metadata']['total_files']}")
    print(f"Total operations: {db.data['metadata']['total_operations']}")
    
    # Example: Log a bidsify operation
    operation_id = log_file_processing(
        db=db,
        operation_type="bidsify",
        input_files=["example_raw.fif"],
        output_files=["sub-001_task-example_meg.fif"],
        process_name="BIDS Conversion",
        parameters={"task": "example", "participant": "001"}
    )
    
    print(f"Logged operation: {operation_id}")
    
    # Search for files
    meg_files = db.search_files(extension=".fif")
    print(f"Found {len(meg_files)} .fif files")
    
    # Export to CSV
    db.export_to_csv("./database_export")
    print("Exported database to CSV files")
    
    return db


if __name__ == "__main__":
    demonstrate_usage()