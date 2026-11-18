// CarPi5 UI Module: Powertrain OBD-II Diagnostics, Emergency DTC HUD & Drag Launch Studio

// --- 8. POWERTRAIN DIAGNOSTICS & FAULT CODES (OBD-II) ---

let latestActiveDTCs = [];
let currentDTCExplanation = null;

function onMilBadgeClicked() {
  if (latestActiveDTCs && latestActiveDTCs.length > 0) {
    lookupAndShowAIReport(latestActiveDTCs[0]);
  } else {
    showDiagnosticsModal();
  }
}

function lookupAndShowAIReport(code) {
  fetch(`/api/dtc/lookup?code=${code}`)
    .then(r => r.json())
    .then(data => {
      currentDTCExplanation = data;
      document.getElementById('diagCodeTitle').innerText = `${data.code}: ${data.title}`;
      document.getElementById('diagCodeSubtitle').innerText = "DODGE DART 1.4L TURBO MULTIAIR • MAGNETI MARELLI 8GM";

      const badge = document.getElementById('diagSeverityBadge');
      badge.innerText = data.severity_badge || "INSPECT FAULT";
      badge.style.color = data.severity_color || "var(--accent-yellow)";
      badge.style.borderColor = data.severity_color || "var(--accent-yellow)";
      badge.style.background = (data.severity_color || "#ffaa00") + "22";

      document.getElementById('diagDescription').innerText = `${data.description} ${data.advice}`;
      document.getElementById('diagCauses').innerText = data.common_causes;

      document.getElementById('aiMechanicModal').style.display = 'flex';
    })
    .catch(err => console.error("[DTC] Lookup error:", err));
}

function closeAiMechanicModal() {
  document.getElementById('aiMechanicModal').style.display = 'none';
}

function speakActiveDiag() {
  if (currentDTCExplanation) {
    speakUtterance(currentDTCExplanation.spoken_summary);
  }
}

function clearActiveDTCAndClose() {
  clearDTC();
  closeAiMechanicModal();
}

function injectDTC(code) {
  fetch(`/api/dtc/inject?code=${code}`)
    .then(r => r.json())
    .then(() => {
      document.getElementById('milBadge').classList.add('show');
      document.getElementById('milText').innerText = `CHECK ENGINE: ${code}`;
      closeAiMechanicModal();
      setTimeout(() => lookupAndShowAIReport(code), 300);
    })
    .catch(err => console.error("[DTC] Inject error:", err));
}

function clearDTC() {
  fetch(`/api/dtc/clear`)
    .then(r => r.json())
    .then(() => {
      latestActiveDTCs = [];
      document.getElementById('milBadge').classList.remove('show');
      const homeDtc = document.getElementById('homeDtcBadge');
      if (homeDtc) {
        homeDtc.innerText = "ECU: HEALTHY";
        homeDtc.style.color = "var(--accent-green)";
        homeDtc.style.borderColor = "var(--accent-green)";
      }
      closeAiMechanicModal();
    })
    .catch(err => console.error("[DTC] Clear error:", err));
}

function showDiagnosticsModal() {
  lookupAndShowAIReport("P0299");
}

// --- 17. FLOATING EMERGENCY DTC DIAGNOSTIC HUD ---

let activeEmergencyDtc = null;
let lastDtcAlertTime = 0;

