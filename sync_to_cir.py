#!/usr/bin/env python3
"""
NatMEG Server Sync Utility
Convenient script for syncing processed data to remote servers (CIR, etc.)
"""

import os
import sys
import argparse
import yaml
import json
import subprocess
import shlex
from pathlib import Path
from os.path import dirname, abspath, exists, isdir
from datetime import datetime
from typing import Dict, List, Optional, Union
from copy import deepcopy
from mne_bids import print_dir_tree
from utils import log, askdirectory
from file_tracker import FileTracker, STATUS_SYNCED, STATUS_SYNCING, STATUS_READY_TO_DELETE

sync_config = '/home/natmeg/.config/sync_config.yml'
general_log_file = '/home/natmeg/.log/sync_to_server.log'

class ServerSync:
    """Handle syncing data to remote servers with rsync"""

    def __init__(self, config: Union[str, Dict] = sync_config):
        """Initialize with configuration"""
        if isinstance(config, str):
            with open(config, 'r') as f:
                if config.endswith('.json'):
                    self.config = json.load(f)
                elif config.endswith('.yml') or config.endswith('.yaml'):
                    self.config = yaml.safe_load(f)
                else:
                    raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
        else:
            self.config = config
            
        self.timestamp = datetime.now().strftime('%Y%m%d')
        self.log_file = f'sync_to_server.log'
        
    def validate_server_config(self, server_name: str) -> Dict:
        """Validate server configuration"""
        servers = self.config.get('servers', {})
        if server_name not in servers:
            available = list(servers.keys())
            raise ValueError(f"Server '{server_name}' not found. Available: {available}")
        
        server_config = servers[server_name]
        required_fields = ['host', 'user', 'remote_path']
        
        for field in required_fields:
            if field not in server_config:
                raise ValueError(f"Missing required field '{field}' in server config for '{server_name}'")
        
        return server_config
    
    def get_local_path(self, path: str = None) -> str:
        """Get local path for syncing"""
        if not path:
            path = askdirectory(title="Select Local Path",
                                initialdir='neuro/data/local')
            if not path:
                raise ValueError("No local path selected")
        
        # Ensure the path exists
        if not os.path.exists(path):
            raise FileNotFoundError(f"Local path does not exist: {path}")
        
        return os.path.abspath(path)
    
    def build_rsync_command(self, local_path: str, server_config: Dict, 
                          exclude_patterns: List[str] = None,
                          include_patterns: List[str] = None,
                          dry_run: bool = False) -> List[str]:
        """Build rsync command with options"""
        
        cmd = ['rsync']

        # Source and destination
        local_path = local_path.rstrip('/')  # Remove trailing slash
        remote_root = server_config['remote_path'].rstrip('/')
        
        # Always avoid duplicating the local basename on the remote path
        remote_dest = f"{server_config['user']}@{server_config['host']}:{remote_root}"

        cmd.extend(self.config.get('default_rsync_options', []))
        
        global_excludes = self.config.get('sync_defaults', {}).get('global_excludes', [])

        # Add includes (processed before excludes)
        global_includes = self.config.get('sync_defaults', {}).get('global_includes', [])
        
        log_commands = self.config.get('log_commands', {})
        
        custom_opts = server_config.get('rsync_options', [])
        
        ssh_opts = server_config.get('ssh_options', [])
        
        if global_excludes:
            for pattern in global_excludes:
                cmd.extend(['--exclude', pattern])
        
        # Add custom excludes and includes
        if exclude_patterns:
            for pattern in exclude_patterns:
                cmd.extend(['--exclude', pattern])
        
        if global_includes:
            for pattern in global_includes:
                cmd.extend(['--include', pattern])
        
        if include_patterns:
            for pattern in include_patterns:
                cmd.extend(['--include', pattern])

        # Also add itemize-changes to track what files are transferred
        if '--itemize-changes' not in cmd:
            cmd.append('--itemize-changes')

        # Add dry-run option
        if dry_run:
            cmd.append('--dry-run')
            
        # Custom rsync options from config
        if custom_opts:
            cmd.extend(custom_opts)
            
        # SSH options
        if ssh_opts:
            ssh_cmd = ['ssh'] + ssh_opts
            cmd.extend(['-e', ' '.join(shlex.quote(arg) for arg in ssh_cmd)])

        if '--stats' not in cmd:
            cmd.append('--stats')
        cmd.extend([local_path, remote_dest])

        # Log 
        if log_commands:
            cmd.extend(['--log-file', log_commands.get('file', '')])

        return cmd
    
    def sync_directory(self, local_path: str, server_name: str,
                      exclude_patterns: List[str] = None,
                      include_patterns: List[str] = None,
                      dry_run: bool = False,
                      delete: bool = False,
                      project_config: str = None) -> bool:
        """Sync a directory to remote server and optionally delete local files after successful transfer"""

        tracker = None
        if project_config:
            try:
                tracker = FileTracker(project_config)
            except Exception as e:
                log(f"File tracker init failed: {e}", 'warning',
                    logfile=self.log_file, logpath=log_path)

        log_path = f'{local_path}/log' or './log'
        if not os.path.exists(log_path):
            os.makedirs(log_path, exist_ok=True)
        
        if not os.path.exists(local_path):
            log(f"Local path does not exist: {local_path}", 'error', 
                logfile=self.log_file, logpath=log_path)
            return False
            
        try:
            server_config = self.validate_server_config(server_name)
            cmd = self.build_rsync_command(
                local_path, server_config, exclude_patterns, 
                include_patterns, dry_run)
            # Log the command
            cmd_str = ' '.join(shlex.quote(arg) for arg in cmd)
            log(f"Executing: {cmd_str}", 'info', logfile=self.log_file, logpath=log_path, )

            if dry_run:
                log("DRY RUN MODE - No files will be transferred", 'info',
                    logfile=self.log_file, logpath=log_path)
                if delete:
                    log("DRY RUN MODE - Local files would be deleted after successful sync", 'info',
                        logfile=self.log_file, logpath=log_path)
                print_dir_tree(local_path, max_depth=2)  # Print directory structure for verification
            
            # Execute rsync
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Log output
            if result.stdout:
                log(f"Rsync output:\n{result.stdout}", 'info',
                    logfile=self.log_file, logpath=log_path)
                    
            if result.stderr:
                log(f"Rsync errors:\n{result.stderr}", 'warning',
                    logfile=self.log_file, logpath=log_path)
            
            if result.returncode == 0:
                log(f"Successfully synced {local_path} to {server_name}", 'info',
                    logfile=self.log_file, logpath=log_path)

                if tracker:
                    transferred = self._get_transferred_files(result.stdout)
                    for file_path in transferred:
                        file_id = tracker.find_file_by_project_path(file_path)
                        if file_id:
                            tracker.update_status(file_id, STATUS_SYNCED, compute_hash=False)
                            tracker.mark_ready_to_delete([file_id])
                            log(f"Marked synced and ready to delete: {file_path}", 'info',
                                logfile=self.log_file, logpath=log_path)

                # If delete flag is set and sync was successful, delete local files
                if delete and not dry_run:
                    self._delete_local_files_after_sync(local_path, result.stdout, log_path, tracker)

                return True
            else:
                log(f"Rsync failed with return code {result.returncode}", 'error',
                    logfile=self.log_file, logpath=log_path)
                return False
                
        except Exception as e:
            log(f"Error syncing to {server_name}: {e}", 'error',
                logfile=self.log_file, logpath=log_path)
            return False
    
    def _get_transferred_files(self, rsync_output: str) -> List[str]:
        """Parse rsync output to get list of transferred file paths"""
        import re
        transferred = []
        lines = rsync_output.strip().split('\n')
        for line in lines:
            match = re.match(r'^[><]f[\+\.\s]*\s+(.+)$', line.strip())
            if match:
                transferred.append(match.group(1))
        return transferred

    def _delete_local_files_after_sync(self, local_path: str, rsync_output: str, log_path: str, tracker=None):
        """Delete local files that were successfully transferred to server"""
        try:
            import re

            transferred = self._get_transferred_files(rsync_output)

            deleted_count = 0
            skipped_count = 0
            for relative_path in transferred:
                full_path = os.path.join(local_path, relative_path)
                if not os.path.exists(full_path) or not os.path.isfile(full_path):
                    continue

                if tracker:
                    file_id = tracker.find_file_by_project_path(full_path)
                    if file_id and not tracker.safe_to_delete(file_id):
                        log(f"Skipped unsafe file (not ready to delete): {full_path}", 'warning',
                            logfile=self.log_file, logpath=log_path)
                        skipped_count += 1
                        continue

                try:
                    os.remove(full_path)
                    deleted_count += 1
                    log(f"Deleted local file after successful sync: {full_path}", 'info',
                        logfile=self.log_file, logpath=log_path)
                except Exception as e:
                    log(f"Failed to delete local file {full_path}: {e}", 'warning',
                        logfile=self.log_file, logpath=log_path)

            if deleted_count > 0 or skipped_count > 0:
                msg = f"Deleted {deleted_count} local files"
                if skipped_count > 0:
                    msg += f", Skipped {skipped_count} (not verified synced)"
                log(msg, 'info', logfile=self.log_file, logpath=log_path)

                self._cleanup_empty_directories(local_path, log_path)

        except Exception as e:
            log(f"Error during local file cleanup: {e}", 'warning',
                logfile=self.log_file, logpath=log_path)
    
    def _cleanup_empty_directories(self, base_path: str, log_path: str):
        """Remove empty directories after file deletion"""
        try:
            for root, dirs, files in os.walk(base_path, topdown=False):
                # Skip the log directory
                if root == log_path or log_path in root:
                    continue
                    
                # If directory is empty (no files and no subdirectories), remove it
                if not files and not dirs:
                    try:
                        os.rmdir(root)
                        log(f"Removed empty directory: {root}", 'info',
                            logfile=self.log_file, logpath=log_path)
                    except Exception as e:
                        log(f"Failed to remove empty directory {root}: {e}", 'warning',
                            logfile=self.log_file, logpath=log_path)
        except Exception as e:
            log(f"Error during directory cleanup: {e}", 'warning',
                logfile=self.log_file, logpath=log_path)
    
    def check_server_connection(self, server_name: str) -> bool:
        """Test connection to server"""
        try:
            server_config = self.validate_server_config(server_name)
            
            # Test SSH connection
            ssh_cmd = ['ssh']
            ssh_opts = server_config.get('ssh_options', [])
            if ssh_opts:
                ssh_cmd.extend(ssh_opts)
            
            ssh_cmd.extend([
                f"{server_config['user']}@{server_config['host']}",
                'echo "Connection test successful"'
            ])
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"✅ Successfully connected to {server_name}")
                return True
            else:
                print(f"❌ Failed to connect to {server_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Error testing connection to {server_name}: {e}")
            return False

