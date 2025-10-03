#!/usr/bin/env python3
"""Debug sync rows generation."""

import os
from render_report import nested_dir_tree, create_hierarchical_list
import yaml

config_path = 'tmp.yml'

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

project_config = config.get('Project', config.get('project', {}))
project = project_config.get("Name", "")
root = project_config.get("Root", "")
local_root = os.path.join(root, project)

print(f"Local root: {local_root}")

# Generate tree data
dir_tree = nested_dir_tree(local_root)
hierarchy = create_hierarchical_list(dir_tree)

print(f"\nFirst 5 hierarchical items:")
for i, item in enumerate(hierarchy[:5]):
    print(f"Item {i}:")
    for key, value in item.items():
        print(f"  {key}: {repr(value)}")
    print()

# Check the key mapping
local_items = {item.get('path') or item.get('relpath'): item for item in hierarchy}
print(f"Local items keys (first 10): {list(local_items.keys())[:10]}")
print(f"Total local items: {len(local_items)}")

# Remote tree (empty)
remote_tree = {}
remote_hierarchy = create_hierarchical_list(remote_tree)
remote_items = {item.get('path') or item.get('relpath'): item for item in remote_hierarchy}

print(f"Remote items: {len(remote_items)}")

# Generate paths
all_paths = []
path_set = set()

for item in hierarchy:
    path = item.get('path') or item.get('relpath')
    if path not in path_set:
        all_paths.append(path)
        path_set.add(path)

print(f"All paths (first 10): {all_paths[:10]}")
print(f"Total paths: {len(all_paths)}")

# Generate sync rows
sync_rows = []
for i, path in enumerate(all_paths[:10]):  # Just first 10 for testing
    local_item = local_items.get(path)
    remote_item = remote_items.get(path)
    
    if not local_item and not remote_item:
        print(f"Skipping path {path} - no local or remote item")
        continue
        
    item_type = (local_item or remote_item)['type']
    name = (local_item or remote_item)['name']
    level = (local_item or remote_item)['level']
    parent = (local_item or remote_item).get('folder_path', '')
    
    # Convert 'folder' to 'dir' for consistency with CSS classes
    display_type = 'dir' if item_type == 'folder' else 'file'
    
    sync_rows.append({
        'type': display_type,
        'relpath': path,
        'name': name,
        'parent': parent,
        'level': level,
        'status': 'ok'  # Simplified for debug
    })

print(f"\nGenerated sync rows: {len(sync_rows)}")
for i, row in enumerate(sync_rows[:5]):
    print(f"Row {i}: {row}")