function showEmergencyDtcHud(dtcCode, customDesc) {
  if (!dtcCode) return;
  activeEmergencyDtc = dtcCode;

  const hud = document.getElementById('emergencyDtcHud');
  const codeEl = document.getElementById('dtcHudCode');
  const descEl = document.getElementById('dtcHudDesc');
  const badgeEl = document.getElementById('dtcHudSeverity');

  if (!hud) return;

  if (codeEl) codeEl.innerText = dtcCode;

  let desc = customDesc;
  if (!desc) {
    const descriptions = {
      "P0299": "Turbocharger Underboost condition on 1.4L MultiAir. Inspect wastegate actuator rod, bypass diverter valve diaphragm, and intercooler boost hoses.",
      "P0234": "Turbocharger Overboost condition on 1.4L MultiAir. Wastegate may be sticking closed or boost control solenoid duty cycle excessive.",
      "P0300": "Random/Multiple Cylinder Misfire. Inspect MultiAir brick actuator solenoids, spark plug gaps, or ignition coils.",
      "P0128": "Coolant Thermostat below regulating temperature. Engine running cold.",
      "OVERHEAT_WARNING": "Engine coolant temperature exceeding safe limit! Pull over safely and allow cooling."
    };
    desc = descriptions[dtcCode] || `Diagnostic trouble code ${dtcCode} reported by Fiat Marelli 8GM powertrain controller.`;
  }

  if (descEl) descEl.innerText = desc;
  if (badgeEl) badgeEl.innerText = (dtcCode === "OVERHEAT_WARNING" || dtcCode === "P0299" || dtcCode === "P0234") ? "CRITICAL ALERT" : "STORED FAULT";

  hud.style.display = "flex";
  setVrmEmotion("CONCERNED");

  // Voice alert throttle: max once every 30 seconds for same code
  const now = Date.now();
  if (now - lastDtcAlertTime > 30000) {
    lastDtcAlertTime = now;
    const warningText = (dtcCode === "OVERHEAT_WARNING")
      ? "Master, your coolant temperature is running hot! Please pull over safely so we can let the turbo cool down!"
      : `Master, I detected an engine trouble code: ${dtcCode}. Tap me if you want me to explain what's happening under the hood!`;
    showAiSpeechToast(warningText);
    speakUtterance(warningText, "CONCERNED");
  }
}

function dismissDtcHud() {
  const hud = document.getElementById('emergencyDtcHud');
  if (hud) hud.style.display = "none";
  setVrmEmotion("DEVOTED");
}

function explainActiveDtc() {
  dismissDtcHud();
  navigateTo('ai');
  const prompt = activeEmergencyDtc
    ? `Explain active engine diagnostic trouble code ${activeEmergencyDtc} in detail for my Dodge Dart 1.4L Turbo MultiAir and tell me exactly what to check.`
    : "Check engine trouble codes and tell me what needs inspection.";
  sendChatMessage(prompt);
}

function triggerDtcHudVoice() {
  if (!activeEmergencyDtc) return;
  const descEl = document.getElementById('dtcHudDesc');
  const explanation = descEl ? descEl.innerText : `Code ${activeEmergencyDtc} active.`;
  showAiSpeechToast(explanation);
  speakUtterance(explanation, "CONCERNED");
}

// ============================================================================

// --- DEDICATED POWERTRAIN OBD-II & ECU DIAGNOSTICS SUITE ---

// ============================================================================

let currentSelectedDtc = null;

let isVrmMechanicActive = false;

function refreshDiagnostics() {

  fetch('/api/dtc/status')

    .then(r => r.json())

    .then(data => {

      renderDiagnosticsScreen(data);

    })

    .catch(err => console.error('[DIAGNOSTICS] Status fetch error:', err));

}