def get_parameters(config: Union[str, Dict]) -> Dict:
    """
    Extract and merge BIDS configuration parameters from file or dictionary.
    
    Reads configuration from JSON/YAML file or processes existing dictionary,
    combining project and BIDS-specific parameters into a unified configuration.

    Args:
        config (str or dict): Path to config file (.json/.yml/.yaml) or
                             configuration dictionary

    Returns:
        dict: Merged configuration dictionary combining project and BIDS settings

    Raises:
        ValueError: If unsupported file format is provided
    """
    if isinstance(config, str):
        if config.endswith('.json'):
            with open(config, 'r') as f:
                config_dict = json.load(f)
        elif config.endswith('.yml') or config.endswith('.yaml'):
            with open(config, 'r') as f:
                config_dict = yaml.safe_load(f)
        else:
            raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
    elif isinstance(config, dict):
        config_dict = deepcopy(config)

    sync_dict = deepcopy(config_dict['Project'])
    return sync_dict


def create_example_config():
    """Create example server configuration"""
    example_config = {
        'servers': {
            'cir': {
                'host': 'cir-server.example.com',
                'user': 'your_username',
                'remote_path': '/data/natmeg/project_name',
                'ssh_options': ['-p', '22', '-i', '~/.ssh/id_rsa'],
                'rsync_options': ['--checksum']  # Additional rsync options
            },
            # 'backup_server': {
            #     'host': 'backup.example.com', 
            #     'user': 'backup_user',
            #     'remote_path': '/backup/natmeg',
            #     'ssh_options': ['-p', '2222'],
            #     'rsync_options': ['--backup', '--backup-dir=old_versions']
            # }
        },
        'default_rsync_options': [
            '--archive',           # Archive mode
            '--verbose',           # Verbose output
            '--compress',          # Compress during transfer
            '--partial',           # Keep partial files on interruption
            '--progress',          # Show progress
            '--human-readable'    # Human readable sizes
        ],
        'sync_defaults': {
            'global_excludes': [
                '*.tmp', 
                '*.log', 
                '.DS_Store', 
                '__pycache__/', 
                '.git/', 
                '*.bak'
            ],
            'global_includes': [
                '*.bids', 
                '*.json', 
                '*.tsv', 
                '*.txt'
            ]
        }
    }
    
    return example_config


