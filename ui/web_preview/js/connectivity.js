// CarPi5 UI Module: Wi-Fi, Bluetooth & Pedal Commander Controller

// --- 12. WI-FI & MOBILE HOTSPOT CONTROLLER ---

let wifiStatus = {};
let selectedWifiSsid = null;
let selectedWifiSecurity = "WPA2-Personal";

function fetchWifiStatus() {
  fetch('/api/wifi/status')
    .then(r => r.json())
    .then(data => {
      wifiStatus = data || {};
      updateWifiHeaderPill();
      updateWifiSettingsCard();
    })
    .catch(err => console.warn("[WIFI] Status error:", err));
}

function updateWifiHeaderPill() {
  const pill = document.getElementById('headerWifiPill');
  const text = document.getElementById('headerWifiText');
  const icon = document.getElementById('headerWifiIcon');
  if (!pill) return;

  if (wifiStatus.connected) {
    pill.style.borderColor = "var(--accent-green)";
    pill.style.color = "var(--accent-green)";
    const sig = wifiStatus.signal_percent ? `${wifiStatus.signal_percent}%` : "100%";

    // Choose signal indicator
    let sigIcon = "📶";
    if (wifiStatus.signal_percent && wifiStatus.signal_percent < 40) sigIcon = "📳";

    if (text) text.innerText = `${wifiStatus.ssid} (${sig})`;
    if (icon) icon.innerText = sigIcon;
    pill.title = `${wifiStatus.ssid} • ${sig} Signal • IP: ${wifiStatus.ip_address || 'DHCP'} • Click to open Wi-Fi Manager`;
  } else {
    pill.style.borderColor = "var(--panel-border)";
    pill.style.color = "var(--text-secondary)";
    if (text) text.innerText = "WI-FI: STANDBY";
    if (icon) icon.innerText = "📡";
    pill.title = "Wi-Fi Disconnected • Click to scan and connect";
  }
}

function updateWifiSettingsCard() {
  const ssidEl = document.getElementById('wifiCurrentSsid');
  const badgeEl = document.getElementById('wifiCurrentBadge');
  const ipEl = document.getElementById('wifiCurrentIp');
  const sigEl = document.getElementById('wifiCurrentSignal');
  const bandEl = document.getElementById('wifiCurrentBand');
  const btnAlways = document.getElementById('btnToggleAlwaysOn');

  if (ssidEl) ssidEl.innerText = wifiStatus.connected ? wifiStatus.ssid : "Disconnected";
  if (badgeEl) {
    if (wifiStatus.connected) {
      badgeEl.innerText = "CONNECTED";
      badgeEl.style.background = "rgba(0,230,118,0.15)";
      badgeEl.style.color = "var(--accent-green)";
      badgeEl.style.borderColor = "var(--accent-green)";
    } else {
      badgeEl.innerText = "STANDBY / DISCONNECTED";
      badgeEl.style.background = "rgba(140,155,165,0.15)";
      badgeEl.style.color = "var(--text-secondary)";
      badgeEl.style.borderColor = "var(--panel-border)";
    }
  }

  if (ipEl) ipEl.innerText = wifiStatus.ip_address || "--";
  if (sigEl) sigEl.innerText = (wifiStatus.connected && wifiStatus.signal_percent) ? `${wifiStatus.signal_percent}%` : "--";
  if (bandEl) bandEl.innerText = wifiStatus.band || "2.4 / 5 GHz";

  if (btnAlways) {
    if (wifiStatus.always_on) {
      btnAlways.innerText = "⚡ ALWAYS-ON: ACTIVE";
      btnAlways.style.background = "rgba(0,230,118,0.15)";
      btnAlways.style.color = "var(--accent-green)";
      btnAlways.style.borderColor = "var(--accent-green)";
    } else {
      btnAlways.innerText = "⚪ ALWAYS-ON: DISABLED";
      btnAlways.style.background = "#141922";
      btnAlways.style.color = "var(--text-secondary)";
      btnAlways.style.borderColor = "var(--panel-border)";
    }
  }
}

