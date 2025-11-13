// This file contains JavaScript that integrates the Electron APIs with the HTML viewer

// Check if running in Electron
const isElectron = typeof window.electronAPI !== 'undefined';

if (isElectron) {
  console.log('Running in Electron - native file APIs available');

  // Override the file input button to use native dialog
  document.addEventListener('DOMContentLoaded', () => {
    // Replace the file input button click handler
    const openButton = document.querySelector('button[onclick*="fileInput.click"]');
    if (openButton) {
      openButton.onclick = async () => {
        const fileData = await window.electronAPI.openFile();
        if (fileData) {
          await loadFileFromElectron(fileData);
        }
      };
    }

    // Listen for menu keyboard shortcuts
    window.electronAPI.onTriggerFileOpen(async () => {
      const fileData = await window.electronAPI.openFile();
      if (fileData) {
        await loadFileFromElectron(fileData);
      }
    });

    window.electronAPI.onTriggerSave(() => {
      const saveButton = document.getElementById('saveButton');
      if (saveButton && !saveButton.disabled) {
        saveChanges();
      }
    });
  });

  // Function to load file data from Electron
  async function loadFileFromElectron(fileData) {
    const loading = document.getElementById('loading');
    const table = document.getElementById('dataTable');
    const errorDiv = document.getElementById('errorMessage');

    loading.style.display = 'block';
    loading.innerHTML = 'Loading data...';
    table.style.display = 'none';
    errorDiv.innerHTML = '';

    try {
      const text = fileData.content;
      
      // Store the full file path for saving
      currentFilePath = fileData.path;
      
      // Parse TSV
      const lines = text.trim().split('\n');
      const headers = lines[0].split('\t');
      columns = headers;
      
      allData = lines.slice(1).map(line => {
        const values = line.split('\t');
        const obj = {};
        headers.forEach((header, index) => {
          obj[header] = values[index] || '';
        });
        return obj;
      });
      
      // Add unique index to each row
      allData.forEach((row, index) => {
        row._originalIndex = index;
      });
      
      // Store a deep copy of original data
      originalData = JSON.parse(JSON.stringify(allData));
      
      filterData();
      renderTable();
      loading.style.display = 'none';
      table.style.display = 'table';
    } catch (error) {
      loading.style.display = 'none';
      errorDiv.innerHTML = `<div class="error">❌ Error loading file: ${error.message}</div>`;
      console.error('Error loading file:', error);
    }
  }

  // Override the saveChanges function to use Electron's file save
  const originalSaveChanges = window.saveChanges;
  window.saveChanges = async function() {
    // Change status to "run" for modified rows, except those with manual status changes
    let autoChangedCount = 0;
    modifiedRows.forEach(originalIndex => {
      if (allData[originalIndex] && !manualStatusChanges.has(originalIndex)) {
        allData[originalIndex].status = 'run';
        autoChangedCount++;
      }
    });
    
    // Convert data back to TSV format (exclude _originalIndex)
    const tsvLines = [
      columns.join('\t'),
      ...allData.map(row => 
        columns.map(col => row[col] || '').join('\t')
      )
    ];
    const tsvContent = tsvLines.join('\n');
    
    try {
      let result;
      
      if (currentFilePath && currentFilePath.includes('/')) {
        // We have a full path, save directly
        result = await window.electronAPI.saveFile(currentFilePath, tsvContent);
      } else {
        // No path or just filename, show save dialog
        result = await window.electronAPI.saveFileDialog(currentFilePath || 'bids_conversion.tsv', tsvContent);
        if (result.filePath) {
          currentFilePath = result.filePath;
        }
      }
      
      if (result.success) {
        // Clear modified state
        modifiedRows.clear();
        manualStatusChanges.clear();
        document.getElementById('saveButton').disabled = true;
        document.getElementById('resetButton').disabled = true;
        
        // Update original data to current state
        originalData = JSON.parse(JSON.stringify(allData));
        
        let message = '✅ File saved successfully';
        if (autoChangedCount > 0) {
          message += '\n\n' + autoChangedCount + ' modified row(s) set to status: run';
        }
        alert(message);
        
        filterData();
      } else if (!result.canceled) {
        throw new Error(result.error || 'Failed to save file');
      }
    } catch (error) {
      alert('❌ Error saving file: ' + error.message);
      console.error('Save error:', error);
    }
  };
}
