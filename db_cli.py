#!/usr/bin/env python3
"""
File Processing Database CLI

Command-line interface for managing the file processing database.
Provides easy access to database operations without writing code.

Usage:
    python db_cli.py init [--path DB_PATH]
    python db_cli.py add-files DIRECTORY [--pattern PATTERN] [--recursive]
    python db_cli.py log-operation TYPE INPUT_FILES [OUTPUT_FILES] [--name NAME]
    python db_cli.py search [--extension EXT] [--operation TYPE] [--exists]
    python db_cli.py report [--format html|csv] [--output OUTPUT]
    python db_cli.py status
    python db_cli.py export [--output-dir DIR]

Author: GitHub Copilot
"""

import argparse
import sys
import os
from pathlib import Path
from glob import glob
import json

# Add current directory to path to import local modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import create_database, FileProcessingDatabase
from database_integration import batch_add_existing_files, generate_processing_report
from utils import extract_info_from_filename


def init_database(args):
    """Initialize a new database."""
    db_path = args.path or "file_processing_database.json"
    db = create_database(db_path)
    print(f"Database initialized at: {db.db_path}")
    print(f"Metadata: {json.dumps(db.data['metadata'], indent=2)}")


def add_files_to_db(args):
    """Add files to the database."""
    if not os.path.exists(args.directory):
        print(f"Error: Directory {args.directory} does not exist")
        return 1
    
    pattern = args.pattern or "*.fif"
    
    try:
        db = batch_add_existing_files(
            directory=args.directory,
            pattern=pattern,
            db_path=args.db_path,
            extract_metadata=True
        )
        print(f"Successfully added files to database: {db.db_path}")
        
    except Exception as e:
        print(f"Error adding files: {e}")
        return 1


def log_operation(args):
    """Log a processing operation."""
    db = create_database(args.db_path)
    
    input_files = args.input_files if isinstance(args.input_files, list) else [args.input_files]
    output_files = args.output_files if args.output_files else []
    
    if isinstance(output_files, str):
        output_files = [output_files]
    
    try:
        operation_id = db.log_operation(
            operation_type=args.type,
            input_files=input_files,
            output_files=output_files,
            process_name=args.name or args.type,
            parameters={"cli_command": " ".join(sys.argv)}
        )
        
        print(f"Logged operation: {operation_id}")
        print(f"Type: {args.type}")
        print(f"Input files: {len(input_files)}")
        print(f"Output files: {len(output_files)}")
        
    except Exception as e:
        print(f"Error logging operation: {e}")
        return 1


def search_files(args):
    """Search for files in the database."""
    db = create_database(args.db_path)
    
    search_criteria = {}
    if args.extension:
        search_criteria["extension"] = args.extension
    if args.operation:
        search_criteria["operation_type"] = args.operation
    if args.exists is not None:
        search_criteria["exists"] = args.exists
    if args.filename:
        search_criteria["filename_contains"] = args.filename
    
    results = db.search_files(**search_criteria)
    
    if not results:
        print("No files found matching criteria")
        return
    
    print(f"Found {len(results)} files:")
    print("-" * 80)
    
    for i, file_record in enumerate(results[:20]):  # Limit to first 20 results
        print(f"{i+1:3d}. {file_record['filename']}")
        print(f"     Path: {file_record['path']}")
        print(f"     Size: {file_record['size_bytes']} bytes")
        print(f"     Exists: {file_record['exists']}")
        print(f"     Operations: {len(file_record['processing_history'])}")
        if file_record['processing_history']:
            last_op = file_record['processing_history'][-1]
            print(f"     Last processed: {last_op['timestamp'][:19]} ({last_op['operation_type']})")
        print()
    
    if len(results) > 20:
        print(f"... and {len(results) - 20} more files")


def generate_report(args):
    """Generate a processing report."""
    db = create_database(args.db_path)
    
    if args.format == "html":
        output_file = args.output or "processing_report.html"
        generate_processing_report(args.db_path, output_file)
        
    elif args.format == "csv":
        output_dir = args.output or "./database_export"
        db.export_to_csv(output_dir)
        print(f"Exported database to CSV files in {output_dir}")
        
    else:
        # JSON format
        output_file = args.output or "processing_report.json"
        with open(output_file, 'w') as f:
            json.dump(db.data, f, indent=2, default=str)
        print(f"Exported database to {output_file}")


