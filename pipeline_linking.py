"""
Pipeline Linking Utilities

Functions to link different stages of the MEG/EEG processing pipeline,
enabling complete traceability from raw copy operations through BIDS conversion.
"""

import json
import pandas as pd
from os.path import join, exists, basename, dirname
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from utils import log


def link_copy_to_bids_results(config: Dict) -> Dict:
    """
    Create a comprehensive report linking copy operations to BIDS conversions.
    
    This function creates a complete pipeline tracking report by linking:
    1. copy_results.json (copy operations)
    2. bids_results.json (BIDS conversions)
    
    The linking is based on matching file paths where:
    - copy_results["New file(s)"] → bids_results["Source File"]
    
    Args:
        config (Dict): Configuration dictionary containing project paths
        
    Returns:
        Dict: Complete pipeline report with linked operations
        
    Side Effects:
        - Creates pipeline_report.json with complete tracking information
        - Logs summary statistics
    """
    project_root = join(config.get('Root', ''), config.get('Name', ''))
    log_path = join(project_root, 'log')
    
    # Load copy results
    copy_results_file = f'{log_path}/copy_results.json'
    bids_results_file = f'{log_path}/bids_results.json'
    
    copy_results = []
    bids_results = []
    
    if exists(copy_results_file):
        with open(copy_results_file, 'r') as f:
            copy_results = json.load(f)
    
    if exists(bids_results_file):
        with open(bids_results_file, 'r') as f:
            bids_results = json.load(f)
    
    # Create mapping from source files to copy operations
    copy_mapping = {}
    for copy_entry in copy_results:
        new_files = copy_entry.get('New file(s)', [])
        if isinstance(new_files, str):
            new_files = [new_files]
        
        for new_file in new_files:
            copy_mapping[new_file] = copy_entry
    
    # Create linked pipeline report
    pipeline_entries = []
    orphaned_copies = []
    orphaned_bids = []
    
    # Process BIDS results and link to copy operations
    for bids_entry in bids_results:
        source_file = bids_entry.get('Source File', '')
        
        # Find matching copy operation
        matching_copy = copy_mapping.get(source_file)
        
        if matching_copy:
            # Create linked entry
            linked_entry = {
                'pipeline_id': f"{matching_copy.get('timestamp', '')}_to_{bids_entry.get('timestamp', '')}",
                'copy_stage': {
                    'original_file': matching_copy.get('Original File', ''),
                    'copied_files': matching_copy.get('New file(s)', []),
                    'copy_date': matching_copy.get('Copy Date', ''),
                    'copy_time': matching_copy.get('Copy Time', ''),
                    'copy_status': matching_copy.get('Transfer status', ''),
                    'copy_message': matching_copy.get('message', ''),
                    'copy_timestamp': matching_copy.get('timestamp', '')
                },
                'bids_stage': {
                    'source_file': bids_entry.get('Source File', ''),
                    'bids_file': bids_entry.get('BIDS File', ''),
                    'participant': bids_entry.get('Participant', ''),
                    'session': bids_entry.get('Session', ''),
                    'task': bids_entry.get('Task', ''),
                    'acquisition': bids_entry.get('Acquisition', ''),
                    'datatype': bids_entry.get('Datatype', ''),
                    'processing': bids_entry.get('Processing', ''),
                    'bids_status': bids_entry.get('Conversion Status', ''),
                    'bids_timestamp': bids_entry.get('timestamp', '')
                },
                'pipeline_status': 'complete' if (
                    matching_copy.get('Transfer status') == 'Success' and 
                    bids_entry.get('Conversion Status') == 'Success'
                ) else 'incomplete',
                'created_timestamp': datetime.now().isoformat()
            }
            pipeline_entries.append(linked_entry)
            
            # Remove from copy mapping to track orphans
            del copy_mapping[source_file]
        else:
            # BIDS entry without matching copy operation
            orphaned_bids.append(bids_entry)
    
    # Remaining copy operations without BIDS conversion
    for source_file, copy_entry in copy_mapping.items():
        orphaned_copies.append({
            'source_file': source_file,
            'copy_entry': copy_entry,
            'reason': 'no_bids_conversion'
        })
    
    # Create comprehensive report
    pipeline_report = {
        'report_metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_linked_entries': len(pipeline_entries),
            'orphaned_copies': len(orphaned_copies),
            'orphaned_bids': len(orphaned_bids),
            'copy_results_file': copy_results_file,
            'bids_results_file': bids_results_file
        },
        'linked_pipeline': pipeline_entries,
        'orphaned_operations': {
            'copies_without_bids': orphaned_copies,
            'bids_without_copies': orphaned_bids
        }
    }
    
    # Save pipeline report
    pipeline_report_file = f'{log_path}/pipeline_report.json'
    with open(pipeline_report_file, 'w') as f:
        json.dump(pipeline_report, f, indent=4)
    
    # Log summary
    logfile = config.get('Logfile', 'pipeline_log.log')
    log('Pipeline', 
        f'Pipeline linking complete: {len(pipeline_entries)} linked, '
        f'{len(orphaned_copies)} orphaned copies, {len(orphaned_bids)} orphaned BIDS',
        logfile=logfile, logpath=log_path)
    
    return pipeline_report