function scanWifiNetworks() {
  const countEl = document.getElementById('wifiScanCount');
  const listEl = document.getElementById('wifiNetworkList');

  if (countEl) countEl.innerText = "Scanning nearby networks & hotspots...";
  if (listEl) listEl.innerHTML = '<div style="color:var(--text-secondary); padding:16px; text-align:center;">Scanning 2.4GHz & 5GHz Wi-Fi and phone hotspots...</div>';

  fetch('/api/wifi/scan')
    .then(r => r.json())
    .then(networks => {
      renderWifiNetworks(networks || []);
      fetchSavedWifi();
    })
    .catch(err => {
      console.error("[WIFI] Scan error:", err);
      if (listEl) listEl.innerHTML = `<div style="color:var(--accent-red); padding:12px;">Scan error: ${err}</div>`;
    });
}

function renderWifiNetworks(networks) {
  const listEl = document.getElementById('wifiNetworkList');
  const countEl = document.getElementById('wifiScanCount');

  if (!listEl) return;
  if (countEl) countEl.innerText = `${networks.length} Network${networks.length === 1 ? '' : 's'} Found`;

  if (networks.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-secondary); padding:16px; text-align:center;">No Wi-Fi networks found. Turn on phone hotspot or check Wi-Fi antenna.</div>';
    return;
  }

  listEl.innerHTML = networks.map(net => {
    const isConn = net.connected;
    const isSaved = net.is_saved;
    const sig = net.signal || 0;
    const sec = net.security || "WPA2-Personal";

    let sigLabel = "📶 Strong";
    if (sig < 45) sigLabel = "📶 Weak";
    else if (sig < 70) sigLabel = "📶 Fair";

    return `



      <div class="wifi-network-row ${isConn ? 'connected' : ''}">



        <div style="display:flex; align-items:center; gap:10px;">



          <span style="font-size:16px;">${isConn ? '🟢' : '📶'}</span>



          <div>



            <div style="font-size:12px; font-weight:800; color:#fff;">${net.ssid}</div>



            <div style="font-size:10px; color:var(--text-secondary); display:flex; gap:8px; margin-top:2px;">



              <span>${sigLabel} (${sig}%)</span>



              <span>•</span>



              <span>🔒 ${sec}</span>



            </div>



          </div>



        </div>



        <div style="display:flex; align-items:center; gap:8px;">



          ${isSaved ? '<span style="font-size:9px; color:var(--accent-green); background:rgba(0,230,118,0.1); border:1px solid var(--accent-green); padding:2px 6px; border-radius:4px;">REMEMBERED</span>' : ''}



          ${isConn 
            ? '<span class="pill" style="background:rgba(0,230,118,0.2); color:var(--accent-green); font-size:10px;">CONNECTED</span>'
            : `<button class="cluster-action-btn" style="color:var(--accent-blue); border-color:var(--accent-blue); padding:4px 12px;" onclick="openWifiConnectModal('${net.ssid}', '${sec}')">CONNECT</button>`
          }



        </div>



      </div>



    `;
  }).join('');
}

function fetchSavedWifi() {
  const savedList = document.getElementById('wifiSavedList');
  if (!savedList) return;

  fetch('/api/wifi/saved')
    .then(r => r.json())
    .then(saved => {
      if (!saved || saved.length === 0) {
        savedList.innerHTML = '<div style="color:var(--text-secondary); font-size:11px; padding:8px;">(No saved networks or hotspots stored)</div>';
        return;
      }

      savedList.innerHTML = saved.map(net => `



        <div class="wifi-saved-row">



          <div>



            <div style="font-size:12px; font-weight:800; color:#fff;">${net.ssid}</div>



            <div style="font-size:10px; color:var(--text-secondary); margin-top:2px;">



              <span>Auto-connect: <strong style="color:var(--accent-green);">${net.auto_connect ? 'YES' : 'NO'}</strong></span>



              ${net.last_connected ? ` • Last active: ${net.last_connected}` : ''}



            </div>



          </div>



          <button class="cluster-action-btn" style="color:var(--accent-red); font-size:10px; padding:3px 8px;" onclick="forgetWifiNetwork('${net.ssid}')">



            ✕ FORGET



          </button>



        </div>



      `).join('');
    })
    .catch(err => console.warn("[WIFI] Saved list error:", err));
}

