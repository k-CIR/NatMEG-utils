# Pipeline Tracker Error Fixes Summary

## Issues Resolved

### 1. Original Error: `'NoneType' object has no attribute 'group'`
**File**: `utils.py` - `extract_info_from_filename()` function
**Problem**: Regex patterns assumed all filenames would match standard MEG naming conventions
**Solution**: Added proper error handling for `re.search()` results

#### Changes Made:
```python
# Before (would crash):
participant = re.search(r'(NatMEG_|sub-)(\d+)', file_name).group(2).zfill(4)

# After (safe):
participant_match = re.search(r'(NatMEG_|sub-)(\d+)', file_name)
if participant_match:
    participant = participant_match.group(2).zfill(4)
else:
    # Fallback logic for non-standard filenames
    number_match = re.search(r'(\d{3,4})', file_name)
    participant = number_match.group(1).zfill(4) if number_match else 'unknown'
```

### 2. Warning: `File [ID] not found for stage update`
**File**: `pipeline_tracker.py` - `register_file()` and `update_file_stage()` methods
**Problem**: Two issues causing file lookup failures:

#### Issue A: Registration Order Problem
- `update_file_stage()` called before `_save_record()`
- Record not in database when trying to load it

**Solution**: Reordered operations in `register_file()`:
```python
# Before:
self.update_file_stage(file_id, stage, status, metadata)  # Fails: record not in DB yet
self._save_record(record)

# After:
# Add stage history directly to record
stage_entry = {'status': status.value, 'timestamp': ..., 'metadata': ...}
record.stage_history[stage.value] = stage_entry
self._save_record(record)  # Save first, then record is findable
```

#### Issue B: Inconsistent File ID Generation
- Same file gets different IDs depending on metadata available at different pipeline stages
- First registration: empty metadata → ID `60e40a0a521fcad8`
- Later update: full metadata → ID `137fe258aebeae1e`
- System looks for new ID but only old ID exists in database

**Solution**: Added robust file lookup in `track_file_operation()`:
```python
# New find_file_by_path() method tries multiple metadata combinations
file_id = tracker.find_file_by_path(file_path, metadata)

if file_id:
    # Update existing file
    tracker.update_file_stage(file_id, stage, status, metadata)
else:
    # Register new file only if none exists
    file_id = tracker.register_file(file_path, stage, status, metadata)
```

## Files Modified

1. **`utils.py`**:
   - Added null-safe regex pattern matching
   - Fixed extension detection for files without extensions
   - Added fallback logic for task and participant extraction

2. **`pipeline_tracker.py`**:
   - Added `find_file_by_path()` method for robust file lookup
   - Fixed registration order in `register_file()` method
   - Updated `track_file_operation()` to use new lookup method

## Testing

Created test scripts to verify fixes:
- **`test_filename_parsing.py`**: Tests filename parsing with various edge cases
- **`test_tracker_fix.py`**: Validates all fixes are in place
- **`pipeline_fix_verification.py`**: Demonstrates the fix logic

## Expected Outcomes

✅ **No more crashes** on non-standard filenames like `neuro/data/sinuhe/opm/test`
✅ **No more "File not found for stage update" warnings**
✅ **Backward compatibility** maintained for existing workflows
✅ **Robust file tracking** across all pipeline stages

## Verification Commands

```bash
# Test filename parsing fix
python test_filename_parsing.py

# Verify all fixes are applied  
python test_tracker_fix.py

# Test with actual pipeline (requires MNE)
python copy_to_cerberos.py --config tmp.yml
```

The pipeline tracking system should now handle edge cases gracefully and maintain consistent file tracking throughout the MEG processing workflow.