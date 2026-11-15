// CarPi5 UI Module: File Explorer, USB Devices & Black-Box Trip Archive

// --- 11. FILE EXPLORER & USB STORAGE CONTROLLER ---

let detectedDevices = [];
let currentExplorerPath = "";
let fileClipboard = null; // { path, name, is_dir }
let editingFilePath = "";

function checkUsbDevices() {
  fetch('/api/fs/devices')
    .then(r => r.json())
    .then(devices => {
      detectedDevices = devices || [];
      updateUsbIndicatorUI();
      renderHomeDrivesShelf();
    })
    .catch(err => console.warn("[FS] USB poll error:", err));
}

function updateUsbIndicatorUI() {
  const pill = document.getElementById('headerUsbPill');
  const text = document.getElementById('headerUsbText');
  const badge = document.getElementById('homeUsbBadge');

  if (!pill) return;

  const removable = detectedDevices.find(d => d.is_removable);
  if (removable) {
    pill.style.display = 'flex';
    const shortLabel = removable.label || removable.name.split(' ')[0] || 'USB';
    const driveLetter = removable.mount_point || 'USB';
    if (text) text.innerText = `💾 ${shortLabel} (${driveLetter})`;
    pill.onclick = () => openFileExplorer(removable.mount_point);
    if (badge) {
      badge.innerText = `💾 USB: ${detectedDevices.length} READY`;
      badge.style.color = "var(--accent-green)";
      badge.style.borderColor = "var(--accent-green)";
    }
  } else {
    pill.style.display = 'none';
    if (badge) {
      badge.innerText = `💾 USB: STANDBY`;
      badge.style.color = "var(--text-secondary)";
      badge.style.borderColor = "var(--panel-border)";
    }
  }
}

function renderHomeDrivesShelf() {
  const shelf = document.getElementById('homeDrivesShelf');
  const list = document.getElementById('drivesShelfList');
  const countLabel = document.getElementById('drivesCountLabel');

  if (!shelf || !list) return;

  if (detectedDevices.length === 0) {
    shelf.style.display = 'none';
    return;
  }

  shelf.style.display = 'flex';
  if (countLabel) countLabel.innerText = `${detectedDevices.length} Storage Device${detectedDevices.length > 1 ? 's' : ''} Connected`;

  list.innerHTML = detectedDevices.map(dev => {
    const isUsb = dev.is_removable;
    const icon = isUsb ? '💾' : '💽';
    const cleanPath = dev.path.replace(/\\/g, '/');
    return `



      <div class="drive-card-mini" onclick="openFileExplorer('${cleanPath}')" title="Click to browse ${dev.name}">



        <span class="drive-icon">${icon}</span>



        <div class="drive-details">



          <span class="drive-label">${dev.name}</span>



          <span class="drive-space">${dev.free_gb.toFixed(1)} GB Free of ${dev.total_gb.toFixed(1)} GB</span>



        </div>



      </div>



    `;
  }).join('');
}

let explorerCurrentItems = [];
let explorerSortBy = 'name'; // 'name', 'size', 'date'
let explorerSortAsc = true;
let explorerSearchQuery = '';

function openFileExplorer(targetPath) {
  const expScreen = document.getElementById('screenExplorer');
  if (!expScreen || !expScreen.classList.contains('active')) {
    navigateTo('explorer');
    if (!targetPath) return;
  }
  if (targetPath && targetPath !== 'thispc') {
    loadExplorerDirectory(targetPath);
  } else {
    renderWin11ThisPcView();
  }
}

function closeFileExplorer() {
  navigateTo('home');
}

function renderExplorerDeviceTabs() {
  const tabsContainer = document.getElementById('explorerDeviceTabs');
  if (!tabsContainer) return;
  if (detectedDevices.length === 0) {
    tabsContainer.innerHTML = '<span style="color:var(--text-secondary); font-size:11px; padding:6px;">No storage roots found</span>';
    return;
  }
  tabsContainer.innerHTML = detectedDevices.map(dev => {
    const icon = dev.icon || (dev.is_removable ? '💾' : '📁');
    const cleanPath = dev.path.replace(/\\/g, '/');
    const currNorm = (currentExplorerPath || '').replace(/\\/g, '/');
    const isActive = currNorm === cleanPath || currNorm.startsWith(cleanPath + '/');
    const freeText = (dev.free_gb !== undefined && dev.free_gb !== null) ? `${dev.free_gb.toFixed(0)}G` : '';
    return `

      <button class="device-tab-btn ${isActive ? 'active' : ''}" onclick="openFileExplorer('${cleanPath}')" title="${dev.name} (${dev.path})">

        <span>${icon}</span>

        <span>${dev.label || dev.name}</span>

        ${freeText ? `<span style="opacity:0.6; font-size:9px;">${freeText}</span>` : ''}

      </button>

    `;
  }).join('');
}

function renderExplorerBreadcrumbs(breadcrumbs, currentPath) {
  const breadcrumbContainer = document.getElementById('explorerBreadcrumbs');
  if (!breadcrumbContainer) return;
  if (!breadcrumbs || breadcrumbs.length === 0) {
    breadcrumbContainer.innerHTML = `<span class="breadcrumb-segment" onclick="loadExplorerDirectory('${currentPath.replace(/\\/g, '/')}')">${currentPath}</span>`;
    return;
  }
  let html = '';
  breadcrumbs.forEach((crumb, idx) => {
    const cleanCrumbPath = crumb.path.replace(/\\/g, '/');
    const isLast = idx === breadcrumbs.length - 1;
    html += `

      <span class="breadcrumb-segment ${isLast ? 'active' : ''}" onclick="loadExplorerDirectory('${cleanCrumbPath}')">${crumb.name}</span>

    `;
    if (!isLast) {
      html += '<span class="breadcrumb-separator">/</span>';
    }
  });
  breadcrumbContainer.innerHTML = html;
  // Scroll to end of breadcrumbs
  breadcrumbContainer.scrollLeft = breadcrumbContainer.scrollWidth;
}