function openWifiConnectModal(ssid, security) {
  selectedWifiSsid = ssid;
  selectedWifiSecurity = security;

  const modal = document.getElementById('wifiConnectModal');
  const ssidEl = document.getElementById('modalWifiSsid');
  const secEl = document.getElementById('modalWifiSecurity');
  const pwdEl = document.getElementById('modalWifiPassword');

  if (ssidEl) ssidEl.innerText = ssid;
  if (secEl) secEl.innerText = security;
  if (pwdEl) {
    pwdEl.value = '';
    pwdEl.type = 'password';
  }
  const showChk = document.getElementById('modalWifiShowPass');
  if (showChk) showChk.checked = false;

  if (modal) modal.style.display = 'flex';
}

function closeWifiConnectModal() {
  const modal = document.getElementById('wifiConnectModal');
  if (modal) modal.style.display = 'none';
  selectedWifiSsid = null;
}

function toggleWifiPasswordVisibility() {
  const pwdEl = document.getElementById('modalWifiPassword');
  const chk = document.getElementById('modalWifiShowPass');
  if (pwdEl && chk) {
    pwdEl.type = chk.checked ? 'text' : 'password';
  }
}

function submitWifiConnect() {
  if (!selectedWifiSsid) return;

  const pwdEl = document.getElementById('modalWifiPassword');
  const autoChk = document.getElementById('modalWifiAutoConnect');
  const btn = document.getElementById('btnSubmitWifiConnect');

  const password = pwdEl ? pwdEl.value : "";
  const autoConnect = autoChk ? autoChk.checked : true;

  if (btn) {
    btn.disabled = true;
    btn.innerText = "CONNECTING...";
  }

  fetch('/api/wifi/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ssid: selectedWifiSsid,
      password: password,
      auto_connect: autoConnect
    })
  })
    .then(r => r.json())
    .then(res => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "CONNECT";
      }

      if (res.error) {
        alert("Wi-Fi Connection Error: " + res.error);
      } else {
        const msg = `Connected to ${selectedWifiSsid}! Network online.`;
        showAiSpeechToast(msg);
        speakUtterance(msg);
        closeWifiConnectModal();
        fetchWifiStatus();
fetchBtStatus();
fetchBtPaired();
scanBtDevices();
setInterval(fetchBtStatus, 8000);
        scanWifiNetworks();
      }
    })
    .catch(err => {
      if (btn) {
        btn.disabled = false;
        btn.innerText = "CONNECT";
      }
      alert("Network connect request failed: " + err);
    });
}

function forgetWifiNetwork(ssid) {
  if (!confirm(`Forget remembered network "${ssid}"?`)) return;

  fetch('/api/wifi/forget', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ssid: ssid })
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast(`Forgot network: ${ssid}`);
      fetchSavedWifi();
      scanWifiNetworks();
    })
    .catch(err => alert("Error forgetting network: " + err));
}

function clearAllSavedWifi() {
  if (!confirm("Are you sure you want to clear ALL saved Wi-Fi networks and remembered hotspots?")) return;

  fetch('/api/wifi/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({})
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast("All saved networks cleared.");
      fetchSavedWifi();
      scanWifiNetworks();
    })
    .catch(err => alert("Error clearing saved networks: " + err));
}

function toggleWifiAlwaysOn() {
  const nextState = !wifiStatus.always_on;
  fetch('/api/wifi/always_on', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: nextState })
  })
    .then(r => r.json())
    .then(res => {
      wifiStatus.always_on = res.always_on;
      updateWifiSettingsCard();
      showAiSpeechToast(res.always_on ? "Wi-Fi Always-On enabled" : "Wi-Fi Always-On disabled");
    })
    .catch(err => alert("Failed to toggle Always-On: " + err));
}

// --- BLUETOOTH & PHONE AUDIO CONNECTION LOGIC ---
let btStatus = {
  powered: false,
  pairable: true,
  discoverable: true,
  controller_name: "CarPi",
  controller_mac: "",
  connected_device: null,
  connected_devices: []
};

function fetchBtStatus() {
  fetch('/api/bluetooth/status')
    .then(r => r.json())
    .then(data => {
      btStatus = data || {};
      updateBtHeaderPill();
      updateBtSettingsCard();
    })
    .catch(err => console.warn("[BT] Status error:", err));
}