def show_status(args):
    """Show database status."""
    db = create_database(args.db_path)
    metadata = db.data["metadata"]
    
    print("Database Status")
    print("=" * 50)
    print(f"Database file: {db.db_path}")
    print(f"File exists: {db.db_path.exists()}")
    print(f"Created: {metadata['created']}")
    print(f"Last updated: {metadata['last_updated']}")
    print(f"Version: {metadata['version']}")
    print(f"Total files: {metadata['total_files']}")
    print(f"Total operations: {metadata['total_operations']}")
    
    if metadata['total_operations'] > 0:
        operations_df = db.get_operations_summary()
        
        print("\nOperation Summary:")
        print("-" * 30)
        op_counts = operations_df['operation_type'].value_counts()
        for op_type, count in op_counts.items():
            print(f"  {op_type}: {count}")
        
        print(f"\nStatus Summary:")
        status_counts = operations_df['status'].value_counts()
        for status, count in status_counts.items():
            print(f"  {status}: {count}")
        
        print(f"\nRecent Operations:")
        recent_ops = operations_df.tail(5)
        for _, op in recent_ops.iterrows():
            print(f"  {op['timestamp'][:19]} - {op['operation_type']} - {op['status']}")


def export_database(args):
    """Export database to various formats."""
    db = create_database(args.db_path)
    output_dir = Path(args.output_dir or "./database_export")
    
    db.export_to_csv(str(output_dir))
    
    # Also export as JSON
    with open(output_dir / "database.json", 'w') as f:
        json.dump(db.data, f, indent=2, default=str)
    
    print(f"Database exported to {output_dir}")
    print(f"Files created:")
    print(f"  - files.csv")
    print(f"  - operations.csv")  
    print(f"  - database.json")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="File Processing Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python db_cli.py init --path ./my_database.json
  python db_cli.py add-files /data/meg --pattern "*.fif" 
  python db_cli.py search --extension .fif --exists true
  python db_cli.py log-operation maxfilter input.fif output.fif --name "MaxFilter Processing"
  python db_cli.py report --format html --output report.html
  python db_cli.py status
        """
    )
    
    parser.add_argument(
        "--db-path",
        help="Path to database file (default: file_processing_database.json)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize new database")
    init_parser.add_argument("--path", help="Database file path")
    
    # Add files command
    add_parser = subparsers.add_parser("add-files", help="Add files to database")
    add_parser.add_argument("directory", help="Directory to scan")
    add_parser.add_argument("--pattern", default="*.fif", help="File pattern (default: *.fif)")
    add_parser.add_argument("--recursive", action="store_true", help="Scan recursively")
    
    # Log operation command
    log_parser = subparsers.add_parser("log-operation", help="Log a processing operation")
    log_parser.add_argument("type", help="Operation type (e.g., maxfilter, bidsify)")
    log_parser.add_argument("input_files", nargs="+", help="Input file paths")
    log_parser.add_argument("output_files", nargs="*", help="Output file paths")
    log_parser.add_argument("--name", help="Process name")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search for files")
    search_parser.add_argument("--extension", help="File extension filter")
    search_parser.add_argument("--operation", help="Operation type filter")
    search_parser.add_argument("--exists", type=bool, help="File existence filter")
    search_parser.add_argument("--filename", help="Filename contains filter")
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate processing report")
    report_parser.add_argument("--format", choices=["html", "csv", "json"], 
                              default="html", help="Report format")
    report_parser.add_argument("--output", help="Output file path")
    
    # Status command
    status_parser = subparsers.add_parser("status", help="Show database status")
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export database")
    export_parser.add_argument("--output-dir", default="./database_export", 
                              help="Output directory")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    command_functions = {
        "init": init_database,
        "add-files": add_files_to_db,
        "log-operation": log_operation,
        "search": search_files,
        "report": generate_report,
        "status": show_status,
        "export": export_database
    }
    
    try:
        return command_functions[args.command](args) or 0
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