def main(path:str=None):
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="NatMEG Server Sync Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test connection to server
  python sync_to_cir.py --test cir
  
  # Sync custom directory
  python sync_to_cir.py --directory /path/to/data cir

  # Generate example config
  python sync_to_cir.py --create-config
        """
    )

    parser.add_argument('--config', help='Project configuration file (YAML or JSON)')
    parser.add_argument('--server-config', help='Server configuration file (YAML or JSON)')
    parser.add_argument('--create-config', action='store_true', 
                       help='Create example server configuration file')
    parser.add_argument('--test', action='store_true',
                       help='Only test connection to server and exit (use --server to pick server)')
    parser.add_argument('--server', help='Server name (default cir)')
    
    parser.add_argument('--directory', nargs='*', metavar=('PATH', 'SERVER'),
                       help='Sync custom directory to specified server')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be transferred without actually doing it')
    parser.add_argument('--delete', action='store_true',
                       help='Delete local files after successful sync to server (use with caution!)', default=False)
    parser.add_argument('--exclude', action='append', metavar='PATTERN',
                       help='Exclude files matching pattern (can be used multiple times)')
    parser.add_argument('--include', action='append', metavar='PATTERN',
                       help='Include files matching pattern (can be used multiple times)')
    
    args = parser.parse_args()

    server_name = args.server or 'cir'
    
    # Create example config
    if args.create_config:
        example = create_example_config()
        server_config_file = 'server_sync_config.yml'
        with open(server_config_file, 'w') as f:
            yaml.dump(example, f, default_flow_style=False, indent=2, sort_keys=False)
        print(f"Created example configuration file: {server_config_file}")
        print("Edit this file with your server details before using the sync tool.")
        return
    
    # Load configuration
    if args.server_config:
        server_config_file = args.server_config
        if not os.path.exists(server_config_file):
            print(f"Configuration file not found: {server_config_file}")
            print("Use --create-config to generate an example configuration.")
            return
    
        try:
            syncer = ServerSync(server_config_file)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return
    else:
        syncer = ServerSync()

    # Test connection only
    if args.test:
        syncer.check_server_connection(server_name)
        return
    
    # Sync operations

    if args.config:
        try:
            config = get_parameters(args.config)
            print(config)
        except Exception as e:
            print(f"Error loading project configuration: {e}")
            return
        
        project_name = config.get('Name', None)
        root_name = config.get('Root', None)

        if not project_name or not root_name:
            print("Project name and root directory must be specified.")
            return

        directory = dirname(os.path.join(root_name, project_name))

        local_path = directory
        success = syncer.sync_directory(
            local_path, server_name,
            exclude_patterns=args.exclude,
            include_patterns=args.include,
            dry_run=args.dry_run,
            delete=args.delete,
            project_config=args.config
        )

    if args.directory:
        local_path = args.directory[0]
        if len(args.directory) > 1 and not args.server:
            server_name = args.directory[1]
        syncer.sync_directory(
            local_path, server_name,
            exclude_patterns=args.exclude,
            include_patterns=args.include,
            dry_run=args.dry_run,
            delete=args.delete,
            project_config=args.config
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