function updateBtHeaderPill() {
  const pill = document.getElementById('btnHeaderBt');
  const text = document.getElementById('headerBtText');
  const icon = document.getElementById('headerBtIcon');
  if (!pill) return;
  if (btStatus.connected_device) {
    pill.style.borderColor = "var(--accent-blue)";
    pill.style.color = "var(--accent-blue)";
    pill.style.background = "rgba(0, 176, 255, 0.25)";
    if (text) text.innerText = btStatus.connected_device.name || "PHONE CONNECTED";
    if (icon) icon.innerText = "ᛒ";
    pill.title = `${btStatus.connected_device.name} • Connected • Click to manage Bluetooth`;
  } else {
    pill.style.borderColor = "var(--panel-border)";
    pill.style.color = "var(--text-secondary)";
    pill.style.background = "rgba(255, 255, 255, 0.04)";
    if (text) text.innerText = "BLUETOOTH";
    if (icon) icon.innerText = "ᛒ";
    pill.title = "Bluetooth Ready (Discoverable as CarPi) • Click to pair phone";
  }
}

function updateBtSettingsCard() {
  const devEl = document.getElementById('btCurrentDevice');
  const badgeEl = document.getElementById('btCurrentBadge');
  const ctrlNameEl = document.getElementById('btControllerName');
  const ctrlMacEl = document.getElementById('btControllerMac');
  const btnPair = document.getElementById('btnToggleBtPairable');
  if (ctrlNameEl && btStatus.controller_name) ctrlNameEl.innerText = btStatus.controller_name;
  if (ctrlMacEl && btStatus.controller_mac) ctrlMacEl.innerText = btStatus.controller_mac;
  if (devEl) {
    if (btStatus.connected_device) {
      devEl.innerText = btStatus.connected_device.name || btStatus.connected_device.mac;
      devEl.style.color = "var(--accent-blue)";
    } else {
      devEl.innerText = "No Device Connected";
      devEl.style.color = "var(--text-secondary)";
    }
  }
  if (badgeEl) {
    if (btStatus.connected_device) {
      badgeEl.innerText = "CONNECTED";
      badgeEl.style.background = "rgba(0,230,118,0.15)";
      badgeEl.style.color = "var(--accent-green)";
    } else {
      badgeEl.innerText = "STANDBY (READY)";
      badgeEl.style.background = "rgba(140,155,165,0.15)";
      badgeEl.style.color = "var(--text-secondary)";
    }
  }
  if (btnPair) {
    if (btStatus.discoverable) {
      btnPair.innerHTML = "🟢 PAIRABLE & DISCOVERABLE";
      btnPair.style.color = "var(--accent-green)";
      btnPair.style.borderColor = "var(--accent-green)";
      btnPair.style.background = "rgba(0,230,118,0.15)";
    } else {
      btnPair.innerHTML = "⚪ DISCOVERY OFF";
      btnPair.style.color = "var(--text-secondary)";
      btnPair.style.borderColor = "var(--panel-border)";
      btnPair.style.background = "rgba(255,255,255,0.05)";
    }
  }
}

function scanBtDevices() {
  const btn = document.getElementById('btnScanBt');
  const countEl = document.getElementById('btScanCount');
  const listEl = document.getElementById('btDeviceList');
  if (btn) {
    btn.innerHTML = "🔄 SCANNING...";
    btn.style.opacity = "0.7";
  }
  if (countEl) countEl.innerText = "Scanning nearby Bluetooth devices...";
  fetch('/api/bluetooth/scan')
    .then(r => r.json())
    .then(devices => {
      renderBtDevices(devices || []);
      fetchBtPaired();
      if (btn) {
        btn.innerHTML = "✓ SCANNED";
        btn.style.opacity = "1";
        setTimeout(() => { if (btn) btn.innerHTML = "🔄 SCAN DEVICES"; }, 2500);
      }
    })
    .catch(err => {
      console.error("[BT] Scan error:", err);
      if (btn) {
        btn.innerHTML = "⚠️ ERROR";
        setTimeout(() => { if (btn) btn.innerHTML = "🔄 SCAN DEVICES"; }, 2000);
      }
    });
}

