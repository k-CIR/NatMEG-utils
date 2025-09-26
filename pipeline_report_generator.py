"""
Pipeline Report Generator for NatMEG Processing

Generates comprehensive HTML reports showing file lifecycle through the entire
MEG processing pipeline. Integrates with the unified pipeline tracking system
to provide real-time status updates and interactive visualization.

Features:
- Interactive HTML dashboard with file lifecycle visualization
- Stage-by-stage progress tracking with timestamps
- Participant-based filtering and grouping
- Real-time status updates with auto-refresh
- Integration with existing report systems
- Export capabilities for sharing and archiving

Author: Andreas Gerhardsson
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from jinja2 import Environment, FileSystemLoader, Template

from pipeline_tracker import PipelineTracker, PipelineStage, FileStatus
from utils import get_logger

class PipelineReportGenerator:
    """
    Generates comprehensive HTML reports for the MEG processing pipeline.
    
    Creates interactive dashboards showing file progress through all pipeline
    stages with detailed status information and filtering capabilities.
    """
    
    def __init__(self, tracker: PipelineTracker):
        """
        Initialize report generator.
        
        Args:
            tracker (PipelineTracker): Pipeline tracker instance
        """
        self.tracker = tracker
        self.logger = get_logger('PipelineReportGenerator')
        self.report_dir = tracker.tracking_dir / 'reports'
        self.report_dir.mkdir(exist_ok=True)
        
        # Setup Jinja2 environment
        template_dir = Path(__file__).parent / 'templates'
        if template_dir.exists():
            self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        else:
            # Use embedded templates if no template directory
            self.jinja_env = Environment(loader=None)
        
        self._setup_filters()
    
    def _setup_filters(self):
        """Setup custom Jinja2 filters for report generation."""
        
        def datetime_format(timestamp_str, fmt='%Y-%m-%d %H:%M:%S'):
            """Format ISO timestamp string."""
            if not timestamp_str:
                return ''
            try:
                dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return dt.strftime(fmt)
            except:
                return timestamp_str
        
        def human_bytes(num, suffix='B'):
            """Convert bytes to human readable format."""
            try:
                num = float(num)
            except:
                return ''
            for unit in ['','K','M','G','T','P','E','Z']:
                if abs(num) < 1024.0:
                    return f"{num:3.1f}{unit}{suffix}"
                num /= 1024.0
            return f"{num:.1f}Y{suffix}"
        
        def stage_progress_percent(stage_history, total_stages=None):
            """Calculate progress percentage through pipeline stages."""
            if not stage_history:
                return 0
            
            stage_order = [stage.value for stage in PipelineStage]
            completed_stages = []
            
            for stage_name, stage_info in stage_history.items():
                if stage_info.get('status') == FileStatus.COMPLETED.value:
                    completed_stages.append(stage_name)
            
            if not completed_stages:
                return 0
                
            # Find highest completed stage
            max_completed_idx = 0
            for stage in completed_stages:
                try:
                    idx = stage_order.index(stage)
                    max_completed_idx = max(max_completed_idx, idx + 1)
                except ValueError:
                    continue
            
            return int((max_completed_idx / len(stage_order)) * 100)
        
        def status_badge_class(status):
            """Get CSS class for status badge."""
            status_classes = {
                FileStatus.PENDING.value: 'badge-warning',
                FileStatus.IN_PROGRESS.value: 'badge-info',
                FileStatus.COMPLETED.value: 'badge-success',
                FileStatus.FAILED.value: 'badge-danger',
                FileStatus.SKIPPED.value: 'badge-secondary',
                FileStatus.REQUIRES_ATTENTION.value: 'badge-warning'
            }
            return status_classes.get(status, 'badge-secondary')
        
        def stage_badge_class(stage):
            """Get CSS class for pipeline stage."""
            stage_classes = {
                PipelineStage.RAW_ACQUISITION.value: 'badge-primary',
                PipelineStage.RAW_COPY.value: 'badge-info',
                PipelineStage.BIDSIFICATION.value: 'badge-success',
                PipelineStage.MAXFILTER.value: 'badge-warning',
                PipelineStage.PREPROCESSING.value: 'badge-info',
                PipelineStage.ANALYSIS.value: 'badge-secondary',
                PipelineStage.VALIDATION.value: 'badge-success',
                PipelineStage.REPORTING.value: 'badge-dark',
                PipelineStage.ARCHIVED.value: 'badge-light'
            }
            return stage_classes.get(stage, 'badge-secondary')
        
        def basename_filter(file_path):
            """Extract basename from file path."""
            if not file_path:
                return ''
            try:
                return os.path.basename(file_path)
            except:
                return str(file_path)
        
        # Register filters
        self.jinja_env.filters['datetime'] = datetime_format
        self.jinja_env.filters['filesize'] = human_bytes
        self.jinja_env.filters['progress'] = stage_progress_percent
        self.jinja_env.filters['status_class'] = status_badge_class
        self.jinja_env.filters['stage_class'] = stage_badge_class
        self.jinja_env.filters['basename'] = basename_filter
    
    def generate_dashboard_report(self, output_file: Optional[str] = None) -> str:
        """
        Generate main pipeline dashboard report.
        
        Args:
            output_file (str, optional): Output file path
            
        Returns:
            str: Path to generated report
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.report_dir / f'pipeline_dashboard_{timestamp}.html'
        
        # Get comprehensive pipeline data
        summary = self.tracker.generate_summary_report()
        
        # Get detailed file information
        all_files = []
        for stage in PipelineStage:
            stage_files = self.tracker.get_files_by_stage(stage)
            all_files.extend(stage_files)
        
        # Organize data for template
        template_data = {
            'report_title': 'NatMEG Pipeline Dashboard',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'summary': summary,
            'files': all_files,
            'stages': [stage.value for stage in PipelineStage],
            'status_types': [status.value for status in FileStatus],
            'project_root': str(self.tracker.project_root)
        }
        
        # Render template
        template = self._get_dashboard_template()
        html_content = template.render(**template_data)
        
        # Write report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"Generated dashboard report: {output_file}")
        return str(output_file)
    
    def generate_participant_report(self, participant: str, output_file: Optional[str] = None) -> str:
        """
        Generate detailed report for a specific participant.
        
        Args:
            participant (str): Participant ID
            output_file (str, optional): Output file path
            
        Returns:
            str: Path to generated report
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.report_dir / f'participant_{participant}_{timestamp}.html'
        
        # Get participant data
        participant_data = self.tracker.get_participant_summary(participant)
        
        # Template data
        template_data = {
            'report_title': f'Participant {participant} Pipeline Report',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'participant': participant_data,
            'stages': [stage.value for stage in PipelineStage],
            'status_types': [status.value for status in FileStatus]
        }
        
        # Render template
        template = self._get_participant_template()
        html_content = template.render(**template_data)
        
        # Write report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"Generated participant report for {participant}: {output_file}")
        return str(output_file)
    
    def generate_stage_report(self, stage: PipelineStage, output_file: Optional[str] = None) -> str:
        """
        Generate detailed report for a specific pipeline stage.
        
        Args:
            stage (PipelineStage): Pipeline stage
            output_file (str, optional): Output file path
            
        Returns:
            str: Path to generated report
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.report_dir / f'stage_{stage.value}_{timestamp}.html'
        
        # Get stage data
        stage_files = self.tracker.get_files_by_stage(stage)
        
        # Template data
        template_data = {
            'report_title': f'{stage.value.title()} Stage Report',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'stage': stage.value,
            'files': stage_files,
            'total_files': len(stage_files)
        }
        
        # Render template
        template = self._get_stage_template()
        html_content = template.render(**template_data)
        
        # Write report
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"Generated stage report for {stage.value}: {output_file}")
        return str(output_file)
    
    def generate_summary_json(self, output_file: Optional[str] = None) -> str:
        """
        Generate JSON summary for API access.
        
        Args:
            output_file (str, optional): Output file path
            
        Returns:
            str: Path to generated JSON file
        """
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = self.report_dir / f'pipeline_summary_{timestamp}.json'
        
        summary = self.tracker.generate_summary_report()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, default=str)
        
        self.logger.info(f"Generated JSON summary: {output_file}")
        return str(output_file)
    
    def _get_dashboard_template(self) -> Template:
        """Get dashboard HTML template."""
        return self.jinja_env.from_string(self._embedded_dashboard_template())
    
    def _get_participant_template(self) -> Template:
        """Get participant report HTML template.""" 
        return self.jinja_env.from_string(self._embedded_participant_template())
    
    def _get_stage_template(self) -> Template:
        """Get stage report HTML template."""
        return self.jinja_env.from_string(self._embedded_stage_template())
    
    def _embedded_dashboard_template(self) -> str:
        """Embedded HTML template for dashboard report."""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report_title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        .pipeline-stage { border-left: 4px solid #007bff; padding-left: 10px; margin-bottom: 10px; }
        .stage-raw_acquisition { border-left-color: #007bff; }
        .stage-raw_copy { border-left-color: #17a2b8; }
        .stage-bidsification { border-left-color: #28a745; }
        .stage-maxfilter { border-left-color: #ffc107; }
        .stage-preprocessing { border-left-color: #17a2b8; }
        .stage-analysis { border-left-color: #6c757d; }
        .stage-validation { border-left-color: #28a745; }
        .stage-reporting { border-left-color: #343a40; }
        .stage-archived { border-left-color: #f8f9fa; }
        .progress-bar-custom { height: 20px; }
        .file-row { transition: background-color 0.2s; }
        .file-row:hover { background-color: #f8f9fa; }
        .badge { font-size: 0.75em; }
        .table-container { max-height: 600px; overflow-y: auto; }
        .sticky-header { position: sticky; top: 0; background: white; z-index: 10; }
    </style>
</head>
<body>
    <div class="container-fluid py-4">
        <!-- Header -->
        <div class="row mb-4">
            <div class="col">
                <h1 class="display-4">{{ report_title }}</h1>
                <p class="lead text-muted">Generated {{ generated_at | datetime('%Y-%m-%d %H:%M:%S UTC') }}</p>
                <p class="text-muted">Project: {{ project_root }}</p>
            </div>
        </div>

        <!-- Summary Statistics -->
        <div class="row mb-4">
            <div class="col-md-3">
                <div class="card bg-primary text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h5 class="card-title">Total Files</h5>
                                <h2>{{ summary.total_files }}</h2>
                            </div>
                            <i class="fas fa-file fa-2x opacity-50"></i>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-info text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h5 class="card-title">Participants</h5>
                                <h2>{{ summary.participants | length }}</h2>
                            </div>
                            <i class="fas fa-users fa-2x opacity-50"></i>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-success text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h5 class="card-title">Recent Activity</h5>
                                <h2>{{ summary.recent_activity }}</h2>
                            </div>
                            <i class="fas fa-clock fa-2x opacity-50"></i>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card bg-warning text-white">
                    <div class="card-body">
                        <div class="d-flex justify-content-between">
                            <div>
                                <h5 class="card-title">Pipeline Stages</h5>
                                <h2>{{ stages | length }}</h2>
                            </div>
                            <i class="fas fa-cogs fa-2x opacity-50"></i>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Stage Distribution -->
        <div class="row mb-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="card-title mb-0">Stage Distribution</h5>
                    </div>
                    <div class="card-body">
                        {% for stage in stages %}
                            {% set count = summary.stage_distribution.get(stage, 0) %}
                            <div class="pipeline-stage stage-{{ stage }} mb-2">
                                <div class="d-flex justify-content-between align-items-center">
                                    <span class="fw-bold">{{ stage.replace('_', ' ').title() }}</span>
                                    <span class="badge {{ stage | stage_class }}">{{ count }}</span>
                                </div>
                                {% if summary.total_files > 0 %}
                                    {% set percentage = (count / summary.total_files * 100) | round(1) %}
                                    <div class="progress progress-bar-custom mt-1">
                                        <div class="progress-bar" style="width: {{ percentage }}%"></div>
                                    </div>
                                    <small class="text-muted">{{ percentage }}%</small>
                                {% endif %}
                            </div>
                        {% endfor %}
                    </div>
                </div>
            </div>
            
            <!-- Participant Overview -->
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">
                        <h5 class="card-title mb-0">Participant Overview</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-container">
                            <table class="table table-sm">
                                <thead class="sticky-header">
                                    <tr>
                                        <th>Participant</th>
                                        <th>Files</th>
                                        <th>Progress</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for participant in summary.participants %}
                                    <tr>
                                        <td><strong>{{ participant.participant }}</strong></td>
                                        <td>{{ participant.total_files }}</td>
                                        <td>
                                            {% set completed = participant.stage_distribution.get('completed', 0) %}
                                            {% set progress = (completed / participant.total_files * 100) if participant.total_files > 0 else 0 %}
                                            <div class="progress progress-bar-custom">
                                                <div class="progress-bar bg-success" style="width: {{ progress | round(1) }}%"></div>
                                            </div>
                                            <small class="text-muted">{{ progress | round(1) }}%</small>
                                        </td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- File Details -->
        <div class="row">
            <div class="col">
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="card-title mb-0">File Details</h5>
                        <div>
                            <button class="btn btn-sm btn-outline-secondary" onclick="toggleFilters()">
                                <i class="fas fa-filter"></i> Filters
                            </button>
                            <button class="btn btn-sm btn-outline-primary" onclick="refreshData()">
                                <i class="fas fa-refresh"></i> Refresh
                            </button>
                        </div>
                    </div>
                    
                    <!-- Filter Panel -->
                    <div id="filterPanel" class="card-header bg-light" style="display: none;">
                        <div class="row g-3">
                            <div class="col-md-3">
                                <select class="form-select form-select-sm" id="stageFilter">
                                    <option value="">All Stages</option>
                                    {% for stage in stages %}
                                    <option value="{{ stage }}">{{ stage.replace('_', ' ').title() }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-3">
                                <select class="form-select form-select-sm" id="participantFilter">
                                    <option value="">All Participants</option>
                                    {% for participant in summary.participants %}
                                    <option value="{{ participant.participant }}">{{ participant.participant }}</option>
                                    {% endfor %}
                                </select>
                            </div>
                            <div class="col-md-3">
                                <input type="text" class="form-control form-control-sm" id="taskFilter" placeholder="Filter by task...">
                            </div>
                            <div class="col-md-3">
                                <button class="btn btn-sm btn-outline-secondary" onclick="clearFilters()">Clear Filters</button>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card-body p-0">
                        <div class="table-container">
                            <table class="table table-hover mb-0">
                                <thead class="sticky-header">
                                    <tr>
                                        <th>File</th>
                                        <th>Participant</th>
                                        <th>Task</th>
                                        <th>Stage</th>
                                        <th>Progress</th>
                                        <th>Size</th>
                                        <th>Last Modified</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for file in files %}
                                    <tr class="file-row" 
                                        data-stage="{{ file.current_stage }}" 
                                        data-participant="{{ file.participant }}" 
                                        data-task="{{ file.task }}">
                                        <td>
                                            <strong>{{ file.original_path | basename }}</strong>
                                            {% if file.bids_path %}
                                                <br><small class="text-muted">BIDS: {{ file.bids_path | basename }}</small>
                                            {% endif %}
                                        </td>
                                        <td>{{ file.participant }}</td>
                                        <td>
                                            <span class="badge bg-light text-dark">{{ file.task }}</span>
                                            {% if file.acquisition %}
                                                <br><small class="text-muted">{{ file.acquisition }}</small>
                                            {% endif %}
                                        </td>
                                        <td>
                                            <span class="badge {{ file.current_stage | stage_class }}">
                                                {{ file.current_stage.replace('_', ' ').title() }}
                                            </span>
                                        </td>
                                        <td>
                                            {% set progress = file.stage_history | progress %}
                                            <div class="progress progress-bar-custom">
                                                <div class="progress-bar" style="width: {{ progress }}%"></div>
                                            </div>
                                            <small class="text-muted">{{ progress }}%</small>
                                        </td>
                                        <td>{{ file.file_size | filesize }}</td>
                                        <td>{{ file.last_modified | datetime('%m-%d %H:%M') }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function toggleFilters() {
            const panel = document.getElementById('filterPanel');
            panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
        }

        function clearFilters() {
            document.getElementById('stageFilter').value = '';
            document.getElementById('participantFilter').value = '';
            document.getElementById('taskFilter').value = '';
            filterFiles();
        }

        function filterFiles() {
            const stageFilter = document.getElementById('stageFilter').value;
            const participantFilter = document.getElementById('participantFilter').value;
            const taskFilter = document.getElementById('taskFilter').value.toLowerCase();
            
            const rows = document.querySelectorAll('.file-row');
            
            rows.forEach(row => {
                let show = true;
                
                if (stageFilter && row.dataset.stage !== stageFilter) {
                    show = false;
                }
                
                if (participantFilter && row.dataset.participant !== participantFilter) {
                    show = false;
                }
                
                if (taskFilter && !row.dataset.task.toLowerCase().includes(taskFilter)) {
                    show = false;
                }
                
                row.style.display = show ? '' : 'none';
            });
        }

        function refreshData() {
            location.reload();
        }

        // Add event listeners for filters
        document.getElementById('stageFilter').addEventListener('change', filterFiles);
        document.getElementById('participantFilter').addEventListener('change', filterFiles);
        document.getElementById('taskFilter').addEventListener('input', filterFiles);

        // Auto-refresh every 5 minutes
        setInterval(refreshData, 300000);
    </script>
</body>
</html>'''
    
    def _embedded_participant_template(self) -> str:
        """Embedded HTML template for participant report."""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report_title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="container py-4">
        <h1>{{ report_title }}</h1>
        <p class="text-muted">Generated {{ generated_at | datetime('%Y-%m-%d %H:%M:%S UTC') }}</p>
        
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5>Total Files</h5>
                        <h2>{{ participant.total_files }}</h2>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col">
                <div class="card">
                    <div class="card-header">
                        <h5>Files</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>File</th>
                                        <th>Task</th>
                                        <th>Stage</th>
                                        <th>Size</th>
                                        <th>Modified</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for file in participant.files %}
                                    <tr>
                                        <td>{{ file.original_path | basename }}</td>
                                        <td>{{ file.task }}</td>
                                        <td>
                                            <span class="badge {{ file.current_stage | stage_class }}">
                                                {{ file.current_stage.replace('_', ' ').title() }}
                                            </span>
                                        </td>
                                        <td>{{ file.file_size | filesize }}</td>
                                        <td>{{ file.last_modified | datetime('%Y-%m-%d %H:%M') }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''
    
    def _embedded_stage_template(self) -> str:
        """Embedded HTML template for stage report."""
        return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report_title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body>
    <div class="container py-4">
        <h1>{{ report_title }}</h1>
        <p class="text-muted">Generated {{ generated_at | datetime('%Y-%m-%d %H:%M:%S UTC') }}</p>
        
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card">
                    <div class="card-body">
                        <h5>Files in {{ stage.replace('_', ' ').title() }}</h5>
                        <h2>{{ total_files }}</h2>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col">
                <div class="card">
                    <div class="card-header">
                        <h5>File Details</h5>
                    </div>
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table">
                                <thead>
                                    <tr>
                                        <th>File</th>
                                        <th>Participant</th>
                                        <th>Task</th>
                                        <th>Size</th>
                                        <th>Modified</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {% for file in files %}
                                    <tr>
                                        <td>{{ file.original_path | basename }}</td>
                                        <td>{{ file.participant }}</td>
                                        <td>{{ file.task }}</td>
                                        <td>{{ file.file_size | filesize }}</td>
                                        <td>{{ file.last_modified | datetime('%Y-%m-%d %H:%M') }}</td>
                                    </tr>
                                    {% endfor %}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>'''

def generate_unified_pipeline_report(project_root: str, config: Optional[Dict] = None) -> str:
    """
    Generate a comprehensive pipeline report for a project.
    
    Args:
        project_root (str): Project root directory
        config (dict, optional): Configuration dictionary
        
    Returns:
        str: Path to generated report
    """
    from pipeline_tracker import get_project_tracker
    
    # Get tracker and import legacy data
    tracker = get_project_tracker(project_root, config)
    tracker.import_legacy_data()
    
    # Generate report
    generator = PipelineReportGenerator(tracker)
    report_path = generator.generate_dashboard_report()
    
    return report_path