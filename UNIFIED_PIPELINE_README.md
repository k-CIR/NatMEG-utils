# Unified Pipeline Tracking & Reporting System

A comprehensive tracking and reporting system for MEG data processing pipelines. This system unifies logging from all pipeline stages and provides interactive HTML reports to track files from raw acquisition through final analysis.

## Overview

The unified system integrates with your existing MEG processing workflow to provide:

- **Centralized File Tracking**: Track files through all pipeline stages
- **Interactive Reports**: HTML dashboards with filtering and real-time updates  
- **Legacy Data Integration**: Import existing logs from copy_results.json and bids_conversion.tsv
- **Stage-based Progress**: Monitor progress through acquisition, copying, BIDS conversion, processing, and analysis
- **Participant Views**: Individual participant reports and summaries

## System Components

### Core Files

- `pipeline_tracker.py` - Central tracking system with SQLite database
- `pipeline_report_generator.py` - HTML report generation with Jinja2 templates
- `pipeline_report.py` - Command-line interface for report generation
- `pipeline_demo.py` - Example usage and integration demonstrations

### Integration Files  

- `copy_to_cerberos.py` - Modified to include pipeline tracking
- `bidsify.py` - Modified to include pipeline tracking
- `render_report.py` - Existing file comparison reports
- `utils.py` - Shared utilities (converted from PyQt6 to tkinter)

## Pipeline Stages

The system tracks files through these stages:

1. **raw_acquisition** - Initial data collection
2. **raw_copy** - Transfer from acquisition systems to local storage
3. **bidsification** - Conversion to BIDS format
4. **maxfilter** - Signal space separation processing
5. **preprocessing** - Filtering, artifact rejection, etc.
6. **analysis** - Statistical analysis and source reconstruction
7. **validation** - Quality control and validation
8. **reporting** - Final reports and summaries
9. **archived** - Long-term storage

## Installation & Setup

### Prerequisites

```bash
# Core dependencies (should already be installed)
pip install pandas numpy jinja2 sqlite3

# Optional dependencies (for full functionality)
pip install mne mne-bids tqdm
```

### Basic Setup

1. **Place files in your project directory**:
   ```
   /your/project/
   ├── pipeline_tracker.py
   ├── pipeline_report_generator.py  
   ├── pipeline_report.py
   ├── copy_to_cerberos.py (modified)
   ├── bidsify.py (modified)
   └── utils.py (updated)
   ```

2. **Initialize tracking for existing project**:
   ```python
   from pipeline_tracker import get_project_tracker
   
   tracker = get_project_tracker('/path/to/project')
   tracker.import_legacy_data()  # Import existing logs
   ```

## Usage Examples

### Generate Main Dashboard

```bash
# Using config file
python pipeline_report.py --config project_config.yml

# Using project directory
python pipeline_report.py --project-root /data/projects/MyStudy

# Generate and open in browser
python pipeline_report.py --config config.yml --open
```

### Participant-Specific Reports

```bash
# Generate report for participant 001
python pipeline_report.py --config config.yml --participant 001

# Generate report for specific pipeline stage
python pipeline_report.py --config config.yml --stage bidsification
```

### Integration with Existing Scripts

The system automatically integrates when you run existing scripts:

```bash
# Copy files with tracking
python copy_to_cerberos.py --config config.yml

# BIDS conversion with tracking  
python bidsify.py --config config.yml

# Generate updated reports
python pipeline_report.py --config config.yml
```

### Programmatic Usage

```python
from pipeline_tracker import get_project_tracker, track_file_operation
from pipeline_report_generator import PipelineReportGenerator

# Initialize tracker
tracker = get_project_tracker('/path/to/project')

# Register a file
file_id = tracker.register_file(
    '/path/to/data.fif',
    PipelineStage.RAW_ACQUISITION
)

# Update file progress
tracker.update_file_stage(
    file_id, 
    PipelineStage.BIDSIFICATION, 
    FileStatus.COMPLETED
)

# Generate reports
generator = PipelineReportGenerator(tracker)
report_path = generator.generate_dashboard_report()
```

## Report Features

### Interactive Dashboard

- **Summary Statistics**: Total files, participants, recent activity
- **Stage Distribution**: Visual breakdown of files per pipeline stage
- **Participant Overview**: Progress summary for each participant
- **File Details Table**: Sortable, filterable table of all files

