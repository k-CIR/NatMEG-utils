#!/usr/bin/env python3
"""
Demo: Unified Pipeline Reporting System

Example script showing how to use the unified pipeline tracking and reporting
system for MEG data processing workflows.

This script demonstrates:
1. Setting up pipeline tracking
2. Importing legacy data
3. Generating comprehensive reports
4. Updating reports as pipeline progresses

Author: Andreas Gerhardsson
"""

import os
import sys
from pathlib import Path

# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def demo_basic_usage():
    """Demonstrate basic usage of the pipeline tracking system."""
    
    print("=== Demo: Basic Pipeline Tracking Usage ===\\n")
    
    try:
        from pipeline_tracker import get_project_tracker, PipelineStage, FileStatus
        from pipeline_report_generator import PipelineReportGenerator
        
        # Example project setup
        project_root = "neuro/data/local/OPM-benchmarking"  # Update this path
        config = {
            'Name': 'DemoProject',
            'Root': 'neuro/data/local',
            'Raw': os.path.join(project_root, 'raw'),
            'BIDS': os.path.join(project_root, 'BIDS'),
            'Logfile': 'pipeline.log'
        }
        
        print(f"1. Initializing tracker for project: {project_root}")
        
        # Initialize tracker
        tracker = get_project_tracker(project_root, config)
        print("   ✓ Pipeline tracker initialized")
        
        print("\\n2. Importing legacy data from existing logs")
        
        # Import existing data
        tracker.import_legacy_data()
        print("   ✓ Legacy data imported")
        
        print("\\n3. Generating pipeline summary")
        
        # Get summary statistics
        summary = tracker.generate_summary_report()
        print(f"   • Total files: {summary['total_files']}")
        print(f"   • Participants: {len(summary['participants'])}")
        print("   • Stage distribution:")
        for stage, count in summary['stage_distribution'].items():
            print(f"     - {stage}: {count} files")
        
        print("\\n4. Generating HTML report")
        
        # Generate comprehensive report
        generator = PipelineReportGenerator(tracker)
        report_path = generator.generate_dashboard_report()
        print(f"   ✓ Report generated: {report_path}")
        
        print("\\n5. Example file registration")
        
        # Example of registering a new file
        example_file = "/example/path/NatMEG_001_Phalanges_raw.fif"
        if os.path.exists(example_file):  # Only if file exists
            file_id = tracker.register_file(
                example_file,
                PipelineStage.RAW_ACQUISITION,
                FileStatus.COMPLETED
            )
            print(f"   ✓ Registered file with ID: {file_id}")
        else:
            print("   • Example file not found, skipping registration demo")
        
        print("\\n=== Demo completed successfully ===")
        
    except ImportError as e:
        print(f"Error: Required modules not available: {e}")
        print("Please ensure pipeline_tracker.py and pipeline_report_generator.py are in the same directory.")
    except Exception as e:
        print(f"Error during demo: {e}")

def demo_integration_with_existing_scripts():
    """Demonstrate integration with existing pipeline scripts."""
    
    print("\\n=== Demo: Integration with Existing Scripts ===\\n")
    
    print("The unified tracking system integrates with your existing scripts:")
    print("")
    print("1. copy_to_cerberos.py")
    print("   - Automatically tracks file copy operations")
    print("   - Records source/destination mappings")
    print("   - Updates pipeline stage to 'raw_copy'")
    print("")
    print("2. bidsify.py")
    print("   - Tracks BIDS conversion progress")
    print("   - Records BIDS paths and metadata")
    print("   - Updates pipeline stage to 'bidsification'")
    print("")
    print("3. render_report.py")
    print("   - Integrates local vs server file comparisons")
    print("   - Updates pipeline stage to 'reporting'")
    print("")
    print("Usage examples:")
    print("")
    print("# Run copy with tracking (if tracking available)")
    print("python copy_to_cerberos.py --config project_config.yml")
    print("")
    print("# Run BIDS conversion with tracking")
    print("python bidsify.py --config project_config.yml")
    print("")
    print("# Generate unified pipeline report")
    print("python pipeline_report.py --config project_config.yml")
    print("")
    print("# Generate participant-specific report")
    print("python pipeline_report.py --config project_config.yml --participant 001")

def demo_report_features():
    """Demonstrate report generation features."""
    
    print("\\n=== Demo: Report Features ===\\n")
    
    print("The unified reporting system provides:")
    print("")
    print("📊 Interactive Dashboard")
    print("   - Overall pipeline statistics")
    print("   - Stage distribution visualization") 
    print("   - Participant progress overview")
    print("   - File-level detail tables")
    print("")
    print("🔍 Interactive Filtering")
    print("   - Filter by pipeline stage")
    print("   - Filter by participant")
    print("   - Search by task name")
    print("   - Real-time table updates")
    print("")
    print("📈 Progress Tracking")
    print("   - File lifecycle visualization")
    print("   - Stage completion percentages")
    print("   - Timestamp tracking")
    print("   - Error and warning indicators")
    print("")
    print("🔄 Real-time Updates")
    print("   - Auto-refresh every 5 minutes")
    print("   - Manual refresh button")
    print("   - Status change notifications")
    print("")
    print("📋 Multiple Report Types")
    print("   - Dashboard (overview of all files)")
    print("   - Participant reports (individual subject)")
    print("   - Stage reports (files in specific stage)")
    print("   - JSON exports (for API integration)")

def main():
    """Main demo function."""
    
    print("MEG Pipeline Unified Tracking & Reporting System")
    print("=" * 50)
    
    # Check if we're in the right directory
    current_dir = Path(__file__).parent
    required_files = ['pipeline_tracker.py', 'pipeline_report_generator.py', 'utils.py']
    
    missing_files = []
    for file in required_files:
        if not (current_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("\\nWarning: Some required files are missing:")
        for file in missing_files:
            print(f"  - {file}")
        print("\\nPlease ensure all files are in the same directory.")
        print("Running demo with available components only...\\n")
    
    # Run demos
    demo_basic_usage()
    demo_integration_with_existing_scripts() 
    demo_report_features()
    
    print("\\n" + "=" * 50)
    print("For more information, see the documentation in each Python file.")
    print("To get started with your project:")
    print("  1. Update project_root path in demo_basic_usage()")
    print("  2. Run: python pipeline_demo.py")
    print("  3. Check generated HTML reports in pipeline_tracking/reports/")

if __name__ == "__main__":
    main()