function renderDiagnosticsScreen(data) {

  const milVal = document.getElementById('diagMilVal');

  const milCard = document.getElementById('diagMilStatCard');

  const faultsVal = document.getElementById('diagFaultsCountVal');

  const pendingVal = document.getElementById('diagPendingCountVal');

  const codesBadge = document.getElementById('diagCodesBadge');

  const codesList = document.getElementById('diagCodesList');

  const obdBadge = document.getElementById('diagObdStatusBadge');

  if (obdBadge) {

    if (data.connected) {

      obdBadge.innerText = '● OBD-II CONNECTED';

      obdBadge.style.color = 'var(--accent-green)';

      obdBadge.style.borderColor = 'var(--accent-green)';

      obdBadge.style.background = 'rgba(0,230,118,0.15)';

    } else {

      obdBadge.innerText = '○ OBD-II DISCONNECTED / STANDBY';

      obdBadge.style.color = '#ff9100';

      obdBadge.style.borderColor = '#ff9100';

      obdBadge.style.background = 'rgba(255,145,0,0.15)';

    }

  }

  if (milVal && milCard) {

    if (data.mil_active) {

      milVal.innerText = 'ACTIVE / MIL ON';

      milVal.style.color = 'var(--accent-red)';

      milCard.classList.add('alert');

    } else {

      milVal.innerText = 'OFF / HEALTHY';

      milVal.style.color = 'var(--accent-green)';

      milCard.classList.remove('alert');

    }

  }

  const dtcs = data.active_dtcs || [];

  if (faultsVal) faultsVal.innerText = `${dtcs.length} CODES`;

  if (pendingVal) pendingVal.innerText = `${(data.pending_dtcs || []).length} CODES`;

  if (codesBadge) {

    codesBadge.innerText = dtcs.length > 0 ? `${dtcs.length} ACTIVE` : 'ALL CLEAR';

    codesBadge.style.color = dtcs.length > 0 ? 'var(--accent-red)' : 'var(--accent-green)';

  }

  // Freeze frame values

  const ff = data.freeze_frame || {};

  const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };

  setEl('ffRpm', `${ff.rpm || '--'} RPM`);

  setEl('ffBoost', `${ff.boost_psi !== undefined ? ff.boost_psi.toFixed(1) : '--'} PSI`);

  setEl('ffCoolant', `${ff.coolant_temp_f || '--'}°F`);

  setEl('ffSpeed', `${ff.speed_mph || '--'} MPH`);

  setEl('ffLoad', `${ff.engine_load_pct !== undefined ? ff.engine_load_pct.toFixed(0) : '--'}%`);

  setEl('ffThrottle', `${ff.throttle_pct !== undefined ? ff.throttle_pct.toFixed(0) : '--'}%`);

  // Render DTC list

  if (codesList) {

    if (dtcs.length === 0) {

      codesList.innerHTML = `
        <div style="text-align:center; padding:24px 12px; color:var(--text-secondary);">
          <div style="font-size:26px; margin-bottom:6px;">✅</div>
          <div style="font-size:12px; font-weight:800; color:#fff;">NO POWERTRAIN FAULTS DETECTED</div>
          <div style="font-size:11px; margin-top:4px;">ECU memory is clear. All systems operating nominally.</div>
        </div>
      `;

      setEl('diagDetailTitle', 'NO FAULT CODES ACTIVE');

      setEl('diagDetailSub', 'Magneti Marelli 8GM Powertrain Diagnostic Module');

      setEl('diagDetailBody', 'All monitored powertrain circuits, MultiAir variable valve solenoids, and turbo boost control loops are performing within OEM specifications.');

      const mBox = document.getElementById('diagMechanicBox');

      if (mBox) mBox.style.display = 'none';

    } else {

      let html = '';

      (data.code_details || []).forEach((item, idx) => {

        const isActive = (idx === 0);

        if (isActive) currentSelectedDtc = item;

        html += `
          <div class="diag-code-item ${isActive ? 'active' : ''}" onclick="selectDtcDetail('${item.code}')">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-size:14px; font-weight:900; color:var(--accent-yellow); font-family:var(--font-mono);">${item.code}</span>
              <span class="card-badge" style="font-size:9px; background:rgba(255,170,0,0.2); color:var(--accent-yellow); border-color:var(--accent-yellow);">${item.severity_badge || 'FAULT'}</span>
            </div>
            <div style="font-size:11px; font-weight:800; color:#fff; margin-top:3px;">${item.title || 'Diagnostic Fault'}</div>
          </div>
        `;

      });

      codesList.innerHTML = html;

      if (currentSelectedDtc) {

        renderDtcDetailPanel(currentSelectedDtc);

      }

    }

  }

}

function selectDtcDetail(code) {

  fetch(`/api/dtc/lookup?code=${code}`)

    .then(r => r.json())

    .then(data => {

      currentSelectedDtc = data;

      renderDtcDetailPanel(data);

    });

}