### Filtering & Navigation

- **Stage Filter**: View files in specific pipeline stages
- **Participant Filter**: Focus on individual participants
- **Task Search**: Find files by task name
- **Real-time Updates**: Auto-refresh every 5 minutes

### Progress Visualization

- **Progress Bars**: Visual completion status for each file
- **Status Badges**: Color-coded stage and status indicators  
- **Timeline View**: File progression through pipeline stages
- **Error Tracking**: Highlight files requiring attention

## Data Storage

### SQLite Database

The system uses SQLite for efficient storage:

- **Location**: `pipeline_tracking/pipeline_tracker.db`
- **Schema**: Comprehensive file metadata with JSON fields
- **Indexing**: Optimized for participant, stage, and task queries
- **Backup**: Standard SQLite backup procedures apply

### Legacy Data Import

Automatically imports from existing systems:

- **copy_results.json**: File transfer logs from copy_to_cerberos.py
- **bids_conversion.tsv**: BIDS conversion logs from bidsify.py  
- **Existing reports**: Integration with render_report.py outputs

## Configuration

### Project Configuration

The system reads standard project configuration files:

```yaml
Project:
  Name: "MyMEGStudy"
  Root: "/data/projects"
  Raw: "/data/projects/MyMEGStudy/raw"
  BIDS: "/data/projects/MyMEGStudy/BIDS"
  Logfile: "pipeline.log"

BIDS:
  Dataset_description: "dataset_description.json"
  Participants: "participants.tsv"
  # ... other BIDS settings
```

### Tracking Configuration

Additional tracking settings can be specified:

```python
config = {
    'pipeline_tracking': {
        'auto_import': True,
        'report_refresh_interval': 300,  # seconds
        'max_file_history': 1000,
        'backup_frequency': 'daily'
    }
}
```

## Backward Compatibility

The system maintains full backward compatibility:

- **Existing Scripts**: Continue to work without modification
- **Legacy Logs**: Automatically imported and integrated
- **File Formats**: No changes to existing file structures
- **Workflows**: Minimal disruption to established processes

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```
   ImportError: No module named 'pipeline_tracker'
   ```
   - Ensure all files are in the same directory or Python path
   - Check that required dependencies are installed

2. **Database Locked**
   ```
   sqlite3.OperationalError: database is locked
   ```
   - Close other applications accessing the database
   - Restart the tracking system

3. **Legacy Data Not Found**
   ```
   Warning: copy_results.json not found, skipping import
   ```
   - Verify file paths in configuration
   - Run copy_to_cerberos.py to generate initial data

### Performance Considerations

- **Large Projects**: Database scales well to thousands of files
- **Report Generation**: May take longer for projects with many participants
- **Memory Usage**: Minimal overhead for normal operation
- **Disk Space**: SQLite database grows with tracked files

## Development & Extension

### Adding New Pipeline Stages

1. **Update PipelineStage enum**:
   ```python
   class PipelineStage(Enum):
       # ... existing stages
       MY_NEW_STAGE = "my_new_stage"
   ```

2. **Add stage tracking to scripts**:
   ```python
   track_file_operation(tracker, 'my_operation', file_path, success, metadata)
   ```

3. **Update report templates** (optional):
   - Add stage-specific styling
   - Include new metadata fields

### Custom Reports

Create custom report generators:

```python
class CustomReportGenerator(PipelineReportGenerator):
    def generate_custom_report(self):
        # Your custom report logic
        pass
```

## Support & Contribution

### Getting Help

1. **Check the demo**: Run `python pipeline_demo.py` for examples
2. **Review logs**: Check pipeline logs for detailed error messages  
3. **Database inspection**: Use SQLite tools to examine tracker database
4. **Documentation**: Review docstrings in source files

### Contributing

1. **Follow existing patterns**: Maintain consistency with current code style
2. **Add tests**: Include examples in pipeline_demo.py
3. **Update documentation**: Keep README and docstrings current
4. **Backward compatibility**: Ensure changes don't break existing workflows

## License & Credits

- **Author**: Andreas Gerhardsson
- **Integration**: Built on existing NatMEG processing pipeline
- **Dependencies**: MNE-Python, MNE-BIDS, pandas, Jinja2
- **License**: Same as parent project

---

For questions or issues, refer to the inline documentation in the source files or run the demo script for hands-on examples.