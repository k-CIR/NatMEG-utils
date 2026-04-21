#!/usr/bin/env python3
"""
Seshat CLI
Main command-line interface for the Seshat data processing pipeline
"""
import sys
import os
import argparse
from pathlib import Path

# Add the current directory to the Python path for local imports
_current_dir = str(Path(__file__).parent)
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import yaml
from utils import log, configure_logging


def main():
    """Main entry point for the seshat command"""
    parser = argparse.ArgumentParser(
        description="Seshat - NatMEG Data Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create default configuration file
  seshat create-config                    # Creates default_config.yml
  seshat create-config -o my_config.yml   # Creates my_config.yml
  
  # Launch GUI for interactive configuration
  seshat gui
  seshat gui --config existing_config.yml
  
  # Run complete processing pipeline
  seshat run --config config.yml
  
  # Run individual pipeline components
  seshat copy --config config.yml         # Data synchronization only
  seshat opm-preprocess --config config.yml          # OPM preprocessing only
  seshat maxfilter --config config.yml    # MaxFilter processing only
  seshat bidsify --config config.yml      # BIDS conversion only
  
  # Server synchronization workflow
  seshat sync --config project.yml [--dry-run]             # Sync operation using project config [preview]
  seshat sync --directory /data/project [--dry-run]        # Sync operation for custom directory [preview]
  seshat sync --create-config                             # Create example server config
  seshat sync --test --server cir --server-config servers.yml  # Test server connection
  seshat sync --config project.yml --delete               # Sync with deletion using project config
  seshat sync --directory /data/project --exclude "*.log" --include "*.fif"
  
  # Advanced sync options
  seshat sync --directory ./processed_data --server server_name \\
    --exclude "temp/*" --exclude "*.tmp" \\
    --include "derivatives/*" \\
    --dry-run --delete

For more information, visit: https://github.com/k-CIR/NatMEG-utils
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # GUI command
    gui_parser = subparsers.add_parser('gui', help='Launch configuration GUI')
    gui_parser.add_argument('--config', help='Configuration file to load')
    gui_parser.add_argument('--create-config', help='Create default configuration file and exit')
    
    # Run complete pipeline
    run_parser = subparsers.add_parser('run', help='Run complete pipeline')
    run_parser.add_argument('--config', required=True, help='Configuration file')
    run_parser.add_argument('--dry-run', action='store_true', help='Show what would be executed without actually running it')
    run_parser.add_argument('--delete', action='store_true', help='Delete files on server not in source')
    run_parser.add_argument('--exclude', action='append', help='Exclude pattern (can be used multiple times)')
    run_parser.add_argument('--include', action='append', help='Include pattern (can be used multiple times)')
    run_parser.add_argument('--no-report', action='store_true', help='Skip final HTML report generation (default: generate report)')
    
    # Individual components
    copy_parser = subparsers.add_parser('copy', help='Data synchronization only')
    copy_parser.add_argument('--config', required=True, help='Configuration file')

    opm_parser = subparsers.add_parser('opm-preprocess', help='OPM preprocessing only')
    opm_parser.add_argument('--config', required=True, help='Configuration file')

    maxfilter_parser = subparsers.add_parser('maxfilter', help='MaxFilter processing only')
    maxfilter_parser.add_argument('--config', required=True, help='Configuration file')
    maxfilter_parser.add_argument('--dry-run', action='store_true', help='Show MaxFilter commands without executing them')
    
    bidsify_parser = subparsers.add_parser('bidsify', help='BIDS conversion only')
    bidsify_parser.add_argument('--config', required=True, help='Configuration file')

    # Standalone report generation
    report_parser = subparsers.add_parser('report', help='Generate project HTML report only')
    report_parser.add_argument('--config', required=True, help='Project configuration file used to locate data roots')
    report_parser.add_argument('--no-report', action='store_true', help='(Ignored for compatibility)')
    
    # Create configuration file command
    create_config_parser = subparsers.add_parser('create-config', help='Create default configuration file')
    create_config_parser.add_argument('--output', '-o', default='default_config.yml', help='Output filename (default: default_config.yml)')
    
    # Server sync command (updated to reflect new sync_to_cir interface)
    sync_parser = subparsers.add_parser('sync', help='Sync data to remote server')
    sync_parser.add_argument('--config', help='Project configuration file (YAML or JSON) used to infer default sync directory')
    sync_parser.add_argument('--directory', nargs='*', metavar=('PATH','SERVER'), help='Sync custom directory to specified server')
    sync_parser.add_argument('--dry-run', action='store_true', help='Show what would be transferred without actually doing it')
    sync_parser.add_argument('--create-config', action='store_true', help='Create example server configuration file')
    sync_parser.add_argument('--server-config', help='Server configuration file (YAML or JSON)')
    sync_parser.add_argument('--server', help='Server name (default cir)', default='cir')
    sync_parser.add_argument('--test', action='store_true', help='Only test connection to server and exit (use --server to pick server)')
    sync_parser.add_argument('--exclude', action='append', metavar='PATTERN', help='Exclude files matching pattern (can be used multiple times)')
    sync_parser.add_argument('--include', action='append', metavar='PATTERN', help='Include files matching pattern (can be used multiple times)')
    sync_parser.add_argument('--delete', action='store_true', help='Delete local files after successful sync to server (use with caution!)', default=False)

    # File tracking commands
    track_parser = subparsers.add_parser('track', help='File tracking operations')
    track_parser.add_argument('--config', '-c', help='Project configuration file')
    track_parser.add_argument('subcommand', choices=['status', 'verify', 'sync-central',
                                                      'sync-from-central', 'delete-ready', 'global-status',
                                                      'migrate', 'scan', 'import'],
                              help='Track command to execute')
    track_parser.add_argument('--dry-run', action='store_true', help='Dry run mode for delete-ready')
    track_parser.add_argument('--file', '-f', help='Specific file path for verify')
    track_parser.add_argument('--path', '-p', help='Project path for migrate/scan (overrides config)')
    track_parser.add_argument('--assume-synced', action='store_true', help='Assume files are already synced')
    track_parser.add_argument('--assume-copied', action='store_true', help='Assume files are copied (default)')
    track_parser.add_argument('--copy-log', help='Path to copy_results.json to import from')


    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'gui':
            from run_config import config_UI
            config = config_UI(args.config)
        
        elif args.command == 'run':
            # Run complete pipeline

            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
                        
            logfile = config['Project'].get('Logfile', 'pipeline_log.log')

            project_root = os.path.join(config['Project'].get('Root', '.'), config['Project'].get('Name', ''))
            logpath = os.path.join(project_root, 'logs')
            os.path.exists(logpath)
            os.makedirs(logpath, exist_ok=True)
            # Initialize centralized logging once for this run
            configure_logging(log_dir=logpath, log_file=logfile)
            dry_run = getattr(args, 'dry_run', False)

            log("Pipeline", '----------------------------------------------------', 'info', )
            log("Pipeline",f'Using config file: {args.config}', 'info', f'{logpath}/{logfile}')

            if dry_run:
                log("Pipeline","DRY RUN MODE - No actual processing will be performed", 'info', f'{logpath}/{logfile}')

            log("Pipeline", "Starting", 'info', f'{logpath}/{logfile}')
            
            pipeline_success = []
            
            # Execute pipeline steps based on config
            if config['RUN'].get('Copy to Cerberos', False):
                import copy_to_cerberos
                copy_success = copy_to_cerberos.main(args.config)
                pipeline_success.append(copy_success)
                
            if config['RUN'].get('OPM preprocessing', False):
                import opm_preprocess
                opm_preprocess_success = opm_preprocess.main(args.config)
                pipeline_success.append(opm_preprocess_success)

            # if config['RUN'].get('Run Maxfilter', False):
            #     import maxfilter
            #     maxfilter_success = maxfilter.main(args.config, dry_run=dry_run)
            #     pipeline_success.append(maxfilter_success)

            # if config['RUN'].get('Run BIDS conversion', False):
            #     import bidsify
            #     bids_success = bidsify.main(args.config)
            #     pipeline_success.append(bids_success)
            
            if config['RUN'].get('Sync to CIR', False):
                import sync_to_cir
                bids_path = config['Project'].get('BIDS', '.')
                sync_path = os.path.dirname(bids_path) if bids_path else '.'

                syncer = sync_to_cir.ServerSync()
                success = syncer.sync_directory(
                    sync_path, 'cir',
                    exclude_patterns=getattr(args, 'exclude', None),
                    include_patterns=getattr(args, 'include', None),
                    dry_run=dry_run,
                    delete=getattr(args, 'delete', False),
                    project_config=args.config
                )
                pipeline_success.append(success)
            
                # Generate project report unless disabled
                if not getattr(args, 'no_report', False):
                    try:
                        import render_report
                        render_report.main(args.config)
                        log("Pipeline", "Report generated (report.html)", 'info', f'{logpath}/{logfile}')
                    except Exception as e:
                        log("Pipeline", f"Report generation failed: {e}", 'warning', f'{logpath}/{logfile}')

            if all(pipeline_success):
                log("Pipeline", "Completed successfully!", 'info', f'{logpath}/{logfile}')
            else:
                log("Pipeline", f"Completed with errors, see {logpath}/{logfile}", 'error', f'{logpath}/{logfile}')

        elif args.command == 'copy':
            import copy_to_cerberos
            copy_to_cerberos.main(args.config)

        elif args.command == 'opm-preprocess':
            import opm_preprocess
            opm_preprocess.main(args.config)
        
        elif args.command == 'maxfilter':
            import maxfilter
            dry_run = getattr(args, 'dry_run', False)
            maxfilter.main(args.config, dry_run=dry_run)
        
        elif args.command == 'bidsify':
            import bidsify
            bidsify.main(args.config)

        elif args.command == 'report':
            # Standalone report generation
            try:
                import render_report
                render_report.main(args.config)
                log("Report", "Report generated (report.html)", 'info')
            except Exception as e:
                log("Report", f"Report generation failed: {e}", 'error')
                sys.exit(1)
        
        elif args.command == 'create-config':
            # Create default configuration file
            from run_config import create_config_file
            success = create_config_file(args.output)
            if success:
                print(f"✅ Created default configuration file: {args.output}")
                print("Edit this file to customize your pipeline settings.")
            else:
                print(f"❌ Failed to create configuration file: {args.output}")
                sys.exit(1)
        
        elif args.command == 'sync':
            import sync_to_cir
            # Create example config
            if args.create_config:
                example = sync_to_cir.create_example_config()
                cfg_file = 'server_sync_config.yml'
                with open(cfg_file, 'w') as f:
                    yaml.dump(example, f, default_flow_style=False, indent=2, sort_keys=False)
                print(f"Created example configuration file: {cfg_file}")
                print("Edit this file with your server details before using the sync tool.")
                return

            # Load custom server config if provided
            if args.server_config:
                syncer = sync_to_cir.ServerSync(args.server_config)
            else:
                try:
                    syncer = sync_to_cir.ServerSync()
                except FileNotFoundError:
                    print("No default server config found. Use --create-config or --server-config.")
                    return

            if args.test:
                syncer.check_server_connection(args.server)
                return

            if args.directory:
                local_path = args.directory[0]
                server = args.server
                if len(args.directory) > 1 and not args.server:
                    server = args.directory[1]
                success = syncer.sync_directory(
                    local_path, server,
                    exclude_patterns=args.exclude,
                    include_patterns=args.include,
                    dry_run=args.dry_run,
                    delete=args.delete,
                    project_config=args.config
                )
                if success:
                    log("Sync", "Completed successfully!", 'info')
                else:
                    log("Sync", "Failed. Check log files for details.", 'error')
            elif args.config:
                # Derive directory from project config
                try:
                    with open(args.config, 'r') as f:
                        proj_cfg = yaml.safe_load(f)

                    project_name = proj_cfg.get('Project', {}).get('Name', None)
                    root_name = proj_cfg.get('Project', {}).get('Root', None)

                    if not project_name or not root_name:
                        print("Project name and root directory must be specified.")
                        return

                    local_path = os.path.join(root_name, project_name)
                    if os.path.exists(local_path):
                        print(f"Inferred local directory from project config: {local_path}")
                    else:
                        print('Could not infer directory from project config; specify --directory')
                        return
                except Exception as e:
                    print(f'Error reading project config {args.config}: {e}')
                    return
                success = syncer.sync_directory(
                    local_path, args.server,
                    exclude_patterns=args.exclude,
                    include_patterns=args.include,
                    dry_run=args.dry_run,
                    delete=args.delete,
                    project_config=args.config
                )
                if success:
                    log("Sync", "Completed successfully!", 'info')
                else:
                    log("Sync", "Failed. Check log files for details.", 'error')
            else:
                # If no directory specified, show help by invoking original script main
                from sync_to_cir import main as sync_main
                sync_main()

        elif args.command == 'track':
            from file_tracker import FileTracker, CENTRAL_DB
            import json

            sub = args.subcommand if hasattr(args, 'subcommand') and args.subcommand else args.command

            if sub == 'global-status':
                if not CENTRAL_DB.exists():
                    print("Central DB not initialized yet")
                    return
                tracker = FileTracker()
                tracker.project_db = str(CENTRAL_DB)
                summary = tracker.get_global_summary()
                print("\nGlobal Status Summary:")
                for project, statuses in summary.items():
                    print(f"\n{project}:")
                    for status, count in sorted(statuses.items()):
                        print(f"  {status}: {count}")

            elif sub in ('migrate', 'scan') and args.path:
                project_path = args.path
                tracker = FileTracker({
                    'Project': {'Name': os.path.basename(project_path), 'Root': os.path.dirname(project_path) or '.'}
                })
                tracker.project_root = project_path

                if sub == 'scan':
                    result = tracker.scan_and_detect_status(root_path=project_path)
                    print(json.dumps(result, indent=2))
                elif sub == 'migrate':
                    assume_synced = args.assume_synced
                    assume_copied = not assume_synced
                    result = tracker.migrate_existing_project(
                        root_path=project_path,
                        assume_synced=assume_synced,
                        assume_copied=assume_copied
                    )
                    print(json.dumps(result, indent=2))

            elif args.config:
                tracker = FileTracker(args.config)

                if sub == 'status':
                    summary = tracker.get_status_summary()
                    print(f"\nProject: {tracker.project_name}")
                    print(f"Project DB: {tracker.project_db}")
                    print("\nStatus Summary:")
                    for status, count in sorted(summary.items()):
                        print(f"  {status}: {count}")

                    print("\nAll tracked files:")
                    for f in tracker.get_all_files():
                        print(f"  [{f['status']}] {f['source_path']}")

                elif sub == 'verify':
                    if args.file:
                        file_id = tracker.find_file_by_project_path(args.file)
                        if file_id:
                            result = tracker.verify_hash(file_id)
                            print(json.dumps(result, indent=2))
                        else:
                            print(f"File not found: {args.file}")
                    else:
                        all_files = tracker.get_all_files()
                        verified = 0
                        failed = 0
                        for f in all_files:
                            result = tracker.verify_hash(f['id'])
                            if result['verified']:
                                verified += 1
                            else:
                                failed += 1
                                print(f"FAILED: {f['source_path']} - {result['reason']}")
                        print(f"\nVerified: {verified}, Failed: {failed}")

                elif sub == 'sync-central':
                    result = tracker.sync_to_central()
                    print(json.dumps(result, indent=2))

                elif sub == 'sync-from-central':
                    result = tracker.sync_from_central()
                    print(json.dumps(result, indent=2))

                elif sub == 'delete-ready':
                    result = tracker.delete_orphans(dry_run=args.dry_run)
                    print(json.dumps(result, indent=2))

                elif sub == 'import':
                    if args.copy_log:
                        result = tracker.import_from_copy_results(args.copy_log)
                        print(json.dumps(result, indent=2))
                    else:
                        print("Error: --copy-log required for import command")
                        return

            else:
                print(f"Error: Unknown track subcommand: {sub}")

    except Exception as e:
        log("Pipeline", f"Error: {e}", 'error')
        sys.exit(1)

if __name__ == "__main__":
    main()