function renderDtcDetailPanel(data) {

  const title = document.getElementById('diagDetailTitle');

  const sub = document.getElementById('diagDetailSub');

  const body = document.getElementById('diagDetailBody');

  const mBox = document.getElementById('diagMechanicBox');

  const mText = document.getElementById('diagMechanicSpeechText');

  if (title) title.innerText = `${data.code}: ${data.title}`;

  if (sub) sub.innerText = `Magneti Marelli 8GM • ${data.severity_badge || 'Dodge Dart 1.4L Turbo MultiAir'}`;

  if (body) {

    body.innerHTML = `
      <div style="margin-bottom:8px;"><strong>Description:</strong> ${data.description || ''}</div>
      <div style="margin-bottom:8px; color:#ffdd88;"><strong>Recommended Action:</strong> ${data.advice || ''}</div>
      <div style="color:var(--text-secondary); font-size:11px;"><strong>Likely MultiAir Root Causes:</strong> ${data.common_causes || 'Check wiring harness and vacuum lines.'}</div>
    `;

  }

  if (mBox && mText) {

    mBox.style.display = 'block';

    mText.innerText = data.spoken_summary || `Code ${data.code} detected on the Dart. Master, let me check the MultiAir actuators!`;

  }

}

function promptClearDtcCodes() {

  if (confirm("Reset Check Engine MIL and clear all active diagnostic codes from ECU memory (Mode 04)?")) {

    fetch('/api/dtc/clear', { method: 'POST' })

      .then(r => r.json())

      .then(() => {

        showAiSpeechToast("Codes cleared and CEL reset!");

        refreshDiagnostics();

      });

  }

}

function toggleVrmMechanicMode() {

  isVrmMechanicActive = !isVrmMechanicActive;

  const btn = document.getElementById('btnVrmMechanicMode');

  if (btn) {

    if (isVrmMechanicActive) {

      btn.style.boxShadow = '0 0 16px rgba(255, 64, 129, 0.8)';

      speakMechanicBriefing();

    } else {

      btn.style.boxShadow = 'none';

    }

  }

}

function speakMechanicBriefing() {

  if (currentSelectedDtc && currentSelectedDtc.spoken_summary) {

    speakUtterance(currentSelectedDtc.spoken_summary);

  } else {

    speakUtterance("Master, powertrain diagnostics are completely clear! The 1.4L MultiAir actuators, Garrett turbo, and oil pressures are looking fantastic!");

  }

}

// ============================================================================
// 🏁 PHASE 9: DRAG LAUNCH CONTROL, NHRA CHRISTMAS TREE & G-G FRICTION HUD
// ============================================================================
let dragTreeMode = 'SPORTSMAN'; // 'SPORTSMAN' (0.5s stagger) | 'PRO' (0.4s flash)
let dragStagingState = 'IDLE'; // 'IDLE' | 'PRE_STAGE' | 'STAGED' | 'COUNTDOWN' | 'GREEN' | 'ACCELERATING' | 'FINISHED' | 'FOUL'
let dragTreeTimeouts = [];
let dragGreenTime = 0;
let dragReactionTime = null;
let ggHistory = [];

function toggleDragTreeMode() {
  if (dragTreeMode === 'SPORTSMAN') {
    dragTreeMode = 'PRO';
  } else {
    dragTreeMode = 'SPORTSMAN';
  }
  const btn = document.getElementById('dragTreeModeBtn');
  if (btn) {
    btn.innerText = dragTreeMode === 'SPORTSMAN' ? '🟡 SPORTSMAN (0.5s)' : '⚡ PRO TREE (0.4s)';
    btn.style.color = dragTreeMode === 'SPORTSMAN' ? '#00b0ff' : '#ff9900';
    btn.style.borderColor = dragTreeMode === 'SPORTSMAN' ? '#00b0ff' : '#ff9900';
  }
  resetDragRun();
}

function clearAllTreeBulbs() {
  const bulbs = [
    'treePreStageL', 'treePreStageR',
    'treeStageL', 'treeStageR',
    'treeAmber1L', 'treeAmber1R',
    'treeAmber2L', 'treeAmber2R',
    'treeAmber3L', 'treeAmber3R',
    'treeGreenL', 'treeGreenR',
    'treeRedL', 'treeRedR'
  ];
  bulbs.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  });
}