function renderBtDevices(devices) {
  const listEl = document.getElementById('btDeviceList');
  const countEl = document.getElementById('btScanCount');
  if (!listEl) return;
  if (!devices || devices.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-secondary); padding:16px; text-align:center;">No Bluetooth devices found nearby. Make sure your phone Bluetooth is on!</div>';
    if (countEl) countEl.innerText = "0 devices found";
    return;
  }
  if (countEl) countEl.innerText = `${devices.length} device${devices.length === 1 ? '' : 's'} available - Tap CONNECT`;
  listEl.innerHTML = devices.map(d => {
    const isConn = d.connected;
    const isPaired = d.paired;
    const icon = "📱";
    return `

      <div class="wifi-network-row ${isConn ? 'connected' : ''}" style="display:flex; justify-content:space-between; align-items:center; padding:10px 14px; background:#0c1017; border:1px solid #1a222e; border-radius:8px; margin-bottom:6px;">

        <div style="display:flex; align-items:center; gap:10px;">

          <span style="font-size:16px;">${icon}</span>

          <div>

            <div style="font-size:12px; font-weight:800; color:#fff; display:flex; align-items:center; gap:6px;">

              ${escapeHtml(d.name || d.mac)}

              ${isPaired ? '<span style="font-size:9px; background:rgba(0,176,255,0.15); color:var(--accent-blue); padding:1px 5px; border-radius:4px;">PAIRED</span>' : ''}

              ${isConn ? '<span style="font-size:9px; background:rgba(0,230,118,0.15); color:var(--accent-green); padding:1px 5px; border-radius:4px;">CONNECTED</span>' : ''}

            </div>

            <div style="font-size:10px; color:var(--text-secondary); font-family:var(--font-mono);">${d.mac}</div>

          </div>

        </div>

        <div style="display:flex; gap:8px;">

          ${isConn
            ? `<button class="cluster-action-btn" style="color:var(--accent-red); border-color:var(--accent-red); font-size:10px; padding:4px 12px;" onclick="disconnectBtDevice('${d.mac}')">DISCONNECT</button>`
            : `<button class="cluster-action-btn" style="color:var(--accent-blue); border-color:var(--accent-blue); font-size:10px; padding:4px 12px;" onclick="connectBtDevice('${d.mac}', '${escapeHtml(d.name || d.mac)}')">CONNECT / PAIR</button>`
          }

        </div>

      </div>

    `;
  }).join('');
}

function fetchBtPaired() {
  const pairedList = document.getElementById('btPairedList');
  fetch('/api/bluetooth/paired')
    .then(r => r.json())
    .then(devices => {
      if (!pairedList) return;
      if (!devices || devices.length === 0) {
        pairedList.innerHTML = '<div style="color:var(--text-secondary); padding:10px; font-size:11px;">No paired devices saved yet. Connect above or discover "CarPi" from your phone!</div>';
        return;
      }
      pairedList.innerHTML = devices.map(d => `

        <div class="wifi-saved-row" style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:#0c1017; border:1px solid #1a222e; border-radius:6px; margin-bottom:4px;">

          <div style="display:flex; align-items:center; gap:8px;">

            <span style="font-size:13px;">📱</span>

            <div>

              <span style="font-size:12px; font-weight:800; color:#fff;">${escapeHtml(d.name)}</span>

              <span style="font-size:10px; color:var(--text-secondary); margin-left:6px; font-family:var(--font-mono);">${d.mac}</span>

            </div>

          </div>

          <div style="display:flex; gap:6px;">

            ${!d.connected ? `<button class="cluster-action-btn" style="color:var(--accent-blue); font-size:10px; padding:3px 10px;" onclick="connectBtDevice('${d.mac}', '${escapeHtml(d.name)}')">CONNECT</button>` : ''}

            <button class="cluster-action-btn" style="color:var(--accent-red); font-size:10px; padding:3px 8px;" onclick="removeBtDevice('${d.mac}', '${escapeHtml(d.name)}')">

              FORGET

            </button>

          </div>

        </div>

      `).join('');
    })
    .catch(err => console.warn("[BT] Paired fetch error:", err));
}

function connectBtDevice(mac, name) {
  showAiSpeechToast(`Connecting to Bluetooth device ${name || mac}...`);
  fetch('/api/bluetooth/connect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac: mac })
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast(res.message || `Bluetooth connection command dispatched for ${name}`);
      setTimeout(() => {
        fetchBtStatus();
        fetchBtPaired();
        scanBtDevices();
      }, 2000);
    })
    .catch(err => showAiSpeechToast(`Bluetooth connect error: ${err.message}`));
}