function loadExplorerDirectory(dirPath) {
  if (typeof syncWin11SidebarActive === 'function') syncWin11SidebarActive(dirPath);
  currentExplorerPath = dirPath || "";
  const fileList = document.getElementById('explorerFileList');
  const footerStatus = document.getElementById('explorerFooterStatus');
  if (fileList) fileList.innerHTML = '<div style="color:var(--text-secondary); padding:28px; text-align:center;"><div style="font-size:24px; margin-bottom:8px;">⏳</div>Loading directory contents...</div>';
  renderExplorerDeviceTabs();
  fetch(`/api/fs/list?path=${encodeURIComponent(currentExplorerPath)}`)
    .then(r => r.json())
    .then(data => {
      if (data.status === 'error' || data.error) {
        if (fileList) fileList.innerHTML = `<div style="color:var(--accent-red); padding:24px; text-align:center;"><div style="font-size:24px; margin-bottom:8px;">⚠️</div>${data.error || 'Permission denied or folder not found'}</div>`;
        return;
      }
      currentExplorerPath = data.path || data.current_path || currentExplorerPath;
      renderExplorerBreadcrumbs(data.breadcrumbs, currentExplorerPath);
      renderExplorerDeviceTabs();
      explorerCurrentItems = data.items || [];
      renderExplorerFilteredItems();
    })
    .catch(err => {
      console.error("[FS] Directory read error:", err);
      if (fileList) fileList.innerHTML = `<div style="color:var(--accent-red); padding:20px;">Network error loading directory: ${err}</div>`;
    });
}

function filterExplorerItems() {
  const input = document.getElementById('explorerSearchInput');
  const clearBtn = document.getElementById('explorerSearchClear');
  explorerSearchQuery = (input ? input.value : '').trim().toLowerCase();
  if (clearBtn) clearBtn.style.display = explorerSearchQuery ? 'inline-block' : 'none';
  renderExplorerFilteredItems();
}

function clearExplorerSearch() {
  const input = document.getElementById('explorerSearchInput');
  const clearBtn = document.getElementById('explorerSearchClear');
  if (input) input.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  explorerSearchQuery = '';
  renderExplorerFilteredItems();
}

function setExplorerSort(field) {
  if (explorerSortBy === field) {
    explorerSortAsc = !explorerSortAsc;
  } else {
    explorerSortBy = field;
    explorerSortAsc = (field === 'name');
  }
  ['Name', 'Size', 'Date'].forEach(f => {
    const btn = document.getElementById('sortBtn' + f);
    if (btn) {
      const active = (f.toLowerCase() === explorerSortBy);
      btn.className = 'sort-chip' + (active ? ' active' : '');
      if (active) {
        btn.innerText = `${f} ${explorerSortAsc ? '▲' : '▼'}`;
      } else {
        btn.innerText = f;
      }
    }
  });
  renderExplorerFilteredItems();
}

function renderExplorerFilteredItems() {
  const fileList = document.getElementById('explorerFileList');
  const footerStatus = document.getElementById('explorerFooterStatus');
  if (!fileList) return;
  let items = [...explorerCurrentItems];
  if (explorerSearchQuery) {
    items = items.filter(i => i.name.toLowerCase().includes(explorerSearchQuery));
  }
  // Sort
  items.sort((a, b) => {
    // Directories always first
    if (a.is_dir !== b.is_dir) {
      return a.is_dir ? -1 : 1;
    }
    let res = 0;
    if (explorerSortBy === 'name') {
      res = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    } else if (explorerSortBy === 'size') {
      res = (a.size_bytes || 0) - (b.size_bytes || 0);
    } else if (explorerSortBy === 'date') {
      res = (a.timestamp || 0) - (b.timestamp || 0);
    }
    return explorerSortAsc ? res : -res;
  });
  const folders = items.filter(i => i.is_dir);
  const files = items.filter(i => !i.is_dir);
  if (footerStatus) {
    footerStatus.innerText = `${items.length} items (${folders.length} folders, ${files.length} files)`;
  }
  if (items.length === 0) {
    const emptyMsg = explorerSearchQuery ? `No files matching "${explorerSearchQuery}"` : "(Folder is empty)";
    fileList.innerHTML = `<div style="color:var(--text-secondary); padding:36px; text-align:center;"><div style="font-size:24px; margin-bottom:8px;">📂</div>${emptyMsg}</div>`;
    return;
  }
  let html = '';
  // Render items
  items.forEach(item => {
    const cleanPath = item.path.replace(/\\/g, '/');
    if (item.is_dir) {
      html += `

        <div class="explorer-item-row" onclick="loadExplorerDirectory('${cleanPath}')">

          <div class="item-left">

            <span class="item-icon">📁</span>

            <div>

              <div class="item-name" style="color:var(--accent-yellow);">${item.name}</div>

              <div class="item-meta">Directory • ${item.modified || ''}</div>

            </div>

          </div>

          <div class="item-actions" onclick="event.stopPropagation()">

            <button class="item-action-btn" onclick="copyExplorerItem('${cleanPath}', '${item.name}', true)" title="Copy folder">📋 COPY</button>

            <button class="item-action-btn" style="color:var(--accent-red);" onclick="deleteExplorerItem('${cleanPath}', '${item.name}')" title="Delete folder">🗑️ DEL</button>

          </div>

        </div>

      `;
    } else {
      const ext = item.ext ? item.ext.toLowerCase() : '';
      let icon = '📄';
      let isEditable = false;
      let isAudio = false;
      let isVideo = false;
      let isRom = false;
      let isModel = false;
      if (['.cfg', '.json', '.txt', '.ini', '.py', '.sh', '.log', '.md', '.conf', '.yaml', '.yml'].includes(ext)) {
        icon = '📝';
        isEditable = true;
      } else if (['.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a'].includes(ext)) {
        icon = '🎵';
        isAudio = true;
      } else if (['.mp4', '.mkv', '.avi', '.mov', '.webm'].includes(ext)) {
        icon = '🎬';
        isVideo = true;
      } else if (['.sfc', '.smc', '.nes', '.gba', '.bin', '.iso', '.zip', '.7z'].includes(ext)) {
        icon = '🕹️';
        isRom = true;
      } else if (['.vrm', '.vrma', '.bvh'].includes(ext)) {
        icon = '🎭';
        isModel = true;
      } else if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext)) {
        icon = '🖼️';
      }
      const sizeFormatted = item.size_str || ((item.size_bytes > 1048576) ? `${(item.size_bytes / 1048576).toFixed(1)} MB` : `${Math.ceil((item.size_bytes || 0) / 1024)} KB`);
      html += `

        <div class="explorer-item-row" ${isEditable ? `onclick="openFileEditor('${cleanPath}')"` : ''}>

          <div class="item-left">

            <span class="item-icon">${icon}</span>

            <div>

              <div class="item-name">${item.name}</div>

              <div class="item-meta">${sizeFormatted} • ${item.modified || ''}</div>

            </div>

          </div>

          <div class="item-actions" onclick="event.stopPropagation()">

            ${isEditable ? `<button class="item-action-btn" style="color:var(--accent-blue); border-color:var(--accent-blue);" onclick="openFileEditor('${cleanPath}')">✏️ EDIT</button>` : ''}

            ${isRom ? `<button class="item-action-btn" style="color:var(--accent-purple);" onclick="launchRetroArch()">▶ PLAY</button>` : ''}

            ${isAudio ? `<button class="item-action-btn" style="color:var(--accent-green);" onclick="navigateTo('media')">▶ PLAY</button>` : ''}

            ${isVideo ? `<button class="item-action-btn" style="color:#ff7700;" onclick="showPlaceholderModal('VLC Player', 'Playing ${item.name} via VLC GPU acceleration')">🎬 VLC</button>` : ''}

            <button class="item-action-btn" onclick="copyExplorerItem('${cleanPath}', '${item.name}', false)" title="Copy file">📋 COPY</button>

            <button class="item-action-btn" style="color:var(--accent-red);" onclick="deleteExplorerItem('${cleanPath}', '${item.name}')" title="Delete file">🗑️ DEL</button>

          </div>

        </div>

      `;
    }
  });
  fileList.innerHTML = html;
}