function setBulbsActive(ids, active) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      if (active) el.classList.add('active');
      else el.classList.remove('active');
    }
  });
}

function updateDragTreeStatus(label, color, bg) {
  const pill = document.getElementById('treeStatusPill');
  if (pill) {
    pill.innerText = label;
    pill.style.color = color || '#94a3b8';
    pill.style.background = bg || 'rgba(100,116,139,0.2)';
    pill.style.borderColor = color || '#475569';
  }
}

function setVrmDragCallout(msg) {
  const callout = document.getElementById('dragVrmCallout');
  const pName = (typeof getPersonaDisplayName === 'function') ? getPersonaDisplayName() : 'Companion';
  if (callout) callout.innerText = `${pName}: ` + msg;
  const bubble = document.getElementById('vrmHudBubble');
  if (bubble) {
    bubble.innerText = msg;
    bubble.style.display = 'block';
  }
}

function armDragStaging() {
  dragTreeTimeouts.forEach(t => clearTimeout(t));
  dragTreeTimeouts = [];
  clearAllTreeBulbs();
  dragStagingState = 'PRE_STAGE';
  dragReactionTime = null;
  dragGreenTime = 0;
  const rtEl = document.getElementById('treeReactionTime');
  if (rtEl) rtEl.innerText = '--.---';
  // 1. Light Pre-Stage
  setBulbsActive(['treePreStageL', 'treePreStageR'], true);
  updateDragTreeStatus('PRE-STAGED', '#38bdf8', 'rgba(56,189,248,0.2)');
  setVrmDragCallout("Rolling into pre-stage... Hold the clutch and rev!");
  // Notify backend
  const apiBase = (typeof DAEMON_ORIGIN !== 'undefined' ? DAEMON_ORIGIN : (window.location.origin.startsWith('http') ? '' : 'http://127.0.0.1:8080'));
  fetch(`${apiBase}/api/drag/stage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tree_type: dragTreeMode })
  }).catch(() => {});
  // 2. Light Stage after 800ms
  dragTreeTimeouts.push(setTimeout(() => {
    if (dragStagingState !== 'PRE_STAGE') return;
    dragStagingState = 'STAGED';
    setBulbsActive(['treeStageL', 'treeStageR'], true);
    updateDragTreeStatus('STAGED - READY', '#00e676', 'rgba(0,230,118,0.2)');
    setVrmDragCallout("STAGED! Eyes on the tree!");
    // 3. Initiate Countdown sequence after 1.2s
    dragTreeTimeouts.push(setTimeout(() => {
      startTreeCountdown();
    }, 1200));
  }, 800));
}

function startTreeCountdown() {
  dragStagingState = 'COUNTDOWN';
  updateDragTreeStatus('COUNTDOWN', '#ffab00', 'rgba(255,170,0,0.2)');
  if (dragTreeMode === 'SPORTSMAN') {
    // 0.5s intervals: Amber 1 -> Amber 2 -> Amber 3 -> GREEN
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive(['treeAmber1L', 'treeAmber1R'], true);
    }, 100));
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive(['treeAmber1L', 'treeAmber1R'], false);
      setBulbsActive(['treeAmber2L', 'treeAmber2R'], true);
    }, 600));
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive(['treeAmber2L', 'treeAmber2R'], false);
      setBulbsActive(['treeAmber3L', 'treeAmber3R'], true);
    }, 1100));
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive(['treeAmber3L', 'treeAmber3R'], false);
      triggerGreenLight();
    }, 1600));
  } else {
    // PRO TREE: All 3 Ambers together for 400ms -> GREEN
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive([
        'treeAmber1L', 'treeAmber1R',
        'treeAmber2L', 'treeAmber2R',
        'treeAmber3L', 'treeAmber3R'
      ], true);
    }, 100));
    dragTreeTimeouts.push(setTimeout(() => {
      if (dragStagingState !== 'COUNTDOWN') return;
      setBulbsActive([
        'treeAmber1L', 'treeAmber1R',
        'treeAmber2L', 'treeAmber2R',
        'treeAmber3L', 'treeAmber3R'
      ], false);
      triggerGreenLight();
    }, 500));
  }
}

function triggerGreenLight() {
  dragStagingState = 'GREEN';
  dragGreenTime = performance.now();
  setBulbsActive(['treeGreenL', 'treeGreenR'], true);
  updateDragTreeStatus('GREEN - GO!', '#00e676', 'rgba(0,230,118,0.3)');
  setVrmDragCallout("GREEN LIGHT! FLOOR IT!");
}

function triggerRedLightFoul() {
  dragTreeTimeouts.forEach(t => clearTimeout(t));
  dragTreeTimeouts = [];
  dragStagingState = 'FOUL';
  clearAllTreeBulbs();
  setBulbsActive(['treeRedL', 'treeRedR'], true);
  updateDragTreeStatus('RED LIGHT - FOUL', '#ff1744', 'rgba(255,23,68,0.3)');
  setVrmDragCallout("RED LIGHT! False start! You jumped the tree!");
  const rtEl = document.getElementById('treeReactionTime');
  if (rtEl) rtEl.innerText = 'FOUL (-.---)';
}

function resetDragRun() {
  dragTreeTimeouts.forEach(t => clearTimeout(t));
  dragTreeTimeouts = [];
  dragStagingState = 'IDLE';
  dragGreenTime = 0;
  dragReactionTime = null;
  clearAllTreeBulbs();
  updateDragTreeStatus('READY TO STAGE', '#94a3b8', 'rgba(100,116,139,0.2)');
  setVrmDragCallout("Drag timer reset. Tap ARM STAGE when staged at the line!");
  const rtEl = document.getElementById('treeReactionTime');
  if (rtEl) rtEl.innerText = '--.---';
  const timerEl = document.getElementById('dragStudioTimer');
  if (timerEl) timerEl.innerText = '0.00';
  const v060 = document.getElementById('dragVal060');
  if (v060) v060.innerText = '-- s';
  const v60ft = document.getElementById('dragVal60ft');
  if (v60ft) v60ft.innerText = '-- s';
  const v18mi = document.getElementById('dragVal18mi');
  if (v18mi) v18mi.innerText = '-- s';
  const v14mi = document.getElementById('dragVal14mi');
  if (v14mi) v14mi.innerText = '-- s';
  const t18 = document.getElementById('dragTrap18mi');
  if (t18) t18.innerText = '--';
  const t14 = document.getElementById('dragTrap14mi');
  if (t14) t14.innerText = '--';
  const peakEl = document.getElementById('dragStudioPeakG');
  if (peakEl) peakEl.innerText = '+0.00';
  const apiBase = (typeof DAEMON_ORIGIN !== 'undefined' ? DAEMON_ORIGIN : (window.location.origin.startsWith('http') ? '' : 'http://127.0.0.1:8080'));
  fetch(`${apiBase}/api/drag/reset`, { method: 'POST' }).catch(() => {});
}

function updateDragyStudioUI(gps, telem) {
  const currentSpeed = (gps && typeof gps.speed_mph === 'number') ? gps.speed_mph : ((telem && typeof telem.speed === 'number') ? telem.speed : 0);
  const currentRpm = (telem && typeof telem.rpm === 'number') ? telem.rpm : 0;
  const currentGear = (telem && telem.gear) ? telem.gear : 'N';
  // 1. Vehicle Movement & Tree False-Start Detection
  if (dragStagingState === 'COUNTDOWN' || dragStagingState === 'STAGED' || dragStagingState === 'PRE_STAGE') {
    if (currentSpeed >= 1.0) {
      triggerRedLightFoul();
      return;
    }
  }
  // 2. Green Light Launch & Reaction Time Recording
  if (dragStagingState === 'GREEN' && currentSpeed >= 1.0) {
    dragStagingState = 'ACCELERATING';
    if (dragGreenTime > 0) {
      const rtMs = performance.now() - dragGreenTime;
      dragReactionTime = (rtMs / 1000).toFixed(3);
      const rtEl = document.getElementById('treeReactionTime');
      if (rtEl) rtEl.innerText = dragReactionTime;
      setVrmDragCallout(`Clean launch! Reaction time: ${dragReactionTime}s! Hammer down!`);
    }
  }
  // 3. Update Drag Studio Speed & Timer
  const speedEl = document.getElementById('dragStudioSpeed');
  if (speedEl) speedEl.innerText = currentSpeed.toFixed(1);
  const rpmEl = document.getElementById('dragRpmVal');
  if (rpmEl) rpmEl.innerText = `${Math.round(currentRpm)} RPM (${currentGear})`;
  // F1 Sequential Shift Lights
  updateF1ShiftLights(currentRpm);
  // 4. Update G-Forces & Friction Circle
  let longG = 0.0;
  let latG = 0.0;
  if (gps && gps.g_forces) {
    longG = gps.g_forces.longitudinal || 0.0;
    latG = gps.g_forces.lateral || 0.0;
  }
  const longEl = document.getElementById('dragStudioLongG');
  if (longEl) longEl.innerText = (longG >= 0 ? '+' : '') + longG.toFixed(2);
  const peakEl = document.getElementById('dragStudioPeakG');
  if (peakEl && gps && gps.dragy && typeof gps.dragy.peak_g === 'number') {
    peakEl.innerText = '+' + gps.dragy.peak_g.toFixed(2);
  }
  // Draw G-G Friction Circle
  renderGgFrictionCircle(longG, latG);
  // 5. Update Dragy Metrics from GPS Telemetry
  if (gps && gps.dragy) {
    const d = gps.dragy;
    const timerEl = document.getElementById('dragStudioTimer');
    if (timerEl && typeof d.current_run_time === 'number') {
      timerEl.innerText = d.current_run_time.toFixed(2);
    }
    if (d.time_0_60) {
      const v060 = document.getElementById('dragVal060');
      if (v060) v060.innerText = `${d.time_0_60.toFixed(2)} s`;
      const b060 = document.getElementById('dragBadge060');
      if (b060) { b060.innerText = 'LOCKED'; b060.style.color = '#00e676'; }
    }
    if (d.time_60ft) {
      const v60 = document.getElementById('dragVal60ft');
      if (v60) v60.innerText = `${d.time_60ft.toFixed(2)} s`;
      const b60 = document.getElementById('dragBadge60ft');
      if (b60) { b60.innerText = 'LOCKED'; b60.style.color = '#00b0ff'; }
    }
    if (d.time_1_8mi) {
      const v18 = document.getElementById('dragVal18mi');
      if (v18) v18.innerText = `${d.time_1_8mi.toFixed(2)} s`;
      const t18 = document.getElementById('dragTrap18mi');
      if (t18 && d.speed_1_8mi) t18.innerText = d.speed_1_8mi.toFixed(1);
    }
    if (d.time_1_4mi) {
      const v14 = document.getElementById('dragVal14mi');
      if (v14) v14.innerText = `${d.time_1_4mi.toFixed(2)} s`;
      const t14 = document.getElementById('dragTrap14mi');
      if (t14 && d.speed_1_4mi) t14.innerText = d.speed_1_4mi.toFixed(1);
      if (dragStagingState === 'ACCELERATING') {
        dragStagingState = 'FINISHED';
        updateDragTreeStatus('RUN COMPLETE', '#00e5ff', 'rgba(0,229,255,0.2)');
        setVrmDragCallout(`1/4-mile complete! ${d.time_1_4mi.toFixed(2)}s @ ${d.speed_1_4mi || '--'} MPH! Amazing run!`);
      }
    }
    if (gps.road_grade_pct !== undefined) {
      const gEl = document.getElementById('dragGrade060');
      if (gEl) gEl.innerText = `${gps.road_grade_pct.toFixed(1)}%`;
    }
  }
}

function updateF1ShiftLights(rpm) {
  for (let i = 1; i <= 12; i++) {
    const led = document.getElementById(`f1Led${i}`);
    if (!led) continue;
    led.className = 'f1-led';
    if (i <= 4) {
      const thresh = 3000 + (i - 1) * 375;
      if (rpm >= thresh) led.classList.add('green-active');
    } else if (i <= 8) {
      const thresh = 4500 + (i - 5) * 250;
      if (rpm >= thresh) led.classList.add('amber-active');
    } else if (i <= 11) {
      const thresh = 5500 + (i - 9) * 166;
      if (rpm >= thresh) led.classList.add('red-active');
    } else {
      if (rpm >= 6000) led.classList.add('flash-active');
    }
  }
}

function renderGgFrictionCircle(longG, latG) {
  const canvas = document.getElementById('ggFrictionCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;
  const maxRadius = cx - 14;
  const clampLong = Math.max(-1.25, Math.min(1.25, longG));
  const clampLat = Math.max(-1.25, Math.min(1.25, latG));
  const px = cx + (clampLat / 1.0) * maxRadius;
  const py = cy - (clampLong / 1.0) * maxRadius;
  ggHistory.push({ x: px, y: py });
  if (ggHistory.length > 7) ggHistory.shift();
  ctx.clearRect(0, 0, w, h);
  ctx.save();
  // Crosshairs
  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(cx, 8);
  ctx.lineTo(cx, h - 8);
  ctx.moveTo(8, cy);
  ctx.lineTo(w - 8, cy);
  ctx.stroke();
  ctx.setLineDash([]);
  // Concentric G-Rings
  const rings = [0.25, 0.50, 0.75, 1.00];
  rings.forEach((r) => {
    ctx.beginPath();
    ctx.arc(cx, cy, r * maxRadius, 0, Math.PI * 2);
    if (r === 1.00) {
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.45)';
      ctx.lineWidth = 1.5;
    } else {
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.18)';
      ctx.lineWidth = 1;
    }
    ctx.stroke();
    ctx.fillStyle = r === 1.00 ? '#ef4444' : '#475569';
    ctx.font = '8px monospace';
    ctx.fillText(`${r.toFixed(2)}G`, cx + 3, cy - r * maxRadius + 9);
  });
  // Historical Trajectory Comet Tail
  for (let i = 0; i < ggHistory.length - 1; i++) {
    const pt = ggHistory[i];
    const opacity = (i + 1) / ggHistory.length * 0.45;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(0, 229, 255, ${opacity})`;
    ctx.fill();
  }
  // Active Instantaneous G Tracer Dot with Glow
  ctx.shadowColor = '#00e5ff';
  ctx.shadowBlur = 12;
  ctx.beginPath();
  ctx.arc(px, py, 6, 0, Math.PI * 2);
  ctx.fillStyle = '#00e5ff';
  ctx.fill();
  ctx.beginPath();
  ctx.arc(px, py, 2.5, 0, Math.PI * 2);
  ctx.fillStyle = '#ffffff';
  ctx.fill();
  ctx.restore();
  // Update numeric badges
  const latEl = document.getElementById('frictionLatG');
  if (latEl) latEl.innerText = (latG >= 0 ? '+' : '') + latG.toFixed(2);
  const longBadge = document.getElementById('frictionLongG');
  if (longBadge) longBadge.innerText = (longG >= 0 ? '+' : '') + longG.toFixed(2);
  const totEl = document.getElementById('frictionTotalG');
  if (totEl) {
    const totalG = Math.sqrt(latG * latG + longG * longG);
    totEl.innerText = totalG.toFixed(2);
  }
}

function initDragyStudio() {
  const canvas = document.getElementById('ggFrictionCanvas');
  if (canvas) {
    renderGgFrictionCircle(0.0, 0.0);
  }
}
// Phase 15 (telephony.js), Phase 11 (navigation.js), and Phase 18 (canyon_thermal.js)
// are modularized under ui/web_preview/js/ and loaded via index.html.
