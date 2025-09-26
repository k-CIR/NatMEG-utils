#!/usr/bin/env python3
"""
Unified Pipeline Reporting System

Main script to generate comprehensive pipeline reports that track files
through the entire MEG processing workflow from raw data to final analysis.

Usage:
    python pipeline_report.py --config config.yml
    python pipeline_report.py --project-root /path/to/project
    python pipeline_report.py --generate-report
    
Features:
- Import legacy logging data from existing systems
- Generate unified HTML reports with interactive filtering
- Real-time pipeline status monitoring
- Participant-specific and stage-specific reports
- Integration with existing workflow scripts

Author: Andreas Gerhardsson
"""

import argparse
import os
import sys
import yaml
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List

from utils import askForConfig, get_logger, log, configure_logging

# Import pipeline components with fallback
try:
    from pipeline_tracker import (
        PipelineTracker, get_project_tracker, PipelineStage, FileStatus
    )
    from pipeline_report_generator import (
        PipelineReportGenerator, generate_unified_pipeline_report
    )
    PIPELINE_COMPONENTS_AVAILABLE = True
except ImportError as e:
    print(f"Pipeline components not available: {e}")
    PIPELINE_COMPONENTS_AVAILABLE = False

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Unified Pipeline Reporting System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Generate report from config file
  python pipeline_report.py --config project_config.yml
  
  # Generate report for specific project
  python pipeline_report.py --project-root /data/projects/MyStudy
  
  # Generate report and open in browser
  python pipeline_report.py --config config.yml --open
  
  # Import legacy data and generate report
  python pipeline_report.py --project-root /data --import-legacy --generate-report
        '''
    )
    
    # Input options
    parser.add_argument(
        '-c', '--config', 
        type=str, 
        help='Path to project configuration file (YAML/JSON)'
    )
    parser.add_argument(
        '--project-root',
        type=str,
        help='Root directory of the project'
    )
    
    # Action options
    parser.add_argument(
        '--generate-report',
        action='store_true',
        help='Generate unified pipeline report'
    )
    parser.add_argument(
        '--import-legacy',
        action='store_true',
        help='Import data from legacy logging systems'
    )
    parser.add_argument(
        '--participant',
        type=str,
        help='Generate report for specific participant'
    )
    parser.add_argument(
        '--stage',
        type=str,
        choices=[stage.value for stage in PipelineStage] if PIPELINE_COMPONENTS_AVAILABLE else [],
        help='Generate report for specific pipeline stage'
    )
    
    # Output options
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path for generated report'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['html', 'json'],
        default='html',
        help='Output format (default: html)'
    )
    parser.add_argument(
        '--open',
        action='store_true',
        help='Open generated report in web browser'
    )
    
    # Configuration options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    return parser.parse_args()

def load_config(config_path: str) -> Dict:
    """
    Load configuration from file.
    
    Args:
        config_path (str): Path to configuration file
        
    Returns:
        dict: Configuration dictionary
    """
    config_path = Path(config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r') as f:
        if config_path.suffix.lower() in ['.yml', '.yaml']:
            config = yaml.safe_load(f)
        elif config_path.suffix.lower() == '.json':
            config = json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {config_path.suffix}")
    
    return config

def get_project_info(args) -> tuple[str, Dict]:
    """
    Get project root and configuration from arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        tuple: (project_root, config)
    """
    project_root = None
    config = {}
    
    if args.config:
        config = load_config(args.config)
        # Extract project root from config
        if 'Project' in config:
            project_config = config['Project']
            root = project_config.get('Root', '')
            name = project_config.get('Name', '')
            if root and name:
                project_root = os.path.join(root, name)
            elif root:
                project_root = root
    
    if args.project_root:
        project_root = args.project_root
    
    if not project_root:
        if args.config is None:
            # Ask user to select config file
            config_file = askForConfig()
            config = load_config(config_file)
            project_config = config.get('Project', {})
            root = project_config.get('Root', '')
            name = project_config.get('Name', '')
            if root and name:
                project_root = os.path.join(root, name)
        else:
            raise ValueError("Could not determine project root. Specify --project-root or provide config with Project.Root")
    
    return project_root, config

def import_legacy_data(tracker: PipelineTracker, logger):
    """
    Import data from legacy logging systems.
    
    Args:
        tracker: Pipeline tracker instance
        logger: Logger instance
    """
    logger.info("Importing legacy pipeline data...")
    
    try:
        tracker.import_legacy_data()
        logger.info("Legacy data import completed successfully")
    except Exception as e:
        logger.error(f"Failed to import legacy data: {e}")
        raise

def generate_reports(project_root: str, config: Dict, args, logger) -> List[str]:
    """
    Generate requested reports.
    
    Args:
        project_root: Project root directory
        config: Configuration dictionary
        args: Command line arguments
        logger: Logger instance
        
    Returns:
        list: Paths to generated reports
    """
    if not PIPELINE_COMPONENTS_AVAILABLE:
        raise ImportError("Pipeline components not available for report generation")
    
    tracker = get_project_tracker(project_root, config)
    generator = PipelineReportGenerator(tracker)
    
    generated_reports = []
    
    if args.participant:
        # Generate participant-specific report
        logger.info(f"Generating report for participant {args.participant}")
        report_path = generator.generate_participant_report(
            args.participant, 
            args.output
        )
        generated_reports.append(report_path)
        
    elif args.stage:
        # Generate stage-specific report
        stage = PipelineStage(args.stage)
        logger.info(f"Generating report for stage {stage.value}")
        report_path = generator.generate_stage_report(
            stage,
            args.output
        )
        generated_reports.append(report_path)
        
    else:
        # Generate main dashboard report
        logger.info("Generating main pipeline dashboard")
        if args.format == 'html':
            report_path = generator.generate_dashboard_report(args.output)
            generated_reports.append(report_path)
        elif args.format == 'json':
            report_path = generator.generate_summary_json(args.output)
            generated_reports.append(report_path)
    
    return generated_reports

def open_report_in_browser(report_path: str):
    """
    Open HTML report in web browser.
    
    Args:
        report_path: Path to HTML report file
    """
    import webbrowser
    
    if report_path.endswith('.html'):
        file_url = f'file://{os.path.abspath(report_path)}'
        webbrowser.open(file_url)
        print(f"Opened report in browser: {file_url}")
    else:
        print(f"Cannot open non-HTML report in browser: {report_path}")

def main():
    """Main entry point."""
    if not PIPELINE_COMPONENTS_AVAILABLE:
        print("ERROR: Pipeline tracking components not available.")
        print("Please ensure pipeline_tracker.py and pipeline_report_generator.py are available.")
        sys.exit(1)
    
    args = parse_arguments()
    
    # Setup logging
    log_level = 'DEBUG' if args.verbose else 'INFO'
    logger = get_logger('PipelineReport')
    
    try:
        # Get project information
        project_root, config = get_project_info(args)
        logger.info(f"Using project root: {project_root}")
        
        # Ensure project directory exists
        if not os.path.exists(project_root):
            raise FileNotFoundError(f"Project directory does not exist: {project_root}")
        
        # Initialize tracker
        tracker = get_project_tracker(project_root, config)
        
        # Import legacy data if requested
        if args.import_legacy:
            import_legacy_data(tracker, logger)
        
        # Generate reports if requested
        if args.generate_report or args.participant or args.stage or not any([
            args.import_legacy, args.participant, args.stage
        ]):
            # Default action is to generate main report
            generated_reports = generate_reports(project_root, config, args, logger)
            
            for report_path in generated_reports:
                logger.info(f"Generated report: {report_path}")
                
                # Open in browser if requested
                if args.open:
                    open_report_in_browser(report_path)
        
        logger.info("Pipeline reporting completed successfully")
        
    except Exception as e:
        logger.error(f"Pipeline reporting failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()