function disconnectBtDevice(mac) {
  fetch('/api/bluetooth/disconnect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac: mac })
  })
    .then(r => r.json())
    .then(res => {
      showAiSpeechToast(`Disconnected ${mac}`);
      fetchBtStatus();
      scanBtDevices();
    })
    .catch(err => console.error("[BT] Disconnect error:", err));
}

function removeBtDevice(mac, name) {
  fetch('/api/bluetooth/remove', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac: mac })
  })
    .then(r => r.json())
    .then(() => {
      showAiSpeechToast(`Forgot Bluetooth device ${name || mac}`);
      fetchBtStatus();
      fetchBtPaired();
      scanBtDevices();
    })
    .catch(err => console.error("[BT] Remove error:", err));
}

function toggleBtDiscoverable() {
  const next = !btStatus.discoverable;
  fetch('/api/bluetooth/discoverable', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: next })
  })
    .then(r => r.json())
    .then(res => {
      btStatus.discoverable = res.discoverable;
      updateBtSettingsCard();
      showAiSpeechToast(res.discoverable ? "Bluetooth is now Discoverable and Pairable" : "Bluetooth Discovery hidden");
    })
    .catch(err => console.error("[BT] Toggle discoverable error:", err));
}

function focusBtSection() {
  const grp = document.getElementById('accSystemGroup');
  if (grp) grp.classList.add('active');
  setTimeout(() => {
    const card = document.getElementById('btSettingsCard');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    fetchAudioDevices();
    fetchBtStatus();
  }, 100);
}

