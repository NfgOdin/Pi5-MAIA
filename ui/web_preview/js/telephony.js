// ============================================================================
// PHASE 15: COCKPIT TELEPHONY, KINSHIP & SMS STUDIO ENGINE
// ============================================================================
let currentPhoneTab = 'history';
let activeSmsThreadNumber = '';
let activeCallPollingInterval = null;

function initPhoneStudio() {
  loadPhoneStatus();
  loadPhoneContacts();
  switchPhoneTab(currentPhoneTab);
}

function loadPhoneStatus() {
  fetch('/api/phone/status')
    .then(r => r.json())
    .then(d => {
      if (!d || !d.phone) return;
      updatePhoneUI(d.phone);
    })
    .catch(e => console.error('[PHONE] Status error:', e));
}

function updatePhoneUI(phone) {
  const badge = document.getElementById('phoneConnectionBadge');
  if (badge) {
    if (phone.connected) {
      badge.innerText = `📱 ${phone.device_name || 'PHONE CONNECTED'}`;
      badge.style.color = '#38bdf8';
      badge.style.borderColor = '#0284c7';
    } else {
      badge.innerText = '📱 BLUETOOTH HFP: STANDBY';
      badge.style.color = '#94a3b8';
      badge.style.borderColor = '#334155';
    }
  }

  const hud = document.getElementById('floatingInCallHud');
  if (!hud) return;

  const state = phone.state || 'IDLE';
  if (state === 'IDLE') {
    hud.style.display = 'none';
    if (activeCallPollingInterval) {
      clearInterval(activeCallPollingInterval);
      activeCallPollingInterval = null;
    }
    return;
  }

  // Call is RINGING, ACTIVE, or SCREENING -> Show Floating HUD
  hud.style.display = 'block';
  if (!activeCallPollingInterval) {
    activeCallPollingInterval = setInterval(loadPhoneStatus, 1000);
  }

  const nameEl = document.getElementById('incallCallerName');
  const badgeEl = document.getElementById('incallKinshipBadge');
  const numEl = document.getElementById('incallCallerNumber');
  const timerEl = document.getElementById('incallCallTimer');
  const statusEl = document.getElementById('incallStatusText');
  const screenBox = document.getElementById('incallScreeningBox');
  const transcriptEl = document.getElementById('incallLiveTranscript');
  const muteBtn = document.getElementById('btnIncallMute');
  const answerBtn = document.getElementById('btnIncallAnswer');
  const screenBtn = document.getElementById('btnIncallScreen');

  if (nameEl) nameEl.innerText = phone.caller_name || phone.caller_number || 'Incoming Call';
  if (badgeEl) badgeEl.innerText = phone.caller_kinship || 'CALL';
  if (numEl) numEl.innerText = phone.caller_number || '';

  if (timerEl) {
    const sec = phone.duration_sec || 0;
    const mins = Math.floor(sec / 60);
    const remSec = sec % 60;
    timerEl.innerText = `${mins.toString().padStart(2, '0')}:${remSec.toString().padStart(2, '0')}`;
  }

  if (statusEl) statusEl.innerText = state;

  if (state === 'RINGING_INBOUND') {
    if (answerBtn) answerBtn.style.display = 'flex';
    if (screenBtn) screenBtn.style.display = 'flex';
    if (muteBtn) muteBtn.style.display = 'none';
    if (screenBox) screenBox.style.display = 'none';
  } else if (state === 'SCREENING') {
    if (answerBtn) {
      answerBtn.style.display = 'flex';
      answerBtn.innerHTML = '<span>📞</span> <span>TAKE OVER CALL</span>';
    }
    if (screenBtn) screenBtn.style.display = 'none';
    if (muteBtn) muteBtn.style.display = 'none';
    if (screenBox) {
      screenBox.style.display = 'block';
      if (transcriptEl) transcriptEl.innerText = phone.live_screening_transcript || 'Listening to caller...';
    }
  } else if (state === 'ACTIVE' || state === 'DIALING_OUTBOUND') {
    if (answerBtn) answerBtn.style.display = 'none';
    if (screenBtn) screenBtn.style.display = 'none';
    if (muteBtn) {
      muteBtn.style.display = 'flex';
      const mText = document.getElementById('incallMuteText');
      if (mText) mText.innerText = phone.is_muted ? 'UNMUTE' : 'MUTE';
    }
    if (screenBox) screenBox.style.display = 'none';
  }
}

function dialpadPress(digit) {
  const disp = document.getElementById('dialerInputDisplay');
  if (disp) disp.innerText += digit;
}

function dialpadBackspace() {
  const disp = document.getElementById('dialerInputDisplay');
  if (disp && disp.innerText.length > 0) {
    disp.innerText = disp.innerText.slice(0, -1);
  }
}

