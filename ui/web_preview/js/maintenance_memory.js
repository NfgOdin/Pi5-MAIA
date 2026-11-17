// CarPi5 UI Module: MultiAir Maintenance Schedule, Living Memory & Automotive Library

// ============================================================================

// --- IN-DASH AUTOMOTIVE LIBRARY & DOCUMENT VIEWER ---

// ============================================================================

function openLibraryBook(bookKey) {

  const shelf = document.getElementById('libraryShelfView');

  const reader = document.getElementById('libraryReaderView');

  const mdContainer = document.getElementById('libraryMarkdownContainer');

  const pdfContainer = document.getElementById('libraryPdfContainer');

  const titleEl = document.getElementById('libraryBookTitle');

  const mdContent = document.getElementById('libraryMarkdownContent');

  const pdfFrame = document.getElementById('libraryPdfFrame');

  if (!shelf || !reader) return;

  shelf.style.display = 'none';

  reader.style.display = 'flex';

  if (bookKey === 'carpi5_manual') {

    if (titleEl) titleEl.innerText = "📖 CARPI5: COMPLETE SYSTEM & ENGINEERING MANUAL";

    if (mdContainer) mdContainer.style.display = 'block';

    if (pdfContainer) pdfContainer.style.display = 'none';

    if (mdContent) {

      mdContent.innerHTML = '<div style="color:var(--text-secondary); padding:40px; text-align:center;">Loading CarPi5 System Manual...</div>';

      fetch('/storage/manuals/CarPi5_Complete_System_Manual.md')

        .then(r => r.text())

        .then(md => {

          if (typeof marked !== 'undefined') {

            mdContent.innerHTML = marked.parse(md);

          } else {

            let html = md

              .replace(/&/g, '&amp;')

              .replace(/</g, '&lt;')

              .replace(/>/g, '&gt;')

              .replace(/^### (.*$)/gim, '<h3 style="color:#00e5ff; margin-top:16px;">$1</h3>')

              .replace(/^## (.*$)/gim, '<h2 style="color:#ff4081; border-bottom:1px solid #1c2636; padding-bottom:6px; margin-top:24px;">$1</h2>')

              .replace(/^# (.*$)/gim, '<h1 style="color:#fff; border-bottom:2px solid #00e5ff; padding-bottom:8px;">$1</h1>')

              .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')

              .replace(/\*(.*?)\*/gim, '<em>$1</em>')

              .replace(/```([\s\S]*?)```/gim, '<pre style="background:#090d14; border:1px solid #1c2636; padding:12px; border-radius:8px; overflow-x:auto; font-family:monospace; color:#00e676;"><code>$1</code></pre>')

              .replace(/`([^`]+)`/gim, '<code style="background:#161f2e; color:#00e5ff; padding:2px 6px; border-radius:4px;">$1</code>')
              .replace(/\n\n/gim, '<p style="margin-bottom:12px;"></p>');
            mdContent.innerHTML = html;
          }
          if (typeof initTouchScrollEngine === 'function') {
            setTimeout(initTouchScrollEngine, 100);
          }
        })
        .catch(err => {
          mdContent.innerHTML = `<div style="color:var(--accent-red); padding:20px;">Failed to load system manual: ${err}</div>`;
        });
    }
  } else if (bookKey === 'dart_owner') {
    if (titleEl) titleEl.innerText = "📕 2013 DODGE DART OWNER'S MANUAL (1.4L TURBO MULTIAIR)";
    if (mdContainer) mdContainer.style.display = 'none';
    if (pdfContainer) pdfContainer.style.display = 'block';
    if (pdfFrame) pdfFrame.src = "http://127.0.0.1:8080/storage/manuals/2013-Dodge-Dart-OM.pdf#toolbar=1&navpanes=1";
  } else if (bookKey === 'dart_repair') {
    if (titleEl) titleEl.innerText = "📙 DODGE DART COLLISION & BODY SERVICE MANUAL (2012-2016)";
    if (mdContainer) mdContainer.style.display = 'none';
    if (pdfContainer) pdfContainer.style.display = 'block';
    if (pdfFrame) pdfFrame.src = "http://127.0.0.1:8080/storage/manuals/Collision_Body_Repair_Manual_Dodge_Dart_2012-2016_253-document.pdf#toolbar=1&navpanes=1";
  }
}

function closeLibraryReader() {
  const shelf = document.getElementById('libraryShelfView');
  const reader = document.getElementById('libraryReaderView');
  const pdfFrame = document.getElementById('libraryPdfFrame');
  if (shelf) shelf.style.display = 'grid';
  if (reader) reader.style.display = 'none';
  if (pdfFrame) pdfFrame.src = 'about:blank';
}

// ============================================================================
// PHASE 8: MULTIAIR MAINTENANCE & R.U.M. VECTOR MEMORY SUITE
// ============================================================================
let currentMaintenanceData = null;

function refreshMaintenanceData(userTriggered = false) {
  fetch('/api/maintenance/status')
    .then(r => r.json())
    .then(data => {
      currentMaintenanceData = data;
      const odo = data.current_odometer || 85240;
      const odoEl = document.getElementById('maintOdometerVal');
      if (odoEl) odoEl.textContent = odo.toLocaleString();
      // Update Vehicle Hub Badge
      const hubBadge = document.getElementById('vehHubMaintBadge');
      if (hubBadge) {
        if (data.alerts && data.alerts.length > 0) {
          hubBadge.innerHTML = `<span>ODO: ${odo.toLocaleString()} MI | ⚠️ ${data.alerts.length} DUE</span>`;
          hubBadge.style.color = 'var(--accent-red)';
          hubBadge.style.borderColor = 'var(--accent-red)';
          hubBadge.style.background = 'rgba(255, 51, 68, 0.2)';
        } else {
          hubBadge.innerHTML = `<span>ODO: ${odo.toLocaleString()} MI | ALL OK</span>`;
          hubBadge.style.color = '#b452ff';
          hubBadge.style.borderColor = '#b452ff';
          hubBadge.style.background = 'rgba(180, 82, 255, 0.18)';
        }
      }
      // Update Global Alert Banner
      const banner = document.getElementById('maintAlertBanner');
      const bannerIcon = document.getElementById('maintAlertIcon');
      const bannerText = document.getElementById('maintAlertText');
      if (banner && bannerIcon && bannerText) {
        if (data.alerts && data.alerts.length > 0) {
          const hasOverdue = data.items && data.items.some(i => i.status === 'DUE_NOW');
          banner.className = 'maint-alert-banner ' + (hasOverdue ? 'maint-alert-danger' : 'maint-alert-warn');
          bannerIcon.textContent = hasOverdue ? '🚨' : '⚠️';
          bannerText.textContent = data.alerts.join(' • ');
        } else {
          banner.className = 'maint-alert-banner maint-alert-ok';
          bannerIcon.textContent = '✅';
          bannerText.textContent = 'ALL MULTIAIR POWERTRAIN SYSTEMS WITHIN FACTORY SERVICE INTERVALS';
        }
      }
      // Render Item Cards
      if (data.items) {
        renderMaintenanceItems(data.items, odo);
        const countBadge = document.getElementById('maintSummaryCountBadge');
        if (countBadge) countBadge.textContent = `${data.items.length} TRACKED ITEMS`;
      }
      if (userTriggered && window.showToast) {
        window.showToast("Maintenance schedules refreshed");
      }
    })
    .catch(err => {
      console.warn('[MAINT] Status fetch note:', err);
    });
}

function renderMaintenanceItems(items, currentOdo) {
  const container = document.getElementById('maintItemsList');
  if (!container) return;
  if (!items || items.length === 0) {
    container.innerHTML = '<div style="text-align:center; padding:30px; color:#64748b;">No maintenance items recorded.</div>';
    return;
  }
  container.innerHTML = items.map(item => {
    let badgeClass = 'maint-badge-green';
    let meterColor = '#10b981';
    let statusLabel = 'OK';
    if (item.status === 'DUE_NOW') {
      badgeClass = 'maint-badge-red';
      meterColor = '#ef4444';
      statusLabel = 'OVERDUE';
    } else if (item.status === 'DUE_SOON') {
      badgeClass = 'maint-badge-yellow';
      meterColor = '#eab308';
      statusLabel = 'DUE SOON';
    }
    const pct = Math.min(100, Math.max(0, item.percent_used || 0));
    const rem = item.miles_remaining;
    const remText = rem <= 0
      ? `<span style="color:#ef4444; font-weight:900;">OVERDUE BY ${Math.abs(rem).toLocaleString()} MI</span>`
      : `<span style="color:${rem < 1000 ? '#fde047' : '#94a3b8'};">${rem.toLocaleString()} mi remaining</span>`;
    const safeName = (item.name || '').replace(/'/g, "\\'");
    const safeKey = (item.item_key || '').replace(/'/g, "\\'");
    return `
      <div class="maint-item-card" data-key="${item.item_key}">
        <div class="maint-item-top">
          <div>
            <div class="maint-item-name">${item.name}</div>
            <div class="maint-item-spec">${item.part_number || 'OEM Standard Specification'}</div>
          </div>
          <span class="maint-badge ${badgeClass}">${statusLabel} (${pct}%)</span>
        </div>
        <div class="maint-meter-track">
          <div class="maint-meter-fill" style="width: ${pct}%; background: ${meterColor};"></div>
        </div>
        <div class="maint-item-footer">
          <div>
            <span>Interval: ${item.interval_miles.toLocaleString()} mi</span> •
            <span>Last: ${item.last_service_mileage.toLocaleString()} mi (${item.last_service_date})</span> •
            ${remText}
          </div>
          <button class="maint-log-btn" onclick="openServiceModal('${safeKey}', '${safeName}', ${currentOdo})">
            ✓ LOG SERVICE
          </button>
        </div>
      </div>
    `;
  }).join('');
}
// Odometer Modal Controls
function openOdometerModal() {
  const modal = document.getElementById('maintOdometerModal');
  const input = document.getElementById('maintModalOdoInput');
  const odoEl = document.getElementById('maintOdometerVal');
  if (input && odoEl) {
    input.value = odoEl.textContent.replace(/,/g, '').trim();
  }
  if (modal) modal.style.display = 'flex';
}

function closeOdometerModal() {
  const modal = document.getElementById('maintOdometerModal');
  if (modal) modal.style.display = 'none';
}

function submitOdometerUpdate() {
  const input = document.getElementById('maintModalOdoInput');
  if (!input) return;
  const val = parseInt(input.value, 10);
  if (isNaN(val) || val < 0) {
    alert("Please enter a valid mileage.");
    return;
  }
  fetch('/api/maintenance/odometer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ odometer: val })
  })
  .then(r => r.json())
  .then(res => {
    closeOdometerModal();
    refreshMaintenanceData();
    if (window.showToast) window.showToast(`Odometer updated to ${val.toLocaleString()} mi`);
  })
  .catch(err => {
    console.error('[MAINT] Odometer update error:', err);
    closeOdometerModal();
  });
}
// Service Modal Controls
function openServiceModal(itemKey, itemName, currentOdo) {
  const modal = document.getElementById('maintServiceModal');
  const title = document.getElementById('maintServiceModalTitle');
  const keyInput = document.getElementById('maintServiceModalItemKey');
  const mileInput = document.getElementById('maintServiceModalMileage');
  const noteInput = document.getElementById('maintServiceModalNotes');
  if (title) title.textContent = `LOG COMPLETED: ${itemName}`;
  if (keyInput) keyInput.value = itemKey;
  if (mileInput) mileInput.value = currentOdo || (currentMaintenanceData ? currentMaintenanceData.current_odometer : 85240);
  if (noteInput) noteInput.value = '';
  if (modal) modal.style.display = 'flex';
}

function closeServiceModal() {
  const modal = document.getElementById('maintServiceModal');
  if (modal) modal.style.display = 'none';
}

function submitServiceLog() {
  const keyInput = document.getElementById('maintServiceModalItemKey');
  const mileInput = document.getElementById('maintServiceModalMileage');
  const noteInput = document.getElementById('maintServiceModalNotes');
  const key = keyInput ? keyInput.value : '';
  const mileage = parseInt(mileInput ? mileInput.value : '0', 10);
  const notes = noteInput ? noteInput.value.trim() : '';
  if (!key || isNaN(mileage) || mileage <= 0) {
    alert("Please provide valid mileage.");
    return;
  }
  fetch('/api/maintenance/record', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_key: key, mileage: mileage, notes: notes })
  })
  .then(r => r.json())
  .then(res => {
    closeServiceModal();
    refreshMaintenanceData();
    quickQueryMemory(key.toLowerCase());
    if (window.showToast) window.showToast(`Service logged at ${mileage.toLocaleString()} mi!`);
  })
  .catch(err => {
    console.error('[MAINT] Service log error:', err);
    closeServiceModal();
  });
}
// Remember Note Modal Controls
function openRememberModal() {
  const modal = document.getElementById('maintRememberModal');
  const titleInput = document.getElementById('maintRememberTitle');
  const contentInput = document.getElementById('maintRememberContent');
  if (titleInput) titleInput.value = '';
  if (contentInput) contentInput.value = '';
  if (modal) modal.style.display = 'flex';
}

function closeRememberModal() {
  const modal = document.getElementById('maintRememberModal');
  if (modal) modal.style.display = 'none';
}

function submitRememberNote() {
  const titleInput = document.getElementById('maintRememberTitle');
  const contentInput = document.getElementById('maintRememberContent');
  const title = titleInput ? titleInput.value.trim() : '';
  const content = contentInput ? contentInput.value.trim() : '';
  if (!title || !content) {
    alert("Please enter both a title and details.");
    return;
  }
  fetch('/api/ai/memory/remember', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title, content: content, category: 'DRIVER_LOG' })
  })
  .then(r => r.json())
  .then(res => {
    closeRememberModal();
    quickQueryMemory(title);
    if (window.showToast) window.showToast("Memory indexed into R.U.M. vector store!");
  })
  .catch(err => {
    console.error('[MAINT] Remember error:', err);
    closeRememberModal();
  });
}
// Semantic Memory Search Controls
function submitMaintSearch() {
  const input = document.getElementById('maintSearchInput');
  if (!input) return;
  const q = input.value.trim();
  if (q) queryCompanionVectorMemory(q);
}

function quickQueryMemory(query) {
  const input = document.getElementById('maintSearchInput');
  if (input) input.value = query;
  queryCompanionVectorMemory(query);
}

function queryCompanionVectorMemory(query) {
  const resultsContainer = document.getElementById('maintSearchResults');
  if (!resultsContainer) return;
  const pName = (typeof getPersonaDisplayName === 'function') ? getPersonaDisplayName() : 'Companion';
  resultsContainer.innerHTML = '<div style="text-align:center; padding:20px; color:#94a3b8;">Searching vector database...</div>';
  fetch('/api/ai/memory/query?q=' + encodeURIComponent(query))
    .then(r => r.json())
    .then(data => {
      const results = data.results || [];
      if (results.length === 0) {
        resultsContainer.innerHTML = `
          <div class="maint-memory-empty">
            No semantic matches found for "<b>${query}</b>". ${pName} searches specifications, service logs, and flight records.
          </div>
        `;
        return;
      }
      resultsContainer.innerHTML = results.map(r => {
        let catColor = '#a855f7';
        if (r.category === 'SPECIFICATION') catColor = '#00f0ff';
        else if (r.category === 'MAINTENANCE') catColor = '#10b981';
        else if (r.category === 'TRIP_LOG') catColor = '#3b82f6';
        else if (r.category === 'DRIVER_LOG') catColor = '#f59e0b';
        return `
          <div class="maint-memory-card">
            <div class="maint-memory-card-header">
              <div style="display:flex; align-items:center; gap:6px;">
                <span style="font-size:9px; font-weight:900; background:rgba(255,255,255,0.08); color:${catColor}; padding:2px 6px; border-radius:4px; border:1px solid ${catColor};">
                  ${r.category}
                </span>
                <span class="maint-memory-title">${r.title}</span>
              </div>
              <span class="maint-memory-similarity">SIM: ${(r.similarity * 100).toFixed(1)}%</span>
            </div>
            <div class="maint-memory-body">${r.content}</div>
          </div>
        `;
      }).join('');
    })
    .catch(err => {
      console.error('[MAINT] Memory query note:', err);
      resultsContainer.innerHTML = '<div style="text-align:center; padding:20px; color:#ef4444;">Error querying vector memory.</div>';
    });
}
// Automatically load maintenance status on system boot
setTimeout(() => {
  refreshMaintenanceData();
}, 2500);

// ============================================================================
// 💖 PHASE 12: LIVING MEMORY, EPISODIC RAG & RELATIONSHIP BOND CONTROLS
// ============================================================================
let currentMaintTab = 'specs';

function switchMaintTab(tab) {
  currentMaintTab = tab;
  const btnSpecs = document.getElementById('btnTabMaintSpecs');
  const btnMind = document.getElementById('btnTabMaintMind');
  const viewSpecs = document.getElementById('maintSpecsView');
  const viewMind = document.getElementById('maintLivingMindView');
  if (tab === 'specs') {
    if (btnSpecs) btnSpecs.classList.add('active');
    if (btnMind) btnMind.classList.remove('active');
    if (viewSpecs) viewSpecs.style.display = 'grid';
    if (viewMind) viewMind.style.display = 'none';
  } else {
    if (btnSpecs) btnSpecs.classList.remove('active');
    if (btnMind) btnMind.classList.add('active');
    if (viewSpecs) viewSpecs.style.display = 'none';
    if (viewMind) {
      viewMind.style.display = 'flex';
      loadLivingMindData();
    }
  }
}

function loadLivingMindData() {
  fetch('/api/ai/memory/living_summary')
    .then(r => r.json())
    .then(data => {
      if (data.status !== 'ok') return;
      // 1. Render Relationship Bond
      const bond = data.bond || {};
      const tierEl = document.getElementById('bondTierTitle');
      const ptsBadge = document.getElementById('bondPtsBadge');
      const sharedMiles = document.getElementById('bondSharedMiles');
      const sharedDrives = document.getElementById('bondSharedDrives');
      const sharedPulls = document.getElementById('bondSharedPulls');
      const sharedCheckins = document.getElementById('bondSharedCheckins');
      const progLabel = document.getElementById('bondProgressLabel');
      const progPct = document.getElementById('bondProgressPct');
      const progBar = document.getElementById('bondProgressBar');
      const msRow = document.getElementById('bondMilestonesRow');
      if (tierEl) tierEl.textContent = (bond.bond_tier || 'INSEPARABLE DAUGHTER').toUpperCase();
      if (ptsBadge) ptsBadge.textContent = `${bond.bond_points || 0} BOND PTS`;
      if (sharedMiles) sharedMiles.textContent = (bond.shared_miles || 0).toLocaleString();
      if (sharedDrives) sharedDrives.textContent = bond.shared_drives || 0;
      if (sharedPulls) sharedPulls.textContent = bond.wot_pulls_together || 0;
      if (sharedCheckins) sharedCheckins.textContent = bond.caring_checkins_count || 0;
      const pct = bond.progress_pct || 0;
      if (progPct) progPct.textContent = `${pct}%`;
      if (progBar) progBar.style.width = `${pct}%`;
      if (progLabel) progLabel.textContent = `PROGRESS TO NEXT BOND TIER (${bond.next_target_points || 0} PTS TARGET)`;
      if (msRow) {
        const msList = [
          { id: 'FIRST_DRIVE', name: '🏅 First Drive Together' },
          { id: 'BOOST_PULL_15PSI', name: '🚀 15+ PSI Boost Pull' },
          { id: '100_MILES_SHARED', name: '🛣️ 100 Shared Miles' },
          { id: '500_MILES_SHARED', name: '⭐ 500 Shared Miles' },
          { id: '1000_MILES_SHARED', name: '👑 1,000 Shared Miles' }
        ];
        const unlocked = bond.unlocked_milestones || [];
        msRow.innerHTML = msList.map(m => {
          const isU = unlocked.includes(m.id);
          return `<span class="maint-milestone-pill ${isU ? 'unlocked' : ''}">${isU ? '✅' : '🔒'} ${m.name}</span>`;
        }).join('');
      }
      // 2. Render Companion Personal Trip Diary
      const diaryList = document.getElementById('companionDiaryList');
      if (diaryList) {
        const entries = data.diary || [];
        if (entries.length === 0) {
          diaryList.innerHTML = '<div style="text-align:center; padding:20px; color:#94a3b8;">No post-drive diary entries recorded yet.</div>';
        } else {
          diaryList.innerHTML = entries.map(d => `
            <div class="maint-diary-card">
              <div class="maint-diary-header">
                <div>
                  <span class="maint-diary-title">${d.title}</span>
                  <span class="maint-diary-meta" style="margin-left:8px;">${d.entry_date} • ${d.mileage} mi • Peak ${d.peak_boost} PSI</span>
                </div>
                <div style="display:flex; align-items:center; gap:6px;">
                  <span style="font-size:9px; font-weight:800; padding:2px 6px; border-radius:4px; background:rgba(168,85,247,0.15); color:#d8b4fe; border:1px solid rgba(168,85,247,0.3);">
                    ${d.mood || 'HAPPY'}
                  </span>
                  <button onclick="deleteDiaryEntry(${d.id})" style="background:transparent; border:none; color:#ef4444; cursor:pointer; font-size:13px; padding:2px;" title="Delete entry">🗑️</button>
                </div>
              </div>
              <div class="maint-diary-body">"${d.content}"</div>
            </div>
          `).join('');
        }
      }
      // 3. Render Driver Facts
      const factsList = document.getElementById('driverFactsList');
      if (factsList) {
        const facts = data.facts || [];
        if (facts.length === 0) {
          factsList.innerHTML = '<div style="text-align:center; padding:20px; color:#94a3b8;">No driver facts learned yet. Tap Teach Companion above!</div>';
        } else {
          factsList.innerHTML = facts.map(f => `
            <div class="maint-fact-card">
              <div style="flex:1;">
                <div class="maint-fact-key">${f.entity.replace('_', ' ')} • ${f.attribute.replace('_', ' ')}</div>
                <div class="maint-fact-val">${f.value}</div>
              </div>
              <button onclick="deleteDriverFact(${f.id})" style="background:transparent; border:none; color:#ef4444; cursor:pointer; font-size:14px; padding:4px;" title="Forget this fact">🗑️</button>
            </div>
          `).join('');
        }
      }
    })
    .catch(err => {
      console.error('[MAINT] Living mind summary error:', err);
    });
}

function deleteDiaryEntry(id) {
  if (!confirm('Are you sure you want to delete this diary entry?')) return;
  fetch('/api/ai/memory/diary/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: id })
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      loadLivingMindData();
      if (window.showToast) window.showToast('Diary entry removed');
    }
  });
}

function deleteDriverFact(id) {
  if (!confirm('Forget this learned driver fact?')) return;
  fetch('/api/ai/memory/facts/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: id })
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      loadLivingMindData();
      if (window.showToast) window.showToast('Memory fact forgotten');
    }
  });
}

function triggerDreamConsolidation() {
  const pName = (typeof getPersonaDisplayName === 'function') ? getPersonaDisplayName() : 'Companion';
  if (window.showToast) window.showToast(`Consolidating drive into ${pName} memory & diary...`);
  fetch('/api/ai/memory/consolidate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manual: true })
  })
  .then(r => r.json())
  .then(data => {
    loadLivingMindData();
    if (window.showToast) window.showToast(`✨ Drive consolidated! Diary #${data.diary_id || 1} created.`);
  })
  .catch(err => {
    console.error('[MAINT] Consolidation error:', err);
  });
}

function openTeachPersonaModal() {
  const modal = document.getElementById('maintTeachPersonaModal');
  const ent = document.getElementById('teachEntityInput');
  const attr = document.getElementById('teachAttrInput');
  const val = document.getElementById('teachValInput');
  if (ent) ent.value = '';
  if (attr) attr.value = '';
  if (val) val.value = '';
  if (modal) modal.style.display = 'flex';
}

function closeTeachPersonaModal() {
  const modal = document.getElementById('maintTeachPersonaModal');
  if (modal) modal.style.display = 'none';
}

function submitTeachPersonaFact() {
  const ent = document.getElementById('teachEntityInput')?.value.trim();
  const attr = document.getElementById('teachAttrInput')?.value.trim();
  const val = document.getElementById('teachValInput')?.value.trim();
  const pName = (typeof getPersonaDisplayName === 'function') ? getPersonaDisplayName() : 'Companion';
  const addr = (typeof getDriverDisplayAddress === 'function') ? getDriverDisplayAddress() : 'Driver';
  if (!ent || !attr || !val) {
    alert(`Please fill in Topic, Detail, and What ${pName} should remember.`);
    return;
  }
  fetch('/api/ai/memory/facts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      entity: ent,
      attribute: attr,
      value: val,
      confidence: 1.0,
      source: 'user_ui'
    })
  })
  .then(r => r.json())
  .then(data => {
    closeTeachPersonaModal();
    loadLivingMindData();
    if (window.showToast) window.showToast(`💖 ${pName} learned new fact about ${addr}!`);
  })
  .catch(err => {
    console.error('[MAINT] Error saving fact:', err);
    closeTeachPersonaModal();
  });
}