def generate_pipeline_summary(config: Dict) -> pd.DataFrame:
    """
    Generate a summary DataFrame of the complete pipeline status.
    
    Creates a tabular summary showing the status of each file through
    the complete pipeline (copy → BIDS conversion).
    
    Args:
        config (Dict): Configuration dictionary
        
    Returns:
        pd.DataFrame: Summary table with pipeline status for each file
    """
    # Generate linked report first
    pipeline_report = link_copy_to_bids_results(config)
    
    # Convert to DataFrame for easier analysis
    summary_data = []
    
    for entry in pipeline_report['linked_pipeline']:
        copy_stage = entry['copy_stage']
        bids_stage = entry['bids_stage']
        
        # Handle multiple copied files
        copied_files = copy_stage['copied_files']
        if isinstance(copied_files, str):
            copied_files = [copied_files]
        
        for copied_file in copied_files:
            summary_data.append({
                'pipeline_id': entry['pipeline_id'],
                'original_file': copy_stage['original_file'],
                'copied_file': copied_file,
                'bids_file': bids_stage['bids_file'],
                'participant': bids_stage['participant'],
                'session': bids_stage['session'],
                'task': bids_stage['task'],
                'acquisition': bids_stage['acquisition'],
                'datatype': bids_stage['datatype'],
                'copy_status': copy_stage['copy_status'],
                'bids_status': bids_stage['bids_status'],
                'pipeline_status': entry['pipeline_status'],
                'copy_timestamp': copy_stage['copy_timestamp'],
                'bids_timestamp': bids_stage['bids_timestamp']
            })
    
    # Add orphaned entries
    for orphan in pipeline_report['orphaned_operations']['copies_without_bids']:
        copy_entry = orphan['copy_entry']
        copied_files = copy_entry.get('New file(s)', [])
        if isinstance(copied_files, str):
            copied_files = [copied_files]
        
        for copied_file in copied_files:
            summary_data.append({
                'pipeline_id': f"orphan_copy_{copy_entry.get('timestamp', '')}",
                'original_file': copy_entry.get('Original File', ''),
                'copied_file': copied_file,
                'bids_file': None,
                'participant': None,
                'session': None,
                'task': None,
                'acquisition': None,
                'datatype': None,
                'copy_status': copy_entry.get('Transfer status', ''),
                'bids_status': 'Not processed',
                'pipeline_status': 'copy_only',
                'copy_timestamp': copy_entry.get('timestamp', ''),
                'bids_timestamp': None
            })
    
    df = pd.DataFrame(summary_data)
    
    # Save summary table
    project_root = join(config.get('Root', ''), config.get('Name', ''))
    log_path = join(project_root, 'log')
    summary_file = f'{log_path}/pipeline_summary.tsv'
    df.to_csv(summary_file, sep='\t', index=False)
    
    return df


def validate_pipeline_integrity(config: Dict) -> Dict:
    """
    Validate the integrity of the complete pipeline by checking for:
    - Missing files in the pipeline
    - Broken links between stages
    - Inconsistent timestamps or metadata
    
    Args:
        config (Dict): Configuration dictionary
        
    Returns:
        Dict: Validation report with issues found
    """
    pipeline_report = link_copy_to_bids_results(config)
    
    issues = {
        'missing_files': [],
        'timestamp_issues': [],
        'metadata_inconsistencies': [],
        'broken_links': []
    }
    
    for entry in pipeline_report['linked_pipeline']:
        copy_stage = entry['copy_stage']
        bids_stage = entry['bids_stage']
        
        # Check if files actually exist
        copied_files = copy_stage['copied_files']
        if isinstance(copied_files, str):
            copied_files = [copied_files]
            
        for copied_file in copied_files:
            if not exists(copied_file):
                issues['missing_files'].append({
                    'file': copied_file,
                    'stage': 'copy',
                    'pipeline_id': entry['pipeline_id']
                })
        
        if bids_stage['bids_file'] and not exists(bids_stage['bids_file']):
            issues['missing_files'].append({
                'file': bids_stage['bids_file'],
                'stage': 'bids',
                'pipeline_id': entry['pipeline_id']
            })
        
        # Check timestamp consistency (BIDS should be after copy)
        try:
            copy_time = datetime.fromisoformat(copy_stage['copy_timestamp'])
            bids_time = datetime.fromisoformat(bids_stage['bids_timestamp'])
            
            if bids_time < copy_time:
                issues['timestamp_issues'].append({
                    'issue': 'BIDS timestamp before copy timestamp',
                    'pipeline_id': entry['pipeline_id'],
                    'copy_time': copy_stage['copy_timestamp'],
                    'bids_time': bids_stage['bids_timestamp']
                })
        except (ValueError, TypeError):
            issues['timestamp_issues'].append({
                'issue': 'Invalid timestamp format',
                'pipeline_id': entry['pipeline_id']
            })
    
    # Log validation results
    project_root = join(config.get('Root', ''), config.get('Name', ''))
    log_path = join(project_root, 'log')
    logfile = config.get('Logfile', 'pipeline_log.log')
    
    total_issues = sum(len(issue_list) for issue_list in issues.values())
    log('Pipeline', f'Validation complete: {total_issues} issues found', 
        logfile=logfile, logpath=log_path)
    
    # Save validation report
    validation_file = f'{log_path}/pipeline_validation.json'
    with open(validation_file, 'w') as f:
        json.dump(issues, f, indent=4)
    
    return issues