"""
Example Integration with Existing Pipeline

Shows how to integrate the file processing database with existing
NatMEG pipeline scripts like bidsify.py, maxfilter.py, etc.

Author: GitHub Copilot
"""

import os
import sys
from pathlib import Path

# Add current directory for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_integration import ProcessingTracker, track_processing_session


def enhanced_bidsify_example():
    """Example of how to enhance the bidsify function with database tracking."""
    
    # This would be added to bidsify.py
    def bidsify_with_tracking(config: dict):
        """Enhanced bidsify function with database tracking."""
        
        # Initialize tracker
        tracker = ProcessingTracker()
        
        with track_processing_session('bidsify') as session_tracker:
            
            # Original bidsify logic would go here...
            # For demo purposes, we'll simulate the operations
            
            print("Starting BIDS conversion with database tracking...")
            
            # Example conversions (this would be the real bidsify logic)
            conversions = [
                {
                    'input': '/data/NatMEG_001_Phalanges_raw.fif',
                    'output': '/bids/sub-001/meg/sub-001_task-phalanges_meg.fif',
                    'participant': '001',
                    'task': 'phalanges'
                },
                {
                    'input': '/data/NatMEG_001_AudOdd_raw.fif', 
                    'output': '/bids/sub-001/meg/sub-001_task-audodd_meg.fif',
                    'participant': '001',
                    'task': 'audodd'
                }
            ]
            
            for conversion in conversions:
                # Log each conversion operation
                session_tracker.log_operation(
                    process_name='BIDS File Conversion',
                    input_files=[conversion['input']],
                    output_files=[conversion['output']],
                    parameters={
                        'participant': conversion['participant'],
                        'task': conversion['task'],
                        'datatype': 'meg'
                    }
                )
                
                print(f"  Converted: {Path(conversion['input']).name} -> {Path(conversion['output']).name}")
            
            print(f"BIDS conversion completed. Logged {len(conversions)} operations.")
    
    return bidsify_with_tracking


def enhanced_maxfilter_example():
    """Example of how to enhance MaxFilter processing with database tracking."""
    
    class MaxFilterWithTracking:
        """Enhanced MaxFilter class with database tracking."""
        
        def __init__(self, config=None):
            self.config = config or {}
            self.tracker = ProcessingTracker()
        
        @ProcessingTracker().track_operation('maxfilter', 'MaxFilter Processing')
        def process_file(self, input_file: str, output_file: str, **maxfilter_params):
            """Process a single file with MaxFilter and track it."""
            
            print(f"Processing {Path(input_file).name} with MaxFilter...")
            
            # This would contain the actual MaxFilter command execution
            # For demo, we just simulate the processing
            
            # Create output file (in real case, MaxFilter would do this)
            Path(output_file).parent.mkdir(parents=True, exist_ok=True)
            Path(output_file).touch()
            
            print(f"  Created processed file: {Path(output_file).name}")
            
            return output_file
        
        def run_command(self, subject: str, session: str):
            """Run MaxFilter on all files for a subject/session."""
            
            with track_processing_session('maxfilter') as session_tracker:
                
                # Simulate finding files to process
                files_to_process = [
                    f'/data/{subject}/{session}/triux/NatMEG_{subject}_Phalanges_raw.fif',
                    f'/data/{subject}/{session}/triux/NatMEG_{subject}_AudOdd_raw.fif'
                ]
                
                processed_files = []
                
                for input_file in files_to_process:
                    output_file = input_file.replace('_raw.fif', '_proc-tsss+mc_meg.fif')
                    
                    # Process the file (this would call the decorated method)
                    result = self.process_file(
                        input_file=input_file,
                        output_file=output_file,
                        tsss=True,
                        movecomp=True,
                        headpos=True
                    )
                    
                    processed_files.append(result)
                
                print(f"MaxFilter processing completed for {subject}/{session}")
                print(f"Processed {len(processed_files)} files")
                
                return processed_files
    
    return MaxFilterWithTracking


def enhanced_logging_example():
    """Example of enhancing the existing log function with database integration."""
    
    # This would modify utils.py
    from database import create_database
    
    def enhanced_log(process: str, message: str, level: str = 'info', 
                    logfile: str = 'log.log', logpath: str = '.', 
                    track_in_database: bool = True):
        """Enhanced log function with optional database tracking."""
        
        # Call original log function (imported from utils)
        from utils import log as original_log
        original_log(process, message, level, logfile, logpath)
        
        # Also track in database if requested
        if track_in_database and any(keyword in message.lower() 
                                   for keyword in ['processed', 'converted', 'saved', 'created']):
            
            try:
                db = create_database()
                
                # Try to extract file information from the message
                import re
                file_pattern = r'[\w\-_./]+\.[\w]+'
                files = re.findall(file_pattern, message)
                
                if files:
                    # Log as a processing operation
                    db.log_operation(
                        operation_type=process.lower().replace(' ', '_'),
                        input_files=[],
                        output_files=files,
                        process_name=f"{process} - {message[:50]}...",
                        parameters={
                            'log_level': level,
                            'original_message': message,
                            'logfile': logfile,
                            'logpath': logpath
                        }
                    )
            except Exception as e:
                # Don't break logging if database fails
                print(f"Warning: Could not log to database: {e}")
    
    return enhanced_log


def demonstrate_integration():
    """Demonstrate the integration examples."""
    
    print("File Processing Database - Integration Examples")
    print("=" * 60)
    
    # Demonstrate enhanced bidsify
    print("\n1. Enhanced BIDS Conversion Demo:")
    print("-" * 40)
    bidsify_func = enhanced_bidsify_example()
    bidsify_func({})  # Run with empty config for demo
    
    # Demonstrate enhanced MaxFilter
    print("\n2. Enhanced MaxFilter Demo:")
    print("-" * 40)
    maxfilter_class = enhanced_maxfilter_example()
    maxfilter = maxfilter_class()
    maxfilter.run_command('001', 'session1')
    
    # Demonstrate enhanced logging
    print("\n3. Enhanced Logging Demo:")
    print("-" * 40)
    enhanced_log_func = enhanced_logging_example()
    enhanced_log_func('DEMO', 'Processing file demo_file.fif completed successfully', 'info')
    enhanced_log_func('DEMO', 'Converted raw_data.fif to processed_data.fif', 'info')
    
    print("\n✅ Integration examples completed!")
    print("\nTo integrate with your existing pipeline:")
    print("1. Add 'from database_integration import ProcessingTracker' to your scripts")
    print("2. Use @tracker.track_operation() decorators on processing functions") 
    print("3. Use 'with track_processing_session()' for batch operations")
    print("4. Enhance existing log calls to include database tracking")


if __name__ == "__main__":
    demonstrate_integration()