function dialpadCall() {
  const disp = document.getElementById('dialerInputDisplay');
  const number = disp ? disp.innerText.trim() : '';
  if (!number) return;
  phoneDial(number);
}

function phoneDial(number) {
  fetch('/api/phone/dial', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ number })
  })
    .then(r => r.json())
    .then(() => loadPhoneStatus())
    .catch(e => console.error('[PHONE] Dial error:', e));
}

function phoneAnswerCall() {
  fetch('/api/phone/answer', { method: 'POST' })
    .then(r => r.json())
    .then(() => loadPhoneStatus());
}

function phoneHangupCall() {
  fetch('/api/phone/hangup', { method: 'POST' })
    .then(r => r.json())
    .then(() => loadPhoneStatus());
}

function phoneScreenCall() {
  fetch('/api/phone/screen', { method: 'POST' })
    .then(r => r.json())
    .then(() => loadPhoneStatus());
}

function phoneToggleMute() {
  fetch('/api/phone/mute', { method: 'POST' })
    .then(r => r.json())
    .then(() => loadPhoneStatus());
}

function loadPhoneContacts() {
  fetch('/api/phone/contacts')
    .then(r => r.json())
    .then(d => {
      if (!d || !d.contacts) return;
      renderKinshipQuickPills(d.contacts);
      renderContactsDirectory(d.contacts);
    });
}

function renderKinshipQuickPills(contacts) {
  const container = document.getElementById('phoneKinshipQuickPills');
  if (!container) return;
  if (!contacts || contacts.length === 0) {
    container.innerHTML = '<div style="grid-column:span 2; font-size:11px; color:#94a3b8;">No kinship contacts configured.</div>';
    return;
  }
  container.innerHTML = contacts.map(c => `
    <div class="kinship-pill" onclick="phoneDial('${c.phone}')" title="Call ${c.kinship} (${c.phone})">
      <span style="font-size:22px;">${c.avatar_icon || '👤'}</span>
      <div style="overflow:hidden;">
        <div style="font-size:12px; font-weight:900; white-space:nowrap; text-overflow:ellipsis; overflow:hidden;">${c.kinship || c.name}</div>
        <div style="font-size:9px; color:#94a3b8;">${c.name}</div>
      </div>
    </div>
  `).join('');
}

function renderContactsDirectory(contacts) {
  const container = document.getElementById('phoneContactsList');
  if (!container) return;
  container.innerHTML = contacts.map(c => `
    <div class="call-log-card">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:24px;">${c.avatar_icon || '👤'}</span>
        <div>
          <div style="font-size:13px; font-weight:800; color:#fff;">${c.kinship} (${c.name})</div>
          <div style="font-size:11px; color:#94a3b8;">${c.phone} • ${c.relationship || 'Family'}</div>
        </div>
      </div>
      <div style="display:flex; gap:6px;">
        <button class="cluster-action-btn" onclick="phoneDial('${c.phone}')" style="min-height:36px; padding:4px 12px; font-size:11px; border-color:#10b981; color:#10b981;">CALL</button>
        <button class="cluster-action-btn" onclick="deleteContact('${c.id}')" style="min-height:36px; padding:4px 10px; font-size:11px; border-color:#ef4444; color:#ef4444;">DELETE</button>
      </div>
    </div>
  `).join('');
}

function switchPhoneTab(tab) {
  currentPhoneTab = tab;
  const btnHist = document.getElementById('btnPhoneTabHistory');
  const btnSms = document.getElementById('btnPhoneTabSms');
  const btnContacts = document.getElementById('btnPhoneTabContacts');

  const viewHist = document.getElementById('phoneViewHistory');
  const viewSms = document.getElementById('phoneViewSms');
  const viewContacts = document.getElementById('phoneViewContacts');

  if (btnHist) btnHist.classList.toggle('active', tab === 'history');
  if (btnSms) btnSms.classList.toggle('active', tab === 'sms');
  if (btnContacts) btnContacts.classList.toggle('active', tab === 'contacts');

  if (viewHist) viewHist.style.display = tab === 'history' ? 'flex' : 'none';
  if (viewSms) viewSms.style.display = tab === 'sms' ? 'flex' : 'none';
  if (viewContacts) viewContacts.style.display = tab === 'contacts' ? 'flex' : 'none';

  if (tab === 'history') loadCallHistory();
  if (tab === 'sms') loadSmsThreads();
  if (tab === 'contacts') loadPhoneContacts();
}

