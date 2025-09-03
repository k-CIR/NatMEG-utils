"""
Database Integration Helper

Helper functions to integrate the file processing database with existing
NatMEG pipeline scripts. Provides decorators and context managers for
automatic operation tracking.

Author: GitHub Copilot
"""

import functools
import time
from contextlib import contextmanager
from typing import List, Union, Optional, Dict, Any, Callable
from pathlib import Path
import traceback
import os

from database import FileProcessingDatabase, create_database, log_file_processing
from utils import extract_info_from_filename


class ProcessingTracker:
    """Context manager and decorator for tracking file processing operations."""
    
    def __init__(self, db_path: str = None):
        """Initialize with database path."""
        self.db = create_database(db_path)
    
    def __enter__(self):
        """Enter context manager."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager."""
        pass
    
    def track_operation(
        self,
        operation_type: str,
        process_name: str = None,
        auto_detect_files: bool = True
    ):
        """
        Decorator to automatically track file processing operations.
        
        Args:
            operation_type (str): Type of operation ('bidsify', 'maxfilter', etc.)
            process_name (str, optional): Human-readable process name
            auto_detect_files (bool): Try to detect input/output files automatically
            
        Usage:
            @tracker.track_operation('maxfilter', 'MaxFilter Processing')
            def my_processing_function(input_file, output_file):
                # Your processing code here
                pass
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                input_files = []
                output_files = []
                error_message = None
                status = "completed"
                
                # Try to extract file paths from arguments
                if auto_detect_files:
                    input_files, output_files = self._extract_file_paths(*args, **kwargs)
                
                try:
                    # Execute the original function
                    result = func(*args, **kwargs)
                    
                    # Try to extract files from result if it's a file path or list
                    if auto_detect_files and result:
                        if isinstance(result, (str, Path)) and os.path.exists(str(result)):
                            output_files.append(str(result))
                        elif isinstance(result, (list, tuple)):
                            for item in result:
                                if isinstance(item, (str, Path)) and os.path.exists(str(item)):
                                    output_files.append(str(item))
                    
                    return result
                
                except Exception as e:
                    status = "failed"
                    error_message = str(e)
                    raise
                
                finally:
                    # Log the operation
                    duration = time.time() - start_time
                    
                    # Get function parameters
                    func_args = {}
                    if args or kwargs:
                        func_args = self._extract_parameters(func, *args, **kwargs)
                    
                    operation_id = self.db.log_operation(
                        operation_type=operation_type,
                        input_files=input_files,
                        output_files=output_files,
                        process_name=process_name or func.__name__,
                        parameters=func_args,
                        status=status,
                        error_message=error_message,
                        duration_seconds=duration
                    )
                    
                    print(f"Logged operation {operation_id}: {operation_type} - {status}")
            
            return wrapper
        return decorator
    
    def _extract_file_paths(self, *args, **kwargs) -> tuple[List[str], List[str]]:
        """Extract file paths from function arguments."""
        input_files = []
        output_files = []
        
        # Look through all arguments for file paths
        all_args = list(args) + list(kwargs.values())
        
        for arg in all_args:
            if isinstance(arg, (str, Path)):
                path_str = str(arg)
                # Check if it looks like a file path
                if ('/' in path_str or '\\' in path_str) and os.path.exists(path_str):
                    # Determine if input or output based on common patterns
                    if any(pattern in path_str.lower() for pattern in ['raw', 'input', 'src']):
                        input_files.append(path_str)
                    elif any(pattern in path_str.lower() for pattern in ['proc', 'output', 'bids', 'clean']):
                        output_files.append(path_str)
                    else:
                        # Default to input
                        input_files.append(path_str)
        
        return input_files, output_files
    
    def _extract_parameters(self, func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """Extract function parameters for logging."""
        try:
            import inspect
            
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Convert to serializable format
            parameters = {}
            for key, value in bound_args.arguments.items():
                if isinstance(value, (str, int, float, bool, list, dict)):
                    parameters[key] = value
                else:
                    parameters[key] = str(value)
            
            return parameters
        except Exception:
            return {"args": str(args)[:100], "kwargs": str(kwargs)[:100]}


@contextmanager
def track_processing_session(operation_type: str, db_path: str = None):
    """
    Context manager for tracking a processing session.
    
    Usage:
        with track_processing_session('bidsify') as tracker:
            tracker.log_operation('convert', input_files, output_files)
    """
    db = create_database(db_path)
    session_start = time.time()
    
    class SessionTracker:
        def log_operation(self, process_name: str, input_files: List[str], 
                         output_files: List[str] = None, **kwargs):
            return log_file_processing(
                db=db,
                operation_type=operation_type,
                input_files=input_files,
                output_files=output_files or [],
                process_name=process_name,
                **kwargs
            )
    
    try:
        yield SessionTracker()
    finally:
        session_duration = time.time() - session_start
        print(f"Processing session completed in {session_duration:.2f} seconds")


def integrate_with_existing_functions():
    """
    Example integration with existing pipeline functions.
    This shows how to modify existing functions to use the database.
    """
    
    # Example 1: Modify the log function in utils.py to also update database
    from utils import log as original_log
    
    def enhanced_log(process: str, message: str, level: str = 'info', 
                    logfile: str = 'log.log', logpath: str = '.', 
                    db_path: str = None):
        """Enhanced log function that also updates the processing database."""
        # Call original log function
        original_log(process, message, level, logfile, logpath)
        
        # Also log to database if this is a file processing message
        if any(keyword in message.lower() for keyword in ['processing', 'converted', 'saved', 'created']):
            db = create_database(db_path)
            
            # Try to extract file paths from message
            import re
            file_pattern = r'[\w\-_./]+\.[\w]+'
            files = re.findall(file_pattern, message)
            
            if files:
                db.log_operation(
                    operation_type=process.lower(),
                    input_files=[],
                    output_files=files,
                    process_name=f"{process} - {message[:50]}...",
                    parameters={"log_level": level, "message": message}
                )
    
    return enhanced_log


def batch_add_existing_files(directory: str, pattern: str = "*.fif", 
                           db_path: str = None, extract_metadata: bool = True):
    """
    Batch add existing files to the database.
    
    Args:
        directory (str): Directory to scan
        pattern (str): File pattern to match
        db_path (str): Database path
        extract_metadata (bool): Extract metadata from filenames
    """
    from glob import glob
    
    db = create_database(db_path)
    files = glob(os.path.join(directory, "**", pattern), recursive=True)
    
    print(f"Found {len(files)} files matching pattern '{pattern}' in {directory}")
    
    for i, file_path in enumerate(files):
        metadata = {}
        
        if extract_metadata:
            try:
                # Use existing filename parsing from utils
                file_info = extract_info_from_filename(file_path)
                metadata.update(file_info)
            except Exception as e:
                print(f"Warning: Could not extract metadata from {file_path}: {e}")
        
        # Add file to database
        file_id = db.add_file(file_path, metadata)
        
        if (i + 1) % 100 == 0:
            print(f"Added {i + 1}/{len(files)} files to database")
    
    print(f"Successfully added {len(files)} files to database")
    return db


def generate_processing_report(db_path: str = None, output_file: str = "processing_report.html"):
    """Generate an HTML report of all processing operations."""
    db = create_database(db_path)
    operations_df = db.get_operations_summary()
    
    if operations_df.empty:
        print("No operations found in database")
        return
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>File Processing Report</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .summary {{ background-color: #f9f9f9; padding: 15px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <h1>File Processing Report</h1>
        
        <div class="summary">
            <h2>Summary</h2>
            <p>Total Operations: {len(operations_df)}</p>
            <p>Total Files Tracked: {db.data['metadata']['total_files']}</p>
            <p>Database Last Updated: {db.data['metadata']['last_updated']}</p>
        </div>
        
        <h2>Recent Operations</h2>
        {operations_df.to_html(table_id="operations_table", classes="table")}
        
    </body>
    </html>
    """
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    print(f"Processing report saved to {output_file}")


if __name__ == "__main__":
    # Example usage
    print("Database Integration Helper")
    print("Available functions:")
    print("- ProcessingTracker: Decorator-based operation tracking")
    print("- track_processing_session: Context manager for sessions")  
    print("- batch_add_existing_files: Add existing files to database")
    print("- generate_processing_report: Generate HTML report")
    
    # Demonstrate batch adding files
    print("\nScanning for existing .fif files...")
    try:
        db = batch_add_existing_files("/neuro/data/local", "*.fif")
        print(f"Database contains {db.data['metadata']['total_files']} files")
        
        # Generate report
        generate_processing_report(output_file="processing_report.html")
        
    except Exception as e:
        print(f"Error: {e}")