function navigateExplorerUp() {
  if (!currentExplorerPath) return;
  const p = currentExplorerPath.replace(/\\/g, '/').replace(/\/+$/, '');
  const lastSlash = p.lastIndexOf('/');
  if (lastSlash > 0) {
    const parent = p.substring(0, lastSlash);
    loadExplorerDirectory(parent);
  } else if (lastSlash === 0) {
    loadExplorerDirectory('/');
  }
}

function promptNewFolder() {
  const name = window.prompt("Enter new folder name (e.g. snes_roms, logs, tuning):");
  if (!name || !name.trim()) return;
  fetch('/api/fs/mkdir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ parent_path: currentExplorerPath, folder_name: name.trim() })
  })
    .then(r => r.json())
    .then(res => {
      if (res.status === 'error' || res.error) alert("Error creating folder: " + (res.message || res.error));
      else loadExplorerDirectory(currentExplorerPath);
    })
    .catch(err => alert("Failed to create folder: " + err));
}

function copyExplorerItem(itemPath, itemName, isDir) {
  fileClipboard = { path: itemPath, name: itemName, is_dir: isDir };
  const pasteBtn = document.getElementById('explorerPasteBtn');
  if (pasteBtn) {
    pasteBtn.style.display = 'inline-flex';
    pasteBtn.innerText = `📋 PASTE (${itemName.substring(0, 14)})`;
  }
  showAiSpeechToast(`Copied "${itemName}" to clipboard`);
}

function pasteFileClipboard() {
  if (!fileClipboard) return;
  fetch('/api/fs/copy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src: fileClipboard.path, dst: currentExplorerPath })
  })
    .then(r => r.json())
    .then(res => {
      if (res.status === 'error' || res.error) {
        alert("Error copying: " + (res.message || res.error));
      } else {
        showAiSpeechToast(`Pasted "${fileClipboard.name}"`);
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Copy failed: " + err));
}

function deleteExplorerItem(itemPath, itemName) {
  if (!confirm(`Delete "${itemName}" permanently?`)) return;
  fetch('/api/fs/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: itemPath })
  })
    .then(r => r.json())
    .then(res => {
      if (res.status === 'error' || res.error) alert("Error deleting: " + (res.message || res.error));
      else {
        showAiSpeechToast(`Deleted "${itemName}"`);
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Delete failed: " + err));
}

function refreshExplorer() {
  loadExplorerDirectory(currentExplorerPath);
}

function openFileEditor(filePath) {
  editingFilePath = filePath;
  const modal = document.getElementById('fileEditorModal');
  const nameEl = document.getElementById('editorFileName');
  const pathEl = document.getElementById('editorFilePath');
  const textEl = document.getElementById('editorTextarea');
  const charEl = document.getElementById('editorCharCount');

  const baseName = filePath.replace(/\\/g, '/').split('/').pop();
  if (nameEl) nameEl.innerText = baseName;
  if (pathEl) pathEl.innerText = filePath;
  if (textEl) textEl.value = "Reading file from storage...";
  if (modal) modal.style.display = 'flex';

  fetch(`/api/fs/read?path=${encodeURIComponent(filePath)}`)
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        if (textEl) textEl.value = `Error opening file: ${data.error}`;
      } else {
        if (textEl) textEl.value = data.content || '';
        if (charEl) charEl.innerText = `${(data.content || '').length} characters | Lines: ${(data.content || '').split('\n').length}`;
      }
    })
    .catch(err => {
      if (textEl) textEl.value = "Failed to fetch file content: " + err;
    });
}

function closeFileEditor() {
  const modal = document.getElementById('fileEditorModal');
  if (modal) modal.style.display = 'none';
  editingFilePath = "";
}

function saveFileEditorContent() {
  const textEl = document.getElementById('editorTextarea');
  if (!textEl || !editingFilePath) return;

  const content = textEl.value;
  const baseName = editingFilePath.replace(/\\/g, '/').split('/').pop();

  fetch('/api/fs/write', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: editingFilePath, content: content })
  })
    .then(r => r.json())
    .then(res => {
      if (res.error) {
        alert("Error saving file: " + res.error);
      } else {
        showAiSpeechToast(`Saved ${baseName} to disk`);
        closeFileEditor();
        loadExplorerDirectory(currentExplorerPath);
      }
    })
    .catch(err => alert("Save failed: " + err));
}
// 5. SQLite Persistent Trip Logs & Driving Diagnostics

// --- BADASS TRIP TELEMETRY FLIGHT RECORDER & INSPECTOR ---
let activeInspectorTripId = null;
let inspectorTripData = null;
let inspectorPoints = [];
let inspectorActiveChannels = {
  speed: true,
  boost: true,
  rpm: true,
  afr: true,
  load: true,
  coolant: false
};
let inspectorScrubIdx = -1;

