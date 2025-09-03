#!/usr/bin/env python3
"""
File Processing Database Demo

Demonstrates the functionality of the file processing database system
with example data and operations.

Author: GitHub Copilot  
"""

import os
import sys
import tempfile
import json
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import FileProcessingDatabase, create_database
from database_integration import ProcessingTracker, track_processing_session


def create_demo_files():
    """Create some demo files for testing."""
    demo_dir = Path("demo_data")
    demo_dir.mkdir(exist_ok=True)
    
    # Create some fake MEG files
    demo_files = [
        "demo_data/NatMEG_001_Phalanges_raw.fif",
        "demo_data/NatMEG_001_AudOdd_raw.fif", 
        "demo_data/NatMEG_002_Phalanges_raw.fif",
        "demo_data/sub-001_task-phalanges_meg.fif",
        "demo_data/sub-001_task-audodd_meg.fif",
        "demo_data/sub-002_task-phalanges_meg.fif"
    ]
    
    for file_path in demo_files:
        Path(file_path).touch()
        # Add some fake content
        with open(file_path, 'w') as f:
            f.write(f"# Demo MEG file: {os.path.basename(file_path)}\n")
            f.write("# This is a demonstration file for the processing database\n")
            f.write("# In real usage, this would be a binary MEG file\n")
    
    return demo_files


def demo_basic_operations():
    """Demonstrate basic database operations."""
    print("🔍 File Processing Database Demo")
    print("=" * 50)
    
    # Create demo files
    print("\n1. Creating demo files...")
    demo_files = create_demo_files()
    print(f"   Created {len(demo_files)} demo files")
    
    # Initialize database
    print("\n2. Initializing database...")
    db = create_database("demo_database.json")
    print(f"   Database initialized at: {db.db_path}")
    
    # Add files to database
    print("\n3. Adding files to database...")
    for file_path in demo_files:
        file_id = db.add_file(file_path, {"demo": True, "file_type": "MEG"})
        print(f"   Added file: {os.path.basename(file_path)} (ID: {file_id[:8]}...)")
    
    # Log some operations
    print("\n4. Logging processing operations...")
    
    # Simulate a MaxFilter operation
    operation_id = db.log_operation(
        operation_type="maxfilter",
        input_files=["demo_data/NatMEG_001_Phalanges_raw.fif"],
        output_files=["demo_data/NatMEG_001_Phalanges_proc-tsss_meg.fif"],
        process_name="MaxFilter tSSS",
        parameters={"movecomp": True, "headpos": True, "tsss": True},
        duration_seconds=45.2
    )
    print(f"   MaxFilter operation logged: {operation_id}")
    
    # Simulate a BIDS conversion
    operation_id = db.log_operation(
        operation_type="bidsify", 
        input_files=["demo_data/NatMEG_001_Phalanges_proc-tsss_meg.fif"],
        output_files=["demo_data/sub-001_task-phalanges_meg.fif"],
        process_name="BIDS Conversion",
        parameters={"participant": "001", "task": "phalanges"},
        duration_seconds=12.1
    )
    print(f"   BIDS conversion logged: {operation_id}")
    
    # Show database status
    print("\n5. Database status:")
    print(f"   Total files: {db.data['metadata']['total_files']}")
    print(f"   Total operations: {db.data['metadata']['total_operations']}")
    
    # Search for files
    print("\n6. Searching for files...")
    fif_files = db.search_files(extension=".fif")
    print(f"   Found {len(fif_files)} .fif files")
    
    bids_files = db.search_files(filename_contains="sub-")
    print(f"   Found {len(bids_files)} BIDS format files")
    
    # Show operations summary
    print("\n7. Operations summary:")
    operations_df = db.get_operations_summary()
    if not operations_df.empty:
        for _, op in operations_df.iterrows():
            print(f"   {op['timestamp'][:19]} - {op['operation_type']} - {op['status']}")
    
    return db


