# Enhanced Pipeline Dashboard - Feature Summary

## 🎯 Overview
Successfully transformed `render_report.py` from a simple sync comparison report into a comprehensive multi-tab pipeline dashboard that provides complete visibility into the MEG/EEG data processing pipeline.

## 📊 Dashboard Structure

### 1. **Overview Tab** 📈
- **Pipeline Flow Visualization**: Interactive flow diagram showing data progression through stages
- **Summary Statistics**: Comprehensive metrics for each pipeline stage
- **Copy Stage Metrics**:
  - Total files processed
  - Success/failure counts
  - Split file handling statistics
- **BIDS Stage Metrics**:
  - Processed vs pending files
  - Participant and session counts
  - Conversion status tracking

### 2. **Original → Raw Tab** 📁
- **Copy Operations Table**: Complete log of file copying operations
- **Split File Grouping**: Enhanced display showing multiple destination files from single source
- **Status Filtering**: Filter by Success/Failed operations
- **File Details**: Shows original files, copied files (with count for splits), timestamps, and messages

### 3. **Raw → BIDS Tab** 🔄
- **BIDS Conversion Table**: Detailed view of BIDS format conversion
- **Processing Status**: Shows processed vs pending files
- **Participant Tracking**: Participant and session management
- **Conversion Filtering**: Filter by processing status

### 4. **Local ↔ Server Tab** ☁️
- **Enhanced Tree View**: Hierarchical file system comparison with advanced tree functionality
- **Tree Statistics**: Summary of directories, files, and sync issues
- **Interactive Controls**:
  - Expand All / Collapse All buttons
  - Collapsible folder tree with visual indicators
  - Status-based filtering
- **Sync Status**: Comprehensive comparison of local vs remote files

## 🌳 Enhanced Tree Functionality

### Visual Improvements
- **Expand/Collapse Icons**: Rotating triangle indicators for folder state
- **Tree Indentation**: Proper hierarchical indentation with visual depth
- **Hover Effects**: Interactive feedback on directory rows
- **Status Color Coding**: Visual status indicators (OK, missing, size mismatch, etc.)

### Interactive Features
- **Click to Toggle**: Click on directories to expand/collapse children
- **Expand All Button**: One-click expansion of entire tree
- **Collapse All Button**: One-click collapse of entire tree
- **Smart Filtering**: Maintains parent-child relationships when filtering
- **Icon Rotation**: Visual feedback showing expanded/collapsed state

### Tree Navigation
- **Hierarchical Display**: Proper parent-child relationship visualization
- **Level-based Indentation**: Clear visual hierarchy with appropriate spacing
- **Status Preservation**: Maintains tree state during filtering operations

## 🔧 Technical Enhancements

### Data Integration
- **Pipeline Linking**: Connects copy results, BIDS conversion, and sync data
- **Cross-stage Tracking**: Follows files through entire pipeline
- **Configuration Compatibility**: Supports both 'Project' and 'project' config formats
- **Error Handling**: Graceful handling of missing data files

### Performance Features
- **Efficient Rendering**: Optimized Jinja2 templates with custom filters
- **Smart Loading**: Conditional data loading based on file availability
- **Responsive Design**: Mobile-friendly layout with responsive components

### User Experience
- **Intuitive Navigation**: Clean tab interface with clear visual hierarchy
- **Visual Feedback**: Status badges, color coding, and interactive elements
- **Comprehensive Filtering**: Multiple filter options across all tabs
- **Progress Tracking**: Clear indication of pipeline completion status

## 📊 Dashboard Statistics Display

### Copy Stage Tracking
- Total files processed
- Success/failure rates
- Split file identification and grouping
- Transfer timestamps and messages

### BIDS Conversion Monitoring
- Processed file counts
- Pending conversion queue
- Participant and session statistics
- Conversion status breakdown

### Sync Status Overview
- Directory tree statistics
- File count summaries
- Sync issue identification
- Local vs remote comparison metrics

## 🎨 Visual Design Features

### Modern UI Components
- **Gradient Header**: Professional branding with project information
- **Card-based Layout**: Clean, organized information presentation
- **Responsive Grid**: Adaptive layout for different screen sizes
- **Professional Typography**: Clean, readable font hierarchy

### Color Scheme
- **Primary**: Professional blue gradient (#667eea to #764ba2)
- **Success**: Green indicators for completed operations
- **Warning**: Yellow/orange for pending or attention items
- **Error**: Red for failed operations or missing items

### Interactive Elements
- **Smooth Transitions**: CSS transitions for hover and click states
- **Status Badges**: Color-coded status indicators
- **Clickable Directories**: Clear visual feedback for interactive elements
- **Filter Controls**: Professional form styling

## 🚀 Usage

### Command Line
```bash
# Generate dashboard with default config
python render_report.py

# Generate with specific config
python render_report.py path/to/config.yml
```

### Output
- **File**: `pipeline_dashboard.html` in project directory
- **Size**: ~340KB (comprehensive with all features)
- **Format**: Self-contained HTML with embedded CSS and JavaScript

## 🔄 Integration Points

### Data Sources
- **copy_results.json**: Copy operation logging
- **bids_results.json**: BIDS conversion tracking
- **bids_conversion.tsv**: Conversion table data
- **File system**: Live directory comparison

### Pipeline Compatibility
- **Config Formats**: Supports both uppercase and lowercase config keys
- **Error Tolerance**: Graceful handling of missing pipeline stages
- **Cross-platform**: Works on macOS, Linux, and Windows

## 📈 Benefits

### For Researchers
- **Complete Visibility**: End-to-end pipeline tracking
- **Issue Identification**: Quick spotting of processing problems
- **Progress Monitoring**: Clear indication of pipeline completion
- **Data Validation**: Comprehensive sync status checking

### For Technical Teams
- **Debugging Aid**: Detailed logging and status information
- **Performance Monitoring**: Track processing efficiency
- **Quality Assurance**: Verify data integrity across stages
- **Maintenance Support**: Easy identification of system issues

## 🎯 Future Enhancement Opportunities
- **Real-time Updates**: Auto-refresh capabilities
- **Export Features**: CSV/JSON data export
- **Advanced Filtering**: Date ranges, file size filters
- **Performance Metrics**: Processing time tracking
- **Notification System**: Alert system for failures
- **Batch Operations**: Multi-project dashboard views