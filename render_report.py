import argparse
import pandas as pd
from glob import glob
import os
import json
from os.path import join, isdir, dirname, basename
from mne_bids import print_dir_tree
import re
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from typing import Union
import yaml
import subprocess
from utils import askForConfig

def nested_dir_tree(root_path, rel_path="", max_entries: int | None = None):
    """Return nested directory tree for local or SSH (user@host:/path) roots.

    Automatically detects remote SSH paths of the form user@host:/absolute/path
    and builds the tree via a remote 'find' command. Falls back gracefully if
    SSH command fails.
    """

    # Remote (SSH) path detection
    if '@' in root_path and ':' in root_path.split('@', 1)[1]:
        user_host, remote_path = root_path.split(':', 1)
        remote_path = remote_path or '/'  # safety
        find_cmd = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', user_host,
            f"find '{remote_path}' -mindepth 1 -printf '%y|%P|%T@|%s\\n'"
        ]
        try:
            proc = subprocess.run(find_cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                print(f"[WARN] SSH find failed ({proc.returncode}): {proc.stderr.strip()[:200]}")
                return {}
            lines = proc.stdout.strip().splitlines()
            if max_entries:
                lines = lines[:max_entries]
            tree: dict = {}
            for line in lines:
                try:
                    ftype, rel, mtime, size = line.split('|', 3)
                except ValueError:
                    continue
                if rel == '':
                    continue
                parts = rel.split('/')
                cursor = tree
                for i, part in enumerate(parts):
                    if i == len(parts) - 1 and ftype != 'd':
                        # file
                        cursor.setdefault('__files__', []).append({
                            'name': part,
                            'relpath': rel,
                            'mtime': float(mtime) if mtime else None,
                            'size': int(size) if size.isdigit() else 0,
                        })
                    else:
                        cursor = cursor.setdefault(part, {})
                # Ensure directories have entry even with no files
                if ftype == 'd' and parts:
                    _ = tree
                    for part in parts:
                        _ = _.setdefault(part, {})
            return tree
        except Exception as e:
            print(f"[WARN] Remote listing failed: {e}")
            return {}

    # Local path handling
    tree = {}
    try:
        for entry in os.scandir(os.path.join(root_path, rel_path)):
            if entry.is_dir():
                tree[entry.name] = nested_dir_tree(root_path, os.path.join(rel_path, entry.name))
            else:
                stat_info = entry.stat()
                tree.setdefault('__files__', []).append({
                    'name': entry.name,
                    'relpath': os.path.join(rel_path, entry.name),
                    'mtime': stat_info.st_mtime,
                    'size': stat_info.st_size,
                })
    except FileNotFoundError:
        print(f"[WARN] Path not found: {root_path}")
    except PermissionError:
        print(f"[WARN] Permission denied: {root_path}")
    return tree

def create_hierarchical_list(tree, current_path="", level=0):
    """Convert nested directory tree to hierarchical list maintaining folder structure.
    Classic tree order: folders first (at current level), then files.
    Files in a directory are shown at the same indentation level as their sibling folders.
    """
    items = []

    # 1) Add directories at this level (classic tree lists folders first)
    directories = [(key, value) for key, value in tree.items() if key != '__files__' and isinstance(value, dict)]
    for dir_name, dir_content in sorted(directories, key=lambda kv: kv[0].lower()):
        dir_path = os.path.join(current_path, dir_name) if current_path else dir_name
        dir_mtime = get_directory_mtime(dir_content)
        dir_size = get_directory_size(dir_content)
        items.append({
            'name': dir_name,
            'type': 'folder',
            'path': dir_path,
            'folder_path': current_path,
            'level': level,
            'mtime': dir_mtime,
            'size': dir_size,
        })
        # Recursively add this folder's contents
        items.extend(create_hierarchical_list(dir_content, dir_path, level + 1))

    # 2) Add files in the current directory
    if '__files__' in tree:
        for file_info in sorted(tree['__files__'], key=lambda x: x['name'].lower()):
            items.append({
                'name': file_info['name'],
                'type': 'file',
                'relpath': file_info['relpath'],
                'folder_path': current_path,
                'level': level,
                'mtime': file_info['mtime'],
                'size': file_info.get('size', 0),
            })

    return items

def get_directory_mtime(dir_tree):
    """Get the latest modification time from a directory tree."""
    max_mtime = 0
    
    for key, value in dir_tree.items():
        if key == '__files__':
            for file_info in value:
                if file_info['mtime']:
                    max_mtime = max(max_mtime, file_info['mtime'])
        elif isinstance(value, dict):
            sub_mtime = get_directory_mtime(value)
            if sub_mtime is not None:
                max_mtime = max(max_mtime, sub_mtime)
    
    return max_mtime if max_mtime > 0 else None

def get_directory_size(dir_tree):
    """Get the total size (bytes) of all files in a directory tree."""
    total = 0
    for key, value in dir_tree.items():
        if key == '__files__':
            for file_info in value:
                total += int(file_info.get('size', 0) or 0)
        elif isinstance(value, dict):
            total += get_directory_size(value)
    return total

def _flatten_files(tree, base_path=""):
    files = {}
    for key, val in tree.items():
        if key == '__files__':
            for f in val:
                files[os.path.join(base_path, f['relpath'] if 'relpath' in f else f['name'])] = f
        elif isinstance(val, dict):
            sub_base = os.path.join(base_path, key) if base_path else key
            files.update(_flatten_files(val, sub_base))
    return files

def load_pipeline_data(config):
    """Load data from all pipeline stages."""
    # Handle both 'Project' and 'project' keys for compatibility
    project_config = config.get('Project', config.get('project', {}))
    project_root = join(project_config.get('Root', ''), project_config.get('Name', ''))
    log_path = join(project_root, 'log')
    
    # Load copy results
    copy_results = []
    copy_file = join(log_path, 'copy_results.json')
    if os.path.exists(copy_file):
        with open(copy_file, 'r') as f:
            copy_results = json.load(f)
    
    # Load BIDS conversion results 
    bids_results = []
    bids_file = join(log_path, 'bids_results.json')
    if os.path.exists(bids_file):
        with open(bids_file, 'r') as f:
            bids_results = json.load(f)
    
    # Load BIDS conversion table
    bids_conversion = None
    bids_conversion_file = join(project_root, 'BIDS', 'conversion_logs', 'bids_conversion.tsv')
    if os.path.exists(bids_conversion_file):
        try:
            import pandas as pd
            bids_conversion = pd.read_csv(bids_conversion_file, sep='\t')
        except ImportError:
            print("Warning: pandas not available for BIDS conversion data")
    
    return {
        'copy_results': copy_results,
        'bids_results': bids_results, 
        'bids_conversion': bids_conversion,
        'project_root': project_root,
        'log_path': log_path
    }

def create_tree_from_paths(file_data, path_key='path', name_key='name', project_root=None):
    """Create hierarchical tree structure from file paths, starting from common root."""
    tree_items = []
    
    # Consolidate BIDS split files: Group entries by BIDS file path
    # For BIDS data, multiple source files may map to the same BIDS file (split files)
    if path_key == 'BIDS File':
        consolidated_data = {}
        for item in file_data:
            bids_file = item.get('BIDS File', '')
            
            # Handle case where BIDS File might already be an array from consolidation
            if isinstance(bids_file, list):
                # Use the first BIDS file as the key for grouping
                bids_file_key = bids_file[0] if bids_file else ''
            else:
                bids_file_key = bids_file
                
            if bids_file_key:
                if bids_file_key not in consolidated_data:
                    consolidated_data[bids_file_key] = {
                        **item,  # Copy all fields from first occurrence
                        'source_files': [],  # Track all source files
                        'split_info': [],    # Track split information
                        'bids_sizes': [],    # Track BIDS sizes for all entries
                        'source_sizes': []   # Track source sizes for all entries
                    }
                
                # Add source file and split info to lists
                source_file = item.get('Source File', '')
                split_info = item.get('Split')
                bids_size = item.get('BIDS Size')
                source_size = item.get('Source Size')
                
                # Handle case where Source File might already be an array from previous consolidation
                if isinstance(source_file, list):
                    # Process each source file in the array
                    processed_source_files = []
                    for sf in source_file:
                        if project_root and sf.startswith(project_root.rstrip('/') + '/'):
                            sf = sf[len(project_root.rstrip('/') + '/'):]
                        processed_source_files.append(sf)
                    source_file = processed_source_files
                else:
                    # Strip project root from source file path if present
                    if project_root and source_file.startswith(project_root.rstrip('/') + '/'):
                        source_file = source_file[len(project_root.rstrip('/') + '/'):]
                
                # Handle both single files and arrays when adding to consolidated data
                if isinstance(source_file, list):
                    consolidated_data[bids_file_key]['source_files'].extend(source_file)
                else:
                    consolidated_data[bids_file_key]['source_files'].append(source_file)
                    
                consolidated_data[bids_file_key]['split_info'].append(split_info)
                consolidated_data[bids_file_key]['bids_sizes'].append(bids_size)
                consolidated_data[bids_file_key]['source_sizes'].append(source_size)
        
        # Convert back to list, using BIDS File as path for tree structure
        file_data = []
        print(f"DEBUG: Consolidating {len(consolidated_data)} BIDS file groups")
        for bids_file, consolidated_item in consolidated_data.items():
            # Use the first source file as the representative source
            first_source = consolidated_item['source_files'][0] if consolidated_item['source_files'] else ''
            
            # Preserve original BIDS file path for display and use it for the tree structure
            original_bids_file = consolidated_item.get('BIDS File', bids_file)
            
            # For BIDS File path_key, construct full BIDS path from filename but keep original for display
            if path_key == 'BIDS File':
                # Extract participant and session from the filename to build proper path
                # bids_file is the first filename from the array (e.g., "sub-0953_ses-241104_task-RSEC_acq-triux_desc-trans_meg.fif")
                participant = consolidated_item.get('Participant', '')
                session = consolidated_item.get('Session', '')
                datatype = consolidated_item.get('Datatype', 'meg')  # default to meg
                
                if participant and session:
                    # Construct BIDS directory path: sub-0953/ses-241104/meg/filename.fif
                    # Use the first BIDS filename as the representative file for the path
                    bids_dir_path = f"sub-{participant}/ses-{session}/{datatype}/{bids_file}"
                    # For tree structure, we need a path that creates directories
                    consolidated_item['_tree_path'] = bids_dir_path  # Internal path for tree building
                    print(f"DEBUG: Set _tree_path for BIDS file: {bids_dir_path}")
                else:
                    # Fallback to just the filename if we can't construct full path
                    consolidated_item['_tree_path'] = bids_file
                    print(f"DEBUG: Set _tree_path fallback for BIDS file: {bids_file}")
            else:
                consolidated_item[path_key] = bids_file
                
            # Always preserve the original BIDS file array for display purposes in the template
            consolidated_item['BIDS File'] = original_bids_file
            
            # Consolidate BIDS Size - use first non-null value or sum if multiple valid sizes
            bids_sizes = consolidated_item['bids_sizes']
            valid_bids_sizes = [size for size in bids_sizes if size is not None]
            if valid_bids_sizes:
                # Use the first valid BIDS size (since split files should have same BIDS target)
                consolidated_item['BIDS Size'] = valid_bids_sizes[0]
            
            # Consolidate Source Size - sum all source sizes
            source_sizes = consolidated_item['source_sizes']
            valid_source_sizes = [size for size in source_sizes if size is not None]
            if valid_source_sizes:
                consolidated_item['Source Size'] = sum(valid_source_sizes)
            
            # Set up name field for consolidation display
            split_files = [s for s in consolidated_item['split_info'] if s is not None]
            if len(consolidated_item['source_files']) > 1:
                # Multiple files - create list representation for split display
                consolidated_item[name_key] = consolidated_item['source_files']
            else:
                # Single file - use the source file name
                consolidated_item[name_key] = first_source
            
            file_data.append(consolidated_item)
    
        print(f"DEBUG: After consolidation, have {len(file_data)} file data entries")
        if file_data:
            print(f"DEBUG: First consolidated entry path_key ({path_key}): {file_data[0].get(path_key, 'NOT_FOUND')}")
    
    # Determine what to strip from paths based on project_root or find common prefix
    path_prefix_to_strip = ""
    
    if project_root:
        # If project_root is provided, use it as the prefix to strip
        path_prefix_to_strip = project_root.rstrip('/') + '/'
    else:
        # Fall back to common prefix calculation
        all_paths = []
        for item in file_data:
            if isinstance(item, dict):
                print(f"DEBUG: Processing item with path_key='{path_key}', has _tree_path={'_tree_path' in item}")
                # For BIDS File path_key, use the internal tree path we constructed
                if path_key == 'BIDS File' and '_tree_path' in item:
                    file_path = item['_tree_path']
                    print(f"DEBUG: Using _tree_path for BIDS: {file_path}")
                else:
                    file_path = item.get(path_key, '')
                    print(f"DEBUG: Using regular path for {path_key}: {file_path}")
                if file_path:
                    # Handle both string paths and lists of paths
                    if isinstance(file_path, list):
                        for path in file_path:
                            if isinstance(path, str):
                                all_paths.append(path.replace('\\', '/'))
                    elif isinstance(file_path, str):
                        all_paths.append(file_path.replace('\\', '/'))
        
        if not all_paths:
            return []
        
        # Find common prefix (deepest common directory)
        if len(all_paths) > 1:
            # Find the common prefix across all paths
            min_path = min(all_paths)
            max_path = max(all_paths)
            
            common_prefix = ''
            for i in range(min(len(min_path), len(max_path))):
                if min_path[i] == max_path[i]:
                    common_prefix += min_path[i]
                else:
                    break
            
            # Trim to last complete directory
            if '/' in common_prefix:
                path_prefix_to_strip = '/'.join(common_prefix.split('/')[:-1]) + '/'
    
    # Group files by directory
    dir_structure = {}
    
    for item in file_data:
        if isinstance(item, dict):
            # For BIDS File path_key, use the internal tree path we constructed
            if path_key == 'BIDS File' and '_tree_path' in item:
                file_paths = item['_tree_path']
            else:
                file_paths = item.get(path_key, '')
            if file_paths:
                # Handle both string paths and lists of paths (consolidate split files)
                if isinstance(file_paths, list):
                    # For split files, use the first path as the representative path
                    # The full list information is preserved in the item itself
                    paths_to_process = [file_paths[0]]  # Only process the first path
                elif isinstance(file_paths, str):
                    paths_to_process = [file_paths]
                else:
                    paths_to_process = []
                
                # Process the representative path (first path for split files)
                for file_path in paths_to_process:
                    if not isinstance(file_path, str):
                        continue
                        
                    # Normalize path
                    file_path = file_path.replace('\\', '/')
                    
                    # Strip prefix to start tree at project root
                    if path_prefix_to_strip and file_path.startswith(path_prefix_to_strip):
                        file_path = file_path[len(path_prefix_to_strip):]
                    # Also handle absolute paths by converting them to relative paths
                    elif file_path.startswith('/') and project_root:
                        # Convert absolute path to relative path from current working directory
                        import os
                        try:
                            rel_path = os.path.relpath(file_path)
                            if rel_path.startswith(project_root):
                                file_path = rel_path[len(project_root):].lstrip('/')
                        except ValueError:
                            pass
                    
                    # Skip empty paths after prefix stripping
                    if not file_path:
                        continue
                    
                    # Split path into directory parts
                    parts = file_path.split('/')
                    current_level = dir_structure
                    
                    # Build nested directory structure and add file
                    file_item = item.copy()
                    
                    # Strip project root from New file(s) field for Copy results
                    if path_prefix_to_strip and 'New file(s)' in file_item:
                        new_files = file_item['New file(s)']
                        if isinstance(new_files, list):
                            # Strip project root from each file in the list
                            stripped_files = []
                            for f in new_files:
                                if isinstance(f, str) and f.startswith(path_prefix_to_strip):
                                    stripped_files.append(f[len(path_prefix_to_strip):])
                                else:
                                    stripped_files.append(f)
                            file_item['New file(s)'] = stripped_files
                        elif isinstance(new_files, str) and new_files.startswith(path_prefix_to_strip):
                            file_item['New file(s)'] = new_files[len(path_prefix_to_strip):]
                    
                    if len(parts) == 1:
                        # Root level file
                        if '__root__' not in dir_structure:
                            dir_structure['__root__'] = {'__files__': [], '__subdirs__': {}}
                        dir_structure['__root__']['__files__'].append(file_item)
                    else:
                        # Create directory structure
                        current_level = dir_structure
                        # Navigate through all directory parts except the filename
                        for part in parts[:-1]:
                            if part not in current_level:
                                current_level[part] = {'__files__': [], '__subdirs__': {}}
                            current_level = current_level[part]['__subdirs__']
                        
                        # The final directory where the file belongs
                        final_dir = parts[-2]  # Parent directory of the file
                        # Go back one level to add the file to the correct directory
                        parent_level = dir_structure
                        for part in parts[:-2]:
                            parent_level = parent_level[part]['__subdirs__']
                        
                        # Add file to the final directory
                        parent_level[final_dir]['__files__'].append(file_item)
    
    # Calculate folder sizes by summing file sizes recursively
    def calculate_folder_sizes(struct):
        """Calculate total size for each folder by summing its contents."""
        sizes = {}
        
        def get_size_for_directory(dir_data, path):
            total_size = 0
            file_count = 0
            
            # Add sizes of files in this directory
            for file_item in dir_data.get('__files__', []):
                file_count += 1
                
                # Try to get file size from various possible fields
                size = 0
                if 'Total Destination Size' in file_item:
                    size = file_item['Total Destination Size'] or 0
                elif 'BIDS Size' in file_item:
                    size = file_item['BIDS Size'] or 0
                elif 'Destination Size(s)' in file_item:
                    dest_size = file_item['Destination Size(s)']
                    if isinstance(dest_size, list):
                        size = sum(s for s in dest_size if isinstance(s, (int, float)))
                    elif isinstance(dest_size, (int, float)):
                        size = dest_size
                elif 'Original Size' in file_item:
                    size = file_item['Original Size'] or 0
                elif 'Source Size' in file_item:
                    size = file_item['Source Size'] or 0
                
                total_size += size
            
            # Add sizes of subdirectories
            for subdir_name, subdir_data in dir_data.get('__subdirs__', {}).items():
                subdir_path = f"{path}/{subdir_name}" if path else subdir_name
                subdir_size, subdir_count = get_size_for_directory(subdir_data, subdir_path)
                total_size += subdir_size
                file_count += subdir_count
                sizes[subdir_path] = {'size': subdir_size, 'file_count': subdir_count}
            
            return total_size, file_count
        
        # Calculate for all directories
        for dir_name, dir_data in struct.items():
            if dir_name != '__root__':
                total_size, total_files = get_size_for_directory(dir_data, dir_name)
                sizes[dir_name] = {'size': total_size, 'file_count': total_files}
        
        # Handle root files
        if '__root__' in struct:
            root_size, root_files = get_size_for_directory(struct['__root__'], '')
            sizes['__root__'] = {'size': root_size, 'file_count': root_files}
        
        return sizes
    
    folder_sizes = calculate_folder_sizes(dir_structure)
    
    # Convert to hierarchical list
    def build_tree_items(struct, current_path='', level=0):
        items = []
        
        # Add directories first
        for dir_name, dir_data in struct.items():
            if dir_name not in ['__files__', '__root__']:
                dir_path = f"{current_path}/{dir_name}" if current_path else dir_name
                
                # Get folder size and file count
                folder_info = folder_sizes.get(dir_path, {'size': 0, 'file_count': 0})
                
                items.append({
                    'type': 'dir',
                    'name': dir_name,
                    'path': dir_path,
                    'parent': current_path,
                    'level': level,
                    'file_count': folder_info['file_count'],
                    'folder_size': folder_info['size'],
                    'is_directory': True
                })
                
                # Add subdirectories recursively
                items.extend(build_tree_items(dir_data['__subdirs__'], dir_path, level + 1))
                
                # Add files in this directory
                for file_item in dir_data.get('__files__', []):
                    file_name = file_item.get(name_key, file_item.get('name', 'Unknown'))
                    items.append({
                        'type': 'file',
                        'name': file_name,
                        'path': file_item.get(path_key, ''),
                        'parent': dir_path,
                        'level': level + 1,
                        'original_data': file_item,
                        'is_directory': False
                    })
        
        return items
    
    return build_tree_items(dir_structure)

def enrich_bids_with_status(bids_results, bids_conversion):
    """Enrich BIDS results with status information from bids_conversion table."""
    if not bids_results or bids_conversion is None or bids_conversion.empty:
        return bids_results
    
    enriched_results = []
    for result in bids_results:
        enriched_result = result.copy()
        
        # Try to match based on BIDS File path
        bids_file = result.get('BIDS File', '')
        if bids_file:
            # Extract key components for matching
            bids_name = bids_file.split('/')[-1] if '/' in bids_file else bids_file
            
            # Look for matching entry in bids_conversion table
            for _, row in bids_conversion.iterrows():
                if row['bids_name'] == bids_name:
                    enriched_result['conversion_status'] = row['status']
                    break
            else:
                # No match found, set default status
                enriched_result['conversion_status'] = 'unknown'
        else:
            enriched_result['conversion_status'] = 'unknown'
            
        enriched_results.append(enriched_result)
    
    return enriched_results

def generate_pipeline_summary(pipeline_data):
    """Generate summary statistics for pipeline overview."""
    copy_results = pipeline_data['copy_results']
    bids_results = pipeline_data['bids_results']
    bids_conversion = pipeline_data['bids_conversion']
    
    # Copy stage stats
    total_copied = len(copy_results)
    successful_copies = len([r for r in copy_results if r.get('Transfer status') == 'Success'])
    failed_copies = total_copied - successful_copies
    
    # Count split files
    split_files = len([r for r in copy_results if isinstance(r.get('New file(s)'), list)])
    single_files = total_copied - split_files
    
    # Calculate copy stage total sizes
    total_original_size = 0
    total_destination_size = 0
    for r in copy_results:
        if r.get('Original Size'):
            total_original_size += r['Original Size']
        if r.get('Total Destination Size'):
            total_destination_size += r['Total Destination Size']
    
    # BIDS stage stats  
    total_bids = len(bids_results) if bids_results else 0
    successful_bids = len([r for r in bids_results if r.get('Conversion Status') == 'Success']) if bids_results else 0
    
    # Calculate BIDS stage total sizes
    total_source_size = 0
    total_bids_size = 0
    if bids_results:
        for r in bids_results:
            if r.get('Source Size'):
                total_source_size += r['Source Size']
            if r.get('BIDS Size'):
                total_bids_size += r['BIDS Size']
    
    # Conversion table stats
    if bids_conversion is not None and not bids_conversion.empty:
        processed_files = len(bids_conversion[bids_conversion['run_conversion'] == 'no'])
        pending_files = len(bids_conversion[bids_conversion['run_conversion'] == 'yes'])
        participants = bids_conversion['participant_to'].nunique()
        sessions = bids_conversion['session_to'].nunique()
    else:
        processed_files = pending_files = participants = sessions = 0
    
    return {
        'copy_stage': {
            'total': total_copied,
            'successful': successful_copies,
            'failed': failed_copies,
            'split_files': split_files,
            'single_files': single_files,
            'total_original_size': total_original_size,
            'total_destination_size': total_destination_size
        },
        'bids_stage': {
            'total': total_bids,
            'successful': successful_bids,
            'processed_files': processed_files,
            'pending_files': pending_files,
            'participants': participants,
            'sessions': sessions,
            'total_source_size': total_source_size,
            'total_bids_size': total_bids_size
        }
    }

def generate_dashboard_report(data, title="Pipeline Dashboard", output_file="pipeline_dashboard.html", remote_tree=None, pipeline_data=None, project_root=None):
    """Generate comprehensive pipeline dashboard with multiple tabs."""
    from datetime import datetime
    import json as json_module
    
    # Environment setup
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [script_dir, os.getcwd()]
    env = Environment(loader=FileSystemLoader(search_paths))

    # Filters
    def datetime_format(timestamp, fmt='%Y-%m-%d %H:%M:%S'):
        if timestamp:
            return datetime.fromtimestamp(timestamp).strftime(fmt)
        return ''
    env.filters['strftime'] = datetime_format

    def human_bytes(num, suffix='B'):
        try:
            num = float(num)
        except Exception:
            return ''
        for unit in ['','K','M','G','T','P','E','Z']:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Y{suffix}"
    env.filters['filesize'] = human_bytes

    def tojson(obj):
        return json_module.dumps(obj)
    env.filters['tojson'] = tojson
    
    def basename_filter(path):
        if isinstance(path, list):
            # For arrays, return the basename of the first item
            return basename(path[0]) if path and path[0] else ''
        return basename(path) if path else ''
    env.filters['basename'] = basename_filter
    
    def truncate_filter(text, length=60):
        return text[:length] + '...' if len(text) > length else text
    env.filters['truncate'] = truncate_filter
    
    def strip_split_suffix(filename):
        """Strip split file suffix like -1, -2, etc. from filename."""
        import re
        if not filename:
            return filename
        
        if isinstance(filename, list):
            # For arrays, process the first item
            first_filename = filename[0] if filename else ''
            if not first_filename:
                return ''
            # Pattern matches -1, -2, etc. before .extension
            return re.sub(r'-\d+(\.[^.]*)?$', r'\1', first_filename)
        
        # Pattern matches -1, -2, etc. before .extension
        # e.g., "PhalangesOPM_raw-1.fif" -> "PhalangesOPM_raw.fif"
        return re.sub(r'-\d+(\.[^.]*)?$', r'\1', filename)
    env.filters['strip_split_suffix'] = strip_split_suffix

    if remote_tree is None:
        remote_tree = {}

    # Generate sync data (existing functionality)
    local_flat = _flatten_files(data)
    remote_flat = _flatten_files(remote_tree)
    local_hierarchy = create_hierarchical_list(data)
    remote_hierarchy = create_hierarchical_list(remote_tree)
    
    # Create dictionaries for quick lookup
    local_items = {item.get('path') or item.get('relpath'): item for item in local_hierarchy}
    remote_items = {item.get('path') or item.get('relpath'): item for item in remote_hierarchy}
    
    # Get all paths in the order they appear in local hierarchy (preserve ordering)
    all_paths = []
    path_set = set()
    
    for item in local_hierarchy:
        path = item.get('path') or item.get('relpath')
        if path not in path_set:
            all_paths.append(path)
            path_set.add(path)
    
    for item in remote_hierarchy:
        path = item.get('path') or item.get('relpath')
        if path not in path_set:
            all_paths.append(path)
            path_set.add(path)
    
    # Convert to rows for sync tab
    sync_rows = []
    for path in all_paths:
        local_item = local_items.get(path)
        remote_item = remote_items.get(path)
        
        if not local_item and not remote_item:
            continue
            
        item_type = (local_item or remote_item)['type']
        name = (local_item or remote_item)['name']
        level = (local_item or remote_item)['level']
        parent = (local_item or remote_item).get('folder_path', '')
        
        # Convert 'folder' to 'dir' for consistency with CSS classes
        display_type = 'dir' if item_type == 'folder' else 'file'
        
        if item_type == 'folder':
            if local_item and remote_item:
                status = 'ok'
                if local_item.get('size', 0) != remote_item.get('size', 0):
                    status = 'issue'
            elif local_item and not remote_item:
                status = 'missing_remote'
            elif remote_item and not local_item:
                status = 'missing_local'
            else:
                status = 'ok'
        else:
            if local_item and remote_item:
                status = 'size_mismatch' if local_item.get('size', 0) != remote_item.get('size', 0) else 'ok'
            elif local_item and not remote_item:
                status = 'missing_remote'
            elif remote_item and not local_item:
                status = 'missing_local'
            else:
                status = 'ok'
        
        sync_rows.append({
            'type': display_type,
            'relpath': path,
            'name': name,
            'parent': parent,
            'level': level,
            'local_size': local_item.get('size') if local_item else None,
            'remote_size': remote_item.get('size') if remote_item else None,
            'local_mtime': local_item.get('mtime') if local_item else None,
            'remote_mtime': remote_item.get('mtime') if remote_item else None,
            'local_exists': local_item is not None,
            'remote_exists': remote_item is not None,
            'status': status
        })

    # Generate pipeline summary
    pipeline_summary = None
    copy_tree_rows = []
    bids_tree_rows = []
    
    if pipeline_data:
        pipeline_summary = generate_pipeline_summary(pipeline_data)
        
        # Create tree structure for copy results (use Raw destination paths to define tree, show Original paths as content)
        if pipeline_data.get('copy_results'):
            copy_tree_items = create_tree_from_paths(pipeline_data['copy_results'], 'New file(s)', 'Original File', project_root)
            copy_tree_rows = copy_tree_items

        # Create tree structure for BIDS results (use BIDS destination paths to define tree, show Source paths as content)
        if pipeline_data.get('bids_results'):
            # Enrich BIDS results with status information from bids_conversion table
            enriched_bids_results = enrich_bids_with_status(pipeline_data['bids_results'], pipeline_data.get('bids_conversion'))
            bids_tree_items = create_tree_from_paths(enriched_bids_results, 'BIDS File', 'Source File', project_root)
            bids_tree_rows = bids_tree_items

    # Enhanced multi-tab dashboard template
    dashboard_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem 0;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .header h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
        .header p { font-size: 1.1rem; opacity: 0.9; }
        
        .container { width: 100%; margin: 0 auto; padding: 0 1rem; }
        
        .tabs {
            background: white;
            margin: 2rem auto;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        
        .tab-nav {
            display: flex;
            background: #f8f9fa;
            border-bottom: 1px solid #dee2e6;
        }
        
        .tab-button {
            flex: 1;
            padding: 1rem 2rem;
            border: none;
            background: none;
            cursor: pointer;
            font-size: 1rem;
            font-weight: 500;
            color: #6c757d;
            transition: all 0.3s ease;
            border-bottom: 3px solid transparent;
        }
        
        .tab-button:hover {
            background: #e9ecef;
            color: #495057;
        }
        
        .tab-button.active {
            color: #667eea;
            border-bottom-color: #667eea;
            background: white;
        }
        
        .tab-content {
            display: none;
            padding: 2rem;
            min-height: 500px;
        }
        
        .tab-content.active { display: block; }
        
        /* Summary Cards */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .summary-card {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }
        
        .summary-card h3 {
            color: #667eea;
            margin-bottom: 1rem;
            font-size: 1.2rem;
        }
        
        .stat-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
            padding: 0.25rem 0;
        }
        
        .stat-label { color: #6c757d; }
        .stat-value { font-weight: 600; }
        
        .success { color: #28a745; }
        .warning { color: #ffc107; }
        .danger { color: #dc3545; }
        
        /* Tables */
        .data-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .data-table th {
            background: #f8f9fa;
            padding: 1rem 0.75rem;
            font-weight: 600;
            text-align: left;
            border-bottom: 1px solid #dee2e6;
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        .data-table td {
            padding: 0.75rem;
            border-bottom: 1px solid #f1f3f4;
            font-size: 0.9rem;
        }
        
        .data-table tr:hover {
            background: #f8f9fa;
        }
        
        /* Smaller font size for file names in tree */
        .data-table tbody tr:not(.dir) td:first-child {
            font-size: 0.8rem;
        }
        
        /* Pipeline specific styles */
        .pipeline-flow {
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 2rem 0;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .flow-step {
            background: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
            min-width: 120px;
        }
        
        .flow-arrow {
            font-size: 1.5rem;
            color: #667eea;
            margin: 0 0.5rem;
        }
        
        .toolbar {
            margin-bottom: 1rem;
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .filter-select {
            padding: 0.5rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 0.9rem;
        }
        
        /* Status badges */
        .status-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
        }
        
        .status-ok { background: #d4edda; color: #155724; }
        .status-warning { background: #fff3cd; color: #856404; }
        .status-error { background: #f8d7da; color: #721c24; }
        
        /* Responsive */
        @media (max-width: 768px) {
            .tab-nav { flex-direction: column; }
            .tab-button { text-align: left; }
            .summary-grid { grid-template-columns: 1fr; }
            .pipeline-flow { flex-direction: column; }
            .flow-arrow { transform: rotate(90deg); }
        }
        
        .indent{display:inline-block;}
        .size{white-space:nowrap;}
        .date{white-space:nowrap;font-size:11px;}
        .dim{color:#888;}
        /* Tree structure styles */
        tr.dir{background:#f0f4ff; cursor: pointer;}
        tbody tr.dir.status-ok{background:#e8f5e8;}
        tbody tr.status-missing_remote{background:#ffe5e5;}
        tbody tr.status-size_mismatch{background:#fff4d6;}
        tbody tr.status-issue{background:#e6f3ff;}
        
        .tree-icon {
            display: inline-block;
            width: 12px;
            text-align: center;
            margin-right: 4px;
            font-size: 10px;
            color: #666;
            transition: transform 0.2s ease;
        }
        
        .tree-icon.expanded {
            transform: rotate(90deg);
        }
        
        tr.dir:hover {
            background-color: rgba(102, 126, 234, 0.1);
        }
        
        .tree-line {
            display: inline-block;
            width: 14px;
            height: 20px;
            vertical-align: middle;
            margin-right: 2px;
        }
        
        .tree-line::before {
            content: '';
            display: block;
            width: 1px;
            height: 100%;
            background: #ccc;
            margin-left: 7px;
        }
        
        .tree-line.last::before {
            height: 50%;
        }
        
        .tree-line.branch::after {
            content: '';
            display: block;
            width: 7px;
            height: 1px;
            background: #ccc;
            margin-top: -10px;
            margin-left: 7px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>{{ title }}</h1>
            <p>MEG/EEG Data Processing Pipeline Dashboard</p>
        </div>
    </div>
    
    <div class="container">
        <div class="tabs">
            <div class="tab-nav">
                <button class="tab-button active" onclick="showTab('overview')">📊 Overview</button>
                <button class="tab-button" onclick="showTab('copy')">📁 Original → Raw</button>
                <button class="tab-button" onclick="showTab('bids')">🔄 Raw → BIDS</button>
                <button class="tab-button" onclick="showTab('sync')">☁️ Local ↔ Server</button>
            </div>
            
            <!-- Overview Tab -->
            <div id="overview" class="tab-content active">
                <h2>Pipeline Summary</h2>
                
                <div class="pipeline-flow">
                    <div class="flow-step">
                        <div><strong>Original Data</strong></div>
                        <div>Source Files</div>
                    </div>
                    <div class="flow-arrow">→</div>
                    <div class="flow-step">
                        <div><strong>Raw Copy</strong></div>
                        <div>Local Processing</div>
                    </div>
                    <div class="flow-arrow">→</div>
                    <div class="flow-step">
                        <div><strong>BIDS Format</strong></div>
                        <div>Standardized</div>
                    </div>
                    <div class="flow-arrow">→</div>
                    <div class="flow-step">
                        <div><strong>Server Sync</strong></div>
                        <div>Backup & Share</div>
                    </div>
                </div>
                
                {% if pipeline_summary %}
                <div class="summary-grid">
                    <div class="summary-card">
                        <h3>📁 Copy Stage (Original → Raw)</h3>
                        <div class="stat-row">
                            <span class="stat-label">Total Files:</span>
                            <span class="stat-value">{{ pipeline_summary.copy_stage.total }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Successful:</span>
                            <span class="stat-value success">{{ pipeline_summary.copy_stage.successful }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Failed:</span>
                            <span class="stat-value {% if pipeline_summary.copy_stage.failed > 0 %}danger{% else %}success{% endif %}">{{ pipeline_summary.copy_stage.failed }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Split Files:</span>
                            <span class="stat-value">{{ pipeline_summary.copy_stage.split_files }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Original Size:</span>
                            <span class="stat-value">{{ pipeline_summary.copy_stage.total_original_size | filesize }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Copied Size:</span>
                            <span class="stat-value">{{ pipeline_summary.copy_stage.total_destination_size | filesize }}</span>
                        </div>
                    </div>
                    
                    <div class="summary-card">
                        <h3>🔄 BIDS Stage (Raw → BIDS)</h3>
                        <div class="stat-row">
                            <span class="stat-label">Processed Files:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.processed_files }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Pending Files:</span>
                            <span class="stat-value {% if pipeline_summary.bids_stage.pending_files > 0 %}warning{% else %}success{% endif %}">{{ pipeline_summary.bids_stage.pending_files }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Participants:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.participants }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Sessions:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.sessions }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Source Size:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.total_source_size | filesize }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">BIDS Size:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.total_bids_size | filesize }}</span>
                        </div>
                    </div>
                </div>
                {% endif %}
            </div>
            
            <!-- Copy Stage Tab -->
            <div id="copy" class="tab-content">
                <h2>📁 Original → Raw Copy Operations</h2>
                
                {% if copy_tree_rows %}
                <div class="summary-grid" style="margin-bottom: 1rem;">
                    <div class="summary-card" style="grid-column: span 2;">
                        <h3>📂 Copy Operations Tree</h3>
                        <div class="stat-row">
                            <span class="stat-label">Total Items:</span>
                            <span class="stat-value">{{ copy_tree_rows|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Directories:</span>
                            <span class="stat-value">{{ copy_tree_rows|selectattr("type", "equalto", "dir")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Files:</span>
                            <span class="stat-value">{{ copy_tree_rows|selectattr("type", "equalto", "file")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Total Size:</span>
                            <span class="stat-value">{{ pipeline_summary.copy_stage.total_destination_size | filesize }}</span>
                        </div>
                    </div>
                </div>
                
                <div class="toolbar">
                    <label>Search:</label>
                    <input type="text" class="filter-select" id="copySearchFilter" placeholder="Search..." onkeyup="filterCopyTable()" style="width: 200px;">
                    <label style="margin-left: 15px;">Status:</label>
                    <select class="filter-select" id="copyMessageFilter" onchange="filterCopyTable()">
                        <option value="">All Status</option>
                    </select>
                    <button onclick="expandAllCopy()" class="filter-select" style="margin-left: 10px;">Expand All</button>
                    <button onclick="collapseAllCopy()" class="filter-select">Collapse All</button>
                </div>
                
                <table class="data-table" id="copyTable">
                    <thead>
                        <tr>
                            <th>Raw (as tree)</th>
                            <th>Original</th>
                            <th>Raw size</th>
                            <th>Original size</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in copy_tree_rows %}
                        <tr class='{{ row.type }}' 
                            data-path='{{ row.path }}' 
                            data-parent='{{ row.parent }}' 
                            data-level='{{ row.level }}' 
                            data-message='{% if row.original_data %}{{ row.original_data.get("status", "") }}{% endif %}'
                            {% if row.type=='dir' %}onclick="toggleCopy('{{ row.path }}')"{% endif %}>
                            <td>
                                <span class='indent' style='width: {{ row.level * 14 }}px'></span>
                                {% if row.type == 'dir' %}
                                    <span class="tree-icon">▶</span>📁 {{ row.name }}
                                    {% if row.file_count %}<span class="dim"> ({{ row.file_count }} files)</span>{% endif %}
                                {% else %}
                                    <span style='width: 16px; display: inline-block;'></span>
                                    {% if row.original_data and row.original_data['New file(s)'] %}
                                        {% if row.original_data['New file(s)'] is sequence and row.original_data['New file(s)'] is not string %}
                                            {{ row.original_data['New file(s)'][0] | basename }}
                                        {% else %}
                                            {{ row.original_data['New file(s)'] | basename }}
                                        {% endif %}
                                    {% else %}
                                        {{ row.name }}
                                    {% endif %}
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    <code style="font-size: 0.85em;">{{ entry['Original File'] }}</code>
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% if entry.get('Destination Size(s)') %}
                                        {% if entry['Destination Size(s)'] is sequence and entry['Destination Size(s)'] is not string %}
                                            {{ entry['Total Destination Size'] | filesize }}
                                        {% else %}
                                            {{ entry['Destination Size(s)'] | filesize }}
                                        {% endif %}
                                    {% else %}
                                        <span class="dim">—</span>
                                    {% endif %}
                                {% elif row.type == 'dir' and row.folder_size %}
                                    {{ row.folder_size | filesize }}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% if entry.get('Original Size') %}
                                        {{ entry['Original Size'] | filesize }}
                                    {% else %}
                                        <span class="dim">—</span>
                                    {% endif %}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {{ entry['Copy Date'] }}-{{ entry['Copy Time'] }}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% elif pipeline_data and pipeline_data.copy_results %}
                <div class="alert">
                    <p>Copy results available but tree structure could not be generated. Showing raw data count: {{ pipeline_data.copy_results|length }}</p>
                </div>
                {% else %}
                <div class="alert">
                    <p>No copy results found. Run copy_to_cerberos.py to generate copy operations data.</p>
                </div>
                {% endif %}
            </div>
            
            <!-- BIDS Stage Tab -->
            <div id="bids" class="tab-content">
                <h2>🔄 Raw → BIDS Conversion</h2>
                
                {% if bids_tree_rows %}
                <div class="summary-grid" style="margin-bottom: 1rem;">
                    <div class="summary-card" style="grid-column: span 2;">
                        <h3>🔄 BIDS Operations Tree</h3>
                        <div class="stat-row">
                            <span class="stat-label">Total Items:</span>
                            <span class="stat-value">{{ bids_tree_rows|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Directories:</span>
                            <span class="stat-value">{{ bids_tree_rows|selectattr("type", "equalto", "dir")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Files:</span>
                            <span class="stat-value">{{ bids_tree_rows|selectattr("type", "equalto", "file")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Total BIDS Size:</span>
                            <span class="stat-value">{{ pipeline_summary.bids_stage.total_bids_size | filesize }}</span>
                        </div>
                    </div>
                </div>
                
                <div class="toolbar">
                    <label>Search:</label>
                    <input type="text" class="filter-select" id="bidsSearchInput" 
                           placeholder="Search..." 
                           onkeyup="filterBidsTable()" style="width: 300px;">
                    <label style="margin-left: 15px;">Status:</label>
                    <select class="filter-select" id="bidsStatusFilter" onchange="filterBidsTable()">
                        <option value="">All Status</option>
                    </select>
                    <button onclick="expandAllBids()" class="filter-select" style="margin-left: 10px;">Expand All</button>
                    <button onclick="collapseAllBids()" class="filter-select">Collapse All</button>
                </div>
                
                <table class="data-table" id="bidsTable">
                    <thead>
                        <tr>
                            <th>BIDS (as tree)</th>
                            <th>Task</th>
                            <th>Status</th>
                            <th>Raw</th>
                            <th>BIDS Size</th>
                            <th>Raw Size</th>
                            <th>Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in bids_tree_rows %}
                        <tr class='{{ row.type }}' 
                            data-path='{{ row.path }}' 
                            data-parent='{{ row.parent }}' 
                            data-level='{{ row.level }}' 
                            data-status='{% if row.original_data %}{{ row.original_data.get("conversion_status", "") }}{% endif %}'
                            data-subject='{% if row.original_data %}{{ row.original_data.get("Participant", "") }}{% endif %}'
                            {% if row.type=='dir' %}onclick="toggleBids('{{ row.path }}')"{% endif %}>
                            <td>
                                <span class='indent' style='width: {{ row.level * 14 }}px'></span>
                                {% if row.type == 'dir' %}
                                    <span class="tree-icon">▶</span>📁 {{ row.name }}
                                    {% if row.file_count %}<span class="dim"> ({{ row.file_count }} files)</span>{% endif %}
                                {% else %}
                                    <span style='width: 16px; display: inline-block;'></span>
                                    {% if row.original_data and row.original_data.get('BIDS File') %}
                                        {% set bids_files = row.original_data['BIDS File'] %}
                                        {% if bids_files is iterable and bids_files is not string %}
                                            <div style="line-height: 1.4;">
                                            {% for bids_file in bids_files %}
                                                <code style="font-size: 0.85em; display: block; margin: 1px 0;">{{ bids_file | basename }}</code>
                                            {% endfor %}
                                            </div>
                                        {% else %}
                                            {{ bids_files | basename }}
                                        {% endif %}
                                    {% else %}
                                        {{ row.name }}
                                    {% endif %}
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {{ entry.get('Task', '') }}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% set status = entry.get('conversion_status', '') %}
                                    <span class="status-badge {% if status == 'processed' %}status-ok{% elif status == 'skip' %}status-warning{% elif status == 'failed' %}status-error{% else %}status-warning{% endif %}">
                                        {{ status.title() if status else '—' }}
                                    </span>
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% if row.name is iterable and row.name is not string %}
                                        <code style="font-size: 0.85em;">{{ row.name[0] | basename }}</code>
                                    {% else %}
                                        <code style="font-size: 0.85em;">{{ entry.get('Source File', '') | basename | strip_split_suffix }}</code>
                                    {% endif %}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% if entry.get('BIDS Size') %}
                                        {{ entry['BIDS Size'] | filesize }}
                                    {% else %}
                                        <span class="dim">—</span>
                                    {% endif %}
                                {% elif row.type == 'dir' and row.folder_size %}
                                    {{ row.folder_size | filesize }}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {% if entry.get('Source Size') %}
                                        {{ entry['Source Size'] | filesize }}
                                    {% else %}
                                        <span class="dim">—</span>
                                    {% endif %}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if row.type == 'file' and row.original_data %}
                                    {% set entry = row.original_data %}
                                    {{ entry.get('Processing Date', '') }}
                                {% else %}
                                    <span class="dim">—</span>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% elif pipeline_data and pipeline_data.bids_conversion is not none and not pipeline_data.bids_results %}
                <div class="toolbar">
                    <label>Filter by status:</label>
                    <select class="filter-select" id="bidsStatusFilter" onchange="filterBidsTable()">
                        <option value="">All</option>
                        <option value="no">Processed</option>
                        <option value="yes">Pending</option>
                    </select>
                </div>
                
                <table class="data-table" id="bidsTable">
                    <thead>
                        <tr>
                            <th>Participant</th>
                            <th>Session</th>
                            <th>Task</th>
                            <th>Acquisition</th>
                            <th>Datatype</th>
                            <th>Processing</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for _, row in pipeline_data.bids_conversion.iterrows() %}
                        <tr data-conversion-status="{{ row['run_conversion'] }}">
                            <td>{{ row['participant_to'] }}</td>
                            <td>{{ row['session_to'] }}</td>
                            <td>{{ row['task'] }}</td>
                            <td>{{ row['acquisition'] }}</td>
                            <td>{{ row['datatype'] }}</td>
                            <td>{{ row['processing'] or '-' }}</td>
                            <td>
                                <span class="status-badge {% if row['run_conversion'] == 'no' %}status-ok{% else %}status-warning{% endif %}">
                                    {% if row['run_conversion'] == 'no' %}Processed{% else %}Pending{% endif %}
                                </span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <div class="alert">
                    <p>No BIDS conversion data found. Run bidsify.py to generate BIDS conversion data.</p>
                </div>
                {% endif %}
            </div>
            
            <!-- Sync Tab -->
            <div id="sync" class="tab-content">
                <h2>☁️ Local ↔ Server Synchronization</h2>
                
                <div class="summary-grid" style="margin-bottom: 1rem;">
                    <div class="summary-card" style="grid-column: span 2;">
                        <h3>🌳 Directory Tree Statistics</h3>
                        <div class="stat-row">
                            <span class="stat-label">Total Items:</span>
                            <span class="stat-value">{{ sync_rows|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Directories:</span>
                            <span class="stat-value">{{ sync_rows|selectattr("type", "equalto", "dir")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Files:</span>
                            <span class="stat-value">{{ sync_rows|selectattr("type", "equalto", "file")|list|length }}</span>
                        </div>
                        <div class="stat-row">
                            <span class="stat-label">Sync Issues:</span>
                            <span class="stat-value {% set issues = sync_rows|rejectattr("status", "equalto", "ok")|list|length %}{% if issues > 0 %}danger{% else %}success{% endif %}">{{ issues }}</span>
                        </div>
                    </div>
                </div>
                
                <div class="toolbar">
                    <label>Search:</label>
                    <input type="text" class="filter-select" id="syncSearchInput" 
                           placeholder="Search..." 
                           onkeyup="filterSyncTable()" style="width: 300px;">
                    <label style="margin-left: 15px;">Status:</label>
                    <select class="filter-select" id="syncStatusFilter" onchange="filterSyncTable()">
                        <option value="">All Status</option>
                        <option value="ok">OK</option>
                        <option value="size_mismatch">Size mismatch</option>
                        <option value="missing_remote">Missing remote</option>
                        <option value="missing_local">Missing local</option>
                        <option value="issue">Directory issues</option>
                    </select>
                    <button onclick="expandAll()" class="filter-select" style="margin-left: 10px;">Expand All</button>
                    <button onclick="collapseAll()" class="filter-select">Collapse All</button>
                </div>
                
                <table class="data-table" id="syncTable">
                    <thead>
                        <tr>
                            <th>Local Path</th>
                            <th>Remote Path</th>
                            <th>Local Size</th>
                            <th>Remote Size</th>
                            <th>Local Modified</th>
                            <th>Remote Modified</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for r in sync_rows %}
                        <tr class='{{ r.type }}{% if r.status %} status-{{ r.status }}{% endif %}' 
                            data-path='{{ r.relpath }}' 
                            data-parent='{{ r.parent }}' 
                            data-status='{{ r.status }}' 
                            data-level='{{ r.level }}' 
                            {% if r.type=='dir' %}onclick="toggle('{{ r.relpath }}')"{% endif %}>
                            <td>
                                <span class='indent' style='width: {{ r.level * 14 }}px'></span>
                                {% if r.local_exists %}
                                    {% if r.type=='dir' %}
                                        <span class="tree-icon">▶</span>📁 {{ r.name }}
                                    {% else %}
                                        <span style='width: 16px; display: inline-block;'></span>{{ r.name }}
                                    {% endif %}
                                {% else %}
                                    <span class='dim'>—</span>
                                {% endif %}
                            </td>
                            <td>
                                {% if r.remote_exists %}
                                    {% if r.type=='dir' %}📁 {{ r.name }}{% else %}{{ r.name }}{% endif %}
                                {% else %}
                                    <span class='dim'>—</span>
                                {% endif %}
                            </td>
                            <td class='size'>{% if r.local_size is not none %}{{ r.local_size|filesize }}{% endif %}</td>
                            <td class='size'>{% if r.remote_size is not none %}{{ r.remote_size|filesize }}{% endif %}</td>
                            <td class='date'>{% if r.local_mtime is not none %}{{ r.local_mtime|strftime }}{% endif %}</td>
                            <td class='date'>{% if r.remote_mtime is not none %}{{ r.remote_mtime|strftime }}{% endif %}</td>
                            <td>
                                <span class="status-badge status-{% if r.status == 'ok' %}ok{% elif r.status in ['missing_remote', 'missing_local'] %}error{% else %}warning{% endif %}">
                                    {{ r.status }}
                                </span>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <script>
        function showTab(tabName) {
            // Hide all tab contents
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(content => content.classList.remove('active'));
            
            // Remove active class from all buttons
            const buttons = document.querySelectorAll('.tab-button');
            buttons.forEach(button => button.classList.remove('active'));
            
            // Show selected tab content
            document.getElementById(tabName).classList.add('active');
            
            // Add active class to clicked button
            event.target.classList.add('active');
        }
        
        // Unified filter function for all tables - eliminates code duplication
        function filterTable(config) {
            const {
                tableId,
                searchInputId = null,
                statusFilterId = null,
                messageFilterId = null,
                searchColumns = [0, 1], // Default: filename and first content column
                dataAttributes = [] // Additional data attributes to search
            } = config;
            
            const table = document.getElementById(tableId);
            const searchInput = searchInputId ? document.getElementById(searchInputId) : null;
            const statusFilter = statusFilterId ? document.getElementById(statusFilterId) : null;
            const messageFilter = messageFilterId ? document.getElementById(messageFilterId) : null;
            
            const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
            const statusValue = statusFilter ? statusFilter.value : '';
            const messageValue = messageFilter ? messageFilter.value : '';
            // Unified status value (use either statusFilter or messageFilter)
            const unifiedStatusValue = statusValue || messageValue;
            
            const rows = table.querySelectorAll('tbody tr');
            let visiblePaths = new Set();
            
            rows.forEach(row => {
                const path = row.getAttribute('data-path') || '';
                let shouldShow = true;
                
                if (row.classList.contains('dir')) {
                    // For directories, hide by default when filtering
                    if (searchTerm || unifiedStatusValue) {
                        shouldShow = false;
                    }
                } else {
                    // For files, apply all filters
                    
                    // Search filter
                    if (searchTerm) {
                        let matchFound = false;
                        
                        // Search in specified columns
                        const cells = row.querySelectorAll('td');
                        for (const colIndex of searchColumns) {
                            if (cells.length > colIndex && cells[colIndex].textContent.toLowerCase().includes(searchTerm)) {
                                matchFound = true;
                                break;
                            }
                        }
                        
                        // Search in path/filename
                        if (!matchFound && path.toLowerCase().includes(searchTerm)) {
                            matchFound = true;
                        }
                        
                        // Search in data attributes
                        for (const attr of dataAttributes) {
                            const attrValue = row.getAttribute(attr) || '';
                            if (attrValue.toLowerCase().includes(searchTerm)) {
                                matchFound = true;
                                break;
                            }
                        }
                        
                        if (!matchFound) {
                            shouldShow = false;
                        }
                    }
                    
                    // Unified status filter (handles both data-status and data-message attributes)
                    if (unifiedStatusValue) {
                        const status = row.getAttribute('data-status') || '';
                        const message = row.getAttribute('data-message') || '';
                        if (status !== unifiedStatusValue && message !== unifiedStatusValue) {
                            shouldShow = false;
                        }
                    }
                }
                
                if (shouldShow) {
                    row.style.display = 'table-row';
                    if (!row.classList.contains('dir')) {
                        visiblePaths.add(path);
                    }
                } else {
                    row.style.display = 'none';
                }
            });
            
            // Show parent directories of visible files when filtering
            if ((searchTerm || unifiedStatusValue) && visiblePaths.size > 0) {
                visiblePaths.forEach(path => {
                    const parts = path.split('/');
                    for (let i = 1; i < parts.length; i++) {
                        const parentPath = parts.slice(0, i).join('/');
                        if (parentPath) {
                            const parentRow = table.querySelector(`tr[data-path="${parentPath}"]`);
                            if (parentRow && parentRow.classList.contains('dir')) {
                                parentRow.style.display = 'table-row';
                            }
                        }
                    }
                });
            }
        }

        // Specific filter functions that call the unified function
        function filterCopyTable() {
            filterTable({
                tableId: 'copyTable',
                searchInputId: 'copySearchFilter',
                statusFilterId: 'copyMessageFilter',  // Reusing messageFilterId as statusFilterId for consistency
                searchColumns: [0, 1], // Path and Original File columns
                dataAttributes: ['data-message']  // Contains status information
            });
        }
        
        function filterBidsTable() {
            const searchInputEl = document.getElementById('bidsSearchInput');
            if (searchInputEl) {
                // Tree table with search
                filterTable({
                    tableId: 'bidsTable',
                    searchInputId: 'bidsSearchInput',
                    statusFilterId: 'bidsStatusFilter',
                    searchColumns: [0, 1, 3], // Filename, Task, BIDS path columns
                    dataAttributes: ['data-subject', 'data-status']
                });
            } else {
                // Conversion table fallback
                const filter = document.getElementById('bidsStatusFilter').value;
                const rows = document.querySelectorAll('#bidsTable tbody tr');
                
                rows.forEach(row => {
                    const status = row.getAttribute('data-conversion-status');
                    if (!filter || status === filter) {
                        row.style.display = 'table-row';
                    } else {
                        row.style.display = 'none';
                    }
                });
            }
        }
        
        function filterSyncTable() {
            filterTable({
                tableId: 'syncTable',
                searchInputId: 'syncSearchInput',
                statusFilterId: 'syncStatusFilter',
                searchColumns: [0, 1], // Local Path and Remote Path columns
                dataAttributes: ['data-status']
            });
        }
        
        function toggle(path) {
            const base = document.querySelector(`tr[data-path="${path}"]`);
            const icon = base.querySelector('.tree-icon');
            const rows = document.querySelectorAll('tr[data-parent]');
            let show = null;
            
            for (let i = 0; i < rows.length; i++) {
                const r = rows[i];
                if (r.dataset.parent === path) {
                    if (show === null) {
                        show = r.style.display === 'none';
                    }
                    if (show) {
                        r.style.display = 'table-row';
                    } else {
                        hideBranch(r);
                    }
                }
            }
            
            // Rotate icon to indicate expanded/collapsed state
            if (icon) {
                if (show) {
                    icon.classList.add('expanded');
                } else {
                    icon.classList.remove('expanded');
                }
            }
        }
        
        function hideBranch(row) {
            row.style.display = 'none';
            const id = row.dataset.path;
            const rows = document.querySelectorAll(`tr[data-parent="${id}"]`);
            for (let i = 0; i < rows.length; i++) {
                hideBranch(rows[i]);
            }
        }
        
        function expandAll() {
            const allRows = document.querySelectorAll('#syncTable tbody tr');
            const allIcons = document.querySelectorAll('#syncTable .tree-icon');
            
            allRows.forEach(row => {
                row.style.display = 'table-row';
            });
            
            allIcons.forEach(icon => {
                icon.classList.add('expanded');
            });
        }
        
        function collapseAll() {
            const dirRows = document.querySelectorAll('#syncTable tbody tr.dir');
            const childRows = document.querySelectorAll('#syncTable tbody tr[data-parent]');
            const allIcons = document.querySelectorAll('#syncTable .tree-icon');
            
            // Hide all child rows
            childRows.forEach(row => {
                if (row.dataset.parent && row.dataset.parent !== '') {
                    row.style.display = 'none';
                }
            });
            
            // Reset all icons to collapsed state
            allIcons.forEach(icon => {
                icon.classList.remove('expanded');
            });
        }
        
        // Copy tab tree functions
        function toggleCopy(path) {
            const base = document.querySelector(`#copyTable tr[data-path="${path}"]`);
            const icon = base.querySelector('.tree-icon');
            const rows = document.querySelectorAll('#copyTable tr[data-parent]');
            let show = null;
            
            for (let i = 0; i < rows.length; i++) {
                const r = rows[i];
                if (r.dataset.parent === path) {
                    if (show === null) {
                        show = r.style.display === 'none';
                    }
                    if (show) {
                        r.style.display = 'table-row';
                    } else {
                        hideBranch(r);
                    }
                }
            }
            
            if (icon) {
                if (show) {
                    icon.classList.add('expanded');
                } else {
                    icon.classList.remove('expanded');
                }
            }
        }
        
        function expandAllCopy() {
            const allRows = document.querySelectorAll('#copyTable tbody tr');
            const allIcons = document.querySelectorAll('#copyTable .tree-icon');
            
            allRows.forEach(row => {
                row.style.display = 'table-row';
            });
            
            allIcons.forEach(icon => {
                icon.classList.add('expanded');
            });
        }
        
        function collapseAllCopy() {
            const childRows = document.querySelectorAll('#copyTable tbody tr[data-parent]');
            const allIcons = document.querySelectorAll('#copyTable .tree-icon');
            
            childRows.forEach(row => {
                if (row.dataset.parent && row.dataset.parent !== '') {
                    row.style.display = 'none';
                }
            });
            
            allIcons.forEach(icon => {
                icon.classList.remove('expanded');
            });
        }
        
        // BIDS tab tree functions
        function toggleBids(path) {
            const base = document.querySelector(`#bidsTable tr[data-path="${path}"]`);
            const icon = base.querySelector('.tree-icon');
            const rows = document.querySelectorAll('#bidsTable tr[data-parent]');
            let show = null;
            
            for (let i = 0; i < rows.length; i++) {
                const r = rows[i];
                if (r.dataset.parent === path) {
                    if (show === null) {
                        show = r.style.display === 'none';
                    }
                    if (show) {
                        r.style.display = 'table-row';
                    } else {
                        hideBranch(r);
                    }
                }
            }
            
            if (icon) {
                if (show) {
                    icon.classList.add('expanded');
                } else {
                    icon.classList.remove('expanded');
                }
            }
        }
        
        function expandAllBids() {
            const allRows = document.querySelectorAll('#bidsTable tbody tr');
            const allIcons = document.querySelectorAll('#bidsTable .tree-icon');
            
            allRows.forEach(row => {
                row.style.display = 'table-row';
            });
            
            allIcons.forEach(icon => {
                icon.classList.add('expanded');
            });
        }
        
        function collapseAllBids() {
            const childRows = document.querySelectorAll('#bidsTable tbody tr[data-parent]');
            const allIcons = document.querySelectorAll('#bidsTable .tree-icon');
            
            childRows.forEach(row => {
                if (row.dataset.parent && row.dataset.parent !== '') {
                    row.style.display = 'none';
                }
            });
            
            allIcons.forEach(icon => {
                icon.classList.remove('expanded');
            });
        }
        
        // Populate filter dropdowns with available subjects and tasks
        function populateFilters() {
            // Populate copy table filters
            const copyMessages = new Set();
            const copyRows = document.querySelectorAll('#copyTable tbody tr:not(.dir)');
            copyRows.forEach(row => {
                const message = row.getAttribute('data-message') || '';
                
                if (message) {
                    copyMessages.add(message);
                }
            });
            
            const copyMessageSelect = document.getElementById('copyMessageFilter');
            if (copyMessageSelect) {
                copyMessages.forEach(message => {
                    const option = document.createElement('option');
                    option.value = message;
                    option.textContent = message;
                    copyMessageSelect.appendChild(option);
                });
            }
            
            // Populate BIDS status filter only (search replaces subject/task filters)
            const bidsStatuses = new Set();
            const bidsRows = document.querySelectorAll('#bidsTable tbody tr:not(.dir)');
            bidsRows.forEach(row => {
                const status = row.getAttribute('data-status') || '';
                if (status) {
                    bidsStatuses.add(status);
                }
            });
            
            const bidsStatusSelect = document.getElementById('bidsStatusFilter');
            if (bidsStatusSelect) {
                bidsStatuses.forEach(status => {
                    const option = document.createElement('option');
                    option.value = status;
                    option.textContent = status.charAt(0).toUpperCase() + status.slice(1);
                    bidsStatusSelect.appendChild(option);
                });
            }
        }
        
        // Initialize tree on page load
        document.addEventListener('DOMContentLoaded', function() {
            console.log('Tree view initializing...');
            
            // Count tree items for debugging
            const allRows = document.querySelectorAll('#syncTable tbody tr');
            const dirRows = document.querySelectorAll('#syncTable tbody tr.dir');
            const fileRows = document.querySelectorAll('#syncTable tbody tr[class*="file"]');
            
            console.log(`Total rows: ${allRows.length}, Directories: ${dirRows.length}, Files: ${fileRows.length}`);
            
            // Start collapsed by default - only show top level directories
            const topLevelDirs = document.querySelectorAll('#syncTable tbody tr.dir[data-level="0"]');
            topLevelDirs.forEach(dir => {
                dir.style.display = 'table-row';
            });
            
            // Hide all nested content by default
            const nestedRows = document.querySelectorAll('#syncTable tbody tr[data-parent]');
            nestedRows.forEach(row => {
                if (row.dataset.parent && row.dataset.parent !== '') {
                    row.style.display = 'none';
                }
            });
            
            // Ensure icons start in collapsed state
            const allIcons = document.querySelectorAll('#syncTable .tree-icon');
            allIcons.forEach(icon => {
                icon.classList.remove('expanded');
            });
            
            // Apply same collapsed state to Copy and BIDS tables
            ['#copyTable', '#bidsTable'].forEach(tableSelector => {
                const table = document.querySelector(tableSelector);
                if (table) {
                    // Show only top level directories
                    const topLevelDirs = table.querySelectorAll('tbody tr.dir[data-level="0"]');
                    topLevelDirs.forEach(dir => {
                        dir.style.display = 'table-row';
                    });
                    
                    // Hide all nested content
                    const nestedRows = table.querySelectorAll('tbody tr[data-parent]');
                    nestedRows.forEach(row => {
                        if (row.dataset.parent && row.dataset.parent !== '') {
                            row.style.display = 'none';
                        }
                    });
                    
                    // Collapse all icons
                    const icons = table.querySelectorAll('.tree-icon');
                    icons.forEach(icon => {
                        icon.classList.remove('expanded');
                    });
                }
            });
            
            // Populate filter dropdowns
            populateFilters();
            
            console.log('Tree view initialized (collapsed by default)');
        });
    </script>
</body>
</html>"""


    
    template = env.from_string(dashboard_template)
    html = template.render(
        title=title, 
        sync_rows=sync_rows,
        pipeline_data=pipeline_data,
        pipeline_summary=pipeline_summary,
        copy_tree_rows=copy_tree_rows,
        bids_tree_rows=bids_tree_rows
    )
    
    with open(output_file, 'w') as f:
        f.write(html)
    print(f"Dashboard generated: {output_file}")

def count_directories(tree):
    """Count total directories in the tree."""
    count = 0
    for key, value in tree.items():
        if key != '__files__' and isinstance(value, dict):
            count += 1 + count_directories(value)
    return count

def args_parser():
    parser = argparse.ArgumentParser(description='Generate a report from a nested directory structure.', add_help=True,
                                     usage='render_report [-h] [-c CONFIG]')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args

def main(config: str=None):
    if config is None:
        args = args_parser()
        config_file = args.config
        if not config_file or not os.path.exists(config_file):
            config_file = askForConfig()
    else:
        config_file = config
        
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Handle both 'Project' and 'project' keys for compatibility
    project_config = config.get('Project', config.get('project', {}))
    project = project_config.get("Name", "")
    root = project_config.get("Root", "")
    local_root = join(root, project)
    # Optional remote mirror path (user@host:/abs/path). Adjust if project stored differently remotely.
    remote_root = f'natmeg@compute.kcir.se:/data/vault/natmeg/{project}' if project else None

    dir_tree = nested_dir_tree(local_root)
    remote_tree = None
    if remote_root:
        remote_tree = nested_dir_tree(remote_root)
        if not remote_tree:
            print(f"[INFO] Remote path unreachable or empty: {remote_root}")

    # Load pipeline data for dashboard
    pipeline_data = load_pipeline_data(config)
    
    # Generate comprehensive dashboard
    generate_dashboard_report(
        dir_tree, 
        title=f"Pipeline Dashboard: {project}", 
        output_file=join(local_root, 'pipeline_dashboard.html'), 
        remote_tree=remote_tree,
        pipeline_data=pipeline_data,
        project_root=root
    )

if __name__ == "__main__":
    main()