function loadCallHistory() {
  fetch('/api/phone/history')
    .then(r => r.json())
    .then(d => {
      const container = document.getElementById('phoneHistoryList');
      if (!container) return;
      const hist = (d.history || []).slice().reverse();
      if (hist.length === 0) {
        container.innerHTML = '<div style="text-align:center; padding:30px; color:#94a3b8;">No call history yet.</div>';
        return;
      }
      container.innerHTML = hist.map(call => {
        const dStr = new Date(call.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return `
          <div class="call-log-card">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-size:20px;">${call.was_screened ? '🛡️' : '📞'}</span>
              <div>
                <div style="font-size:12px; font-weight:800; color:#fff;">${call.kinship || call.name || call.number}</div>
                <div style="font-size:10px; color:#94a3b8;">${dStr} • Duration: ${call.duration_sec}s ${call.notes ? '• Note: ' + call.notes : ''}</div>
              </div>
            </div>
            <button class="cluster-action-btn" onclick="phoneDial('${call.number}')" style="min-height:36px; padding:4px 10px; font-size:10px; border-color:#38bdf8; color:#38bdf8;">REDIAL</button>
          </div>
        `;
      }).join('');
    });
}

function loadSmsThreads() {
  fetch('/api/sms/threads')
    .then(r => r.json())
    .then(d => {
      const listEl = document.getElementById('smsThreadsList');
      if (!listEl) return;
      const threads = d.threads || {};
      const keys = Object.keys(threads);
      if (keys.length === 0) {
        listEl.innerHTML = '<div style="font-size:11px; color:#94a3b8; padding:8px;">No SMS conversations.</div>';
        return;
      }
      listEl.innerHTML = keys.map(k => `
        <div class="kinship-pill" style="min-height:44px; padding:6px 8px; ${activeSmsThreadNumber === k ? 'border-color:#38bdf8; background:#0c4a6e;' : ''}" onclick="selectSmsThread('${k}')">
          <div style="font-size:11px; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${k}</div>
        </div>
      `).join('');

      if (!activeSmsThreadNumber && keys.length > 0) {
        selectSmsThread(keys[0]);
      }
    });
}

function selectSmsThread(number) {
  activeSmsThreadNumber = number;
  loadSmsThreads();
  fetch(`/api/sms/thread?number=${encodeURIComponent(number)}`)
    .then(r => r.json())
    .then(d => {
      const msgList = document.getElementById('smsMessagesList');
      if (!msgList) return;
      const msgs = d.thread || [];
      if (msgs.length === 0) {
        msgList.innerHTML = '<div style="text-align:center; padding:20px; color:#94a3b8;">Empty thread. Send a text below!</div>';
        return;
      }
      msgList.innerHTML = msgs.map(m => `
        <div class="${m.direction === 'OUTBOUND' ? 'sms-bubble-outbound' : 'sms-bubble-inbound'}">
          <div style="font-size:9px; opacity:0.7; margin-bottom:2px;">${m.sender_kinship || m.sender_name || m.sender}</div>
          <div>${m.text}</div>
        </div>
      `).join('');
      msgList.scrollTop = msgList.scrollHeight;
    });
}

function submitSendSms() {
  const input = document.getElementById('smsTextInput');
  const text = input ? input.value.trim() : '';
  if (!text || !activeSmsThreadNumber) return;

  fetch('/api/sms/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recipient: activeSmsThreadNumber, text })
  })
    .then(r => r.json())
    .then(() => {
      if (input) input.value = '';
      selectSmsThread(activeSmsThreadNumber);
    });
}

function openAddContactModal() {
  const m = document.getElementById('phoneAddContactModal');
  if (m) m.style.display = 'flex';
}

function closeAddContactModal() {
  const m = document.getElementById('phoneAddContactModal');
  if (m) m.style.display = 'none';
}

function submitAddContact() {
  const name = document.getElementById('contactNameInput')?.value.trim();
  const kinship = document.getElementById('contactKinshipInput')?.value.trim();
  const phone = document.getElementById('contactPhoneInput')?.value.trim();
  const icon = document.getElementById('contactIconInput')?.value.trim() || '👤';
  if (!name || !phone) return;

  fetch('/api/phone/contacts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contact: { name, kinship: kinship || name, phone, avatar_icon: icon, direct_announce: true, vip: true }
    })
  })
    .then(r => r.json())
    .then(() => {
      closeAddContactModal();
      loadPhoneContacts();
    });
}

function deleteContact(id) {
  fetch('/api/phone/contacts/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id })
  })
    .then(r => r.json())
    .then(() => loadPhoneContacts());
}

function phoneSimulateInboundModal() {
  const m = document.getElementById('phoneSimulateModal');
  if (m) m.style.display = 'flex';
}

function closeSimulateModal() {
  const m = document.getElementById('phoneSimulateModal');
  if (m) m.style.display = 'none';
}

function phoneSimulateInbound(number) {
  closeSimulateModal();
  fetch('/api/phone/incoming', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ number })
  })
    .then(r => r.json())
    .then(() => loadPhoneStatus());
}

setTimeout(loadPhoneStatus, 2000);