function fetchTripLogs(isManual = false) {
  const btn = document.getElementById('btnRefreshTrips');
  if (isManual && btn) {
    btn.innerHTML = '🔄 REFRESHING...';
    btn.style.opacity = '0.7';
  }
  Promise.all([
    fetch('/api/trips/stats').then(r => r.json()).catch(() => ({})),
    fetch('/api/trips/recent').then(r => r.json()).catch(() => []),
    fetch('/api/trips/settings').then(r => r.json()).catch(() => ({}))
  ])
  .then(([stats, trips, settings]) => {
    // 1. Settings synchronization
    const retentionSelect = document.getElementById('tripRetentionSelect');
    if (retentionSelect && settings && settings.retention_days !== undefined) {
      retentionSelect.value = String(settings.retention_days);
    }
    const zipSelect = document.getElementById('tripZipIntervalSelect');
    if (zipSelect && settings && settings.auto_zip_interval_min !== undefined) {
      zipSelect.value = String(settings.auto_zip_interval_min);
    }
    // 2. Active Flight Recorder Banner
    const recStatus = document.getElementById('liveTripRecorderStatus');
    if (recStatus) {
      if (stats.active_trip_id) {
        recStatus.innerHTML = `<span style="color:#00e676; font-weight:800;">ACTIVE TRIP #${stats.active_trip_id}</span> &bull; ${stats.total_distance_miles || 0} mi total &bull; Auto-Zip every ${settings.auto_zip_interval_min || 30}m`;
      } else {
        recStatus.innerText = `Standby (Auto-starts when engine starts / rolling)`;
      }
    }
    // 3. Lifetime Stats Cards (8 key metrics)
    const statsContainer = document.getElementById('tripLifetimeStats');
    if (statsContainer) {
      statsContainer.innerHTML = `

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL DRIVES</div>

          <div style="font-size:16px; font-weight:900; color:#fff;">${stats.total_trips || 0}</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL MILES</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-blue);">${stats.total_distance_miles || 0} MI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOTAL DRIVE TIME</div>

          <div style="font-size:16px; font-weight:900; color:#fff;">${stats.total_drive_hours || 0} HRS</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">PEAK BOOST EVER</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-green);">+${stats.peak_boost_ever || 0} PSI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">TOP SPEED EVER</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-blue);">${stats.top_speed_ever || 0} MPH</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">MAX RPM EVER</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-red);">${stats.max_rpm_ever || 0} RPM</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">LIFETIME AVG MPG</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-yellow);">${stats.lifetime_avg_mpg || 0} MPG</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:8px 12px; border-radius:8px;">

          <div style="font-size:9px; color:var(--text-secondary); font-weight:800;">BOOST PULLS</div>

          <div style="font-size:16px; font-weight:900; color:var(--accent-purple);">${stats.total_boost_pulls || 0} PULLS</div>

        </div>

      `;
    }
    // 4. Badass Trips Table with Inspect, Print & Zip Download Actions
    const tableContainer = document.getElementById('recentTripsTableContainer');
    if (tableContainer) {
      const validTrips = Array.isArray(trips) ? trips : ((trips && trips.trips) || []);
      if (validTrips.length === 0) {
        tableContainer.innerHTML = '<div style="color:var(--text-secondary); font-size:11px; padding:12px; text-align:center;">No trip history recorded in vehicle_data.db yet. Go for a drive to begin logging!</div>';
        return;
      }
      tableContainer.innerHTML = `

        <table style="width:100%; border-collapse:collapse; font-size:11px; text-align:left; white-space:nowrap;">

          <thead>

            <tr style="border-bottom:1px solid #212b38; color:var(--text-secondary); background:rgba(0,0,0,0.3);">

              <th style="padding:7px 8px;">TRIP ID &amp; DATE</th>

              <th style="padding:7px 8px;">DURATION &amp; DIST</th>

              <th style="padding:7px 8px;">SPEED (TOP / AVG)</th>

              <th style="padding:7px 8px;">MAX BOOST</th>

              <th style="padding:7px 8px;">MAX RPM</th>

              <th style="padding:7px 8px;">ECONOMY</th>

              <th style="padding:7px 8px;">FAULTS</th>

              <th style="padding:7px 8px; text-align:right;">ACTIONS</th>

            </tr>

          </thead>

          <tbody>

            ${validTrips.map(t => {
              const dtcBadge = (t.dtc_count > 0)
                ? `<span style="background:rgba(239,68,68,0.25); color:#ef4444; border:1px solid #ef4444; padding:1px 5px; border-radius:4px; font-weight:800; font-size:9px;">${t.dtc_count} DTC</span>`
                : `<span style="color:var(--accent-green); font-weight:700; font-size:9px;">✓ CLEAN</span>`;
              const activeBadge = t.is_active
                ? `<span style="color:#00e676; font-size:9px; font-weight:800; margin-left:4px;">● REC</span>`
                : ``;
              return `

                <tr style="border-bottom:1px solid #141b24; transition:background 0.15s ease;">

                  <td style="padding:7px 8px; color:#fff; font-weight:700;">

                    #${t.id} <span style="color:var(--text-secondary); font-weight:400; font-size:10px;">${t.start_time}</span>${activeBadge}

                  </td>

                  <td style="padding:7px 8px; color:var(--text-secondary);">

                    ${t.duration_min || 0} min <span style="color:#fff; font-weight:700;">(${t.distance_miles || 0} mi)</span>

                  </td>

                  <td style="padding:7px 8px; color:var(--accent-blue); font-weight:800;">

                    ${t.max_speed_mph || 0} MPH <span style="font-size:9px; color:var(--text-secondary); font-weight:400;">(${t.avg_speed_mph || 0} avg)</span>

                  </td>

                  <td style="padding:7px 8px; color:var(--accent-green); font-weight:800;">

                    +${t.max_boost_psi || 0} PSI

                  </td>

                  <td style="padding:7px 8px; color:var(--accent-red); font-weight:700;">

                    ${t.max_rpm || 0}

                  </td>

                  <td style="padding:7px 8px; color:var(--accent-yellow); font-weight:700;">

                    ${t.avg_mpg || 0} MPG <span style="font-size:9px; color:var(--text-secondary); font-weight:400;">(${t.fuel_used_gal || 0} gal)</span>

                  </td>

                  <td style="padding:7px 8px;">${dtcBadge}</td>

                  <td style="padding:7px 8px; text-align:right;">

                    <div style="display:inline-flex; gap:4px; align-items:center;">

                      <button onclick="openTripInspectorModal(${t.id})" class="cluster-action-btn" style="font-size:9px; padding:3px 8px; color:var(--accent-blue); border-color:var(--accent-blue);" title="Inspect Multi-Channel Graphs">📊 INSPECT</button>

                      <button onclick="printTripManifest(${t.id})" class="cluster-action-btn" style="font-size:9px; padding:3px 8px; color:#fff; background:#1f6feb; border-color:#388bfd;" title="Open Court / Legal Print Manifest">🖨️ PRINT</button>

                      <button onclick="downloadTripZip(${t.id})" class="cluster-action-btn" style="font-size:9px; padding:3px 8px; color:var(--accent-green); border-color:var(--accent-green);" title="Download Full .ZIP Archive">📦 ZIP</button>

                      <button onclick="promptDeleteSingleTrip(${t.id}, '${t.start_time || ''}')" style="background:transparent; border:none; color:var(--text-secondary); cursor:pointer; font-size:12px; padding:2px 4px;" title="Delete this trip">🗑️</button>

                    </div>

                  </td>

                </tr>

              `;
            }).join('')}

          </tbody>

        </table>

      `;
    }
    // Visual feedback on manual refresh
    if (isManual && btn) {
      btn.innerHTML = '✓ REFRESHED!';
      btn.style.borderColor = 'var(--accent-green)';
      btn.style.color = 'var(--accent-green)';
      btn.style.opacity = '1.0';
      setTimeout(() => {
        btn.innerHTML = '🔄 REFRESH';
        btn.style.borderColor = '';
        btn.style.color = '';
      }, 1500);
      showAiSpeechToast("Trip telemetry refreshed.");
    }
  })
  .catch(err => {
    console.warn("[TRIP] Fetch error:", err);
    if (isManual && btn) {
      btn.innerHTML = '❌ ERROR';
      setTimeout(() => { btn.innerHTML = '🔄 REFRESH'; btn.style.opacity = '1.0'; }, 2000);
    }
  });
}

