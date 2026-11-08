/**
 * CarPi5 Automotive Pop-Up Touchscreen Virtual Keyboard
 * Designed specifically for 1024x600 in-dash touch display
 * Supports: QWERTY, Uppercase/Caps, Symbols/Numbers, Audio feedback,
 * auto-scroll into view, repeat backspace, and universal input synchronization.
 */

let vkActiveInput = null;
let vkMode = 'LOWER'; // 'LOWER', 'UPPER', 'SYMBOLS'
let vkShiftLocked = false;
let vkShiftLastTap = 0;
let vkSoundEnabled = true;
let vkMaskPassword = true;
let vkAudioCtx = null;
let vkBackspaceTimer = null;
let vkBackspaceInterval = null;

// Layout definitions
const VK_LAYOUTS = {
  LOWER: [
    [
      { id: '1', label: '1' }, { id: '2', label: '2' }, { id: '3', label: '3' },
      { id: '4', label: '4' }, { id: '5', label: '5' }, { id: '6', label: '6' },
      { id: '7', label: '7' }, { id: '8', label: '8' }, { id: '9', label: '9' },
      { id: '0', label: '0' }, { id: 'backspace', label: '⌫', cls: 'tk-key-fn tk-key-backspace' }
    ],
    [
      { id: 'q', label: 'q' }, { id: 'w', label: 'w' }, { id: 'e', label: 'e' },
      { id: 'r', label: 'r' }, { id: 't', label: 't' }, { id: 'y', label: 'y' },
      { id: 'u', label: 'u' }, { id: 'i', label: 'i' }, { id: 'o', label: 'o' },
      { id: 'p', label: 'p' }
    ],
    [
      { id: 'a', label: 'a' }, { id: 's', label: 's' }, { id: 'd', label: 'd' },
      { id: 'f', label: 'f' }, { id: 'g', label: 'g' }, { id: 'h', label: 'h' },
      { id: 'j', label: 'j' }, { id: 'k', label: 'k' }, { id: 'l', label: 'l' },
      { id: '-', label: '-' }
    ],
    [
      { id: 'shift', label: '⇧ SHIFT', cls: 'tk-key-fn tk-key-shift' },
      { id: 'z', label: 'z' }, { id: 'x', label: 'x' }, { id: 'c', label: 'c' },
      { id: 'v', label: 'v' }, { id: 'b', label: 'b' }, { id: 'n', label: 'n' },
      { id: 'm', label: 'm' }, { id: ',', label: ',' }, { id: '.', label: '.' },
      { id: 'enter', label: '↵ ENTER', cls: 'tk-key-enter' }
    ],
    [
      { id: 'symbols', label: '?123', cls: 'tk-key-fn tk-key-mode' },
      { id: '@', label: '@', cls: 'tk-key-quick' },
      { id: 'space', label: 'SPACE', cls: 'tk-key-space' },
      { id: '_', label: '_', cls: 'tk-key-quick' },
      { id: '.com', label: '.com', cls: 'tk-key-fn tk-key-quick' },
      { id: 'hide', label: '⬇ HIDE', cls: 'tk-key-fn' }
    ]
  ],

  UPPER: [
    [
      { id: '!', label: '!' }, { id: '@', label: '@' }, { id: '#', label: '#' },
      { id: '$', label: '$' }, { id: '%', label: '%' }, { id: '^', label: '^' },
      { id: '&', label: '&' }, { id: '*', label: '*' }, { id: '(', label: '(' },
      { id: ')', label: ')' }, { id: 'backspace', label: '⌫', cls: 'tk-key-fn tk-key-backspace' }
    ],
    [
      { id: 'Q', label: 'Q' }, { id: 'W', label: 'W' }, { id: 'E', label: 'E' },
      { id: 'R', label: 'R' }, { id: 'T', label: 'T' }, { id: 'Y', label: 'Y' },
      { id: 'U', label: 'U' }, { id: 'I', label: 'I' }, { id: 'O', label: 'O' },
      { id: 'P', label: 'P' }
    ],
    [
      { id: 'A', label: 'A' }, { id: 'S', label: 'S' }, { id: 'D', label: 'D' },
      { id: 'F', label: 'F' }, { id: 'G', label: 'G' }, { id: 'H', label: 'H' },
      { id: 'J', label: 'J' }, { id: 'K', label: 'K' }, { id: 'L', label: 'L' },
      { id: '_', label: '_' }
    ],
    [
      { id: 'shift', label: '⇧ SHIFT', cls: 'tk-key-fn tk-key-shift shift-active' },
      { id: 'Z', label: 'Z' }, { id: 'X', label: 'X' }, { id: 'C', label: 'C' },
      { id: 'V', label: 'V' }, { id: 'B', label: 'B' }, { id: 'N', label: 'N' },
      { id: 'M', label: 'M' }, { id: '<', label: '<' }, { id: '>', label: '>' },
      { id: 'enter', label: '↵ ENTER', cls: 'tk-key-enter' }
    ],
    [
      { id: 'symbols', label: '?123', cls: 'tk-key-fn tk-key-mode' },
      { id: '@', label: '@', cls: 'tk-key-quick' },
      { id: 'space', label: 'SPACE', cls: 'tk-key-space' },
      { id: '-', label: '-', cls: 'tk-key-quick' },
      { id: '.com', label: '.com', cls: 'tk-key-fn tk-key-quick' },
      { id: 'hide', label: '⬇ HIDE', cls: 'tk-key-fn' }
    ]
  ],

  SYMBOLS: [
    [
      { id: '1', label: '1' }, { id: '2', label: '2' }, { id: '3', label: '3' },
      { id: '4', label: '4' }, { id: '5', label: '5' }, { id: '6', label: '6' },
      { id: '7', label: '7' }, { id: '8', label: '8' }, { id: '9', label: '9' },
      { id: '0', label: '0' }, { id: 'backspace', label: '⌫', cls: 'tk-key-fn tk-key-backspace' }
    ],
    [
      { id: '~', label: '~' }, { id: '`', label: '`' }, { id: '!', label: '!' },
      { id: '@', label: '@' }, { id: '#', label: '#' }, { id: '$', label: '$' },
      { id: '%', label: '%' }, { id: '^', label: '^' }, { id: '&', label: '&' },
      { id: '*', label: '*' }
    ],
    [
      { id: '(', label: '(' }, { id: ')', label: ')' }, { id: '+', label: '+' },
      { id: '=', label: '=' }, { id: '{', label: '{' }, { id: '}', label: '}' },
      { id: '[', label: '[' }, { id: ']', label: ']' }, { id: '\\', label: '\\' },
      { id: '|', label: '|' }
    ],
    [
      { id: 'abc', label: 'ABC', cls: 'tk-key-fn tk-key-shift' },
      { id: ':', label: ':' }, { id: ';', label: ';' }, { id: '"', label: '"' },
      { id: "'", label: "'" }, { id: '?', label: '?' }, { id: '/', label: '/' },
      { id: '<', label: '<' }, { id: '>', label: '>' },
      { id: 'enter', label: '↵ ENTER', cls: 'tk-key-enter' }
    ],
    [
      { id: 'abc', label: 'ABC', cls: 'tk-key-fn tk-key-mode' },
      { id: '/', label: '/', cls: 'tk-key-quick' },
      { id: 'space', label: 'SPACE', cls: 'tk-key-space' },
      { id: '=', label: '=', cls: 'tk-key-quick' },
      { id: '.org', label: '.org', cls: 'tk-key-fn tk-key-quick' },
      { id: 'hide', label: '⬇ HIDE', cls: 'tk-key-fn' }
    ]
  ]
};