function focusWifiSection() {
  const grp = document.getElementById('accSystemGroup');
  if (grp) grp.classList.add('active');
  setTimeout(() => {
    const card = document.getElementById('wifiSettingsCard');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

// --- PEDAL COMMANDER THROTTLE CONTROLLER WIDGET ---
let currentPdlMode = 'SPORT';
let currentPdlLevel = 2;

function sendPdlCommand() {
  const pin = localStorage.getItem('carpi5_pdl_pin') || '';
  fetch('/api/pedal_commander/set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode: currentPdlMode, level: currentPdlLevel, pin: pin })
  })
  .then(r => r.json())
  .then(data => {
    updatePdlBadge(Boolean(data.connected), data);
    const lastAck = document.getElementById('pdlLastAck');
    if (lastAck) {
      if (data.connected && data.sent) {
        lastAck.innerText = `TX ${currentPdlMode} (${currentPdlLevel >= 0 ? '+' : ''}${currentPdlLevel})`;
        lastAck.style.color = 'var(--accent-green)';
      } else {
        lastAck.innerText = `Offline (${currentPdlMode} ${currentPdlLevel >= 0 ? '+' : ''}${currentPdlLevel} queued)`;
        lastAck.style.color = '#ffab00';
      }
    }
    if (data.connected && data.sent) {
      showAiSpeechToast(`⚡ Pedal Commander: ${currentPdlMode} (${currentPdlLevel >= 0 ? '+' : ''}${currentPdlLevel}) transmitted!`);
    } else {
      showAiSpeechToast(`⚠️ ${data.message || 'Pedal Commander BLE offline; target saved locally.'}`);
    }
  })
  .catch(err => {
    console.warn('Pedal commander send err:', err);
  });
}

function updatePdlBadge(isConnected, statusObj) {
  const badge = document.getElementById('pdlCommanderStatusBadge');
  const mac = (statusObj && statusObj.mac) ? statusObj.mac : '18:62:E4:46:73:8B';
  const transport = (statusObj && statusObj.transport) ? statusObj.transport.toUpperCase() : 'BLE';
  if (badge) {
    if (isConnected) {
      badge.innerText = `● CONNECTED (${transport} ${mac})`;
      badge.style.background = 'rgba(0,230,118,0.18)';
      badge.style.color = '#00e676';
      badge.style.borderColor = 'rgba(0,230,118,0.4)';
    } else {
      badge.innerText = `○ OFFLINE (BLE STANDBY • ${mac})`;
      badge.style.background = 'rgba(148,163,184,0.15)';
      badge.style.color = '#94a3b8';
      badge.style.borderColor = 'rgba(148,163,184,0.35)';
    }
  }
}

function savePdlPin() {
  const pinEl = document.getElementById('pdlPinInput');
  const macEl = document.getElementById('pdlMacInput');
  const pin = pinEl ? pinEl.value.trim() : '';
  const mac = macEl ? macEl.value.trim() : '';
  localStorage.setItem('carpi5_pdl_pin', pin);
  fetch('/api/pedal_commander/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mac: mac || undefined, pin: pin })
  })
  .then(r => r.json())
  .then(data => {
    updatePdlBadge(Boolean(data.connected), data);
    if (data.connected) {
      showAiSpeechToast(`Pedal Commander config synced (${data.mac}).`);
      sendPdlCommand();
    } else {
      showAiSpeechToast(`Pedal Commander config saved (${data.mac}); BLE currently offline.`);
    }
  })
  .catch(() => {});
}

function scanPedalCommanderBle() {
  const lastAck = document.getElementById('pdlLastAck');
  if (lastAck) { lastAck.innerText = 'Scanning BLE...'; lastAck.style.color = '#38bdf8'; }
  fetch('/api/pedal_commander/scan')
    .then(r => r.json())
    .then(data => {
      const devs = (data && Array.isArray(data.devices)) ? data.devices : [];
      if (devs.length === 0) {
        if (lastAck) { lastAck.innerText = data.message || 'No BLE devices found'; lastAck.style.color = '#ffab00'; }
        showAiSpeechToast(data.message || 'No BLE Pedal Commander units detected.');
        return;
      }
      const best = devs[0];
      const macEl = document.getElementById('pdlMacInput');
      if (macEl) macEl.value = best.mac;
      if (lastAck) { lastAck.innerText = `Found ${best.name} (${best.mac})`; lastAck.style.color = '#00e676'; }
      showAiSpeechToast(`Found BLE: ${best.name} (${best.mac}). Tap SAVE to bind.`);
    })
    .catch(() => {});
}

function pollPedalCommanderStatus() {
  fetch('/api/pedal_commander/status')
    .then(r => r.json())
    .then(data => {
      updatePdlBadge(Boolean(data.connected), data);
      const macEl = document.getElementById('pdlMacInput');
      if (macEl && !macEl.value && data.mac) macEl.value = data.mac;
      const lastAck = document.getElementById('pdlLastAck');
      if (lastAck && data.last_ack) {
        lastAck.innerText = data.last_ack;
        lastAck.style.color = data.connected ? 'var(--accent-green)' : '#94a3b8';
      }
      if (data.mode && data.mode !== currentPdlMode) {
        currentPdlMode = data.mode;
        updatePdlUI();
      }
      if (data.level !== undefined && data.level !== currentPdlLevel) {
        currentPdlLevel = data.level;
        updatePdlUI();
      }
    })
    .catch(() => {});
}
// Poll Pedal Commander status every 5 seconds
setInterval(pollPedalCommanderStatus, 5000);
setTimeout(pollPedalCommanderStatus, 1500);

function setPdlMode(mode) {
  currentPdlMode = mode;
  updatePdlUI();
  sendPdlCommand();
}

function adjustPdlLevel(delta) {
  currentPdlLevel = Math.max(-4, Math.min(4, currentPdlLevel + delta));
  updatePdlUI();
  sendPdlCommand();
}

function updatePdlUI() {
  ['Eco', 'City', 'Sport', 'SportPlus'].forEach(m => {
    const btn = document.getElementById(`btnPdl${m}`);
    if (btn) {
      if (m.toUpperCase().replace('PLUS', '_PLUS') === currentPdlMode.replace('SPORT+', 'SPORT_PLUS')) {
        btn.classList.add('active');
        btn.style.boxShadow = '0 0 10px rgba(255,119,0,0.5)';
      } else {
        btn.classList.remove('active');
        btn.style.boxShadow = 'none';
      }
    }
  });
  const disp = document.getElementById('pdlLevelDisplay');
  if (disp) {
    disp.innerText = (currentPdlLevel >= 0 ? '+' : '') + currentPdlLevel;
    disp.style.color = currentPdlLevel > 0 ? '#ff7700' : (currentPdlLevel < 0 ? '#00e676' : '#fff');
  }
}