function updateTripRetention(val) {
  fetch('/api/trips/retention', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ retention_days: parseInt(val) || 0 })
  })
  .then(r => r.json())
  .then(() => fetchTripLogs(true))
  .catch(err => console.warn("Retention update error:", err));
}

function updateTripZipInterval(val) {
  fetch('/api/trips/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ auto_zip_interval_min: parseInt(val) || 0 })
  })
  .then(r => r.json())
  .then(() => fetchTripLogs(true))
  .catch(err => console.warn("Zip interval update error:", err));
}

function archiveCurrentTripNow() {
  showAiSpeechToast("Compiling telemetry & generating ZIP archive...");
  fetch('/api/trips/archive_now', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
  .then(r => r.json())
  .then(res => {
    showAiSpeechToast("Trip archive successfully created in storage/trip_archives!");
    fetchTripLogs(true);
  })
  .catch(err => showAiSpeechToast("Archive error: " + err));
}
// Single Trip Deletion Modal Controls
let pendingDeleteTripId = null;

function promptDeleteSingleTrip(tripId, infoStr = '') {
  pendingDeleteTripId = tripId;
  const title = document.getElementById('deleteSingleTripTitle');
  if (title) title.innerText = `DELETE TRIP #${tripId}?`;
  const msg = document.getElementById('deleteSingleTripMsg');
  if (msg) {
    msg.innerHTML = `Are you sure you want to permanently delete <strong>Trip #${tripId}</strong> ${infoStr ? `(${infoStr})` : ''} and its telemetry points from <code>vehicle_data.db</code>?<br><br><strong style="color:#fff;">This action cannot be undone.</strong>`;
  }
  const m = document.getElementById('confirmDeleteSingleTripModal');
  if (m) m.style.display = 'flex';
}

function closeDeleteSingleTripModal() {
  pendingDeleteTripId = null;
  const m = document.getElementById('confirmDeleteSingleTripModal');
  if (m) m.style.display = 'none';
}

function executeDeleteSingleTrip() {
  if (!pendingDeleteTripId) return;
  const tripId = pendingDeleteTripId;
  closeDeleteSingleTripModal();
  fetch('/api/trips/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: tripId })
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      showAiSpeechToast(`Trip #${tripId} deleted.`);
      fetchTripLogs(true);
    } else {
      showAiSpeechToast(`Failed to delete trip #${tripId}.`);
    }
  })
  .catch(err => {
    console.warn("[TRIP] Delete trip error:", err);
    showAiSpeechToast("Network error deleting trip.");
  });
}
// Clear All Trips Modal Controls

function promptClearTripLogs() {
  const m = document.getElementById('confirmClearTripsModal');
  if (m) m.style.display = 'flex';
}

function closeClearTripsModal() {
  const m = document.getElementById('confirmClearTripsModal');
  if (m) m.style.display = 'none';
}

function executeClearTripLogs() {
  closeClearTripsModal();
  fetch('/api/trips/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      showAiSpeechToast("All trip logs and sensor data cleared successfully.");
      fetchTripLogs(true);
    } else {
      showAiSpeechToast("Failed to clear trip logs: " + (data.message || 'Error'));
    }
  })
  .catch(err => {
    console.error("[TRIP] Clear error:", err);
    showAiSpeechToast("Error clearing trip logs.");
  });
}

function printTripManifest(tripId) {
  const id = tripId || activeInspectorTripId;
  if (!id) return;
  const win = window.open(`/api/trips/manifest?id=${id}`, '_blank');
  if (win) win.focus();
}

function downloadTripZip(tripId) {
  const id = tripId || activeInspectorTripId;
  if (!id) return;

  window.location.href = `/api/trips/download?id=${id}`;
}

// --- INTERACTIVE TRIP INSPECTOR MODAL & MULTI-CHANNEL GRAPH ---

