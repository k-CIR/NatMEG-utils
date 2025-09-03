# File Processing Database System

A comprehensive JSON-based database system for tracking all file processing operations in the NatMEG pipeline. This system provides centralized logging, provenance tracking, and analysis capabilities for MEG data processing workflows.

## Features

- **JSON-based storage** for easy reading and writing
- **File integrity tracking** with SHA256 checksums
- **Processing step history** and provenance tracking
- **Search and query capabilities** for files and operations
- **Automatic backup** and versioning
- **CSV and HTML export** capabilities
- **Integration decorators** for existing functions
- **Command-line interface** for easy management

## Core Components

### 1. Database Module (`database.py`)

The main database class that handles all file and operation tracking:

```python
from database import create_database

# Create or load database
db = create_database("my_processing_database.json")

# Add files
file_id = db.add_file("/path/to/file.fif", metadata={"participant": "001"})

# Log operations
operation_id = db.log_operation(
    operation_type="maxfilter",
    input_files=["/path/to/raw.fif"],
    output_files=["/path/to/processed.fif"],
    process_name="MaxFilter tSSS",
    parameters={"tsss": True, "movecomp": True},
    duration_seconds=45.2
)

# Search files
meg_files = db.search_files(extension=".fif")
processed_files = db.search_files(operation_type="maxfilter")
```

### 2. Integration Helpers (`database_integration.py`)

Provides decorators and context managers for automatic tracking:

```python
from database_integration import ProcessingTracker, track_processing_session

# Using decorators
tracker = ProcessingTracker()

@tracker.track_operation('maxfilter', 'MaxFilter Processing')
def process_meg_file(input_file, output_file, **params):
    # Your processing code here
    return output_file

# Using context managers
with track_processing_session('bidsify') as session:
    session.log_operation('convert', input_files, output_files)
```

### 3. Command Line Interface (`db_cli.py`)

Easy-to-use CLI for database management:

```bash
# Initialize database
python db_cli.py init --path my_database.json

# Add files to database
python db_cli.py add-files /data/meg --pattern "*.fif"

# Search for files
python db_cli.py search --extension .fif --exists true

# Log operations manually
python db_cli.py log-operation maxfilter input.fif output.fif --name "MaxFilter tSSS"

# Generate reports
python db_cli.py report --format html --output report.html

# Check database status
python db_cli.py status
```

## Database Structure

The JSON database has the following structure:

```json
{
  "metadata": {
    "created": "2025-09-03T11:17:31.788864",
    "last_updated": "2025-09-03T11:17:31.795058", 
    "version": "1.0.0",
    "total_files": 150,
    "total_operations": 45
  },
  "files": {
    "file_id_hash": {
      "file_id": "abc123...",
      "path": "/full/path/to/file.fif",
      "filename": "file.fif",
      "directory": "/full/path/to",
      "extension": ".fif",
      "size_bytes": 12345,
      "checksum": "sha256_hash",
      "created_in_db": "2025-09-03T10:00:00",
      "last_modified": "2025-09-03T09:30:00",
      "exists": true,
      "processing_history": [...],
      "metadata": {...}
    }
  },
  "operations": [...],
  "processing_chains": {...}
}
```

## Integration with Existing Pipeline

### Option 1: Decorator Integration

Add decorators to existing functions:

```python
# In maxfilter.py
from database_integration import ProcessingTracker

tracker = ProcessingTracker()

class MaxFilter:
    @tracker.track_operation('maxfilter', 'MaxFilter Processing')
    def process_file(self, input_file, output_file, **params):
        # Existing MaxFilter code
        pass
```

### Option 2: Manual Logging

Add explicit logging calls:

```python
# In bidsify.py
from database import create_database

def bidsify(config):
    db = create_database()
    
    # Existing bidsify logic...
    
    # Log the operation
    db.log_operation(
        operation_type="bidsify",
        input_files=[raw_file],
        output_files=[bids_file],
        process_name="BIDS Conversion",
        parameters=config
    )
```

### Option 3: Enhanced Logging

Modify the existing `log` function in `utils.py`:

```python
def enhanced_log(process, message, level='info', **kwargs):
    # Call original log function
    original_log(process, message, level, **kwargs)
    
    # Also track in database if it's a processing message
    if 'processed' in message.lower():
        db = create_database()
        # Extract files and log operation...
```

## Usage Examples

### Basic File Tracking

```python
from database import create_database

db = create_database()

# Add all .fif files in a directory
import glob
for fif_file in glob.glob("/data/**/*.fif", recursive=True):
    db.add_file(fif_file)

print(f"Database now tracks {db.data['metadata']['total_files']} files")
```

### Process Monitoring

```python
import time
from database_integration import track_processing_session

with track_processing_session('data_analysis') as tracker:
    start_time = time.time()
    
    # Your analysis code here
    result = analyze_data(input_files)
    
    tracker.log_operation(
        'analysis_complete',
        input_files=input_files,
        output_files=[result],
        duration_seconds=time.time() - start_time
    )
```

### Batch Processing with Tracking

```python
from database_integration import ProcessingTracker

tracker = ProcessingTracker()

@tracker.track_operation('preprocessing')
def preprocess_file(file_path):
    # Your preprocessing code
    output_path = file_path.replace('.fif', '_preprocessed.fif')
    # ... processing logic ...
    return output_path

# Process multiple files - each will be automatically tracked
for file_path in file_list:
    preprocess_file(file_path)
```

## Reporting and Analysis

### Generate Processing Reports

```python
from database_integration import generate_processing_report

# Generate HTML report
generate_processing_report(output_file="processing_report.html")

# Export to CSV
db = create_database()
db.export_to_csv("./export_directory")
```

### Query Operations

```python
db = create_database()

# Find all MaxFilter operations
operations = db.get_operations_summary()
maxfilter_ops = operations[operations['operation_type'] == 'maxfilter']

# Find files processed in the last 24 hours
from datetime import datetime, timedelta
recent_files = []
cutoff = datetime.now() - timedelta(hours=24)

for file_record in db.data['files'].values():
    if file_record['processing_history']:
        last_processed = datetime.fromisoformat(
            file_record['processing_history'][-1]['timestamp']
        )
        if last_processed > cutoff:
            recent_files.append(file_record)

print(f"Found {len(recent_files)} recently processed files")
```

## Maintenance

### Backup Management

The database automatically creates backups with timestamps. To clean old backups:

```python
db = create_database()
db.cleanup_old_backups(keep_last_n=10)  # Keep only 10 most recent backups
```

### Database Integrity

Check and update file statuses:

```python
db = create_database()

# Update file existence status
for file_id, file_record in db.data['files'].items():
    current_exists = os.path.exists(file_record['path'])
    if current_exists != file_record['exists']:
        db.update_file_status(file_record['path'], {'exists': current_exists})
```

## Demo and Testing

Run the demonstration script to see all features in action:

```bash
python demo_database.py
```

This will create sample files, demonstrate all database features, and clean up afterwards.

## Best Practices

1. **Initialize early**: Create the database at the start of your pipeline
2. **Use context managers**: For batch operations, use `track_processing_session`
3. **Add metadata**: Include relevant parameters and settings in operation logs
4. **Regular backups**: The system auto-backs up, but consider external backups too
5. **Monitor disk space**: JSON databases can grow large with extensive file tracking
6. **Use search efficiently**: Index by common query patterns for better performance

## Troubleshooting

### Database locked or corrupt
```bash
# Create new database from backup
cp database.backup_20250903_101500.json database.json
```

### Large database files
```bash
# Export to CSV and restart with clean database
python db_cli.py export --output-dir ./archive
python db_cli.py init --path new_database.json
```

### Integration issues
```python
# Test database connectivity
from database import create_database
try:
    db = create_database()
    print("Database connection successful")
except Exception as e:
    print(f"Database error: {e}")
```

## Contributing

To extend the database system:

1. Add new operation types in `database.py`
2. Create integration helpers in `database_integration.py` 
3. Add CLI commands in `db_cli.py`
4. Update this README with examples

The system is designed to be extensible and can accommodate new processing steps, file types, and analysis workflows as needed.