// Web Audio Key Click
function vkPlayKeyClick() {
  if (!vkSoundEnabled) return;
  try {
    if (!vkAudioCtx) {
      vkAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (vkAudioCtx.state === 'suspended') {
      vkAudioCtx.resume();
    }
    const osc = vkAudioCtx.createOscillator();
    const gain = vkAudioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(1100, vkAudioCtx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(180, vkAudioCtx.currentTime + 0.022);
    gain.gain.setValueAtTime(0.06, vkAudioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, vkAudioCtx.currentTime + 0.022);
    osc.connect(gain);
    gain.connect(vkAudioCtx.destination);
    osc.start();
    osc.stop(vkAudioCtx.currentTime + 0.022);
  } catch (e) {}
}

// Render the keyboard grid
function vkRenderKeys() {
  const body = document.getElementById('tkKeysBody');
  if (!body) return;

  const rows = VK_LAYOUTS[vkMode] || VK_LAYOUTS.LOWER;
  let html = '';

  rows.forEach((row, rIdx) => {
    html += '<div class="tk-row">';
    row.forEach(k => {
      let cls = 'tk-key ' + (k.cls || '');
      if (k.id === 'shift') {
        if (vkShiftLocked) {
          cls += ' caps-locked';
        } else if (vkMode === 'UPPER') {
          cls += ' shift-active';
        }
      }
      html += `<div class="${cls}" data-key="${k.id}">${k.label}</div>`;
    });
    html += '</div>';
  });

  body.innerHTML = html;
  vkAttachKeyEvents();
}

function vkAttachKeyEvents() {
  const body = document.getElementById('tkKeysBody');
  if (!body) return;

  const keys = body.querySelectorAll('.tk-key');
  keys.forEach(k => {
    const keyId = k.getAttribute('data-key');

    // Special hold repeat for backspace
    if (keyId === 'backspace') {
      const startDelete = (e) => {
        e.preventDefault();
        e.stopPropagation();
        vkPlayKeyClick();
        k.classList.add('active-tap');
        vkHandleKey('backspace');

        clearTimeout(vkBackspaceTimer);
        clearInterval(vkBackspaceInterval);

        vkBackspaceTimer = setTimeout(() => {
          vkBackspaceInterval = setInterval(() => {
            vkPlayKeyClick();
            vkHandleKey('backspace');
          }, 65);
        }, 320);
      };

      const stopDelete = (e) => {
        k.classList.remove('active-tap');
        clearTimeout(vkBackspaceTimer);
        clearInterval(vkBackspaceInterval);
      };

      k.addEventListener('pointerdown', startDelete);
      k.addEventListener('pointerup', stopDelete);
      k.addEventListener('pointercancel', stopDelete);
      k.addEventListener('pointerleave', stopDelete);
    } else {
      k.addEventListener('pointerdown', (e) => {
        e.preventDefault();
        e.stopPropagation();
        vkPlayKeyClick();
        k.classList.add('active-tap');
        vkHandleKey(keyId);
      });

      const clearTap = () => k.classList.remove('active-tap');
      k.addEventListener('pointerup', clearTap);
      k.addEventListener('pointercancel', clearTap);
      k.addEventListener('pointerleave', clearTap);
    }
  });
}

function vkHandleKey(keyId) {
  if (!vkActiveInput) return;

  switch (keyId) {
    case 'shift':
      const now = Date.now();
      if (now - vkShiftLastTap < 320) {
        // Double tap: toggle Caps Lock!
        vkShiftLocked = !vkShiftLocked;
        vkMode = vkShiftLocked ? 'UPPER' : 'LOWER';
      } else {
        if (vkShiftLocked) {
          vkShiftLocked = false;
          vkMode = 'LOWER';
        } else {
          vkMode = vkMode === 'UPPER' ? 'LOWER' : 'UPPER';
        }
      }
      vkShiftLastTap = now;
      vkRenderKeys();
      break;

    case 'symbols':
      vkMode = 'SYMBOLS';
      vkRenderKeys();
      break;

    case 'abc':
      vkMode = vkShiftLocked ? 'UPPER' : 'LOWER';
      vkRenderKeys();
      break;

    case 'space':
      vkInsertText(' ');
      break;

    case 'backspace':
      vkBackspace();
      break;

    case 'enter':
      vkSubmitEnter();
      break;

    case 'hide':
      vkCloseKeyboard();
      break;

    default:
      vkInsertText(keyId);
      // Auto-revert shift after typing single character if not caps locked
      if (vkMode === 'UPPER' && !vkShiftLocked) {
        vkMode = 'LOWER';
        vkRenderKeys();
      }
      break;
  }
}

function vkInsertText(text) {
  if (!vkActiveInput) return;

  const el = vkActiveInput;
  const val = el.value || '';

  // Reliable cursor tracking: prevent selectionStart=0 collapse on touch
  let start = val.length;
  let end = val.length;

  if (typeof el._vkCursor === 'number') {
    start = el._vkCursor;
    end = el._vkCursor;
  } else {
    try {
      if (typeof el.selectionStart === 'number' && el.selectionStart > 0) {
        start = el.selectionStart;
        end = el.selectionEnd;
      }
    } catch (e) {}
  }

  // Bounds safety check
  start = Math.max(0, Math.min(val.length, start));
  end = Math.max(start, Math.min(val.length, end));

  el.value = val.substring(0, start) + text + val.substring(end);
  const nextPos = start + text.length;
  el._vkCursor = nextPos;
  try {
    el.selectionStart = el.selectionEnd = nextPos;
  } catch (e) {}

  vkDispatchInputEvents(el);
  vkUpdatePreview();
}

function vkBackspace() {
  if (!vkActiveInput) return;

  const el = vkActiveInput;
  const val = el.value || '';

  let start = val.length;
  let end = val.length;

  if (typeof el._vkCursor === 'number') {
    start = el._vkCursor;
    end = el._vkCursor;
  } else {
    try {
      if (typeof el.selectionStart === 'number' && el.selectionStart > 0) {
        start = el.selectionStart;
        end = el.selectionEnd;
      }
    } catch (e) {}
  }

  start = Math.max(0, Math.min(val.length, start));
  end = Math.max(start, Math.min(val.length, end));

  if (start !== end) {
    el.value = val.substring(0, start) + val.substring(end);
    el._vkCursor = start;
    try {
      el.selectionStart = el.selectionEnd = start;
    } catch (e) {}
  } else if (start > 0) {
    el.value = val.substring(0, start - 1) + val.substring(start);
    el._vkCursor = start - 1;
    try {
      el.selectionStart = el.selectionEnd = start - 1;
    } catch (e) {}
  }

  vkDispatchInputEvents(el);
  vkUpdatePreview();
}

function vkClearInput() {
  if (!vkActiveInput) return;
  vkActiveInput.value = '';
  vkActiveInput._vkCursor = 0;
  try {
    vkActiveInput.selectionStart = vkActiveInput.selectionEnd = 0;
  } catch (e) {}
  vkDispatchInputEvents(vkActiveInput);
  vkUpdatePreview();
}

function vkSubmitEnter() {
  if (!vkActiveInput) return;

  const el = vkActiveInput;

  // Dispatch Enter key events
  const enterDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
  const enterUp = new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true });
  el.dispatchEvent(enterDown);
  el.dispatchEvent(enterUp);

  // App-specific trigger hooks
  if (el.id === 'browserUrlInput' && typeof loadBrowserUrl === 'function') {
    loadBrowserUrl();
  } else if (el.id === 'chatInput' && typeof sendAiChatMessage === 'function') {
    sendAiChatMessage();
  } else if (el.id === 'modalWifiPassword' && typeof submitWifiConnect === 'function') {
    submitWifiConnect();
  } else if (el.id === 'modalGoogleClientId' && typeof submitModalClientIdAndStart === 'function') {
    submitModalClientIdAndStart();
  } else if (el.form) {
    // If inside a form, submit
    try {
      el.form.requestSubmit();
    } catch (e) {
      el.form.submit();
    }
  }

  vkCloseKeyboard();
}

