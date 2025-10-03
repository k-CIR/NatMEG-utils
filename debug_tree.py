#!/usr/bin/env python3
"""Debug script to check tree generation."""

import os
import sys
from render_report import nested_dir_tree, create_hierarchical_list
import yaml

# Test with the OPM benchmarking config
config_path = 'tmp.yml'

if os.path.exists(config_path):
    print(f"Loading config: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Handle both 'Project' and 'project' keys for compatibility
    project_config = config.get('Project', config.get('project', {}))
    project = project_config.get("Name", "")
    root = project_config.get("Root", "")
    local_root = os.path.join(root, project)
    
    print(f"Project: {project}")
    print(f"Root: {root}")
    print(f"Local root: {local_root}")
    print(f"Local root exists: {os.path.exists(local_root)}")
    
    if os.path.exists(local_root):
        print("\n=== Testing nested_dir_tree ===")
        dir_tree = nested_dir_tree(local_root)
        print(f"Tree keys: {list(dir_tree.keys())[:10]}...")  # Show first 10 keys
        print(f"Total tree items: {len(dir_tree)}")
        
        print("\n=== Testing create_hierarchical_list ===")
        hierarchy = create_hierarchical_list(dir_tree)
        print(f"Hierarchy items: {len(hierarchy)}")
        
        # Show first few items
        for i, item in enumerate(hierarchy[:10]):
            print(f"  {i}: {item.get('type', '?')} - {item.get('name', '?')} (level {item.get('level', '?')})")
            
        if len(hierarchy) == 0:
            print("\n❌ No hierarchical items generated!")
            print("First few tree items:")
            for key, value in list(dir_tree.items())[:5]:
                print(f"  {key}: {type(value)}")
        else:
            print(f"\n✅ Generated {len(hierarchy)} hierarchical items")
    else:
        print(f"❌ Local root doesn't exist: {local_root}")
        
else:
    print(f"❌ Config file not found: {config_path}")