function openTripInspectorModal(tripId) {
  activeInspectorTripId = tripId;
  const modal = document.getElementById('tripInspectorModal');
  if (modal) modal.style.display = 'flex';
  Promise.all([
    fetch('/api/trips/recent').then(r => r.json()).catch(() => []),
    fetch(`/api/trips/telemetry?id=${tripId}&max_points=400`).then(r => r.json()).catch(() => [])
  ])
  .then(([recentTrips, points]) => {
    const trip = recentTrips.find(t => t.id === tripId) || {};
    inspectorTripData = trip;
    inspectorPoints = points;
    const title = document.getElementById('inspTripTitle');
    if (title) title.innerText = `TRIP #${trip.id || tripId} TELEMETRY FLIGHT RECORDER`;
    const badge = document.getElementById('inspTripStatusBadge');
    if (badge) {
      badge.innerText = trip.is_active ? "● ACTIVE RECORDING" : "ARCHIVED FLIGHT";
      badge.style.color = trip.is_active ? "#00e676" : "#00b0ff";
    }
    const metricsGrid = document.getElementById('inspMetricsGrid');
    if (metricsGrid) {
      metricsGrid.innerHTML = `

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">TOP SPEED</div>

          <div style="font-size:15px; font-weight:900; color:var(--accent-blue);">${trip.max_speed_mph || 0} MPH</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">AVG SPEED</div>

          <div style="font-size:15px; font-weight:900; color:#fff;">${trip.avg_speed_mph || 0} MPH</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">PEAK BOOST</div>

          <div style="font-size:15px; font-weight:900; color:var(--accent-green);">+${trip.max_boost_psi || 0} PSI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">MAX RPM</div>

          <div style="font-size:15px; font-weight:900; color:var(--accent-red);">${trip.max_rpm || 0}</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">MULTIAIR TEMP</div>

          <div style="font-size:15px; font-weight:900; color:#ff7700;">${trip.peak_coolant_f || 0}°F</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">PEAK LOAD</div>

          <div style="font-size:15px; font-weight:900; color:#ff5252;">${trip.peak_load_pct || 0}%</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">DISTANCE</div>

          <div style="font-size:15px; font-weight:900; color:#fff;">${trip.distance_miles || 0} MI</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">DURATION</div>

          <div style="font-size:15px; font-weight:900; color:#fff;">${trip.duration_min || 0} MIN</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">AVG ECONOMY</div>

          <div style="font-size:15px; font-weight:900; color:var(--accent-yellow);">${trip.avg_mpg || 0} MPG</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">FUEL CONSUMED</div>

          <div style="font-size:15px; font-weight:900; color:#fff;">${trip.fuel_used_gal || 0} GAL</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">ENGINE HOURS</div>

          <div style="font-size:15px; font-weight:900; color:#00e676;">${((trip.engine_runtime_sec || 0) / 3600.0).toFixed(2)} HRS</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">AVG AFR</div>

          <div style="font-size:15px; font-weight:900; color:#69f0ae;">${trip.avg_afr || 14.7}:1</div>

        </div>

        <div style="background:#0c1219; border:1px solid #212b38; padding:6px 10px; border-radius:6px;">

          <div style="font-size:8px; color:var(--text-secondary); font-weight:800;">VOLTS RANGE</div>

          <div style="font-size:15px; font-weight:900; color:#00e5ff;">${trip.min_volts || 12}V - ${trip.max_volts || 14}V</div>

        </div>

      `;
    }
    const sampleCountEl = document.getElementById('inspSampleCount');
    if (sampleCountEl) sampleCountEl.innerText = String(points.length);
    const hashEl = document.getElementById('inspShaSeal');
    if (hashEl) hashEl.innerText = trip.sha256_hash ? trip.sha256_hash : "GENERATED DYNAMICALLY ON ZIP EXPORT";
    const csvLink = document.getElementById('btnInspCsvDownload');
    if (csvLink) csvLink.href = `/api/trips/csv?id=${tripId}`;
    setupInspectorCanvasEvents();
    renderInspectorGraph();
  })
  .catch(err => console.warn("[INSP] Error loading trip telemetry:", err));
}

function closeTripInspectorModal() {
  const modal = document.getElementById('tripInspectorModal');
  if (modal) modal.style.display = 'none';
  activeInspectorTripId = null;
  inspectorPoints = [];
}

function toggleInspChannel(chan) {
  inspectorActiveChannels[chan] = !inspectorActiveChannels[chan];
  const btn = document.getElementById(`btnChan_${chan}`);
  if (btn) {
    if (inspectorActiveChannels[chan]) {
      btn.style.opacity = '1.0';
      btn.classList.add('active');
    } else {
      btn.style.opacity = '0.35';
      btn.classList.remove('active');
    }
  }
  renderInspectorGraph();
}

function setupInspectorCanvasEvents() {
  const canvas = document.getElementById('tripScrubberCanvas');
  if (!canvas || canvas._hasEvents) return;
  canvas._hasEvents = true;

  function handleScrub(clientX) {
    if (!inspectorPoints || inspectorPoints.length < 2) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const pct = x / rect.width;
    inspectorScrubIdx = Math.max(0, Math.min(inspectorPoints.length - 1, Math.round(pct * (inspectorPoints.length - 1))));
    renderInspectorGraph();
  }
  canvas.addEventListener('mousemove', (e) => handleScrub(e.clientX));
  canvas.addEventListener('touchmove', (e) => {
    if (e.touches && e.touches[0]) handleScrub(e.touches[0].clientX);
  });
  canvas.addEventListener('mouseleave', () => {
    inspectorScrubIdx = -1;
    const tt = document.getElementById('tripScrubberTooltip');
    if (tt) tt.style.display = 'none';
    renderInspectorGraph();
  });
}

function renderInspectorGraph() {
  const canvas = document.getElementById('tripScrubberCanvas');
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (rect.width > 0 && (canvas.width !== Math.round(rect.width * dpr) || canvas.height !== Math.round(rect.height * dpr))) {
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
  }
  const w = canvas.width;
  const h = canvas.height;
  if (w <= 0 || h <= 0) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, w, h);
  if (!inspectorPoints || inspectorPoints.length === 0) {
    ctx.fillStyle = '#8b949e';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No high-resolution telemetry samples recorded for this session yet.', w / 2, h / 2);
    return;
  }
  // Draw background horizontal gridlines (25%, 50%, 75%)
  ctx.strokeStyle = '#18202b';
  ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach(pct => {
    ctx.beginPath();
    ctx.moveTo(0, h * pct);
    ctx.lineTo(w, h * pct);
    ctx.stroke();
  });
  const channelsConfig = {
    speed: { key: 'speed_mph', color: '#00b0ff', min: 0, max: 120, label: 'Speed' },
    boost: { key: 'boost_psi', color: '#00e676', min: -20, max: 22, label: 'Boost' },
    rpm: { key: 'rpm', color: '#ffcc00', min: 0, max: 7000, label: 'RPM' },
    afr: { key: 'afr', color: '#69f0ae', min: 10, max: 20, label: 'AFR' },
    load: { key: 'engine_load_pct', color: '#ff5252', min: 0, max: 100, label: 'Load' },
    coolant: { key: 'coolant_temp_f', color: '#ff7700', min: 100, max: 230, label: 'Coolant' }
  };
  const pts = inspectorPoints;
  const n = pts.length;
  // Plot active channels
  Object.keys(channelsConfig).forEach(cKey => {
    if (!inspectorActiveChannels[cKey]) return;
    const cfg = channelsConfig[cKey];
    ctx.beginPath();
    ctx.strokeStyle = cfg.color;
    ctx.lineWidth = Math.max(1.5, 2.0 * dpr);
    ctx.lineJoin = 'round';
    for (let i = 0; i < n; i++) {
      const val = pts[i][cfg.key] !== undefined ? pts[i][cfg.key] : 0;
      const x = (i / (n - 1)) * w;
      const normY = Math.max(0, Math.min(1, (val - cfg.min) / (cfg.max - cfg.min)));
      const y = h - (normY * (h - 20) + 10);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  });
  // Draw Scrubber Line & Tooltip if scrubbing
  if (inspectorScrubIdx >= 0 && inspectorScrubIdx < n) {
    const p = pts[inspectorScrubIdx];
    const scrubX = (inspectorScrubIdx / (n - 1)) * w;
    ctx.beginPath();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 4]);
    ctx.moveTo(scrubX, 0);
    ctx.lineTo(scrubX, h);
    ctx.stroke();
    ctx.setLineDash([]);
    // Update Tooltip
    const tt = document.getElementById('tripScrubberTooltip');
    if (tt) {
      tt.style.display = 'block';
      const cssX = scrubX / dpr;
      const alignRight = cssX > (rect.width * 0.65);
      tt.style.left = alignRight ? `${Math.max(10, cssX - 260)}px` : `${Math.min(rect.width - 260, cssX + 12)}px`;
      const time12 = p.time_12h || (p.time_str ? p.time_str.split(' ')[1] : '');
      const elapsed = p.elapsed_str ? `(${p.elapsed_str} into drive)` : '';
      tt.innerHTML = `

        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #212b38; padding-bottom:3px; margin-bottom:4px; gap:8px;">

          <span style="font-weight:900; color:var(--accent-blue); font-size:11px;">⏱ ${time12}</span>

          <span style="color:var(--text-secondary); font-size:9.5px; font-family:monospace;">${p.time_str || ''} ${elapsed}</span>

        </div>

        <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:6px; font-size:9.5px;">

          <div>Speed: <strong style="color:#00b0ff; font-size:11px;">${(p.speed_mph || 0).toFixed(1)} MPH</strong></div>

          <div>Boost: <strong style="color:#00e676;">${(p.boost_psi || 0).toFixed(1)} PSI</strong></div>

          <div>RPM: <strong style="color:#ffcc00;">${Math.round(p.rpm || 0)}</strong></div>

          <div>AFR: <strong style="color:#69f0ae;">${(p.afr || 14.7).toFixed(2)}</strong></div>

          <div>Load: <strong style="color:#ff5252;">${Math.round(p.engine_load_pct || 0)}%</strong></div>

          <div>Volts: <strong style="color:#00e5ff;">${(p.battery_volts || 0).toFixed(1)}V</strong></div>

        </div>

      `;
    }
  }
}