def demo_context_manager():
    """Demonstrate context manager usage."""
    print("\n🔧 Context Manager Demo")
    print("=" * 50)
    
    with track_processing_session('demo_processing', 'demo_database.json') as tracker:
        print("\n1. Starting processing session...")
        
        # Log multiple operations
        tracker.log_operation(
            'file_copy',
            input_files=['demo_data/source.fif'],
            output_files=['demo_data/dest.fif']
        )
        
        tracker.log_operation(
            'quality_check',
            input_files=['demo_data/dest.fif'],
            parameters={'check_type': 'automatic', 'passed': True}
        )
        
        print("   Logged operations within session")


def demo_decorator():
    """Demonstrate decorator usage."""
    print("\n🎯 Decorator Demo")
    print("=" * 50)
    
    # Create processing tracker
    tracker = ProcessingTracker('demo_database.json')
    
    @tracker.track_operation('preprocessing', 'Signal Preprocessing')
    def preprocess_signal(input_file: str, output_file: str, filter_low: float = 1.0):
        """Mock preprocessing function."""
        print(f"   Processing {input_file} -> {output_file}")
        print(f"   Applying high-pass filter at {filter_low} Hz")
        
        # Create output file
        Path(output_file).touch()
        with open(output_file, 'w') as f:
            f.write(f"# Preprocessed file from {input_file}\n")
        
        return output_file
    
    # Use the decorated function
    print("\n1. Running decorated preprocessing function...")
    result = preprocess_signal(
        "demo_data/NatMEG_001_AudOdd_raw.fif",
        "demo_data/NatMEG_001_AudOdd_filt.fif", 
        filter_low=1.5
    )
    print(f"   Function returned: {result}")


def demo_export_and_reporting():
    """Demonstrate export and reporting features."""
    print("\n📊 Export and Reporting Demo")
    print("=" * 50)
    
    db = create_database("demo_database.json")
    
    print("\n1. Exporting to CSV...")
    db.export_to_csv("demo_export")
    print("   Exported files:")
    for file in Path("demo_export").glob("*.csv"):
        print(f"     - {file}")
    
    print("\n2. Generating JSON export...")
    with open("demo_database_export.json", 'w') as f:
        json.dump(db.data, f, indent=2, default=str)
    print("   JSON export saved to demo_database_export.json")
    
    print("\n3. Database statistics:")
    metadata = db.data['metadata']
    for key, value in metadata.items():
        print(f"   {key}: {value}")


def cleanup_demo():
    """Clean up demo files."""
    print("\n🧹 Cleaning up demo files...")
    
    # Remove demo files
    import shutil
    for path in ["demo_data", "demo_export", "demo_database.json", 
                 "demo_database_export.json", "processing_report.html"]:
        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    
    # Remove backup files
    for backup_file in Path(".").glob("demo_database.backup_*.json"):
        backup_file.unlink()
    
    print("   Demo cleanup completed")


def main():
    """Run the complete demonstration."""
    try:
        print("File Processing Database - Complete Demo")
        print("=" * 60)
        
        # Run demonstrations
        db = demo_basic_operations()
        demo_context_manager()
        demo_decorator()
        demo_export_and_reporting()
        
        print(f"\n✅ Demo completed successfully!")
        print(f"   Database contains {db.data['metadata']['total_files']} files")
        print(f"   Database contains {db.data['metadata']['total_operations']} operations")
        
        # Ask if user wants to keep demo files
        print(f"\nDemo files created:")
        print(f"   - demo_database.json (main database)")
        print(f"   - demo_data/ (demo MEG files)")
        print(f"   - demo_export/ (CSV exports)")
        print(f"   - demo_database_export.json (JSON export)")
        
        keep_files = input("\nKeep demo files? [y/N]: ").lower().strip()
        if keep_files != 'y':
            cleanup_demo()
        else:
            print("Demo files kept for your inspection")
        
    except KeyboardInterrupt:
        print(f"\n\nDemo interrupted by user")
        cleanup_demo()
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        cleanup_demo()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