function vkDispatchInputEvents(el) {
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function vkUpdatePreview() {
  const preview = document.getElementById('tkPreviewText');
  const label = document.getElementById('tkFieldLabel');
  const eyeBtn = document.getElementById('tkToggleMask');

  if (!vkActiveInput) {
    if (preview) preview.innerText = '';
    return;
  }

  const isPass = (vkActiveInput.type === 'password');
  if (eyeBtn) eyeBtn.style.display = isPass ? 'flex' : 'none';

  if (label) {
    let lblText = vkActiveInput.placeholder || vkActiveInput.getAttribute('aria-label') || vkActiveInput.id || 'INPUT';
    lblText = lblText.replace(/\.\.\.$/, '').toUpperCase();
    if (lblText.length > 22) lblText = lblText.substring(0, 20) + '..';
    label.innerText = lblText;
  }

  if (preview) {
    const val = vkActiveInput.value || '';
    if (isPass && vkMaskPassword) {
      preview.innerText = '•'.repeat(val.length);
    } else {
      preview.innerText = val;
    }
  }
}

function vkToggleMask() {
  vkMaskPassword = !vkMaskPassword;
  const eyeBtn = document.getElementById('tkToggleMask');
  if (eyeBtn) eyeBtn.innerText = vkMaskPassword ? '👁️' : '🔒';
  vkUpdatePreview();
}

function vkToggleSound() {
  vkSoundEnabled = !vkSoundEnabled;
  const btn = document.getElementById('tkSoundBtn');
  if (btn) btn.innerText = vkSoundEnabled ? '🔊' : '🔇';
}

function openVirtualKeyboard(inputEl) {
  if (!inputEl) return;
  vkActiveInput = inputEl;

  // Select initial mode based on input type
  if (inputEl.type === 'number') {
    vkMode = 'SYMBOLS';
  } else {
    vkMode = vkShiftLocked ? 'UPPER' : 'LOWER';
  }

  const kb = document.getElementById('virtualTouchKeyboard');
  if (!kb) return;

  kb.style.display = 'flex';
  // Small delay to trigger smooth CSS slide animation
  requestAnimationFrame(() => {
    kb.classList.remove('hidden');
    kb.classList.add('visible');
    document.body.classList.add('keyboard-open');
  });

  vkRenderKeys();
  vkUpdatePreview();

  // Smooth scroll active element into visible top area
  setTimeout(() => {
    try {
      inputEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } catch (e) {}
  }, 120);
}

function vkCloseKeyboard() {
  const kb = document.getElementById('virtualTouchKeyboard');
  if (!kb) return;

  kb.classList.remove('visible');
  kb.classList.add('hidden');
  document.body.classList.remove('keyboard-open');

  clearTimeout(vkBackspaceTimer);
  clearInterval(vkBackspaceInterval);

  setTimeout(() => {
    if (kb.classList.contains('hidden')) {
      kb.style.display = 'none';
    }
  }, 250);

  if (vkActiveInput) {
    if (document.activeElement !== vkActiveInput) {
      try {
        vkActiveInput.blur();
      } catch (e) {}
    }
  }
  vkActiveInput = null;
}

// Check if element is an eligible text input
function isEligibleInput(el) {
  if (!el || !el.tagName) return false;
  const tag = el.tagName.toLowerCase();
  if (tag === 'textarea') return true;
  if (tag === 'input') {
    const type = (el.type || 'text').toLowerCase();
    const ignored = ['checkbox', 'radio', 'range', 'file', 'hidden', 'button', 'submit', 'reset', 'image', 'color'];
    return !ignored.includes(type);
  }
  return false;
}

// Track the most recent pointer interaction to distinguish touchscreen taps vs physical mouse clicks
let vkLastPointerType = ('ontouchstart' in window && navigator.maxTouchPoints > 0) ? 'touch' : 'mouse';

// Universal initialization & listeners
function initVirtualKeyboard() {
  const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0) || (window.matchMedia && window.matchMedia('(pointer: coarse)').matches);

  // Track pointer movements/clicks to know whether user is actively using a mouse or finger
  window.addEventListener('pointermove', (e) => {
    if (e.pointerType) vkLastPointerType = e.pointerType;
  }, { passive: true });

  // 1. Focusin listener - auto-open ONLY on touchscreen/pen taps. Physical mouse clicks never pop keyboard
  document.addEventListener('focusin', (e) => {
    if (isEligibleInput(e.target)) {
      if (vkLastPointerType === 'mouse') {
        // Physical mouse click: keep keyboard hidden so hardware keyboard types freely
        return;
      }
      if (vkLastPointerType === 'touch' || vkLastPointerType === 'pen') {
        openVirtualKeyboard(e.target);
      }
    }
  });

  // 2. Pointerdown listener with strict mouse vs touch discrimination
  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType) vkLastPointerType = e.pointerType;
    const kb = document.getElementById('virtualTouchKeyboard');
    if (kb && kb.contains(e.target)) return;

    if (isEligibleInput(e.target)) {
      if (e.pointerType === 'mouse' || vkLastPointerType === 'mouse') {
        // User clicked with physical mouse - dismiss virtual keyboard if open
        if (kb && kb.classList.contains('visible')) {
          vkCloseKeyboard();
        }
        return;
      }
      // Touch or pen tap on touchscreen - slide up virtual keyboard
      if (e.pointerType === 'touch' || e.pointerType === 'pen' || isTouchDevice) {
        openVirtualKeyboard(e.target);
      }
    } else if (kb && kb.classList.contains('visible')) {
      if (e.target !== vkActiveInput) {
        vkCloseKeyboard();
      }
    }
  });

  // 3. Keep preview synchronized with physical keyboard typing
  document.addEventListener('input', (e) => {
    if (isEligibleInput(e.target)) {
      if (vkActiveInput === e.target) {
        vkActiveInput._vkCursor = e.target.selectionEnd || e.target.value.length;
        vkUpdatePreview();
      }
    }
  });

  // 4. Auto-dismiss touch keyboard when physical typing is detected
  window.addEventListener('keydown', (e) => {
    const kb = document.getElementById('virtualTouchKeyboard');
    if (kb && kb.classList.contains('visible')) {
      if (e.key && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        vkCloseKeyboard();
      }
    }
  });

  // Render initial keyboard
  vkRenderKeys();
  console.log('[KEYBOARD] Touchscreen Virtual Keyboard initialized successfully.');
}

// Auto-run when DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initVirtualKeyboard);
} else {
  initVirtualKeyboard();
}

function toggleManualKeyboard() {
  const kb = document.getElementById('virtualTouchKeyboard');
  const activeScreen = document.querySelector('.screen-view.active');
  const isBrowserScreen = activeScreen && (activeScreen.id === 'screenBrowser' || activeScreen.id === 'screenGames');

  if (kb && kb.classList.contains('visible')) {
    vkCloseKeyboard();
  } else {
    if (!vkActiveInput) {
      const candidate = activeScreen ? activeScreen.querySelector('input:not([type="checkbox"]):not([type="radio"]):not([type="range"]), textarea') : null;
      if (candidate) {
        candidate.focus();
        return;
      }
    }
    openVirtualKeyboard(vkActiveInput || document.getElementById('browserUrlInput') || document.getElementById('chatInput'));
  }

  // Also notify backend to toggle OS-level wvkbd overlay if in fullscreen or browser mode
  if (isBrowserScreen) {
    fetch('/api/system/keyboard/toggle').catch(() => {});
  }
}