function deleteSingleTrip(tripId) {
  promptDeleteSingleTrip(tripId);
}

// ============================================================================

// --- DEDICATED BLACK-BOX TRIP LOGGER & FLIGHT RECORDER ---

// ============================================================================
let currentTripSessionPoints = [];

function refreshTripsList() {
  fetch('/api/trips/recent')
    .then(r => r.json())
    .then(trips => {
      renderTripsList(trips);
    })
    .catch(err => console.error('[TRIPS] Fetch error:', err));
  fetch('/api/trips/stats')
    .then(r => r.json())
    .then(stats => {
      const badge = document.getElementById('tripLifetimeBadge');
      if (badge) {
        badge.innerText = `LIFETIME: ${stats.total_miles || 0} MILES • ${stats.total_trips || 0} SESSIONS`;
      }
    });
}

function renderTripsList(trips) {
  const container = document.getElementById('tripsListContainer');
  const countBadge = document.getElementById('tripsCountBadge');
  if (countBadge) countBadge.innerText = `${trips.length} SESSIONS`;
  if (!container) return;
  if (trips.length === 0) {
    container.innerHTML = `

      <div style="text-align:center; padding:24px 8px; color:var(--text-secondary); font-size:11.5px;">

        <div>📊</div>

        <div style="margin-top:6px;">No recorded drive sessions yet.</div>

        <div style="font-size:10px; color:#667;">Start driving to record black-box telemetry.</div>

      </div>

    `;
    return;
  }
  let html = '';
  trips.forEach((t, idx) => {
    const isFirst = (idx === 0);
    html += `

      <div class="trip-item-card ${isFirst ? 'active' : ''}" onclick="selectTripSession(${t.id})">

        <div style="display:flex; justify-content:space-between; align-items:center;">

          <span style="font-size:12px; font-weight:900; color:#fff;">TRIP #${t.id}</span>

          <span style="font-size:10px; color:var(--accent-blue); font-family:var(--font-mono);">${(t.distance_miles || 0).toFixed(1)} mi</span>

        </div>

        <div style="font-size:10px; color:var(--text-secondary); margin-top:3px;">${t.start_time || 'Recent Drive'} • ${(t.duration_min || 0).toFixed(0)} min</div>

        <div style="display:flex; gap:8px; font-size:9.5px; font-family:var(--font-mono); margin-top:4px; color:#a0b8d0;">

          <span>TOP: ${(t.max_speed_mph || 0).toFixed(0)} MPH</span>

          <span>BOOST: ${(t.max_boost_psi || 0).toFixed(1)} PSI</span>

        </div>

      </div>

    `;
  });
  container.innerHTML = html;
  if (trips.length > 0) {
    selectTripSession(trips[0].id);
  }
}

function selectTripSession(tripId) {
  fetch(`/api/trips/telemetry?id=${tripId}`)
    .then(r => r.json())
    .then(points => {
      currentTripSessionPoints = points;
      renderTripChart(points);
    });
}

function renderTripChart(points) {
  const canvas = document.getElementById('tripChartCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.clientWidth || 400;
  const h = canvas.clientHeight || 140;
  canvas.width = w;
  canvas.height = h;
  ctx.clearRect(0, 0, w, h);
  if (!points || points.length < 2) {
    ctx.fillStyle = '#667788';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Accumulating telemetry stream points...', w / 2, h / 2);
    return;
  }
  // Draw Grid Lines
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
  ctx.lineWidth = 1;
  for (let y = 0; y < h; y += 30) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  // Draw Speed (Cyan)
  ctx.beginPath();
  ctx.strokeStyle = '#00e5ff';
  ctx.lineWidth = 2;
  points.forEach((p, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - ((p.speed_mph || 0) / 100) * (h - 20) - 10;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  // Draw Boost (Yellow)
  ctx.beginPath();
  ctx.strokeStyle = '#ffcc00';
  ctx.lineWidth = 1.8;
  points.forEach((p, i) => {
    const x = (i / (points.length - 1)) * w;
    const boost = Math.max(0, p.boost_psi || 0);
    const y = h - (boost / 25) * (h - 20) - 10;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function exportCurrentTripManifest() {

  window.open('/api/trips/manifest', '_blank');
}

function promptClearAllTrips() {
  if (confirm("Purge all recorded driving sessions from the vehicle black-box database?")) {
    fetch('/api/trips/clear', { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        showAiSpeechToast("Flight records purged.");
        refreshTripsList();
      });
  }
}

// --- PHASE 3: WINDOWS 11 "THIS PC" DRIVES OVERVIEW ---

function renderWin11ThisPcView() {
  if (typeof syncWin11SidebarActive === 'function') syncWin11SidebarActive('thispc');
  // Full-window screenExplorer view rendered directly
  const fileList = document.getElementById('explorerFileList');
  const breadcrumbContainer = document.getElementById('explorerBreadcrumbs');
  const footerStatus = document.getElementById('explorerFooterStatus');
  currentExplorerPath = 'thispc';
  if (breadcrumbContainer) {
    breadcrumbContainer.innerHTML = '<span class="breadcrumb-segment active" style="font-weight:900; color:#fff;">🖥️ This PC</span>';
  }
  if (footerStatus) {
    footerStatus.innerText = 'Devices and Drives (7 items)';
  }
  if (!fileList) return;
  let drives = [];
  if (detectedDevices && detectedDevices.length > 0) {
    drives = detectedDevices.map(d => {
      const usedPct = d.total_gb ? Math.round(((d.total_gb - d.free_gb) / d.total_gb) * 100) : 30;
      return {
        icon: d.icon || '💾',
        name: d.name || d.label,
        path: d.path,
        sub: d.is_removable ? 'Removable USB Automotive Storage' : (d.mount_point || d.path),
        usedPct: Math.max(0, Math.min(100, usedPct)),
        freeText: `${d.free_gb} GB free of ${d.total_gb} GB`
      };
    });
  } else {
    drives = [
      { icon: '💽', name: 'OS System Drive (Root /)', path: '/', sub: 'MicroSD / NVMe Storage', usedPct: 50, freeText: 'System Drive' },
      { icon: '💼', name: 'CarPi5 Workspace', path: 'carpi5', sub: 'Backend, 3D Engine & Telemetry', usedPct: 35, freeText: 'Active Workspace' },
      { icon: '🏠', name: 'User Home (~)', path: '~', sub: 'User Profile & Configurations', usedPct: 38, freeText: 'User Home' },
      { icon: '💾', name: 'USB External Media', path: 'usb', sub: 'Removable Storage', usedPct: 20, freeText: 'Automotive Media' },
      { icon: '📹', name: 'Dashcam Storage', path: 'dashcam', sub: 'Video Replays & Dashcam Cache', usedPct: 45, freeText: 'Dashcam Network Storage' },
      { icon: '🎮', name: 'Retro ROMs', path: 'roms', sub: 'Emulation Library', usedPct: 40, freeText: 'Game ROMs' },
      { icon: '🎵', name: 'Music Library', path: 'music', sub: 'Audio Library', usedPct: 30, freeText: 'Local Audio Tracks' }
    ];
  }
  fileList.innerHTML = `

    <div class="win11-drives-grid">

      ${drives.map(d => `

        <div class="win11-drive-card" onclick="loadExplorerDirectory('${d.path}')" title="Click to open ${d.name}">

          <div class="win11-drive-header">

            <span class="win11-drive-icon">${d.icon}</span>

            <div>

              <div class="win11-drive-name">${d.name}</div>

              <div class="win11-drive-sub">${d.sub}</div>

            </div>

          </div>

          <div class="win11-drive-meter">

            <div class="win11-drive-meter-fill ${d.usedPct > 85 ? 'warn' : ''}" style="width: ${d.usedPct}%;"></div>

          </div>

          <div class="win11-drive-capacity">

            <span>${d.path}</span>

            <span>${d.freeText}</span>

          </div>

        </div>

      `).join('')}

    </div>

  `;
}
// Hook renderExplorerBreadcrumbs to add "This PC" root button
const originalRenderBreadcrumbs = typeof renderExplorerBreadcrumbs === 'function' ? renderExplorerBreadcrumbs : null;
renderExplorerBreadcrumbs = function(breadcrumbs, currentPath) {
  const breadcrumbContainer = document.getElementById('explorerBreadcrumbs');
  if (!breadcrumbContainer) return;
  if (currentPath === 'thispc') {
    breadcrumbContainer.innerHTML = '<span class="breadcrumb-segment active" style="font-weight:900; color:#fff;">🖥️ This PC</span>';
    return;
  }
  let html = '<span class="breadcrumb-segment" onclick="renderWin11ThisPcView()" style="color:var(--accent-cyan); font-weight:800;">🖥️ This PC</span> <span class="breadcrumb-separator">&gt;</span> ';
  if (!breadcrumbs || breadcrumbs.length === 0) {
    html += `<span class="breadcrumb-segment active">${currentPath}</span>`;
  } else {
    breadcrumbs.forEach((b, idx) => {
      const isLast = (idx === breadcrumbs.length - 1);
      html += `<span class="breadcrumb-segment ${isLast ? 'active' : ''}" onclick="loadExplorerDirectory('${b.path}')">${b.name}</span>`;
      if (!isLast) html += '<span class="breadcrumb-separator">/</span>';
    });
  }
  breadcrumbContainer.innerHTML = html;
  breadcrumbContainer.scrollLeft = breadcrumbContainer.scrollWidth;
};

function syncWin11SidebarActive(path) {
  document.querySelectorAll('.win11-nav-item').forEach(b => b.classList.remove('active'));
  if (!path || path === 'thispc') {
    const el = document.getElementById('win11NavThisPc');
    if (el) el.classList.add('active');
  } else if (path === '~' || path === 'home' || (path.startsWith('/home/') && path.split('/').filter(Boolean).length === 2)) {
    const el = document.getElementById('win11NavHome');
    if (el) el.classList.add('active');
  } else if (path === 'carpi5' || path.includes('CarPi5')) {
    const el = document.getElementById('win11NavProject');
    if (el) el.classList.add('active');
  } else if (path.startsWith('/media')) {
    const el = document.getElementById('win11NavUsb');
    if (el) el.classList.add('active');
  } else if (path.includes('dashcam')) {
    const el = document.getElementById('win11NavDashcam');
    if (el) el.classList.add('active');
  } else if (path.includes('roms') || path.includes('RetroPie')) {
    const el = document.getElementById('win11NavRoms');
    if (el) el.classList.add('active');
  } else if (path.includes('Music')) {
    const el = document.getElementById('win11NavMusic');
    if (el) el.classList.add('active');
  } else if (path === '/') {
    const el = document.getElementById('win11NavRoot');
    if (el) el.classList.add('active');
  }
}
