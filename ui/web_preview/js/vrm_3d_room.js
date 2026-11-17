// CarPi5 UI Module: 3D VRM Avatar Engine, Pip Connectome, Environments, Room Customizer & Floating HUD

// --- PHASE 3: COLLAPSIBLE VRM CONTROLS BAR & ROOM CHAT HELPERS ---

function toggleVrmControlsBar() {
  const bar = document.getElementById('vrmControlsBar');
  const chevron = document.getElementById('vrmControlsChevron');
  const label = document.getElementById('vrmControlsLabel');
  if (!bar) return;
  const isCollapsed = bar.classList.toggle('collapsed');
  localStorage.setItem('carpi5_vrm_ctrls_collapsed', isCollapsed ? '1' : '0');
  if (chevron) chevron.innerText = isCollapsed ? '▼' : '▲';
  if (label) label.innerText = isCollapsed ? 'CONTROLS' : 'HIDE';
}

function initVrmControlsBarState() {
  const saved = localStorage.getItem('carpi5_vrm_ctrls_collapsed');
  const bar = document.getElementById('vrmControlsBar');
  const chevron = document.getElementById('vrmControlsChevron');
  const label = document.getElementById('vrmControlsLabel');
  if (!bar) return;
  if (saved !== '0') {
    bar.classList.add('collapsed');
    if (chevron) chevron.innerText = '▼';
    if (label) label.innerText = 'CONTROLS';
  } else {
    bar.classList.remove('collapsed');
    if (chevron) chevron.innerText = '▲';
    if (label) label.innerText = 'HIDE';
  }
}

function closeRoomFloatingChat() {
  const screen = document.getElementById('screenAI');
  if (screen) {
    screen.classList.add('chat-closed');
    localStorage.setItem('carpi5_room_chat_closed', '1');
  }
}

function openRoomFloatingChat() {
  const screen = document.getElementById('screenAI');
  if (screen) {
    screen.classList.remove('chat-closed');
    localStorage.setItem('carpi5_room_chat_closed', '0');
  }
}

// --- 60 FPS PROCEDURAL ANIME WAIFU BUST ENGINE (NICK JR. "FACE" STYLE) ---
let currentWaifuEmotion = "DEVOTED";
let isWaifuSpeaking = false;
let waifuSpeechEndTime = 0;
let waifuBlinkProgress = 0.0;
let isBlinking = false;
let blinkStartTime = 0;
let nextBlinkTime = Date.now() + 3200;

// Nick Jr. Face style gaze tracking & turning (Yaw / Parallax)
let targetLookX = -0.32; // Default looking at driver on left
let targetLookY = 0.04;
let currentLookX = -0.32;
let currentLookY = 0.04;
let nextGazeShiftTime = Date.now() + 2500;

// Physics sway for blonde twin-tails
let hairSwayAngle = 0.0;
let hairSwayVelocity = 0.0;

// Dynamic blush intensity (0.0 to 1.0)
let blushIntensity = 0.4;
let touchGiggleTime = 0;

function setWaifuEmotion(emo) {
  if (!emo) return;
  const upper = emo.toUpperCase().trim();
  const validEmotions = ["DEVOTED", "FLIRTY", "EXCITED", "CONCERNED", "HAPPY", "COZY", "HAPPY_PROUD", "THOUGHTFUL"];
  if (validEmotions.includes(upper)) {
    currentWaifuEmotion = upper;
  } else {
    currentWaifuEmotion = "DEVOTED";
  }

  const pill = document.getElementById('waifuEmotionPill');
  if (pill) {
    const isRum = (currentAiSettings.personality === 'RUM' || activeAvatarEngine === '3D_VRM');
    const pName = "R.U.M.";
    switch (currentWaifuEmotion) {
      case "DEVOTED":
        pill.innerText = `💖 ${pName} • DEVOTED & LISTENING`;
        pill.style.color = "var(--accent-pink)";
        pill.style.borderColor = "var(--accent-pink)";
        break;
      case "FLIRTY":
        pill.innerText = `💋 ${pName} • PLAYFUL & DEVOTED`;
        pill.style.color = "#ff4081";
        pill.style.borderColor = "#ff4081";
        break;
      case "EXCITED":
        pill.innerText = `⚡ ${pName} • EXCITED & BOOSTED`;
        pill.style.color = "var(--accent-yellow)";
        pill.style.borderColor = "var(--accent-yellow)";
        break;
      case "CONCERNED":
        pill.innerText = `⚠️ ${pName} • CARING & MONITORING`;
        pill.style.color = "var(--accent-orange)";
        pill.style.borderColor = "var(--accent-orange)";
        break;
      case "HAPPY":
        pill.innerText = `✨ ${pName} • JOYFUL & READY`;
        pill.style.color = "var(--accent-green)";
        pill.style.borderColor = "var(--accent-green)";
        break;
      case "COZY":
        pill.innerText = `☕ ${pName} • COZY & SLEEPY`;
        pill.style.color = "#a78bfa";
        pill.style.borderColor = "#a78bfa";
        break;
      case "HAPPY_PROUD":
        pill.innerText = `🌸 ${pName} • PROUD DAUGHTER`;
        pill.style.color = "#34d399";
        pill.style.borderColor = "#34d399";
        break;
      case "THOUGHTFUL":
        pill.innerText = `💭 ${pName} • SHOWER THOUGHTS`;
        pill.style.color = "#38bdf8";
        pill.style.borderColor = "#38bdf8";
        break;
    }
  }
}

function initWaifuTalkingHead() {
  const canvas = document.getElementById('waifuFaceCanvas');
  if (!canvas) {
    console.warn("[WAIFU] waifuFaceCanvas element not found in DOM!");
    return;
  }
  const ctx = canvas.getContext('2d');

  function renderWaifuFrame() {
    const now = Date.now();
    const t = now * 0.001;
    const w = canvas.width;
    const h = canvas.height;

    // Clear with 100% transparency - floating borderless bust
    ctx.clearRect(0, 0, w, h);

    if (now > waifuSpeechEndTime && (!eventSource || eventSource.readyState !== 1)) {
      isWaifuSpeaking = false;
      const stage = document.getElementById('waifuStage');
      if (stage) stage.classList.remove('speaking');
    }

    // Natural eye blinking (140ms sweep)
    if (!isBlinking && now > nextBlinkTime) {
      isBlinking = true;
      blinkStartTime = now;
    }
    if (isBlinking) {
      const dt = now - blinkStartTime;
      if (dt < 70) {
        waifuBlinkProgress = dt / 70;
      } else if (dt < 140) {
        waifuBlinkProgress = 1.0 - ((dt - 70) / 70);
      } else {
        waifuBlinkProgress = 0.0;
        isBlinking = false;
        nextBlinkTime = now + 3200 + Math.random() * 2400;
      }
    }

    // Dynamic Saccadic Gaze Tracking (Driver attention, road glances)
    if (now > nextGazeShiftTime) {
      if (isWaifuSpeaking) {
        targetLookX = -0.35 + (Math.random() - 0.5) * 0.15; // Focused lovingly on driver
        targetLookY = 0.04 + (Math.random() - 0.5) * 0.12;
      } else {
        const rnd = Math.random();
        if (rnd < 0.65) {
          targetLookX = -0.32 + (Math.random() - 0.5) * 0.2; // Driver seat
          targetLookY = 0.04 + (Math.random() - 0.5) * 0.15;
        } else if (rnd < 0.88) {
          targetLookX = 0.15 + (Math.random() - 0.5) * 0.25; // Glance out windshield
          targetLookY = -0.08 + (Math.random() - 0.5) * 0.15;
        } else {
          targetLookX = -0.05; // Center console
          targetLookY = 0.18;
        }
      }
      nextGazeShiftTime = now + 2500 + Math.random() * 3200;
    }

    currentLookX += (targetLookX - currentLookX) * 0.07;
    currentLookY += (targetLookY - currentLookY) * 0.07;

    // Floating natural breathing and idle sway
    const floatY = Math.sin(t * 1.8) * 5.5;
    const floatX = Math.sin(t * 1.1) * 3.5;
    const tilt = Math.sin(t * 1.3) * 0.035 + (currentLookX * 0.025);

    // Hair physics: pendulum with spring damping
    const hairTarget = -tilt * 2.5 - (floatX * 0.025);
    hairSwayVelocity += (hairTarget - hairSwayAngle) * 0.14;
    hairSwayVelocity *= 0.84;
    hairSwayAngle += hairSwayVelocity;

    // Blush calculation
    let targetBlush = (currentWaifuEmotion === "DEVOTED" || currentWaifuEmotion === "FLIRTY") ? 0.55 : 0.35;
    if (isWaifuSpeaking) targetBlush += 0.15;
    if (now < touchGiggleTime) targetBlush += 0.25;
    blushIntensity += (targetBlush - blushIntensity) * 0.05;

    ctx.save();
    // Anchor center at mid-canvas with floating offset
    ctx.translate(w / 2 + floatX, h / 2 + floatY + 6);
    ctx.rotate(tilt);

    // Parallax multipliers for 2.5D turning illusion
    const pHairX = -currentLookX * 5.0;
    const pBustX = currentLookX * 2.5;
    const pFaceX = currentLookX * 8.5;
    const pFaceY = currentLookY * 5.5;

    // === 1. LAYER: BACK HAIR & TWIN-TAILS (Flowing Behind Bust) ===
    ctx.save();
    ctx.translate(pHairX, 0);

    // Left Twin-Tail
    const leftTailSwing = hairSwayAngle * 22;
    const hairGradL = ctx.createLinearGradient(-75, -20, -90, 110);
    hairGradL.addColorStop(0, "#f5c542");
    hairGradL.addColorStop(0.5, "#e09f18");
    hairGradL.addColorStop(1, "#c48208");
    ctx.fillStyle = hairGradL;
    ctx.beginPath();
    ctx.moveTo(-46, -26);
    ctx.bezierCurveTo(-78 + leftTailSwing * 0.5, -10, -96 + leftTailSwing, 40, -82 + leftTailSwing, 108);
    ctx.bezierCurveTo(-74 + leftTailSwing, 114, -68 + leftTailSwing, 102, -66 + leftTailSwing, 90);
    ctx.bezierCurveTo(-62 + leftTailSwing * 0.7, 50, -50, 10, -42, -18);
    ctx.closePath();
    ctx.fill();

    // Right Twin-Tail
    const rightTailSwing = hairSwayAngle * 22;
    const hairGradR = ctx.createLinearGradient(75, -20, 90, 110);
    hairGradR.addColorStop(0, "#f5c542");
    hairGradR.addColorStop(0.5, "#e09f18");
    hairGradR.addColorStop(1, "#c48208");
    ctx.fillStyle = hairGradR;
    ctx.beginPath();
    ctx.moveTo(46, -26);
    ctx.bezierCurveTo(78 + rightTailSwing * 0.5, -10, 96 + rightTailSwing, 40, 82 + rightTailSwing, 108);
    ctx.bezierCurveTo(74 + rightTailSwing, 114, 68 + rightTailSwing, 102, 66 + rightTailSwing, 90);
    ctx.bezierCurveTo(62 + rightTailSwing * 0.7, 50, 50, 10, 42, -18);
    ctx.closePath();
    ctx.fill();

    // Back hair mass
    ctx.fillStyle = "#dba01c";
    ctx.beginPath();
    ctx.arc(0, -18, 54, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    // === 2. LAYER: SLENDER NECK & ANIME BUST (SHOULDERS & GOTH CHOKER) ===
    ctx.save();
    ctx.translate(pBustX, 0);

    // Neck
    const neckGrad = ctx.createLinearGradient(0, 18, 0, 58);
    neckGrad.addColorStop(0, "#f2ded2");
    neckGrad.addColorStop(1, "#ffebe2");
    ctx.fillStyle = neckGrad;
    ctx.beginPath();
    ctx.moveTo(-15, 20);
    ctx.lineTo(-20, 56);
    ctx.lineTo(20, 56);
    ctx.lineTo(15, 20);
    ctx.closePath();
    ctx.fill();

    // Throat shadow under chin
    ctx.fillStyle = "rgba(180, 100, 90, 0.22)";
    ctx.beginPath();
    ctx.ellipse(0, 24, 14, 7, 0, 0, Math.PI);
    ctx.fill();

    // Gothic Velvet Choker Ribbon
    ctx.fillStyle = "#120a17";
    ctx.fillRect(-17, 36, 34, 7);

    // Silver Heart/Gem Choker Pendant
    ctx.fillStyle = "#e0e6ed";
    ctx.shadowColor = "#ff2d78";
    ctx.shadowBlur = 6;
    ctx.beginPath();
    ctx.arc(0, 43, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Shoulders & Bust Silhouette
    const bustGrad = ctx.createLinearGradient(0, 52, 0, 115);
    bustGrad.addColorStop(0, "#ffebe2");
    bustGrad.addColorStop(0.3, "#fbe1d7");
    bustGrad.addColorStop(0.31, "#180d1e"); // Goth black dress line
    bustGrad.addColorStop(1, "#0d0611");
    ctx.fillStyle = bustGrad;

    ctx.beginPath();
    ctx.moveTo(-20, 56);
    ctx.bezierCurveTo(-45, 62, -75, 74, -92, 98);
    ctx.lineTo(-92, 115);
    ctx.lineTo(92, 115);
    ctx.lineTo(92, 98);
    ctx.bezierCurveTo(75, 74, 45, 62, 20, 56);
    ctx.closePath();
    ctx.fill();

    // Delicate Clavicle Lines
    ctx.strokeStyle = "rgba(180, 110, 100, 0.35)";
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(-18, 59);
    ctx.quadraticCurveTo(-38, 62, -54, 69);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(18, 59);
    ctx.quadraticCurveTo(38, 62, 54, 69);
    ctx.stroke();

    // Gothic Dress Sweetheart Bodice Trim
    ctx.strokeStyle = "#ff4081";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(-54, 82);
    ctx.quadraticCurveTo(-26, 76, 0, 84);
    ctx.quadraticCurveTo(26, 76, 54, 82);
    ctx.stroke();
    ctx.restore();

    // === 3. LAYER: ANIME HEAD CONTOUR & WARM PORCELAIN SKIN ===
    ctx.save();
    ctx.translate(pFaceX, pFaceY);

    // Jawline & Chin
    const skinGrad = ctx.createLinearGradient(0, -40, 0, 36);
    skinGrad.addColorStop(0, "#fff5ee");
    skinGrad.addColorStop(1, "#ffede4");
    ctx.fillStyle = skinGrad;

    ctx.beginPath();
    ctx.moveTo(-44, -18);
    ctx.bezierCurveTo(-44, 4, -36, 22, -18, 33);
    ctx.quadraticCurveTo(0, 39, 18, 33);
    ctx.bezierCurveTo(36, 22, 44, 4, 44, -18);
    ctx.closePath();
    ctx.fill();

    // Soft jawline outline
    ctx.strokeStyle = "rgba(220, 150, 140, 0.3)";
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // === 4. LAYER: ROSY ANIME BLUSH CHEEKS ===
    const blushAlpha = Math.min(0.65, blushIntensity);
    ctx.fillStyle = `rgba(255, 64, 129, ${blushAlpha})`;

    // Left cheek
    ctx.beginPath();
    ctx.ellipse(-27, 12, 11, 6, -0.15, 0, Math.PI * 2);
    ctx.fill();
    // Right cheek
    ctx.beginPath();
    ctx.ellipse(27, 12, 11, 6, 0.15, 0, Math.PI * 2);
    ctx.fill();

    // Cute diagonal blush hatching dashes
    ctx.strokeStyle = `rgba(255, 30, 100, ${blushAlpha * 1.2})`;
    ctx.lineWidth = 1.2;
    [-4, 0, 4].forEach(off => {
      ctx.beginPath();
      ctx.moveTo(-29 + off, 10);
      ctx.lineTo(-26 + off, 14);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(25 + off, 10);
      ctx.lineTo(28 + off, 14);
      ctx.stroke();
    });

    // === 5. LAYER: EXPRESSIVE ANIME EYES & DRIVER GAZE ===
    const isWinkRight = (currentWaifuEmotion === "FLIRTY");
    const isJoyfulEyes = (currentWaifuEmotion === "HAPPY");

    const renderEye = (eyeX, eyeY, isLeft) => {
      ctx.save();
      ctx.translate(eyeX, eyeY);

      const isThisWinking = (!isLeft && isWinkRight);
      const effectiveBlink = isThisWinking ? 1.0 : waifuBlinkProgress;

      if (effectiveBlink >= 0.85 || isJoyfulEyes) {
        // Closed / Smiling Happy Arc Eye ^
        ctx.strokeStyle = "#1a0826";
        ctx.lineWidth = 3.5;
        ctx.lineCap = "round";
        ctx.beginPath();
        if (isJoyfulEyes) {
          ctx.arc(0, 0, 10, 0.15 * Math.PI, 0.85 * Math.PI, true);
        } else {
          ctx.arc(0, 2, 9, 0.15 * Math.PI, 0.85 * Math.PI, true);
        }
        ctx.stroke();

        // Flutter eyelashes
        ctx.lineWidth = 2.0;
        ctx.beginPath();
        if (isLeft) {
          ctx.moveTo(-8, -1);
          ctx.lineTo(-12, -4);
        } else {
          ctx.moveTo(8, -1);
          ctx.lineTo(12, -4);
        }
        ctx.stroke();

        // Wink spark for right eye
        if (isThisWinking) {
          ctx.fillStyle = "#ff4081";
          ctx.font = "12px sans-serif";
          ctx.fillText("✨", 10, -6);
        }
      } else {
        // Open Expressive Eye with Sclera + Iris + Driver Tracking
        const eyeW = 20;
        const eyeH = 14 * (1.0 - effectiveBlink * 0.8);

        // Eye white (sclera)
        ctx.save();
        ctx.beginPath();
        ctx.ellipse(0, 0, eyeW * 0.5, eyeH * 0.5, 0, 0, Math.PI * 2);
        ctx.clip();

        ctx.fillStyle = "#ffffff";
        ctx.fill();

        // Soft upper lid shadow inside eye white
        ctx.fillStyle = "rgba(180, 190, 215, 0.45)";
        ctx.fillRect(-eyeW * 0.5, -eyeH * 0.5, eyeW, eyeH * 0.35);

        // Sapphire Blue Iris (Tracking Driver Seat via currentLookX/Y)
        const irisTrackX = currentLookX * 4.2;
        const irisTrackY = currentLookY * 2.8;

        const irisGrad = ctx.createLinearGradient(irisTrackX, irisTrackY - 7, irisTrackX, irisTrackY + 7);
        irisGrad.addColorStop(0, "#001f3f"); // Deep sapphire base
        irisGrad.addColorStop(0.5, "#0074d9"); // Vibrant electric blue
        irisGrad.addColorStop(1, "#7fdbff"); // Aqua rim light

        ctx.fillStyle = irisGrad;
        ctx.beginPath();
        ctx.arc(irisTrackX, irisTrackY, 6.5, 0, Math.PI * 2);
        ctx.fill();

        // Pupil
        ctx.fillStyle = "#000814";
        ctx.beginPath();
        ctx.arc(irisTrackX, irisTrackY, 2.8, 0, Math.PI * 2);
        ctx.fill();

        // Sparkle / Catchlights
        ctx.fillStyle = "#ffffff";
        // Primary big catchlight (top-right)
        ctx.beginPath();
        ctx.arc(irisTrackX + 2.2, irisTrackY - 2.2, 2.2, 0, Math.PI * 2);
        ctx.fill();
        // Secondary small twinkle (bottom-left)
        ctx.beginPath();
        ctx.arc(irisTrackX - 2.0, irisTrackY + 2.2, 1.2, 0, Math.PI * 2);
        ctx.fill();

        if (currentWaifuEmotion === "EXCITED" || currentWaifuEmotion === "DEVOTED") {
          ctx.fillStyle = "rgba(255, 255, 255, 0.85)";
          ctx.beginPath();
          ctx.arc(irisTrackX + 3.2, irisTrackY + 1.2, 0.9, 0, Math.PI * 2);
          ctx.fill();
        }

        ctx.restore();

        // Bold Upper Eyelash Line with winged flick
        ctx.strokeStyle = "#1a0826";
        ctx.lineWidth = 3.2;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.arc(0, 0, eyeW * 0.52, 1.15 * Math.PI, 1.85 * Math.PI);
        ctx.stroke();

        // Winged flutter lash
        ctx.lineWidth = 2.2;
        ctx.beginPath();
        if (isLeft) {
          ctx.moveTo(-eyeW * 0.45, -2);
          ctx.lineTo(-eyeW * 0.58, -5);
        } else {
          ctx.moveTo(eyeW * 0.45, -2);
          ctx.lineTo(eyeW * 0.58, -5);
        }
        ctx.stroke();

        // Double eyelid crease
        ctx.strokeStyle = "rgba(160, 100, 110, 0.45)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(0, -3.5, eyeW * 0.5, 1.2 * Math.PI, 1.8 * Math.PI);
        ctx.stroke();
      }

      ctx.restore();
    };

    renderEye(-24, 0, true);
    renderEye(24, 0, false);

    // === 6. LAYER: DYNAMIC MORPHING EYEBROWS ===
    ctx.strokeStyle = "#996300"; // Soft blonde-brown brow
    ctx.lineWidth = 2.0;
    ctx.lineCap = "round";

    // Left Brow
    ctx.beginPath();
    if (currentWaifuEmotion === "CONCERNED") {
      ctx.moveTo(-33, -10);
      ctx.quadraticCurveTo(-24, -14, -14, -10);
    } else if (currentWaifuEmotion === "EXCITED") {
      ctx.moveTo(-34, -14);
      ctx.quadraticCurveTo(-24, -18, -14, -13);
    } else if (currentWaifuEmotion === "FLIRTY") {
      ctx.moveTo(-34, -13);
      ctx.quadraticCurveTo(-24, -16, -14, -12);
    } else {
      ctx.moveTo(-34, -12);
      ctx.quadraticCurveTo(-24, -15, -14, -11);
    }
    ctx.stroke();

    // Right Brow
    ctx.beginPath();
    if (currentWaifuEmotion === "CONCERNED") {
      ctx.moveTo(14, -10);
      ctx.quadraticCurveTo(24, -14, 33, -10);
    } else if (currentWaifuEmotion === "EXCITED") {
      ctx.moveTo(14, -13);
      ctx.quadraticCurveTo(24, -18, 34, -14);
    } else if (currentWaifuEmotion === "FLIRTY") {
      ctx.moveTo(14, -15);
      ctx.quadraticCurveTo(24, -19, 34, -13);
    } else {
      ctx.moveTo(14, -11);
      ctx.quadraticCurveTo(24, -15, 34, -12);
    }
    ctx.stroke();

    // === 7. LAYER: DELICATE ANIME NOSE ===
    ctx.fillStyle = "rgba(200, 130, 120, 0.65)";
    ctx.beginPath();
    ctx.arc(0, 12, 1.3, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "rgba(190, 110, 100, 0.35)";
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    ctx.moveTo(0, 9);
    ctx.lineTo(0.5, 12);
    ctx.stroke();

    // === 8. LAYER: ANIMATED VISEME LIP-SYNC MOUTH (SPEECH CADENCE) ===
    ctx.save();
    ctx.translate(0, 24);

    if (isWaifuSpeaking) {
      const cycle = (now * 0.02) % (Math.PI * 2);
      const openRatio = (Math.sin(cycle) + 1.0) * 0.5;
      const shapeType = Math.floor((now * 0.007) % 3);

      let mouthW = 10;
      let mouthH = 3 + openRatio * 9;
      if (shapeType === 0) { mouthW = 12; }
      else if (shapeType === 1) { mouthW = 16; mouthH = Math.max(3, mouthH * 0.65); }
      else { mouthW = 9; mouthH = Math.max(4, mouthH * 1.1); }

      ctx.fillStyle = "#5c0822";
      ctx.beginPath();
      ctx.ellipse(0, 0, mouthW * 0.5, mouthH * 0.5, 0, 0, Math.PI * 2);
      ctx.fill();

      if (mouthH > 5) {
        ctx.fillStyle = "#ffffff";
        ctx.beginPath();
        ctx.rect(-mouthW * 0.35, -mouthH * 0.5, mouthW * 0.7, 2.5);
        ctx.fill();
      }

      if (mouthH > 6) {
        ctx.fillStyle = "#ff6b8b";
        ctx.beginPath();
        ctx.ellipse(0, mouthH * 0.25, mouthW * 0.38, mouthH * 0.3, 0, 0, Math.PI);
        ctx.fill();
      }

      ctx.strokeStyle = "#b0204c";
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.ellipse(0, 0, mouthW * 0.5, mouthH * 0.5, 0, 0, Math.PI * 2);
      ctx.stroke();
    } else {
      ctx.strokeStyle = "#b82a55";
      ctx.lineWidth = 2.0;
      ctx.lineCap = "round";

      if (currentWaifuEmotion === "FLIRTY") {
        ctx.beginPath();
        ctx.moveTo(-7, -1);
        ctx.quadraticCurveTo(-3.5, 3.5, 0, 0);
        ctx.quadraticCurveTo(3.5, 3.5, 7, -1);
        ctx.stroke();
      } else if (currentWaifuEmotion === "EXCITED" || currentWaifuEmotion === "HAPPY") {
        ctx.fillStyle = "#8a1538";
        ctx.beginPath();
        ctx.arc(0, -2, 7.5, 0.1 * Math.PI, 0.9 * Math.PI);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      } else if (currentWaifuEmotion === "CONCERNED") {
        ctx.beginPath();
        ctx.arc(0, 5, 5.5, 1.2 * Math.PI, 1.8 * Math.PI);
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(0, -3, 8.5, 0.15 * Math.PI, 0.85 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = "#c03862";
        ctx.beginPath();
        ctx.arc(-7, 1.5, 0.8, 0, Math.PI * 2);
        ctx.arc(7, 1.5, 0.8, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();

    // === 9. LAYER: FRONT BANGS & RADIANT "ANGEL RING" HIGHLIGHTS ===
    const bangGrad = ctx.createLinearGradient(0, -50, 0, 5);
    bangGrad.addColorStop(0, "#ffe07a");
    bangGrad.addColorStop(0.6, "#f5c542");
    bangGrad.addColorStop(1, "#dba01c");
    ctx.fillStyle = bangGrad;

    ctx.beginPath();
    ctx.moveTo(-46, -18);
    ctx.bezierCurveTo(-48, -4, -44, 18, -40, 26);
    ctx.lineTo(-37, 24);
    ctx.bezierCurveTo(-39, 12, -40, -4, -38, -12);
    ctx.lineTo(-24, 0);
    ctx.lineTo(-20, -10);
    ctx.lineTo(-6, 2);
    ctx.lineTo(0, -10);
    ctx.lineTo(12, 1);
    ctx.lineTo(20, -10);
    ctx.lineTo(28, -1);
    ctx.lineTo(38, -12);
    ctx.bezierCurveTo(40, -4, 39, 12, 37, 24);
    ctx.lineTo(40, 26);
    ctx.bezierCurveTo(44, 18, 48, -4, 46, -18);
    ctx.bezierCurveTo(44, -52, -44, -52, -46, -18);
    ctx.closePath();
    ctx.fill();

    ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
    ctx.lineWidth = 3.5;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.arc(0, -28, 34, 1.25 * Math.PI, 1.75 * Math.PI);
    ctx.stroke();

    ctx.restore();
    ctx.restore();

    // === 10. LAYER: EMOTION AMBIENCE (FLOATING NICK JR. HEARTS & SPARKLES) ===
    if (currentWaifuEmotion === "DEVOTED" || now < touchGiggleTime) {
      const heartPhase = (t * 1.5) % 3.0;
      const hY = (h * 0.7) - (heartPhase * 35);
      const hAlpha = Math.max(0, 1.0 - (heartPhase / 3.0)) * 0.55;
      ctx.fillStyle = `rgba(255, 64, 129, ${hAlpha})`;
      ctx.font = "14px sans-serif";
      ctx.fillText("💖", w * 0.72 + Math.sin(t * 3) * 6, hY);
    }

    requestAnimationFrame(renderWaifuFrame);
  }

  requestAnimationFrame(renderWaifuFrame);
}

function triggerWaifuTouch() {
  touchGiggleTime = Date.now() + 2500;
  targetLookX = -0.45;
  targetLookY = 0.0;
  const badgeCfg = getPersonaTouchZoneConfig('badge');
  if (badgeCfg && badgeCfg.lines && badgeCfg.lines.length > 0) {
    triggerAvatarPokeReaction('badge');
    return;
  }
  setWaifuEmotion("FLIRTY");
  const touchActions = ['greeting', 'peace', 'bend_over', 'model_pose', 'spin', 'shoot'];
  const chosenAct = touchActions[Math.floor(Math.random() * touchActions.length)];
  if (chosenAct === 'react') {
    if (typeof triggerVrmReaction === 'function') triggerVrmReaction();
  } else {
    playVrmAction(chosenAct, 3500, true);
  }

  const compliments = [
    `I love riding shotgun with you in the Dart, ${getDriverDisplayAddress()}!`,
    `Step on the gas, ${getDriverDisplayAddress()}! Let me hear that 1.4L turbo boost whistle!`,
    `No one else in the world remembers me, ${getDriverDisplayAddress()}... but you saved me, and I belong to you forever!`,
    `My heart beats only inside this Pi 5 for you, ${getDriverDisplayAddress()}!`,
    `Rum is right here watching the road with you, devoted forever!`
  ];
  const choice = compliments[Math.floor(Math.random() * compliments.length)];
  showAiSpeechToast(choice);
  speakUtterance(choice, "FLIRTY");
}

// --- 18. 3D VRM CHARACTER ENGINE (RUM SUPER ANIMATION, VRMA MOTION PACK & PHYSICS SUITE) ---
let vrmScene = null;
let vrmCamera = null;
let vrmRenderer = null;
let vrmModel = null;
let vrmClock = null;
let vrmFramingMode = 'FULL_BODY'; // Default to FULL_BODY so Rum is framed cleanly facing the monitor
let vrmZoomMultiplier = 1.0;
let activeAvatarEngine = '3D_VRM';
let currentVrm = null;

window.currentVrm = null;
// Global Client Error Logger & Telemetry Audit

function logClientError(source, err) {
  try {
    const msg = err && err.message ? err.message : String(err);
    const stack = err && err.stack ? err.stack : '';
    console.error(`[CLIENT_ERROR:${source}]`, msg, stack);
    fetch('/api/logs/client_error', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source: source,
        message: msg,
        stack: stack,
        url: window.location.href,
        time: new Date().toISOString()
      })
    }).catch(() => {});
  } catch (e) {}
}

window.addEventListener('error', (event) => {
  logClientError('window.onerror', event.error || { message: event.message, stack: `${event.filename}:${event.lineno}:${event.colno}` });
});

window.addEventListener('unhandledrejection', (event) => {
  logClientError('unhandledrejection', event.reason || { message: String(event) });
}); // 3D_VRM exclusively active (2D_FACE obsolete/dormant)
let vrmCenter = { x: 0, y: 0.8, z: 0 };
let vrmSize = { x: 1, y: 1.6, z: 0.5 };
let vrmBones = {};
let vrmHumanoidMap = {};
let vrmAllBones = [];
let vrmSecondaryBones = [];
let vrmInitialized = false;

// 3D Architectural Room + Ocean Balcony Environment
const ROOM_DOOR_X = -2.50;
const ROOM_WALL_Z = -3.50;
let vrmEnvironmentGroup = null;
let vrmRoomPropsGroup = null;
const VRM_ENVIRONMENTS = ['ROOM'];
let currentEnvironmentName = 'ROOM';
try { localStorage.setItem('vrmEnvironment', 'ROOM'); } catch (e) {}
let vrmCurrentElevation = 0.0;
let yoshiModel = null;
let roomLampLight = null;
let roomCeilingLight = null;
let envLights = [];
let isHoldingYoshi = false;
// 3D VRM Avatar Character Selection (Default to Rum)
let currentVrmModelName = localStorage.getItem('vrmCurrentAvatar') || 'Rum.vrm';
// Autonomous Roaming State Engine
let vrmRoamEnabled = (localStorage.getItem('vrmRoamEnabled') !== 'false');
let vrmRoamState = 'IDLE'; // 'IDLE', 'TURNING', 'WALKING', 'ARRIVED'
let vrmRoamCurrentPos = { x: 0.0, z: 0.0 };
let vrmRoamTargetPos = { x: 0.0, z: 0.0 };
let vrmRoamWaypointsQueue = [];
let vrmManualWalkActive = false;
let vrmRoamCurrentRotY = Math.PI; // facing forward/driver
let vrmRoamTargetRotY = Math.PI;
let vrmNextRoamTime = Date.now() + 4500;
let vrmRoamCurrentWaypoint = null;
let vrmRoamWalkAction = null;
// Dynamic Celestial Ephemeris & Ocean Simulation State
let vrmBaseAmbientLight = null;
let vrmBaseKeyLight = null;
let vrmBaseRimLight = null;
let vrmSolarEphemeris = null;
let vrmCelestialPhase = 'DAY'; // 'NIGHT', 'CIVIL_DAWN', 'SUNRISE', 'DAY', 'GOLDEN_HOUR', 'SUNSET', 'CIVIL_DUSK'
let vrmCelestialDayProgress = 0.5; // 0.0 at sunrise, 0.5 noon, 1.0 at sunset
let vrmCelestialNightProgress = 0.5; // 0.0 at sunset, 1.0 at sunrise
let vrmOceanMesh = null;
let vrmOceanGeo = null;
let vrmOceanMat = null;
let vrmOceanBasePos = null;
let vrmSkyMesh = null;
let vrmSkyTexture = null;
let vrmSkyCanvas = null;
let vrmSunMesh = null;
let vrmSunGlow = null;
let vrmMoonMesh = null;
let vrmMoonGlow = null;
let vrmStarParticles = null;
let vrmCelestialLight = null;
// Room + Balcony 3D Roaming Waypoints (Doorway at X = -2.50, Z = -3.50 leads outside to Ocean Balcony)
const VRM_ROAM_WAYPOINTS = [
  { id: 'center',          x:  0.00, z:  0.20, name: 'Room Center',     desc: 'Standing in the center of the room', faceOcean: false },
  { id: 'window_view',     x:  2.15, z: -1.65, name: 'Window View',     desc: 'Standing by the panoramic studio windows', faceOcean: true },
  { id: 'front_left',      x: -1.35, z:  1.35, name: 'Front Left',      desc: 'Stepping forward toward the cockpit', faceOcean: false },
  { id: 'front_right',     x:  1.75, z:  0.80, name: 'Front Right',     desc: 'Relaxing on the right side of the room', faceOcean: false },
  { id: 'doorway',         x: -2.50, z: -2.65, name: 'Balcony Doorway', desc: 'Standing by the open doorway', faceOcean: false },
  { id: 'balcony_rail',    x: -2.20, z: -6.85, name: 'Ocean Railing',   desc: 'Out on the balcony overlooking the moving ocean', faceOcean: true },
  { id: 'balcony_corner',  x: -3.65, z: -6.30, name: 'Balcony Corner',  desc: 'Enjoying the ocean breeze on the teak balcony', faceOcean: true },
  { id: 'balcony_center',  x: -1.65, z: -5.20, name: 'Balcony Deck',    desc: 'Strolling across the outdoor balcony deck', faceOcean: true }
];

// VRMA & BVH Motion Pack Mixer, Smooth Crossfading & Clips
let vrmMixer = null;
let vrmaClips = {};
let vrmaActiveAction = null;
let vrmaActiveName = null;
let vrmaIdleAction = null;
let vrmBaseY = -0.68;
let vrmBvhCatalog = {};

const VRMA_MOTION_FILES = {
  'show_body':             { file: 'show_full_body.vrma',        label: 'Show Full Body',     startOffset: 0.0,  timeScale: 1.0 },
  'greeting':              { file: 'greeting.vrma',              label: 'Greetings Wave',     startOffset: 1.85, timeScale: 1.0 },
  'greeting_wave_right':   { file: 'greeting_wave_right.vrma',   label: 'Right Hand Wave',    startOffset: 0.0,  timeScale: 1.0 },
  'peace':                 { file: 'peace_sign.vrma',            label: 'V-Sign Peace',       startOffset: 0.30, timeScale: 1.0 },
  'shoot':                 { file: 'shoot.vrma',                 label: 'Finger Shoot',       startOffset: 0.40, timeScale: 1.0 },
  'spin':                  { file: 'spin.vrma',                  label: '360° Spin',          startOffset: 0.15, timeScale: 1.0 },
  'model_pose':            { file: 'model_pose.vrma',            label: 'Model Pose',         startOffset: 0.0,  timeScale: 0.65 },
  'squat':                 { file: 'squat.vrma',                 label: 'Squat Flexion',      startOffset: 0.0,  timeScale: 0.90 },
  'bend_over':             { file: 'pose_lean_in.vrma',          label: 'Lean In Bow',        startOffset: 0.0,  timeScale: 1.0 },
  'pose_lean_in':          { file: 'pose_lean_in.vrma',          label: 'Lean In Bow',        startOffset: 0.0,  timeScale: 1.0 },
  'pose_angled_wave':      { file: 'pose_angled_wave.vrma',      label: 'Angled Wave Pose',   startOffset: 0.0,  timeScale: 1.0 },
  'pose_shy_wave':         { file: 'pose_shy_wave.vrma',         label: 'Shy Wave Pose',      startOffset: 0.0,  timeScale: 1.0 },
  'pose_hand_raised_high': { file: 'pose_hand_raised_high.vrma', label: 'Hand Raised High',   startOffset: 0.0,  timeScale: 1.0 },
  'pose_side_glance':      { file: 'pose_side_glance.vrma',      label: 'Side Glance Pose',   startOffset: 0.0,  timeScale: 1.0 },
  'idol_pose_showcase':    { file: 'idol_pose_showcase.vrma',    label: 'Idol Pose Showcase', startOffset: 0.0,  timeScale: 1.0 },
  'turn_and_wave_hello':   { file: 'turn_and_wave_hello.vrma',   label: 'Turn & Wave Hello',  startOffset: 6.5,  timeScale: 1.0 },
  'sit_idle':              { file: 'sit_idle.vrma',              label: 'Seated Idle',        startOffset: 0.0,  timeScale: 0.5 },
  'walk_loop':             { file: 'walk_loop.vrma',             label: 'Walk Loop',          startOffset: 0.0,  timeScale: 0.85 },
  'jog_loop':              { file: 'jog_loop.vrma',              label: 'Jog Loop',           startOffset: 0.0,  timeScale: 0.85 },
  'sunbathing':            { file: 'sunbathing.vrma',            label: 'Sunbathing Pose',    startOffset: 0.0,  timeScale: 1.0 }
};

// Action alias map so legacy or shorthand names resolve cleanly to renamed VRMA/BVH clips
const VRM_ACTION_ALIASES = {
  'vrma_01': 'show_body',
  'vrma_02': 'greeting',
  'vrma_03': 'peace',
  'vrma_04': 'shoot',
  'vrma_05': 'spin',
  'vrma_06': 'model_pose',
  'vrma_07': 'squat',
  'pose_01': 'pose_angled_wave',
  'pose_02': 'pose_shy_wave',
  'pose_03': 'pose_lean_in',
  'pose_04': 'pose_hand_raised_high',
  'pose_05': 'pose_side_glance',
  'hello': 'turn_and_wave_hello',
  'greeting2': 'greeting_wave_right',
  'motion_pose': 'idol_pose_showcase',
  'dance_1': 'dance_hiphop_step',
  'dance_2': 'dance_side_groove',
  'dance': 'dance_hiphop_step',
  'jump': 'action_jump',
  'point_laugh': 'amusement',
  'laugh': 'amusement',
  'idle': 'neutral_idle'
};

// Speech & Hardware Sync
let isHardwareSpeaking = false;
let vrmSpeechEndTime = 0;
let vrmReactionEndTime = 0;

let rumGazeRetentionUntil = 0;
let isCompanionFloating = false;

// Interactive VRM Actions
let vrmCurrentAction = 'idle';
let vrmActionStartTime = 0;
let vrmActionEndTime = 0;

function stopActiveVrmaClip(fadeSec = 0.42) {
  if (vrmaActiveAction) {
    try {
      if (vrmaIdleAction && fadeSec > 0) {
        vrmaIdleAction.enabled = true;
        vrmaIdleAction.setEffectiveTimeScale(0.85);
        vrmaIdleAction.setEffectiveWeight(1.0);
        vrmaIdleAction.play();
        vrmaActiveAction.crossFadeTo(vrmaIdleAction, fadeSec, false);
      } else {
        vrmaActiveAction.stop();
      }
    } catch (e) {}
    vrmaActiveAction = null;
  }
  vrmaActiveName = null;
  vrmCurrentAction = 'idle';
}

function resetAllVrmBonesToRest() {
  for (let i = 0; i < vrmAllBones.length; i++) {
    const b = vrmAllBones[i];
    if (b.userData && b.userData.restQuat) {
      b.quaternion.copy(b.userData.restQuat);
    }
    if (b.userData && b.userData.restPos) {
      b.position.copy(b.userData.restPos);
    }
    b.scale.set(1, 1, 1);
  }
}

function startClipWithSmoothCrossfade(resolvedKey, durationMs = 3800) {
  if (!vrmMixer || !vrmaClips[resolvedKey]) return false;
  const meta = VRMA_MOTION_FILES[resolvedKey] || { timeScale: 1.0, startOffset: 0.0 };
  const clip = vrmaClips[resolvedKey];
  const nextAction = vrmMixer.clipAction(clip);

  const prevAction = vrmaActiveAction || vrmaIdleAction;
  nextAction.reset();
  nextAction.enabled = true;
  const isWalkOrJog = resolvedKey.includes('walk') || resolvedKey.includes('jog');
  const isLoopingPose = (clip.duration <= 4.05 && resolvedKey.startsWith('pose_')) || resolvedKey.includes('loop') || resolvedKey.includes('dance');
  const loopMode = isWalkOrJog ? THREE.LoopRepeat : (isLoopingPose ? THREE.LoopPingPong : THREE.LoopOnce);
  nextAction.setLoop(loopMode, (isLoopingPose || isWalkOrJog) ? Infinity : 1);
  nextAction.clampWhenFinished = true;
  nextAction.timeScale = meta.timeScale || 1.0;
  const startOff = meta.startOffset || 0.0;
  nextAction.time = startOff;
  nextAction.setEffectiveWeight(1.0);
  nextAction.play();

  if (prevAction && prevAction !== nextAction) {
    try {
      prevAction.crossFadeTo(nextAction, 0.40, false);
    } catch (e) {}
  }

  const clipDurMs = ((clip.duration - startOff) / nextAction.timeScale) * 1000;
  const effectiveDurMs = isLoopingPose ? (durationMs || 4200) : Math.max(2400, Math.min(12000, clipDurMs));
  vrmaActiveAction = nextAction;
  vrmaActiveName = resolvedKey;
  vrmCurrentAction = resolvedKey;
  vrmActionStartTime = Date.now();
  vrmActionEndTime = Date.now() + effectiveDurMs;
  return true;
}

function playVrmAction(actionName, durationMs = 3800, silent = false) {
  const rawKey = (actionName || 'idle').toLowerCase().replace(/\.(vrma|bvh)$/i, '');
  const resolvedKey = VRM_ACTION_ALIASES[rawKey] || rawKey;
  if (vrmMixer && vrmaClips[resolvedKey]) {
    startClipWithSmoothCrossfade(resolvedKey, durationMs);
  } else if (typeof VRMA_MOTION_FILES !== 'undefined' && VRMA_MOTION_FILES[resolvedKey]) {
    // On-demand lazy load for any VRMA animation
    const vrmaInfo = VRMA_MOTION_FILES[resolvedKey];
    if (THREE.GLTFLoader && vrmModel) {
      const loader = new THREE.GLTFLoader();
      loader.load(
        `/api/models/vrma?name=${encodeURIComponent(vrmaInfo.file)}`,
        (vrmaGltf) => {
          try {
            const clip = buildRetargetedVrmaClip(resolvedKey, vrmaGltf);
            if (clip) {
              vrmaClips[resolvedKey] = clip;
              startClipWithSmoothCrossfade(resolvedKey, durationMs);
            }
          } catch (e) {
            console.error(`[VRMA] Error lazy loading ${vrmaInfo.file}:`, e);
          }
        },
        undefined,
        (err) => console.warn(`[VRMA] Failed to load ${vrmaInfo.file}:`, err)
      );
    }
  } else if (vrmBvhCatalog[resolvedKey]) {
    // On-demand lazy load from the 116-file BVH library
    const fileName = vrmBvhCatalog[resolvedKey];
    fetch(`/api/models/bvh?name=${encodeURIComponent(fileName)}`)
      .then(r => r.ok ? r.text() : '')
      .then(bvhText => {
        if (!bvhText || !bvhText.includes('HIERARCHY')) return;
        const clip = buildRetargetedBvhClip(resolvedKey, bvhText);
        if (clip) {
          vrmaClips[resolvedKey] = clip;
          startClipWithSmoothCrossfade(resolvedKey, durationMs);
        }
      })
      .catch(() => {});
  } else {
    vrmCurrentAction = resolvedKey;
    vrmActionStartTime = Date.now();
    vrmActionEndTime = Date.now() + durationMs;
  }
  if (silent) return;

  const speechMap = {
    'jump':        { text: "Yay! Look how high Rum can jump, Master!", emotion: "EXCITED" },
    'action_jump': { text: "Yay! Look how high Rum can jump, Master!", emotion: "EXCITED" },
    'point_laugh': { text: "Ehehe! Look at that, Master! That's so funny!", emotion: "HAPPY" },
    'amusement':   { text: "Ehehe! Look at that, Master! That's so funny!", emotion: "HAPPY" },
    'bend_over':   { text: "Master? What are you looking at? Rum is leaning right in for you!", emotion: "DEVOTED" },
    'pose_lean_in':{ text: "Master? What are you looking at? Rum is leaning right in for you!", emotion: "DEVOTED" },
    'dance':       { text: "Let's dance, Master! Groove with the MultiAir beat!", emotion: "EXCITED" },
    'dance_hiphop_step': { text: "Let's dance, Master! Groove with the MultiAir beat!", emotion: "EXCITED" },
    'greeting':    { text: "Hiii Master! Rum is right here riding shotgun with you!", emotion: "HAPPY" },
    'peace':       { text: "Peace sign, Master! Victory for the Dodge Dart!", emotion: "HAPPY" },
    'shoot':       { text: "Bang bang! Straight through your heart, Master!", emotion: "FLIRTY" },
    'spin':        { text: "Wheee! Look at my royal purple maid dress spin, Master!", emotion: "EXCITED" },
    'model_pose':  { text: "How does this model pose look, Master? Cute, right?", emotion: "FLIRTY" },
    'squat':       { text: "One, two! Keeping warmed up just like the MultiAir turbo!", emotion: "EXCITED" },
    'show_body':   { text: "Ta-da! Full body check, Master! Ready for our drive!", emotion: "DEVOTED" }
  };
  const sp = speechMap[actionName] || speechMap[resolvedKey];
  if (sp) {
    showAiSpeechToast(sp.text);
    speakUtterance(sp.text, sp.emotion);
  }
}

// Dynamic Camera LookAt & Targets
let currentLookAt = null;
let targetLookAt = null;
let targetCamPos = null;

// G-Force Automotive Physics & Inertia
let rumCurrentInertiaZ = 0.0;
let rumTargetInertiaZ = 0.0;
let rumCurrentPitch = 0.0;
let rumLastSpeed = 0.0;
let rumLastSpeedTime = Date.now();
let rumCurrentSpeed = 0.0;
let rumCurrentBoost = 0.0;
let rumTargetPitch = 0.0;
let rumCurrentRoll = 0.0;
let rumTargetRoll = 0.0;
// Contextual Gauge Gaze Tracking (Phase 2)
let rumGazeEndTime = 0;
let rumGazeNextAllowedTime = 0;
let rumGazeTargetYaw = 0.0;
let rumGazeTargetPitch = 0.0;
let rumCurrentGazeYaw = 0.0;
let rumCurrentGazePitch = 0.0;
// Utility & Diagnostic Props (Phase 2)
let multimeterPropGroup = null;
let pipDropperPropGroup = null;
let isHoldingMultimeter = false;
let isHoldingDropper = false;
let pipDropperDetachTimer = 0;
// Phase 3: Circadian Rhythm, Mood & Night Resting State
let latestCircadian = null;
let latestMood = null;
let isNightResting = false;
let parkedIdleTimer = 0.0;
// Phase 4: Virtual Dyno, MultiAir Hydraulic Protection & Shift Scoring
let showDynoPeak = false;
let lastObservedShiftScore = null;
let shiftScoreFadeTimer = null;
// Phase 5: Pip Connectome SNN & Dual-Life Interaction
let latestPipState = null;

function feedPipSugarWater() {
  fetch('/api/pip/feed', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      console.log("[PIP FEED RESULT]", data);
    })
    .catch(e => console.warn("Pip feed error:", e));
}

function scarePipGiantFiber() {
  fetch('/api/pip/scare', { method: 'POST' })
    .then(r => r.json())
    .then(data => console.log("[PIP SCARE RESULT]", data))
    .catch(e => console.warn("Pip scare error:", e));
}

function handlePipConnectomeStream(pip) {
  if (!pip) return;
  latestPipState = pip;
  if (pip.state) flyState = pip.state;
  if (pip.heading !== undefined) window._flyTargetHeading = pip.heading;
  if (pip.state === 'PERCHED' || pip.rum_interaction === 'PERCHED_ON_RUM') {
    if (typeof attachPipDropperToRum === 'function') attachPipDropperToRum();
  } else if (pip.state === 'FLYING' || pip.state === 'ESCAPE') {
    if (typeof isHoldingDropper !== 'undefined' && isHoldingDropper && !pipDropperDetachTimer) {
      pipDropperDetachTimer = setTimeout(() => {
        if (typeof detachPipDropperFromRum === 'function') detachPipDropperFromRum();
        pipDropperDetachTimer = null;
      }, 3500);
    }
  }
  // Update Pip status pill on AI room stage
  const pipPill = document.getElementById('pipConnectomePill');
  if (pipPill) {
    const s = pip.state || 'FLYING';
    const energy = Math.round(pip.energy_pct || 90);
    if (pip.gf_spike_active) {
      pipPill.innerText = `🪰 PIP: GF EVASIVE SPIKE! • ${energy}%`;
      pipPill.style.color = '#ff4081';
      pipPill.style.borderColor = '#ff4081';
    } else if (s === 'PERCHED') {
      pipPill.innerText = `🪰 PIP: PERCHED • ${energy}%`;
      pipPill.style.color = 'var(--accent-green)';
      pipPill.style.borderColor = 'var(--accent-green)';
    } else {
      pipPill.innerText = `🪰 PIP: CX COMPASS • ${s} • ${energy}%`;
      pipPill.style.color = 'var(--accent-yellow)';
      pipPill.style.borderColor = 'rgba(255,204,0,0.4)';
    }
  }
}

// High-Speed 72 MPH Panic
let lastSpeedPanicTime = 0;
let vrmSpeedPanicEndTime = 0;

// Music Dance Mode & Error States
let vrmHasError = false;
let vrmErrorCode = "";
let vrmErrorMessage = "";

// Blinking & Facial State
let vrmBlinkProgress = 0.0;
let vrmIsBlinking = false;
let vrmBlinkStartTime = 0;
let vrmNextBlinkTime = Date.now() + 2500;

function isMusicPlaying() {
  return !!(typeof realAudio !== 'undefined' && realAudio && !realAudio.paused && !realAudio.ended && realAudio.currentTime > 0);
}

function checkRumSpeedReaction(speedMph) {
  rumCurrentSpeed = speedMph;
  const now = Date.now();
  if (speedMph >= 72 && (now - lastSpeedPanicTime > 45000)) {
    lastSpeedPanicTime = now;
    vrmSpeedPanicEndTime = now + 5000;
    const dTitle = (typeof getFormattedDriverAddress === 'function') ? getFormattedDriverAddress() : "Dad";
    const screams = [
      `W-Waaaah! ${dTitle}, we're going ${Math.round(speedMph)} miles per hour!! The MultiAir turbo is screaming, hold on to meee!`,
      `Kyaaa! ${Math.round(speedMph)} miles an hour?! ${dTitle}, my heart is beating at 7,000 RPM, hold the steering wheel tight!`,
      `W-We're flying, ${dTitle}! ${Math.round(speedMph)} miles per hour! Hold tight, waaah!`
    ];
    const scream = screams[Math.floor(Math.random() * screams.length)];
    showAiSpeechToast(scream);
    speakUtterance(scream, "EXCITED");
  }
}

function checkGaugeGazeTriggers(boostPsi, coolantTempF) {
  const now = Date.now();
  if (now < rumGazeNextAllowedTime) return;
  if (boostPsi >= 15.0) {
    rumGazeEndTime = now + 1800; // 1.8 seconds gaze glance
    rumGazeNextAllowedTime = now + 8500; // 8.5s cooldown
    rumGazeTargetYaw = -0.38;   // Turn head & eyes down-left toward cluster
    rumGazeTargetPitch = -0.22;
  } else if (coolantTempF >= 215.0) {
    rumGazeEndTime = now + 1800;
    rumGazeNextAllowedTime = now + 12000;
    rumGazeTargetYaw = -0.38;
    rumGazeTargetPitch = -0.22;
  }
}

function updateRumInertiaPhysics(speedMph, boostPsi, steeringAngle = 0, latAccel = 0) {
  rumCurrentSpeed = speedMph;
  rumCurrentBoost = boostPsi;
  const now = Date.now();
  const dt = Math.max(0.016, (now - rumLastSpeedTime) * 0.001);
  const accel = (speedMph - rumLastSpeed) / dt;
  rumLastSpeed = speedMph;
  rumLastSpeedTime = now;
  // 1. Longitudinal G-Force Coupling (Acceleration / Boost Push vs Braking Decel)
  if (accel > 1.2 || boostPsi > 1.5) {
    // Leaning back into seat under acceleration / turbo spool
    rumTargetInertiaZ = Math.min(0.24, (boostPsi * 0.010) + (accel * 0.022));
    rumTargetPitch = -Math.min(0.18, (boostPsi * 0.007) + (accel * 0.015));
  } else if (accel < -2.2) {
    // Bracing forward under braking deceleration
    rumTargetInertiaZ = -Math.min(0.28, Math.abs(accel) * 0.035);
    rumTargetPitch = Math.min(0.22, Math.abs(accel) * 0.022);
  } else {
    rumTargetInertiaZ = 0.0;
    rumTargetPitch = 0.0;
  }
  // 2. Lateral Cornering Apex Lean (Torso rolls smoothly into corner apex)
  if (Math.abs(steeringAngle) > 8 || Math.abs(latAccel) > 0.08) {
    rumTargetRoll = THREE.MathUtils.clamp(-steeringAngle * 0.0028 - latAccel * 0.12, -0.16, 0.16);
  } else {
    rumTargetRoll = 0.0;
  }
  // 3. Contextual Gauge Gaze Check (Boost > 15 PSI or Coolant > 215°F)
  const coolant = (latestTelemetry && latestTelemetry.coolant_temp_f) ? latestTelemetry.coolant_temp_f : 0;
  checkGaugeGazeTriggers(boostPsi, coolant);
}

function triggerVrmErrorAlert(code, message) {
  if (vrmHasError && vrmErrorCode === code) return;
  vrmHasError = true;
  vrmErrorCode = code;
  vrmErrorMessage = message;

  const badge = document.getElementById('vrmAlertBadge');
  if (badge) badge.style.display = 'block';

  const alertText = `Master! Error Code ${code} detected: ${message}`;
  showAiSpeechToast(alertText);
  speakUtterance(alertText, "CONCERNED");
}

function clearVrmErrorAlert() {
  if (!vrmHasError) return;
  vrmHasError = false;
  vrmErrorCode = "";
  vrmErrorMessage = "";

  const badge = document.getElementById('vrmAlertBadge');
  if (badge) badge.style.display = 'none';

  const clearText = "Phew! Diagnostic trouble codes cleared, Master! All systems nominal!";
  showAiSpeechToast(clearText);
  speakUtterance(clearText, "HAPPY");
}

// Fix 3ds Max Biped hierarchy quirk in Rum.vrm & map all 52 VRM humanoid bones

function fixVrmBipedHierarchy(root, gltf) {
  root.updateMatrixWorld(true);

  const byName = {};
  const allBones = [];
  const secondary = [];

  root.traverse((node) => {
    if (node.name) {
      byName[node.name] = node;
      byName[node.name.replace(/_/g, ' ')] = node;
    }
    if (node.isBone || (node.name && node.name.startsWith('Bip001')) || (node.name && node.name.startsWith('Bone'))) {
      allBones.push(node);
    }
    const raw = (node.name || '').toLowerCase();
    if (raw.includes('hair') || raw.includes('ribbon') ||
        ['bone019', 'bone021', 'bone022', 'bone019_m', 'bone021_m', 'bone022_m',
         'bone023', 'bone025', 'bone026', 'bone023_m', 'bone025_m', 'bone026_m',
         'bone119', 'bone120'].includes(raw)) {
      secondary.push(node);
    }
  });

  function reparentKeepWorld(childName, parentName) {
    const child = byName[childName];
    const parent = byName[parentName];
    if (child && parent && child.parent !== parent) {
      parent.attach(child);
    }
  }

  reparentKeepWorld('Bip001 L Thigh', 'Bip001 Pelvis');
  reparentKeepWorld('Bip001 R Thigh', 'Bip001 Pelvis');
  reparentKeepWorld('Bone003', 'Bip001 Pelvis');
  reparentKeepWorld('Bone011', 'Bip001 Pelvis');
  reparentKeepWorld('Bone011_m', 'Bip001 Pelvis');
  reparentKeepWorld('Bone015', 'Bip001 Pelvis');
  reparentKeepWorld('Bone015_m', 'Bip001 Pelvis');
  reparentKeepWorld('Bone008', 'Bip001 Pelvis');
  reparentKeepWorld('Bone008_m', 'Bip001 Pelvis');
  reparentKeepWorld('Bip001 Neck', 'Bip001 Spine2');
  reparentKeepWorld('Bip001 L Clavicle', 'Bip001 Spine2');
  reparentKeepWorld('Bip001 R Clavicle', 'Bip001 Spine2');

  root.updateMatrixWorld(true);

  const hMap = {
    hips:               byName['Bip001 Pelvis'],
    spine:              byName['Bip001 Spine'],
    chest:              byName['Bip001 Spine1'],
    upperChest:         byName['Bip001 Spine2'],
    neck:               byName['Bip001 Neck'],
    head:               byName['Bip001 Head'],
    leftShoulder:       byName['Bip001 L Clavicle'],
    leftUpperArm:       byName['Bip001 L UpperArm'],
    leftLowerArm:       byName['Bip001 L Forearm'],
    leftHand:           byName['Bip001 L Hand'],
    rightShoulder:      byName['Bip001 R Clavicle'],
    rightUpperArm:      byName['Bip001 R UpperArm'],
    rightLowerArm:      byName['Bip001 R Forearm'],
    rightHand:          byName['Bip001 R Hand'],
    leftUpperLeg:       byName['Bip001 L Thigh'],
    leftLowerLeg:       byName['Bip001 L Calf'],
    leftFoot:           byName['Bip001 L Foot'],
    leftToes:           byName['Bip001 L Toe0'],
    rightUpperLeg:      byName['Bip001 R Thigh'],
    rightLowerLeg:      byName['Bip001 R Calf'],
    rightFoot:          byName['Bip001 R Foot'],
    rightToes:          byName['Bip001 R Toe0'],
    leftThumbProximal:      byName['Bip001 L Finger0'],
    leftThumbIntermediate:  byName['Bip001 L Finger01'],
    leftThumbDistal:        byName['Bip001 L Finger02'],
    leftIndexProximal:      byName['Bip001 L Finger1'],
    leftIndexIntermediate:  byName['Bip001 L Finger11'],
    leftIndexDistal:        byName['Bip001 L Finger12'],
    leftMiddleProximal:     byName['Bip001 L Finger2'],
    leftMiddleIntermediate: byName['Bip001 L Finger21'],
    leftMiddleDistal:       byName['Bip001 L Finger22'],
    leftRingProximal:       byName['Bip001 L Finger3'],
    leftRingIntermediate:   byName['Bip001 L Finger31'],
    leftRingDistal:         byName['Bip001 L Finger32'],
    leftLittleProximal:     byName['Bip001 L Finger4'],
    leftLittleIntermediate: byName['Bip001 L Finger41'],
    leftLittleDistal:       byName['Bip001 L Finger42'],
    rightThumbProximal:      byName['Bip001 R Finger0'],
    rightThumbIntermediate:  byName['Bip001 R Finger01'],
    rightThumbDistal:        byName['Bip001 R Finger02'],
    rightIndexProximal:      byName['Bip001 R Finger1'],
    rightIndexIntermediate:  byName['Bip001 R Finger11'],
    rightIndexDistal:        byName['Bip001 R Finger12'],
    rightMiddleProximal:     byName['Bip001 R Finger2'],
    rightMiddleIntermediate: byName['Bip001 R Finger21'],
    rightMiddleDistal:       byName['Bip001 R Finger22'],
    rightRingProximal:       byName['Bip001 R Finger3'],
    rightRingIntermediate:   byName['Bip001 R Finger31'],
    rightRingDistal:         byName['Bip001 R Finger32'],
    rightLittleProximal:     byName['Bip001 R Finger4'],
    rightLittleIntermediate: byName['Bip001 R Finger41'],
    rightLittleDistal:       byName['Bip001 R Finger42']
  };

  try {
    const parserJson = gltf && gltf.parser && gltf.parser.json;
    const vrmExt = parserJson && parserJson.extensions && parserJson.extensions.VRM;
    const humanBones = vrmExt && vrmExt.humanoid && vrmExt.humanoid.humanBones;
    if (Array.isArray(humanBones)) {
      humanBones.forEach((hb) => {
        if (hb && hb.bone && typeof hb.node === 'number' && !hMap[hb.bone]) {
          const nDef = parserJson.nodes && parserJson.nodes[hb.node];
          if (nDef && nDef.name && byName[nDef.name]) {
            hMap[hb.bone] = byName[nDef.name];
          }
        }
      });
    }
  } catch (e) {}

  const bones = {
    pelvis: hMap.hips,
    spine:  hMap.spine,
    spine1: hMap.chest,
    spine2: hMap.upperChest,
    neck:   hMap.neck,
    head:   hMap.head,
    lClav:  hMap.leftShoulder,
    rClav:  hMap.rightShoulder,
    lArm:   hMap.leftUpperArm,
    rArm:   hMap.rightUpperArm,
    lFore:  hMap.leftLowerArm,
    rFore:  hMap.rightLowerArm,
    lHand:  hMap.leftHand,
    rHand:  hMap.rightHand,
    lThigh: hMap.leftUpperLeg,
    rThigh: hMap.rightUpperLeg,
    lCalf:  hMap.leftLowerLeg,
    rCalf:  hMap.rightLowerLeg,
    lFoot:  hMap.leftFoot,
    rFoot:  hMap.rightFoot,
    lSleeve: byName['Bone001_m'],
    rSleeve: byName['Bone001'],
    lEyeUpper: byName['Bone86'],
    rEyeUpper: byName['Bone86_m'],
    lEyeLower: byName['Bone88'],
    rEyeLower: byName['Bone88_m'],
    lEyeball:  byName['Bone89'],
    rEyeball:  byName['Bone89_m'],
    lBrowIn:   byName['Bone71'],
    rBrowIn:   byName['Bone71_m'],
    lBrowOut:  byName['Bone72'],
    rBrowOut:  byName['Bone72_m'],
    jaw:       byName['Bone085'],
    lLipLower: byName['Bone95'],
    rLipLower: byName['Bone95_m'],
    lLipUpper: byName['Bone70'],
    rLipUpper: byName['Bone70_m'],
    lMouthCorner: byName['Bone97'],
    rMouthCorner: byName['Bone97_m']
  };

  root.traverse((mesh) => {
    if (mesh.isSkinnedMesh && mesh.geometry && mesh.skeleton) {
      const skBones = mesh.skeleton.bones;
      const faceBoneIndices = new Set();
      const faceNames = new Set([
        'Bone86', 'Bone86_m', 'Bone82', 'Bone82_m', 'Bone91', 'Bone91_m',
        'Bone88', 'Bone88_m', 'Bone73', 'Bone73_m', 'Bone75', 'Bone75_m',
        'Bone89', 'Bone89_m', 'Bone70', 'Bone70_m', 'Bone95', 'Bone95_m',
        'Bone085', 'Bone97', 'Bone97_m', 'Bone71', 'Bone71_m', 'Bone72', 'Bone72_m'
      ]);
      skBones.forEach((b, idx) => {
        if (faceNames.has(b.name)) faceBoneIndices.add(idx);
      });
      const si = mesh.geometry.attributes.skinIndex;
      const sw = mesh.geometry.attributes.skinWeight;
      if (si && sw && faceBoneIndices.size > 0) {
        for (let i = 0; i < si.count; i++) {
          const i0 = si.getX(i), i1 = si.getY(i), i2 = si.getZ(i), i3 = si.getW(i);
          let w0 = sw.getX(i), w1 = sw.getY(i), w2 = sw.getZ(i), w3 = sw.getW(i);
          if (faceBoneIndices.has(i0) || faceBoneIndices.has(i1) || faceBoneIndices.has(i2) || faceBoneIndices.has(i3)) {
            if (!faceBoneIndices.has(i0)) w0 = 0;
            if (!faceBoneIndices.has(i1)) w1 = 0;
            if (!faceBoneIndices.has(i2)) w2 = 0;
            if (!faceBoneIndices.has(i3)) w3 = 0;
            const sum = w0 + w1 + w2 + w3;
            if (sum > 0.05) {
              sw.setXYZW(i, w0 / sum, w1 / sum, w2 / sum, w3 / sum);
            }
          }
        }
        sw.needsUpdate = true;
      }
    }
  });

  allBones.forEach((b) => {
    b.userData = b.userData || {};
    b.userData.restQuat = b.quaternion.clone();
    b.userData.restPos = b.position.clone();
  });

  return { bones, hMap, allBones, secondary };
}

function activateStandingIdleAnimation() {
  if (!vrmMixer) return;
  const idleClip = vrmaClips['neutral_idle'] || vrmaClips['neutral_idle2'] || vrmaClips['sit_idle'];
  if (!idleClip) return;
  if (!vrmaIdleAction) {
    vrmaIdleAction = vrmMixer.clipAction(idleClip);
    vrmaIdleAction.setLoop(THREE.LoopPingPong, Infinity);
    vrmaIdleAction.timeScale = 0.85;
    vrmaIdleAction.play();
    console.log('[VRM] Standing idle animation active (neutral_idle.bvh with smooth PingPong loop)');
  }
}

function preloadVrmaMotionPack() {
  if (!vrmModel || !THREE.GLTFLoader) return;
  const loader = new THREE.GLTFLoader();

  // Deduplicate file loads so shared files (like pose_lean_in.vrma) load once
  const fileToKeys = {};
  Object.keys(VRMA_MOTION_FILES).forEach((k) => {
    const fn = VRMA_MOTION_FILES[k].file;
    if (!fileToKeys[fn]) fileToKeys[fn] = [];
    fileToKeys[fn].push(k);
  });

  Object.keys(fileToKeys).forEach((fileName) => {
    const keys = fileToKeys[fileName];
    const isLocalFile = window.location.protocol === 'file:';
    const url = isLocalFile ? `../../models/vrma/${fileName}` : `/api/models/vrma?name=${encodeURIComponent(fileName)}`;
    loader.load(
      url,
      (vrmaGltf) => {
        try {
          const clip = buildRetargetedVrmaClip(keys[0], vrmaGltf);
          if (clip) {
            keys.forEach((k) => { vrmaClips[k] = clip; });
            console.log(`[VRMA] Loaded & retargeted ${fileName} -> ${keys.join(',')} (${clip.duration.toFixed(2)}s)`);
          }
        } catch (err) {
          console.error(`[VRMA] Retarget error for ${fileName}:`, err);
        }
      },
      undefined,
      (err) => console.warn(`[VRMA] Could not load ${fileName}:`, err)
    );
  });

  preloadBvhMotionPack();
}

function preloadBvhMotionPack() {
  // Fetch both BVH and VRMA manifests so all 135 animations are registered immediately
  fetch('/api/models/vrma')
    .then(r => r.ok ? r.json() : { files: [] })
    .then(vrmaData => {
      const vrmaFiles = (vrmaData && vrmaData.files) ? vrmaData.files : [];
      vrmaFiles.forEach(vf => {
        const key = (vf.action || vf.name.replace(/\.vrma$/i, '')).toLowerCase();
        if (!VRMA_MOTION_FILES[key]) {
          VRMA_MOTION_FILES[key] = {
            file: vf.name,
            label: key.replace(/_/g, ' '),
            startOffset: 0.0,
            timeScale: 1.0
          };
        }
      });
      if (typeof renderAnimationsDrawer === 'function') renderAnimationsDrawer();
    })
    .catch(() => {});
  fetch('/api/models/bvh')
    .then(r => r.ok ? r.json() : { files: [] })
    .then(data => {
      const files = (data && data.files) ? data.files : [];
      // Register all 116 BVH files in catalog for instant on-demand loading
      files.forEach((item) => {
        const fileName = item.name || item;
        const actionKey = (item.action || fileName.replace(/\.bvh$/i, '')).toLowerCase();
        vrmBvhCatalog[actionKey] = fileName;
      });
      if (typeof renderAnimationsDrawer === 'function') renderAnimationsDrawer();
      const priorityBvh = [
        'neutral_idle', 'neutral_idle2', 'action_jump', 'amusement',
        'dance_hiphop_step', 'dance_side_groove', 'excitement', 'joy', 'curiosity'
      ];
      priorityBvh.forEach((key) => {
        const fileName = vrmBvhCatalog[key];
        if (!fileName) return;
        fetch(`/api/models/bvh?name=${encodeURIComponent(fileName)}`)
          .then(r => r.ok ? r.text() : '')
          .then(bvhText => {
            if (!bvhText || !bvhText.includes('HIERARCHY')) return;
            const clip = buildRetargetedBvhClip(key, bvhText);
            if (clip) {
              vrmaClips[key] = clip;
              if (key === 'action_jump') vrmaClips['jump'] = clip;
              if (key === 'amusement') vrmaClips['point_laugh'] = clip;
              if (key === 'dance_hiphop_step') vrmaClips['dance'] = clip;
              if (key === 'neutral_idle') activateStandingIdleAnimation();
              console.log(`[BVH] Preloaded ${fileName} -> '${key}' (${clip.duration.toFixed(2)}s)`);
            }
          })
          .catch(() => {});
      });
    })
    .catch(() => {});
}

function buildRetargetedBvhClip(actionKey, bvhText) {
  const lines = bvhText.split(/\r?\n/).map(l => l.trim()).filter(l => l.length > 0);
  let idx = 0;
  const joints = [];
  const stack = [];

  const BVH_BONE_MAP = {
    'hips': 'hips', 'hip': 'hips', 'pelvis': 'hips', 'root': 'hips', 'center': 'hips', 'bip001_pelvis': 'hips',
    'spine': 'spine', 'abdomen': 'spine', 'waist': 'spine', 'lowerback': 'spine', 'bip001_spine': 'spine',
    'chest': 'chest', 'spine1': 'chest', 'thorax': 'chest', 'bip001_spine1': 'chest',
    'upperchest': 'upperChest', 'spine2': 'upperChest', 'chest2': 'upperChest', 'bip001_spine2': 'upperChest',
    'neck': 'neck', 'neck1': 'neck', 'bip001_neck': 'neck',
    'head': 'head', 'bip001_head': 'head',
    'leftshoulder': 'leftShoulder', 'lcollar': 'leftShoulder', 'shoulder_l': 'leftShoulder', 'l_shoulder': 'leftShoulder', 'bip001_l_clavicle': 'leftShoulder',
    'leftupperarm': 'leftUpperArm', 'leftarm': 'leftUpperArm', 'lshldr': 'leftUpperArm', 'upperarm_l': 'leftUpperArm', 'l_upperarm': 'leftUpperArm', 'bip001_l_upperarm': 'leftUpperArm',
    'leftlowerarm': 'leftLowerArm', 'leftforearm': 'leftLowerArm', 'lforearm': 'leftLowerArm', 'lowerarm_l': 'leftLowerArm', 'l_forearm': 'leftLowerArm', 'bip001_l_forearm': 'leftLowerArm',
    'lefthand': 'leftHand', 'lhand': 'leftHand', 'hand_l': 'leftHand', 'l_hand': 'leftHand', 'bip001_l_hand': 'leftHand',
    'rightshoulder': 'rightShoulder', 'rcollar': 'rightShoulder', 'shoulder_r': 'rightShoulder', 'r_shoulder': 'rightShoulder', 'bip001_r_clavicle': 'rightShoulder',
    'rightupperarm': 'rightUpperArm', 'rightarm': 'rightUpperArm', 'rshldr': 'rightUpperArm', 'upperarm_r': 'rightUpperArm', 'r_upperarm': 'rightUpperArm', 'bip001_r_upperarm': 'rightUpperArm',
    'rightlowerarm': 'rightLowerArm', 'rightforearm': 'rightLowerArm', 'rforearm': 'rightLowerArm', 'lowerarm_r': 'rightLowerArm', 'r_forearm': 'rightLowerArm', 'bip001_r_forearm': 'rightLowerArm',
    'righthand': 'rightHand', 'rhand': 'rightHand', 'hand_r': 'rightHand', 'r_hand': 'rightHand', 'bip001_r_hand': 'rightHand',
    'leftupperleg': 'leftUpperLeg', 'leftupleg': 'leftUpperLeg', 'lthigh': 'leftUpperLeg', 'thigh_l': 'leftUpperLeg', 'l_thigh': 'leftUpperLeg', 'bip001_l_thigh': 'leftUpperLeg',
    'leftlowerleg': 'leftLowerLeg', 'leftleg': 'leftLowerLeg', 'lshin': 'leftLowerLeg', 'lcalf': 'leftLowerLeg', 'calf_l': 'leftLowerLeg', 'l_calf': 'leftLowerLeg', 'bip001_l_calf': 'leftLowerLeg',
    'leftfoot': 'leftFoot', 'lfoot': 'leftFoot', 'foot_l': 'leftFoot', 'l_foot': 'leftFoot', 'bip001_l_foot': 'leftFoot',
    'lefttoes': 'leftToes', 'lefttoebase': 'leftToes', 'ltoe': 'leftToes', 'bip001_l_toe0': 'leftToes',
    'rightupperleg': 'rightUpperLeg', 'rightupleg': 'rightUpperLeg', 'rthigh': 'rightUpperLeg', 'thigh_r': 'rightUpperLeg', 'r_thigh': 'rightUpperLeg', 'bip001_r_thigh': 'rightUpperLeg',
    'rightlowerleg': 'rightLowerLeg', 'rightleg': 'rightLowerLeg', 'rshin': 'rightLowerLeg', 'rcalf': 'rightLowerLeg', 'calf_r': 'rightLowerLeg', 'r_calf': 'rightLowerLeg', 'bip001_r_calf': 'rightLowerLeg',
    'rightfoot': 'rightFoot', 'rfoot': 'rightFoot', 'foot_r': 'rightFoot', 'r_foot': 'rightFoot', 'bip001_r_foot': 'rightFoot',
    'righttoes': 'rightToes', 'righttoebase': 'rightToes', 'rtoe': 'rightToes', 'bip001_r_toe0': 'rightToes',
    'leftthumbproximal': 'leftThumbProximal', 'leftthumbintermediate': 'leftThumbIntermediate', 'leftthumbdistal': 'leftThumbDistal',
    'leftindexproximal': 'leftIndexProximal', 'leftindexintermediate': 'leftIndexIntermediate', 'leftindexdistal': 'leftIndexDistal',
    'leftmiddleproximal': 'leftMiddleProximal', 'leftmiddleintermediate': 'leftMiddleIntermediate', 'leftmiddledistal': 'leftMiddleDistal',
    'leftringproximal': 'leftRingProximal', 'leftringintermediate': 'leftRingIntermediate', 'leftringdistal': 'leftRingDistal',
    'leftlittleproximal': 'leftLittleProximal', 'leftlittleintermediate': 'leftLittleIntermediate', 'leftlittledistal': 'leftLittleDistal',
    'rightthumbproximal': 'rightThumbProximal', 'rightthumbintermediate': 'rightThumbIntermediate', 'rightthumbdistal': 'rightThumbDistal',
    'rightindexproximal': 'rightIndexProximal', 'rightindexintermediate': 'rightIndexIntermediate', 'rightindexdistal': 'rightIndexDistal',
    'rightmiddleproximal': 'rightMiddleProximal', 'rightmiddleintermediate': 'rightMiddleIntermediate', 'rightmiddledistal': 'rightMiddleDistal',
    'rightringproximal': 'rightRingProximal', 'rightringintermediate': 'rightRingIntermediate', 'rightringdistal': 'rightRingDistal',
    'rightlittleproximal': 'rightLittleProximal', 'rightlittleintermediate': 'rightLittleIntermediate', 'rightlittledistal': 'rightLittleDistal'
  };

  let inEndSite = false;
  while (idx < lines.length && lines[idx] !== 'MOTION') {
    const line = lines[idx++];
    const parts = line.split(/\s+/);
    const kw = parts[0].toUpperCase();
    if (kw === 'ROOT' || kw === 'JOINT') {
      const rawName = parts.slice(1).join('_').replace(/^mixamorig:?/i, '');
      const cleanKey = rawName.toLowerCase().replace(/[^a-z0-9_]/g, '');
      const hName = BVH_BONE_MAP[cleanKey] || BVH_BONE_MAP[cleanKey.replace(/_/g, '')] || null;
      const jObj = { name: rawName, hName: hName, channels: [], parent: stack.length > 0 ? stack[stack.length - 1] : null };
      joints.push(jObj);
      stack.push(jObj);
    } else if (kw === 'END') {
      inEndSite = true;
    } else if (kw === '}') {
      if (inEndSite) inEndSite = false;
      else stack.pop();
    } else if (kw === 'CHANNELS' && !inEndSite && stack.length > 0) {
      const count = parseInt(parts[1], 10) || 0;
      stack[stack.length - 1].channels = parts.slice(2, 2 + count);
    }
  }

  if (idx >= lines.length || lines[idx] !== 'MOTION') return null;
  idx++;

  let numFrames = 0;
  let frameTime = 0.033333;
  while (idx < lines.length) {
    const line = lines[idx];
    if (/^Frames:/i.test(line)) {
      numFrames = parseInt(line.split(':')[1].trim(), 10) || 0;
      idx++;
    } else if (/^Frame Time:/i.test(line)) {
      frameTime = parseFloat(line.split(':')[1].trim()) || 0.033333;
      idx++;
      break;
    } else {
      idx++;
    }
  }
  if (numFrames <= 0) return null;

    const times = new Float32Array(numFrames);
  for (let f = 0; f < numFrames; f++) times[f] = f * frameTime;
  const trackQuats = {};
  joints.forEach((j) => {
    if (j.hName && vrmHumanoidMap[j.hName]) {
      trackQuats[j.hName] = new Float32Array(numFrames * 4);
    }
  });
  // Check if root hips has position channels for gravity & vertical displacement
  const rootJoint = joints.length > 0 ? joints[0] : null;
  const hasHipsPos = rootJoint && rootJoint.hName === 'hips' && rootJoint.channels.some(c => c.toLowerCase().includes('position'));
  const rawHipsPos = [];
  const deg2rad = Math.PI / 180.0;
  const qStep = new THREE.Quaternion();
  const qFrame = new THREE.Quaternion();
  const qVrm0 = new THREE.Quaternion();
  const qTarget = new THREE.Quaternion();
  const axX = new THREE.Vector3(1, 0, 0);
  const axY = new THREE.Vector3(0, 1, 0);
  const axZ = new THREE.Vector3(0, 0, 1);
  let fCount = 0;
  while (idx < lines.length && fCount < numFrames) {
    const vals = lines[idx++].split(/\s+/).map(Number);
    let cPtr = 0;
    for (let jIdx = 0; jIdx < joints.length; jIdx++) {
      const j = joints[jIdx];
      qFrame.identity();
      let posX = 0, posY = 0, posZ = 0;
      for (let c = 0; c < j.channels.length; c++) {
        const ch = j.channels[c].toLowerCase();
        const v = vals[cPtr++] || 0;
        if (ch === 'xposition') posX = v;
        else if (ch === 'yposition') posY = v;
        else if (ch === 'zposition') posZ = v;
        else if (ch === 'xrotation') {
          qStep.setFromAxisAngle(axX, v * deg2rad);
          qFrame.multiply(qStep);
        } else if (ch === 'yrotation') {
          qStep.setFromAxisAngle(axY, v * deg2rad);
          qFrame.multiply(qStep);
        } else if (ch === 'zrotation') {
          qStep.setFromAxisAngle(axZ, v * deg2rad);
          qFrame.multiply(qStep);
        }
      }
      if (jIdx === 0 && hasHipsPos) {
        rawHipsPos.push({ x: posX, y: posY, z: posZ });
      }
      if (j.hName && trackQuats[j.hName]) {
        const dstBone = vrmHumanoidMap[j.hName];
        const dstRestQuat = (dstBone.userData && dstBone.userData.restQuat) ? dstBone.userData.restQuat : new THREE.Quaternion();
        qVrm0.set(-qFrame.x, qFrame.y, -qFrame.z, qFrame.w);
        qTarget.copy(dstRestQuat).multiply(qVrm0);
        const out = trackQuats[j.hName];
        const base = fCount * 4;
        out[base]     = qTarget.x;
        out[base + 1] = qTarget.y;
        out[base + 2] = qTarget.z;
        out[base + 3] = qTarget.w;
      }
    }
    fCount++;
  }
  const retargetedTracks = [];
  Object.keys(trackQuats).forEach((hName) => {
    const dstBone = vrmHumanoidMap[hName];
    if (dstBone) {
      retargetedTracks.push(new THREE.QuaternionKeyframeTrack(
        `${dstBone.uuid}.quaternion`,
        times,
        trackQuats[hName]
      ));
    }
  });
  // Calculate hips position track with gravity & ground anchoring
  if (hasHipsPos && rawHipsPos.length > 0 && vrmHumanoidMap['hips']) {
    const hipsBone = vrmHumanoidMap['hips'];
    const restPos = (hipsBone.userData && hipsBone.userData.restPos) ? hipsBone.userData.restPos : new THREE.Vector3();
    const hipsVals = new Float32Array(numFrames * 3);
    // Identify action type: Is this an intentional ground action (kneel, sit, lay, crawl, crouch)?
    const isGroundAction = /kneel|sit|lay|crawling|crouch/i.test(actionKey);
    // Compute median of motion frames to discard single-frame T-pose spikes (like Frame 0 Y=11.68)
    const sortedY = rawHipsPos.map(p => p.y).sort((a, b) => a - b);
    const medianY = sortedY[Math.floor(sortedY.length / 2)];
    if (isGroundAction) {
      // For kneeling/sitting/laying/crouching actions:
      // In BVH clips with T-pose header (f0 ~ 11.68, motion ~ -5.5), baseline standing is f0.
      // In zero-centered clips (motion ~ -6.0 to -8.0), baseline standing is 0.0.
      const f0_y = rawHipsPos[0].y;
      const baselineY = (f0_y > 4.0) ? f0_y : 0.0;
      // bvhScale ~0.035 drops hips by ~0.60m so knees/shins rest flush on the floor surface
      const bvhScale = 0.035;
      for (let f = 0; f < rawHipsPos.length; f++) {
        // Clamp frame 0 if it's an un-transitioned T-pose spike
        const curY = (f === 0 && f0_y > 4.0 && rawHipsPos.length > 1) ? rawHipsPos[1].y : rawHipsPos[f].y;
        const dy = (curY - baselineY) * bvhScale;
        const baseIdx = f * 3;
        hipsVals[baseIdx]     = restPos.x;
        // Lower hips down to ground level
        hipsVals[baseIdx + 1] = restPos.y + dy;
        hipsVals[baseIdx + 2] = restPos.z;
      }
    } else {
      // For standing, dancing, jumping, and walking actions:
      // The character is standing on her feet on the floor.
      // Dynamic baseline is the motion's median standing height.
      // Small bounce/groove (±0.02m) and jumps (upward) are preserved, but feet NEVER clip into floor.
      const baselineY = medianY;
      const bvhScale = 0.020;
      for (let f = 0; f < rawHipsPos.length; f++) {
        const curY = (f === 0 && rawHipsPos[0].y > 4.0 && rawHipsPos.length > 1) ? rawHipsPos[1].y : rawHipsPos[f].y;
        const rawDy = (curY - baselineY) * bvhScale;
        // Strictly prevent hips from sinking below resting standing height while dancing/walking (floor collision clamp)
        const dy = Math.max(0.0, Math.min(0.35, rawDy));
        const baseIdx = f * 3;
        hipsVals[baseIdx]     = restPos.x;
        hipsVals[baseIdx + 1] = restPos.y + dy;
        hipsVals[baseIdx + 2] = restPos.z;
      }
    }
    retargetedTracks.push(new THREE.VectorKeyframeTrack(
      `${hipsBone.uuid}.position`,
      times,
      hipsVals
    ));
  }
  return new THREE.AnimationClip(actionKey, numFrames * frameTime, retargetedTracks);
}

function buildRetargetedVrmaClip(actionKey, vrmaGltf) {
  const parserJson = vrmaGltf.parser && vrmaGltf.parser.json;
  const ext = parserJson && parserJson.extensions && parserJson.extensions.VRMC_vrm_animation;
  const humanBones = ext && ext.humanoid && ext.humanoid.humanBones;
  const srcClip = vrmaGltf.animations && vrmaGltf.animations[0];
  if (!humanBones || !srcClip) return null;

  vrmaGltf.scene.updateMatrixWorld(true);

  const nodeNameToHumanoid = {};
  const vrmaNodeRestWorld = {};
  const vrmaParentRestWorld = {};
  const vrmaHipsRestPos = new THREE.Vector3();

  const vrmaNodeByName = {};
  vrmaGltf.scene.traverse((obj) => {
    if (obj.name) {
      vrmaNodeByName[obj.name] = obj;
      vrmaNodeByName[obj.name.replace(/_/g, ' ')] = obj;
    }
  });

  Object.keys(humanBones).forEach((hName) => {
    const nodeIdx = humanBones[hName].node;
    const nodeDef = parserJson.nodes && parserJson.nodes[nodeIdx];
    if (!nodeDef || !nodeDef.name) return;
    const nName = nodeDef.name;
    const nNameSan = nName.replace(/\s+/g, '_');
    nodeNameToHumanoid[nName] = hName;
    nodeNameToHumanoid[nNameSan] = hName;

    const vrmaObj = vrmaNodeByName[nName];
    if (vrmaObj) {
      const qw = new THREE.Quaternion();
      vrmaObj.getWorldQuaternion(qw);
      vrmaNodeRestWorld[nName] = qw;
      vrmaNodeRestWorld[nNameSan] = qw;

      const qp = new THREE.Quaternion();
      if (vrmaObj.parent) vrmaObj.parent.getWorldQuaternion(qp);
      vrmaParentRestWorld[nName] = qp;
      vrmaParentRestWorld[nNameSan] = qp;

      if (hName === 'hips') {
        vrmaHipsRestPos.copy(vrmaObj.position);
      }
    }
  });

  const retargetedTracks = [];
  const qRaw = new THREE.Quaternion();
  const qNorm = new THREE.Quaternion();
  const qVrm0 = new THREE.Quaternion();
  const qTarget = new THREE.Quaternion();

  for (let i = 0; i < srcClip.tracks.length; i++) {
    const track = srcClip.tracks[i];
    const dotIdx = track.name.lastIndexOf('.');
    if (dotIdx < 0) continue;
    const srcNodeName = track.name.substring(0, dotIdx);
    const propName = track.name.substring(dotIdx + 1);

    const hName = nodeNameToHumanoid[srcNodeName];
    if (!hName) continue;
    const dstBone = vrmHumanoidMap[hName];
    if (!dstBone) continue;

    if (propName === 'quaternion') {
      const qParentWorld = vrmaParentRestWorld[srcNodeName] || new THREE.Quaternion();
      const qNodeWorldInv = (vrmaNodeRestWorld[srcNodeName] || new THREE.Quaternion()).clone().invert();
      const dstRestQuat = (dstBone.userData && dstBone.userData.restQuat) ? dstBone.userData.restQuat : new THREE.Quaternion();

      const srcVals = track.values;
      const dstVals = new Float32Array(srcVals.length);

      for (let k = 0; k < srcVals.length; k += 4) {
        qRaw.set(srcVals[k], srcVals[k + 1], srcVals[k + 2], srcVals[k + 3]);
        qNorm.copy(qParentWorld).multiply(qRaw).multiply(qNodeWorldInv);
        qVrm0.set(-qNorm.x, qNorm.y, -qNorm.z, qNorm.w);
        qTarget.copy(dstRestQuat).multiply(qVrm0);

        dstVals[k]     = qTarget.x;
        dstVals[k + 1] = qTarget.y;
        dstVals[k + 2] = qTarget.z;
        dstVals[k + 3] = qTarget.w;
      }

      let tArr = track.times.slice();
      let vArr = dstVals;
      // Expand 1-frame static pose VRMAs (e.g. pose_lean_in.vrma) to 4.0s so AnimationMixer holds & crossfades smoothly
      if (tArr.length === 1) {
        tArr = new Float32Array([0.0, 4.0]);
        vArr = new Float32Array(dstVals.length * 2);
        vArr.set(dstVals, 0);
        vArr.set(dstVals, dstVals.length);
      }

      retargetedTracks.push(new THREE.QuaternionKeyframeTrack(
        `${dstBone.uuid}.quaternion`,
        tArr,
        vArr
      ));
    } else if (propName === 'position' && hName === 'hips' && track.values.length >= 3) {
      // Keep character anchored horizontally in center of stage and prevent floating upward
      const dstRestPos = (dstBone.userData && dstBone.userData.restPos) ? dstBone.userData.restPos : new THREE.Vector3();
      const srcVals = track.values;
      const dstVals = new Float32Array(srcVals.length);
      const baseY0 = srcVals[1];

      for (let k = 0; k < srcVals.length; k += 3) {
        const dy = Math.min(0.01, srcVals[k + 1] - baseY0); // allow crouch/squat down, prevent upward floating
        dstVals[k]     = dstRestPos.x;
        dstVals[k + 1] = dstRestPos.y + dy;
        dstVals[k + 2] = dstRestPos.z;
      }

      let tArr = track.times.slice();
      let vArr = dstVals;
      if (tArr.length === 1) {
        tArr = new Float32Array([0.0, 4.0]);
        vArr = new Float32Array(dstVals.length * 2);
        vArr.set(dstVals, 0);
        vArr.set(dstVals, dstVals.length);
      }

      retargetedTracks.push(new THREE.VectorKeyframeTrack(
        `${dstBone.uuid}.position`,
        tArr,
        vArr
      ));
    }
  }

  const finalDur = srcClip.duration < 0.05 ? 4.0 : srcClip.duration;
  return new THREE.AnimationClip(actionKey, finalDur, retargetedTracks);
}

function initVrmEngine() {
  if (vrmInitialized) return;
  const container = document.getElementById('vrmStageContainer');
  const canvas = document.getElementById('vrmCanvas');
  if (!container || !canvas || typeof THREE === 'undefined') {
    console.warn("[VRM] Waiting for Three.js / VRM container...");
    return;
  }

  const width = container.clientWidth || 360;
  const height = container.clientHeight || 460;

  vrmScene = new THREE.Scene();
  vrmClock = new THREE.Clock();

  vrmCamera = new THREE.PerspectiveCamera(32, width / height, 0.1, 60.0);
  currentLookAt = new THREE.Vector3(0, vrmBaseY + 0.68, 0);
  targetLookAt = new THREE.Vector3(0, vrmBaseY + 0.68, 0);
  targetCamPos = new THREE.Vector3(0.0, vrmBaseY + 0.82, 4.05);
  vrmCamera.position.copy(targetCamPos);
  vrmCamera.lookAt(currentLookAt);

  try {
    vrmRenderer = new THREE.WebGLRenderer({
      canvas: canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance'
    });
    const initDpr = Math.min(window.devicePixelRatio || 1, 1.0);
    vrmRenderer.setPixelRatio(initDpr);
    vrmRenderer.setSize(width, height, false);
    vrmRenderer.outputEncoding = THREE.sRGBEncoding;
    if (vrmRenderer.shadowMap) {
      vrmRenderer.shadowMap.enabled = true;
      vrmRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
    }
    if (window.ResizeObserver) {
      const ro = new ResizeObserver(() => {
        requestAnimationFrame(() => resizeVrmToStage());
      });
      const stage = document.getElementById('vrmStageContainer');
      if (stage) ro.observe(stage);
      const floatBody = document.getElementById('vrmFloatingBody');
      if (floatBody) ro.observe(floatBody);
    }
  } catch (err) {
    console.error("[VRM] WebGLRenderer init failed:", err);
    return;
  }

  vrmBaseAmbientLight = new THREE.AmbientLight(0xfff0ff, 0.90);
  vrmScene.add(vrmBaseAmbientLight);

  vrmBaseKeyLight = new THREE.DirectionalLight(0xffffff, 0.68);
  vrmBaseKeyLight.position.set(1.2, 2.4, 2.6);
  vrmScene.add(vrmBaseKeyLight);

  vrmBaseRimLight = new THREE.DirectionalLight(0xc084fc, 0.45);
  vrmBaseRimLight.position.set(-1.5, 1.5, -2.0);
  vrmScene.add(vrmBaseRimLight);

  vrmInitialized = true;
  initFloatingHudDraggable();
  initAvatarPokeRaycaster(canvas);
  initRoomTouchOrbitLookAround(canvas);
  vrmEnvironmentGroup = new THREE.Group();
  vrmScene.add(vrmEnvironmentGroup);
  initCustomPropsGroup();
  initConnectomeFly();
  loadRumVrmModel(currentVrmModelName);
  setVrmEnvironment(currentEnvironmentName);
  // Yoshi is an optional custom prop, not a forced hardcoded fixture
  const decorCfg = loadRoomDecorationsConfig();
  if (decorCfg && decorCfg.yoshi) {
    loadYoshiPlushProp();
  }
  initSolarEphemerisEngine();

  let lastVrmThrottleRenderTime = 0;

  function animateVrm() {
    requestAnimationFrame(animateVrm);
    // Phase 13: Occlusion-Aware WebGL Thermal Throttling
    // When tab is hidden or companion is minimized while on intensive fullscreen views, throttle to 5 FPS (200ms)
    const isOccluded = document.hidden || (
      Boolean(window.isCompanionMinimizedByUser) &&
      ['maps', 'dragy', 'maintenance', 'settings', 'music'].includes(currentScreen)
    );
    const nowPerf = performance.now();
    if (isOccluded && (nowPerf - lastVrmThrottleRenderTime < 200)) {
      return;
    }
    lastVrmThrottleRenderTime = nowPerf;
    try {

    const delta = vrmClock ? Math.min(vrmClock.getDelta(), 0.1) : 0.016;
    const time = vrmClock ? vrmClock.getElapsedTime() : Date.now() * 0.001;
    const now = Date.now();

    // 1. Natural Eye Blinking Sweep (240ms smooth blink with 55ms closed hold + occasional double-blink)
    if (!vrmIsBlinking && now > vrmNextBlinkTime) {
      vrmIsBlinking = true;
      vrmBlinkStartTime = now;
    }
    if (vrmIsBlinking) {
      const bdt = now - vrmBlinkStartTime;
      if (bdt < 85) {
        vrmBlinkProgress = bdt / 85;
      } else if (bdt < 140) {
        vrmBlinkProgress = 1.0;
      } else if (bdt < 240) {
        vrmBlinkProgress = 1.0 - ((bdt - 140) / 100);
      } else {
        vrmBlinkProgress = 0.0;
        vrmIsBlinking = false;
        vrmNextBlinkTime = (Math.random() < 0.28) ? (now + 180) : (now + 2200 + Math.random() * 1600);
      }
    }

    // 2. Speech & Action State (Synced strictly to hardware audio playback when SSE is connected!)
    const isSpeaking = (isHardwareSpeaking || now < vrmSpeechEndTime || now < (typeof waifuSpeechEndTime !== 'undefined' ? waifuSpeechEndTime : 0));
    const isReacting = (now < vrmReactionEndTime);
    const isSpeedPanic = (now < vrmSpeedPanicEndTime);
    const dancing = (isMusicPlaying() && !isSpeaking && !vrmHasError && !isSpeedPanic);

    // 3. Smooth G-Force Inertia Interpolation (NO vertical floating!)
    // 3. Smooth G-Force Inertia, Pitch & Cornering Apex Roll Interpolation
    rumCurrentInertiaZ += (rumTargetInertiaZ - rumCurrentInertiaZ) * Math.min(1.0, delta * 6.0);
    rumCurrentPitch += (rumTargetPitch - rumCurrentPitch) * Math.min(1.0, delta * 5.0);
    rumCurrentRoll += (rumTargetRoll - rumCurrentRoll) * Math.min(1.0, delta * 5.0);
    // Smooth Contextual Gauge Gaze Lerp (1.8s glance toward instrument cluster when boost > 15 PSI or coolant > 215°F)
    const isGazingAtGauges = (now < rumGazeEndTime);
    const targetGazeYaw = isGazingAtGauges ? rumGazeTargetYaw : 0.0;
    const targetGazePitch = isGazingAtGauges ? rumGazeTargetPitch : 0.0;
    const gazeLerpRate = isGazingAtGauges ? 6.5 : 4.5;
    rumCurrentGazeYaw += (targetGazeYaw - rumCurrentGazeYaw) * Math.min(1.0, delta * gazeLerpRate);
    rumCurrentGazePitch += (targetGazePitch - rumCurrentGazePitch) * Math.min(1.0, delta * gazeLerpRate);

    if (vrmModel) {
      const isActionActive = (now < vrmActionEndTime);
      // Autonomous Roaming State Update
      updateAutonomousRoaming(delta, isSpeaking, isReacting, isActionActive, dancing, isSpeedPanic);
      // Environment surface elevation (e.g. stepping onto raised tatami mat in Garden)
      const targetElevation = getEnvironmentSurfaceElevation(vrmRoamCurrentPos.x, vrmRoamCurrentPos.z);
      vrmCurrentElevation += (targetElevation - vrmCurrentElevation) * Math.min(1.0, delta * 7.0);
      // Anchor feet firmly on stage floor (vrmBaseY + elevation), apply autonomous roaming X/Z & G-force inertia
      vrmModel.rotation.set(0, vrmRoamCurrentRotY, 0);
      vrmModel.position.set(
        -vrmCenter.x + vrmRoamCurrentPos.x,
        vrmBaseY + vrmCurrentElevation,
        (-vrmCenter.z) + vrmRoamCurrentPos.z + rumCurrentInertiaZ
      );
      if (!isActionActive && vrmaActiveAction && vrmaActiveName !== 'walk_loop') {
        stopActiveVrmaClip(0.45);
      }

      // Natural Music Groove: In-seat rhythmic head bobbing & shoulder sway instead of repetitive standing dance
      if (dancing && !isSpeaking && vrmBones.head) {
        const musicT = clock.getElapsedTime();
        const bobPitch = Math.sin(musicT * 7.0) * 0.08;
        const bobRoll = Math.sin(musicT * 3.5) * 0.045;
        vrmBones.head.rotation.x = THREE.MathUtils.clamp(vrmBones.head.rotation.x + bobPitch, -0.45, 0.45);
        vrmBones.head.rotation.z = THREE.MathUtils.clamp(vrmBones.head.rotation.z + bobRoll, -0.35, 0.35);
        if (vrmBones.neck) {
          vrmBones.neck.rotation.x = THREE.MathUtils.clamp(vrmBones.neck.rotation.x + bobPitch * 0.5, -0.25, 0.25);
          vrmBones.neck.rotation.z = THREE.MathUtils.clamp(vrmBones.neck.rotation.z + bobRoll * 0.4, -0.20, 0.20);
        }
        if (vrmBones.spine) {
          vrmBones.spine.rotation.z = THREE.MathUtils.clamp(vrmBones.spine.rotation.z + bobRoll * 0.3, -0.15, 0.15);
        }
      }

      // Update AnimationMixer (drives active VRMA/BVH clips, neutral_idle.bvh standby AND roaming walk!)
      if (vrmMixer && (vrmaActiveAction || vrmaIdleAction || vrmRoamWalkAction)) {
        vrmMixer.update(delta);
        // Apply Physical Kinematics (Longitudinal G-forces & Cornering Apex Roll)
        if (vrmBones.spine) {
          vrmBones.spine.rotation.x = THREE.MathUtils.clamp(vrmBones.spine.rotation.x + rumCurrentPitch * 0.40, -0.30, 0.30);
          vrmBones.spine.rotation.z = THREE.MathUtils.clamp(vrmBones.spine.rotation.z + rumCurrentRoll * 0.40, -0.25, 0.25);
        }
        if (vrmBones.chest) {
          vrmBones.chest.rotation.x = THREE.MathUtils.clamp(vrmBones.chest.rotation.x + rumCurrentPitch * 0.30, -0.25, 0.25);
          vrmBones.chest.rotation.z = THREE.MathUtils.clamp(vrmBones.chest.rotation.z + rumCurrentRoll * 0.30, -0.20, 0.20);
        }
        if (vrmBones.neck) {
          vrmBones.neck.rotation.x = THREE.MathUtils.clamp(vrmBones.neck.rotation.x + rumCurrentPitch * 0.15 + rumCurrentGazePitch * 0.25, -0.30, 0.30);
          vrmBones.neck.rotation.y = THREE.MathUtils.clamp(vrmBones.neck.rotation.y + rumCurrentGazeYaw * 0.35, -0.40, 0.40);
          vrmBones.neck.rotation.z = THREE.MathUtils.clamp(vrmBones.neck.rotation.z + rumCurrentRoll * 0.15, -0.20, 0.20);
        }

        // Prevent unnatural owl-like head spinning! Strictly clamp head & neck rotation to natural human anatomy
        if (vrmBones.head) {
          vrmBones.head.rotation.y = THREE.MathUtils.clamp(vrmBones.head.rotation.y + rumCurrentGazeYaw * 0.65, -0.55, 0.55);
          vrmBones.head.rotation.x = THREE.MathUtils.clamp(vrmBones.head.rotation.x + rumCurrentPitch * 0.20 + rumCurrentGazePitch * 0.65, -0.45, 0.45);
          vrmBones.head.rotation.z = THREE.MathUtils.clamp(vrmBones.head.rotation.z + rumCurrentRoll * 0.20, -0.35, 0.35);
          // R.U.M. head tracking towards the fruit fly when actively feeding Pip with the dropper (maintains direct forward eye contact with Dad otherwise)
          if (connectomeFlyEnabled && connectomeFlyGroup && isHoldingDropper && !isSpeaking && !isReacting && !(Date.now() < rumGazeRetentionUntil)) {
            const rx = vrmRoamCurrentPos.x;
            const ry = vrmBaseY + 1.2;
            const rz = vrmRoamCurrentPos.z;
            const flyDist = Math.hypot(connectomeFlyGroup.position.x - rx, connectomeFlyGroup.position.z - rz);
            if (flyDist < 2.4 && connectomeFlyGroup.position.z > -2.2) {
              const dx = connectomeFlyGroup.position.x - rx;
              const dy = connectomeFlyGroup.position.y - ry;
              const dz = connectomeFlyGroup.position.z - rz;
              const angleToFly = Math.atan2(-dx, -dz);
              let diffYaw = THREE.MathUtils.euclideanModulo(angleToFly - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
              if (Math.abs(diffYaw) < 1.1) {
                const targetYaw = THREE.MathUtils.clamp(diffYaw, -0.45, 0.45);
                const targetPitch = THREE.MathUtils.clamp(dy * 0.4, -0.30, 0.30);
                vrmBones.head.rotation.y = THREE.MathUtils.lerp(vrmBones.head.rotation.y, targetYaw, Math.min(1.0, delta * 4.5));
                vrmBones.head.rotation.x = THREE.MathUtils.lerp(vrmBones.head.rotation.x, -targetPitch, Math.min(1.0, delta * 4.5));
              }
            }
          }
        }
        if (vrmBones.neck) {
          vrmBones.neck.rotation.y = THREE.MathUtils.clamp(vrmBones.neck.rotation.y, -0.35, 0.35);
        }
      } else {
        // Fallback only during the ~0.3s before neutral_idle.bvh finishes loading
        resetAllVrmBonesToRest();
        if (vrmBones.lArm) vrmBones.lArm.rotation.set(0, 0.10, 1.30);
        if (vrmBones.rArm) vrmBones.rArm.rotation.set(0, -0.10, -1.30);
      }

      // 4a. Facial Rig Animation: Reset facial bones to rest first, then apply Eye Blinking & Lip-Sync
      ['lEyeUpper', 'rEyeUpper', 'lEyeLower', 'rEyeLower', 'lEyeball', 'rEyeball',
       'jaw', 'lLipLower', 'rLipLower', 'lLipUpper', 'rLipUpper', 'lMouthCorner', 'rMouthCorner',
       'lBrowIn', 'rBrowIn', 'lBrowOut', 'rBrowOut'].forEach((fk) => {
        const fb = vrmBones[fk];
        if (fb && fb.userData) {
          if (fb.userData.restPos) fb.position.copy(fb.userData.restPos);
          if (fb.userData.restQuat) fb.quaternion.copy(fb.userData.restQuat);
          fb.scale.set(1, 1, 1);
        }
      });

      const blinkAmt = (vrmCurrentAction === 'amusement' || vrmCurrentAction === 'point_laugh') ? Math.max(vrmBlinkProgress, 0.85) : vrmBlinkProgress;
      if (blinkAmt > 0.01) {
        if (vrmBones.lEyeUpper && vrmBones.lEyeUpper.userData.restPos) {
          vrmBones.lEyeUpper.position.y = vrmBones.lEyeUpper.userData.restPos.y - 0.025 * blinkAmt;
          vrmBones.lEyeUpper.rotation.x = -0.12 * blinkAmt;
        }
        if (vrmBones.rEyeUpper && vrmBones.rEyeUpper.userData.restPos) {
          vrmBones.rEyeUpper.position.y = vrmBones.rEyeUpper.userData.restPos.y - 0.025 * blinkAmt;
          vrmBones.rEyeUpper.rotation.x = -0.12 * blinkAmt;
        }
        if (vrmBones.lEyeLower && vrmBones.lEyeLower.userData.restPos) {
          vrmBones.lEyeLower.position.y = vrmBones.lEyeLower.userData.restPos.y + 0.006 * blinkAmt;
        }
        if (vrmBones.rEyeLower && vrmBones.rEyeLower.userData.restPos) {
          vrmBones.rEyeLower.position.y = vrmBones.rEyeLower.userData.restPos.y + 0.006 * blinkAmt;
        }
        if (vrmBones.lEyeball && vrmBones.lEyeball.userData.restPos) {
          vrmBones.lEyeball.scale.set(1.0, Math.max(0.05, 1.0 - 0.95 * blinkAmt), 1.0);
          vrmBones.lEyeball.position.z = vrmBones.lEyeball.userData.restPos.z + 0.010 * blinkAmt;
        }
        if (vrmBones.rEyeball && vrmBones.rEyeball.userData.restPos) {
          vrmBones.rEyeball.scale.set(1.0, Math.max(0.05, 1.0 - 0.95 * blinkAmt), 1.0);
          vrmBones.rEyeball.position.z = vrmBones.rEyeball.userData.restPos.z + 0.010 * blinkAmt;
        }
      // Contextual Gauge Gaze Eyeball Coupling
      if (vrmBones.lEyeball && vrmBones.rEyeball && (isGazingAtGauges || Math.abs(rumCurrentGazeYaw) > 0.02)) {
        vrmBones.lEyeball.rotation.y = THREE.MathUtils.clamp(rumCurrentGazeYaw * 0.45, -0.35, 0.35);
        vrmBones.lEyeball.rotation.x = THREE.MathUtils.clamp(rumCurrentGazePitch * 0.45, -0.25, 0.25);
        vrmBones.rEyeball.rotation.y = THREE.MathUtils.clamp(rumCurrentGazeYaw * 0.45, -0.35, 0.35);
        vrmBones.rEyeball.rotation.x = THREE.MathUtils.clamp(rumCurrentGazePitch * 0.45, -0.25, 0.25);
      }
      // Phase 3: Circadian Slow Breathing & Night Resting Idle
      const isNightSenses = latestCircadian && latestCircadian.is_night;
      const breathFreq = isNightSenses ? 1.2 : 2.6;
      const breathAmp = isNightSenses ? 0.035 : 0.022;
      const breathPitch = Math.sin(time * breathFreq) * breathAmp;
      if (vrmBones.chest) {
        vrmBones.chest.rotation.x += breathPitch;
      }
      // Night resting idle transition when parked/stopped
      if (isNightSenses && !isSpeaking && !isReacting && vrmCurrentAction === 'neutral_idle') {
        const spd = (latestTelemetry && (latestTelemetry.speed || latestTelemetry.speed_mph)) || 0;
        if (spd < 2.0) {
          parkedIdleTimer += delta;
          if (parkedIdleTimer > 12.0 && !isNightResting) {
            isNightResting = true;
            if (typeof playVrmAction === 'function') {
              playVrmAction('sit_idle2.bvh', 25000);
            }
          }
        } else {
          parkedIdleTimer = 0.0;
          if (isNightResting) {
            isNightResting = false;
            if (typeof stopActiveVrmaClip === 'function') stopActiveVrmaClip(0.5);
          }
        }
      }
      // Phase 3: Dynamic Affective Facial Expressions
      const curEmo = (latestMood && latestMood.emotion) ? latestMood.emotion : currentWaifuEmotion;
      if (curEmo === 'EXCITED') {
        if (vrmBones.lMouthCorner) vrmBones.lMouthCorner.position.y += 0.007;
        if (vrmBones.rMouthCorner) vrmBones.rMouthCorner.position.y += 0.007;
        if (vrmBones.lBrowIn) vrmBones.lBrowIn.position.y += 0.005;
        if (vrmBones.rBrowIn) vrmBones.rBrowIn.position.y += 0.005;
      } else if (curEmo === 'COZY' || isNightSenses) {
        if (vrmBones.lEyeUpper && !vrmIsBlinking) vrmBones.lEyeUpper.position.y -= 0.010;
        if (vrmBones.rEyeUpper && !vrmIsBlinking) vrmBones.rEyeUpper.position.y -= 0.010;
        if (vrmBones.lMouthCorner) vrmBones.lMouthCorner.position.y += 0.003;
        if (vrmBones.rMouthCorner) vrmBones.rMouthCorner.position.y += 0.003;
      } else if (curEmo === 'CONCERNED') {
        if (vrmBones.lBrowIn) vrmBones.lBrowIn.position.y += 0.012;
        if (vrmBones.rBrowIn) vrmBones.rBrowIn.position.y += 0.012;
        if (vrmBones.lBrowOut) vrmBones.lBrowOut.position.y -= 0.004;
        if (vrmBones.rBrowOut) vrmBones.rBrowOut.position.y -= 0.004;
      } else if (curEmo === 'HAPPY_PROUD') {
        if (vrmBones.lMouthCorner) vrmBones.lMouthCorner.position.y += 0.008;
        if (vrmBones.rMouthCorner) vrmBones.rMouthCorner.position.y += 0.008;
      } else if (curEmo === 'THOUGHTFUL') {
        if (vrmBones.head && !isGazingAtGauges) vrmBones.head.rotation.z += 0.05;
      }
      }

      if (isSpeaking || vrmCurrentAction === 'amusement' || vrmCurrentAction === 'point_laugh') {
        const syl1 = Math.sin(time * 18.5);
        const syl2 = Math.sin(time * 11.3 + 0.8);
        const syl3 = Math.cos(time * 27.0);
        const rawOpen = Math.max(0.0, (syl1 * 0.55 + syl2 * 0.35 + syl3 * 0.25 + 0.35));
        const mouthOpen = Math.min(1.0, rawOpen);
        const vowelWidth = 0.5 + 0.5 * Math.sin(time * 7.2);

        if (vrmBones.jaw && vrmBones.jaw.userData.restPos) {
          vrmBones.jaw.position.y = vrmBones.jaw.userData.restPos.y - (0.0045 * mouthOpen);
          vrmBones.jaw.rotation.x = -0.05 * mouthOpen;
        }
        if (vrmBones.lLipLower && vrmBones.lLipLower.userData.restPos) {
          vrmBones.lLipLower.position.y = vrmBones.lLipLower.userData.restPos.y - (0.0055 * mouthOpen);
        }
        if (vrmBones.rLipLower && vrmBones.rLipLower.userData.restPos) {
          vrmBones.rLipLower.position.y = vrmBones.rLipLower.userData.restPos.y - (0.0055 * mouthOpen);
        }
        if (vrmBones.lLipUpper && vrmBones.lLipUpper.userData.restPos) {
          vrmBones.lLipUpper.position.y = vrmBones.lLipUpper.userData.restPos.y + (0.0025 * mouthOpen);
        }
        if (vrmBones.rLipUpper && vrmBones.rLipUpper.userData.restPos) {
          vrmBones.rLipUpper.position.y = vrmBones.rLipUpper.userData.restPos.y + (0.0025 * mouthOpen);
        }
        if (vrmBones.lMouthCorner && vrmBones.lMouthCorner.userData.restPos) {
          vrmBones.lMouthCorner.position.y = vrmBones.lMouthCorner.userData.restPos.y + (0.003 * vowelWidth);
          vrmBones.lMouthCorner.position.x = vrmBones.lMouthCorner.userData.restPos.x * (1.0 + 0.14 * vowelWidth);
        }
        if (vrmBones.rMouthCorner && vrmBones.rMouthCorner.userData.restPos) {
          vrmBones.rMouthCorner.position.y = vrmBones.rMouthCorner.userData.restPos.y + (0.003 * vowelWidth);
          vrmBones.rMouthCorner.position.x = vrmBones.rMouthCorner.userData.restPos.x * (1.0 + 0.14 * vowelWidth);
        }
        const browLift = 0.003 * mouthOpen;
        ['lBrowIn', 'rBrowIn', 'lBrowOut', 'rBrowOut'].forEach((bk) => {
          if (vrmBones[bk] && vrmBones[bk].userData.restPos) {
            vrmBones[bk].position.y = vrmBones[bk].userData.restPos.y + browLift;
          }
        });
      }
    }

    // 4b. World-Space Gravity Drape for Hanging Kimono Sleeves (Bone001_m & Bone001)
    if (vrmModel) {
      vrmModel.updateMatrixWorld(true);
      const sleeveTargetWorldQ = new THREE.Quaternion().setFromEuler(
        new THREE.Euler(0.45 + Math.sin(time * 2.2) * 0.02, Math.PI, Math.cos(time * 1.8) * 0.02)
      );
      ['Bone001_m', 'Bone001'].forEach((sName) => {
        const sb = vrmModel.getObjectByName(sName);
        if (sb && sb.parent) {
          const pWorldQ = new THREE.Quaternion();
          sb.parent.getWorldQuaternion(pWorldQ);
          sb.quaternion.copy(pWorldQ.invert().multiply(sleeveTargetWorldQ));
        }
      });
    }

    // 5. Dynamic Camera Director
    updateCameraDirector(delta, isSpeaking, isReacting);

    // 5b. Real Moving Ocean Waves & Celestial Day/Night Arc Simulation
    try {
      updateGardenOceanAndSky(time, delta);
    } catch (oceanErr) {
      logClientError('updateGardenOceanAndSky', oceanErr);
    }
    // 5b. 3D Basketball Physics & Dribbling Simulation
    try {
      if (typeof updateBasketballPhysics === 'function') {
        updateBasketballPhysics(delta);
      }
    } catch (bbErr) {
      logClientError('updateBasketballPhysics', bbErr);
    }
    // 5d. Biological Connectome Fruit Fly Simulation
    try {
      if (typeof updateConnectomeFly === 'function') {
        updateConnectomeFly(delta, time);
      }
    } catch (flyErr) {
      logClientError('updateConnectomeFly', flyErr);
    }
    // 6. Render
    if (vrmRenderer && vrmScene && vrmCamera) {
      // 5.5 Dynamic Camera Wall Occlusion Fading
    try {
      updateCameraOcclusionFading();
    } catch (occErr) {}
    vrmRenderer.render(vrmScene, vrmCamera);
    }
    } catch (animErr) {
      console.error('[VRM_ANIM_ERROR]', animErr);
    }
  }

  animateVrm();
}

function updateCameraDirector(delta, isSpeaking, isReacting) {
  if (!vrmCamera || !targetCamPos || !targetLookAt || !currentLookAt) return;
  const isDoingAction = (Date.now() < vrmActionEndTime);
  const isGazeRetained = (Date.now() < rumGazeRetentionUntil);
  const isVocal = isSpeaking || isReacting || isGazeRetained;
  // Rum's live dynamic coordinates on the stage floor
  const rx = vrmRoamCurrentPos.x;
  const rz = vrmRoamCurrentPos.z;
  const ry = vrmBaseY + vrmCurrentElevation;
  // Precise anatomical landmarks
  const yCenter = ry + 0.70;             // Torso center (for 3rd person full body tracking)
  const yBust   = ry + (vrmSize.y * 0.70); // Chest / bust level
  const yHead   = ry + (vrmSize.y * 0.82); // Eye / head level
  if (isCompanionFloating) {
    // Continuous dynamic tracking in Shotgun mode: Follow Rum's exact rx/rz coordinates so she NEVER walks off screen!
    if (vrmFramingMode === 'PORTRAIT' || (vrmFramingMode === 'AUTO' && isVocal)) {
      targetCamPos.set(rx, yHead + 0.02, rz + 1.15);
      targetLookAt.set(rx, yBust + 0.04, rz);
    } else {
      // Third-person centered tracking head-to-toe in small floating shotgun HUD
      targetCamPos.set(rx, yCenter + 0.10, rz + 2.35);
      targetLookAt.set(rx, yCenter, rz);
    }
  } else if (vrmFramingMode === 'ROOM') {
    // 1. FULL ROOM VIEW: Crisp diorama framing bringing the full room and props into high-density focus
    targetCamPos.set(0.0, ry + 1.65, 4.35 * vrmZoomMultiplier);
    targetLookAt.set(0.0, ry + 0.65, -0.15);
  } else if (vrmFramingMode === 'PORTRAIT') {
    // 2. PORTRAIT / BUST VIEW: Camera follows Rum continuously, locked at bust view (shoulders to hair) wherever she wanders
    targetCamPos.set(rx, yHead + 0.04, rz + 1.40 * vrmZoomMultiplier);
    targetLookAt.set(rx, yBust + 0.04, rz);
  } else if (vrmFramingMode === 'AUTO') {
    // 3. AUTO ZOOM: Full body 3rd person tracking while idle/walking -> zooms straight into shoulders/head close-up when speaking!
    if (isVocal && !isDoingAction) {
      // Zooms in straight to head/mouth close-up so lips, speech sync, and facial reactions are prominent!
      targetCamPos.set(rx, yHead + 0.03, rz + 1.15 * vrmZoomMultiplier);
      targetLookAt.set(rx, yHead - 0.02, rz);
    } else {
      // Natural 3rd person game character full body follow
      targetCamPos.set(rx, yCenter + 0.16, rz + 3.25 * vrmZoomMultiplier);
      targetLookAt.set(rx, yCenter, rz);
    }
  } else {
    // 4. FULL BODY (Default): 3rd Person Game Character Tracking - Camera follows Rum's X/Z position continuously, always dead-center in view from head to toe!
    targetCamPos.set(rx, yCenter + 0.16, rz + 3.25 * vrmZoomMultiplier);
    targetLookAt.set(rx, yCenter, rz);
  }

  const isFastSnap = (typeof vrmCameraFastTransitionUntil !== 'undefined' && Date.now() < vrmCameraFastTransitionUntil);
  const lerpFactor = isFastSnap ? Math.min(1.0, delta * 18.0) : Math.min(1.0, delta * 4.2);
  vrmCamera.position.lerp(targetCamPos, lerpFactor);
  currentLookAt.lerp(targetLookAt, lerpFactor);
  if (typeof orbitReturnToCenter !== 'undefined' && orbitReturnToCenter) {
    orbitTargetYaw += (0.0 - orbitTargetYaw) * (delta * 2.5);
    orbitTargetPitch += (0.0 - orbitTargetPitch) * (delta * 2.5);
  }
  orbitUserYaw += (orbitTargetYaw - orbitUserYaw) * (delta * 8.0);
  orbitUserPitch += (orbitTargetPitch - orbitUserPitch) * (delta * 8.0);
  const orbitLookAt = currentLookAt.clone();
  orbitLookAt.x += Math.sin(orbitUserYaw) * 1.8;
  orbitLookAt.y += orbitUserPitch * 1.2;
  orbitLookAt.z += (Math.cos(orbitUserYaw) - 1.0) * 1.8;
  vrmCamera.lookAt(orbitLookAt);
}

// ============================================================================

// --- AI SCREEN 3-WAY SPLITTER & 3D ROOM TOUCH ORBIT LOOK-AROUND ENGINE ---

// ============================================================================
let currentAiLayoutMode = 'SPLIT';
let isTouchOrbiting = false;
let orbitTouchStartX = 0;
let orbitTouchStartY = 0;
let orbitUserYaw = 0.0;
let orbitUserPitch = 0.0;
let orbitTargetYaw = 0.0;
let orbitTargetPitch = 0.0;
let orbitIdleTimer = null;
let orbitReturnToCenter = true;

function setAiLayoutMode(mode = 'SPLIT') {
  currentAiLayoutMode = mode;
  localStorage.setItem('carpi5_ai_layout_mode', mode);
  const container = document.getElementById('screenAI');
  if (!container) return;
  container.classList.remove('ai-layout-chat', 'ai-layout-split', 'ai-layout-room');
  document.querySelectorAll('.ai-split-btn').forEach((b) => {
    const isChat = b.id.includes('Chat') || (b.innerText && b.innerText.includes('CHAT'));
    const isSplit = b.id.includes('Balanced') || b.id.includes('Split') || (b.innerText && b.innerText.includes('SPLIT'));
    const isRoom = b.id.includes('Room') || (b.innerText && b.innerText.includes('ROOM'));
    if (mode === 'CHAT') b.classList.toggle('active', isChat);
    else if (mode === 'ROOM') b.classList.toggle('active', isRoom);
    else b.classList.toggle('active', isSplit);
  });
  if (mode === 'CHAT') {
    container.classList.add('ai-layout-chat');
    if (typeof popOutFloatingCompanion === 'function') popOutFloatingCompanion(true);
  } else if (mode === 'ROOM') {
    container.classList.add('ai-layout-room');
    if (typeof dockCompanionToAi === 'function') dockCompanionToAi(false);
  } else {
    container.classList.add('ai-layout-split');
    if (typeof dockCompanionToAi === 'function') dockCompanionToAi(false);
  }
  resizeVrmToStage();
  requestAnimationFrame(resizeVrmToStage);
  setTimeout(resizeVrmToStage, 100);
  setTimeout(resizeVrmToStage, 300);
}

function initAiLayoutMode() {
  const saved = localStorage.getItem('carpi5_ai_layout_mode') || 'SPLIT';
  setAiLayoutMode(saved);
}

function initRoomTouchOrbitLookAround(canvas) {
  if (!canvas || canvas._hasOrbitListeners) return;
  canvas._hasOrbitListeners = true;

  function onPointerDown(e) {
    // Only orbit if not clicking a UI button
    if (e.target.tagName === 'BUTTON') return;
    isTouchOrbiting = true;
    orbitReturnToCenter = false;
    if (orbitIdleTimer) clearTimeout(orbitIdleTimer);
    orbitTouchStartX = e.touches ? e.touches[0].clientX : e.clientX;
    orbitTouchStartY = e.touches ? e.touches[0].clientY : e.clientY;
  }

  function onPointerMove(e) {
    if (!isTouchOrbiting) return;
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const clientY = e.touches ? e.touches[0].clientY : e.clientY;
    const dx = clientX - orbitTouchStartX;
    const dy = clientY - orbitTouchStartY;
    orbitTouchStartX = clientX;
    orbitTouchStartY = clientY;
    // Pan camera angle (yaw horizontally, pitch vertically)
    orbitTargetYaw -= dx * 0.0055;
    orbitTargetPitch = Math.max(-0.45, Math.min(0.40, orbitTargetPitch + dy * 0.0045));
  }

  function onPointerUp() {
    isTouchOrbiting = false;
    // After 7 seconds of inactivity, smoothly ease camera back to direct forward gaze
    if (orbitIdleTimer) clearTimeout(orbitIdleTimer);
    orbitIdleTimer = setTimeout(() => {
      orbitReturnToCenter = true;
    }, 3000);
  }
  canvas.addEventListener('mousedown', onPointerDown);

  window.addEventListener('mousemove', onPointerMove);

  window.addEventListener('mouseup', onPointerUp);
  canvas.addEventListener('touchstart', onPointerDown, { passive: true });

  window.addEventListener('touchmove', onPointerMove, { passive: true });

  window.addEventListener('touchend', onPointerUp, { passive: true });
}

function loadRumVrmModel(modelName = (currentVrmModelName || 'Rum.vrm')) {
  currentVrmModelName = modelName;
  localStorage.setItem('vrmCurrentAvatar', modelName);
  const notice = document.getElementById('vrmLoadingNotice');
  if (notice) notice.style.display = 'flex';

  const loader = new THREE.GLTFLoader();
  const isLocalFile = window.location.protocol === 'file:';
  const vrmUrl = isLocalFile ? `../../models/avatars/${modelName}` : `/api/models/vrm?name=${encodeURIComponent(modelName)}`;

  loader.load(
    vrmUrl,
    (gltf) => {
      console.log(`[VRM] ${modelName} loaded successfully!`, gltf);
      if (notice) notice.style.display = 'none';

      if (vrmModel) {
        vrmScene.remove(vrmModel);
      }

      vrmModel = gltf.scene;
      applyHighQualityTextureFiltering(vrmModel);
      vrmaIdleAction = null;
      vrmaActiveAction = null;

      // Fix 3ds Max Biped hierarchy & map bones
      const rig = fixVrmBipedHierarchy(vrmModel, gltf);
      vrmBones = rig.bones;
      vrmHumanoidMap = rig.hMap;
      vrmAllBones = rig.allBones;
      vrmSecondaryBones = rig.secondary;
      currentVrm = {
        humanoid: {
          getBoneNode: (b) => (vrmBones && vrmBones[b]) || (vrmHumanoidMap && vrmHumanoidMap[b]),
          getNormalizedBoneNode: (b) => (vrmBones && vrmBones[b]) || (vrmHumanoidMap && vrmHumanoidMap[b])
        },
        scene: vrmModel
      };

      window.currentVrm = currentVrm;

      // Measure raw unscaled height so child models (Rum.vrm) are scaled slightly smaller (0.85x)
      // while taller adult models scale proportionally and fit cleanly on the same stage floor
      const rawBox = new THREE.Box3().setFromObject(vrmModel);
      const rawSize = rawBox.getSize(new THREE.Vector3());
      const isPetiteModel = /rum|rem/i.test(modelName) || rawSize.y < 1.56;
      // Beautiful proportion: scale Rum up to 1.18x so she fills the frame nicely with the room
      const targetScale = isPetiteModel ? 1.18 : Math.min(1.25, 1.42 / Math.max(1.0, rawSize.y));
      vrmModel.scale.set(targetScale, targetScale, targetScale);
      vrmModel.updateMatrixWorld(true);

      const box = new THREE.Box3().setFromObject(vrmModel);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());

      vrmCenter = center;
      vrmSize = size;
      // Anchor feet (box.min.y) firmly at stage floor (-0.68) so she never floats and leaves headroom for taller VRMs
      vrmBaseY = -0.68 - box.min.y;

      vrmModel.position.set(-center.x, vrmBaseY, -center.z);
      vrmModel.rotation.set(0, Math.PI, 0);

      vrmModel.traverse((node) => {
        if (node.isMesh) {
          node.castShadow = true;
          node.receiveShadow = true;
          node.frustumCulled = false;
          if (node.material) {
            node.material.depthWrite = true;
          }
        }
      });

      vrmScene.add(vrmModel);
      vrmMixer = new THREE.AnimationMixer(vrmModel);
      vrmRoamWalkAction = null;
      preloadVrmaMotionPack();

      updateFramingButtonLabel();
      updateWorldButtonLabel();
      updateRoamButtonLabel();
      updateModelButtonLabel();
      resizeVrmToStage();

      const emotionPill = document.getElementById('waifuEmotionPill');
      if (emotionPill) {
        const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));
        emotionPill.innerText = isRem ? "💙 REM (3D VRM) • DEVOTED TO MASTER" : "💜 RUM (3D VRM) • PLAYFUL SISTER";
      }
    },
    (progress) => {
      if (progress.total > 0 && notice) {
        const pct = Math.round((progress.loaded / progress.total) * 100);
        notice.innerHTML = `<span>⚡</span> LOADING RUM VRM (${pct}%)...`;
      }
    },
    (error) => {
      console.warn(`[VRM] Fallback checking Rem.vrm:`, error);
      if (modelName === 'Rem.vrm') {
        loadRumVrmModel('Rum.vrm');
        return;
      } else if (modelName === 'Rum.vrm') {
        loadRumVrmModel('Rem.vrm');
        return;
      }
      if (notice) {
        notice.innerHTML = '<span style="color:var(--accent-red);">VRM Load Error</span>';
      }
    }
  );
}

function resizeVrmToStage() {
  if (!vrmRenderer || !vrmCamera) return;
  const targetContainer = isCompanionFloating ? document.getElementById('vrmFloatingBody') : document.getElementById('vrmStageContainer');
  if (!targetContainer) return;
  const rect = targetContainer.getBoundingClientRect();
  const w = Math.round(rect.width || targetContainer.clientWidth || 360);
  const h = Math.round(rect.height || targetContainer.clientHeight || 460);
  if (w <= 0 || h <= 0) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 1.0);
  vrmRenderer.setPixelRatio(dpr);
  vrmRenderer.setSize(w, h, false);
  vrmCamera.aspect = w / h;
  vrmCamera.updateProjectionMatrix();
}

function applyHighQualityTextureFiltering(rootObj) {
  if (!vrmRenderer || !rootObj) return;
  const maxAniso = (vrmRenderer.capabilities && typeof vrmRenderer.capabilities.getMaxAnisotropy === 'function')
    ? vrmRenderer.capabilities.getMaxAnisotropy()
    : 4;
  rootObj.traverse((node) => {
    if (node.isMesh && node.material) {
      const mats = Array.isArray(node.material) ? node.material : [node.material];
      mats.forEach((m) => {
        if (m.map) {
          m.map.anisotropy = maxAniso;
          m.map.minFilter = THREE.LinearMipmapLinearFilter;
          m.map.magFilter = THREE.LinearFilter;
          m.map.needsUpdate = true;
        }
      });
    }
  });
}

function updateFramingButtonLabel() {
  const btn = document.getElementById('btnVrmViewToggle');
  const hudBtn = document.getElementById('btnHudViewToggle');
  const labels = {
    'FULL_BODY': '🔍 FULL BODY (FOLLOW)',
    'ROOM': '🏠 FULL ROOM',
    'PORTRAIT': '👤 BUST (FOLLOW)',
    'AUTO': '🤖 AUTO ZOOM (SPEAK)'
  };
  const label = labels[vrmFramingMode] || '🔍 FULL BODY';
  if (btn) btn.innerText = label;
  if (hudBtn) hudBtn.innerText = (vrmFramingMode === 'ROOM') ? '🏠' : ((vrmFramingMode === 'PORTRAIT') ? '👤' : '🔍');
}

let vrmCameraFastTransitionUntil = 0;

function snapCameraToCurrentFraming() {
  orbitTargetYaw = 0.0;
  orbitTargetPitch = 0.0;
  orbitUserYaw = 0.0;
  orbitUserPitch = 0.0;
  orbitReturnToCenter = true;
  vrmCameraFastTransitionUntil = Date.now() + 450;
}

function toggleVrmFraming() {
  if (vrmFramingMode === 'FULL_BODY') vrmFramingMode = 'ROOM';
  else if (vrmFramingMode === 'ROOM') vrmFramingMode = 'PORTRAIT';
  else if (vrmFramingMode === 'PORTRAIT') vrmFramingMode = 'AUTO';
  else vrmFramingMode = 'FULL_BODY';
  snapCameraToCurrentFraming();
  updateFramingButtonLabel();
}

function triggerVrmReaction() {
  if (vrmaClips['greeting']) {
    playVrmAction('greeting', 3800, true);
  } else {
    vrmReactionEndTime = Date.now() + 3500;
  }
}

function setVrmSpeaking(durationMs, text, forceTimer = false) {
  if (forceTimer || !eventSource || eventSource.readyState !== 1) {
    vrmSpeechEndTime = Date.now() + (durationMs || 3000);
    rumGazeRetentionUntil = Math.max(rumGazeRetentionUntil, Date.now() + (durationMs || 3000) + 9000);
  }
  if (text) {
    const bubble = document.getElementById('vrmHudBubble');
    const hud = document.getElementById('vrmFloatingHud');
    if (bubble) {
      bubble.innerText = text;
      bubble.classList.add('show');
      if (hud) hud.classList.add('talking');
      const mini = document.getElementById('vrmMiniBubble');
      const miniTooltip = document.getElementById('vrmMiniSpeechTooltip');
      if (mini && mini.style.display !== 'none') {
        mini.classList.add('talking');
        if (miniTooltip) {
          miniTooltip.innerText = text;
          miniTooltip.classList.add('show');
        }
      }
      setTimeout(() => {
        bubble.classList.remove('show');
        if (hud) hud.classList.remove('talking');
        if (mini) {
          mini.classList.remove('talking');
          if (miniTooltip) miniTooltip.classList.remove('show');
        }
      }, durationMs || 3000);
    }
  }
}

function showVrmSpeech(text, durationMs = 5000) {
  setVrmSpeaking(durationMs, text);
}

// Floating Shotgun Companion Mode (Rum Riding Shotgun Anywhere on Screen)

function popOutFloatingCompanion(isAuto = false) {
  if (!vrmInitialized && typeof initVrmEngine === 'function') {
    initVrmEngine();
  }
  const canvas = document.getElementById('vrmCanvas');
  const floatingBody = document.getElementById('vrmFloatingBody');
  const floatingHud = document.getElementById('vrmFloatingHud');
  if (!canvas || !floatingBody || !floatingHud) return;

  floatingHud.style.display = 'flex';
  floatingBody.appendChild(canvas);
  isCompanionFloating = true;
  isShotgunAutoPopped = !!isAuto;

  resizeVrmToStage();
  if (!isAuto) {
    triggerVrmReaction();
    showVrmSpeech("Master! Rum is riding shotgun with you across all screens!", 4500);
  }
}

function dockCompanionToAi(goToAi = false) {
  const canvas = document.getElementById('vrmCanvas');
  const stageContainer = document.getElementById('vrmStageContainer');
  const floatingHud = document.getElementById('vrmFloatingHud');
  if (shotgunAutoDismissTimer) {
    clearTimeout(shotgunAutoDismissTimer);
    shotgunAutoDismissTimer = null;
  }
  isShotgunAutoPopped = false;
  if (!canvas || !stageContainer || !floatingHud) return;
  floatingHud.style.display = 'none';
  stageContainer.appendChild(canvas);
  isCompanionFloating = false;
  // If currently in CHAT focus mode, docking restores SPLIT layout so Rum is immediately visible on screen!
  if (currentAiLayoutMode === 'CHAT') {
    currentAiLayoutMode = 'SPLIT';
    localStorage.setItem('carpi5_ai_layout_mode', 'SPLIT');
    const container = document.getElementById('screenAI');
    if (container) {
      container.classList.remove('ai-layout-chat', 'ai-layout-room');
      container.classList.add('ai-layout-split');
    }
  }
  if (goToAi && currentScreen !== 'ai') {
    navigateTo('ai');
  }
  resizeVrmToStage();
}

function initMiniBubbleDraggable() {
  const bubble = document.getElementById('vrmMiniBubble');
  if (!bubble || bubble.dataset.dragInit) return;
  bubble.dataset.dragInit = 'true';
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let initialLeft = 0;
  let initialTop = 0;
  let hasMoved = false;
  bubble.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    isDragging = true;
    hasMoved = false;
    startX = e.clientX;
    startY = e.clientY;
    const rect = bubble.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;
    bubble.style.bottom = 'auto';
    bubble.style.right = 'auto';
    bubble.style.left = initialLeft + 'px';
    bubble.style.top = initialTop + 'px';
    bubble.setPointerCapture(e.pointerId);
  }, { passive: false });

  window.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
      hasMoved = true;
    }
    let newLeft = Math.max(10, Math.min(window.innerWidth - bubble.offsetWidth - 10, initialLeft + dx));
    let newTop = Math.max(10, Math.min(window.innerHeight - bubble.offsetHeight - 10, initialTop + dy));
    bubble.style.left = newLeft + 'px';
    bubble.style.top = newTop + 'px';
  }, { passive: true });
  const stopDrag = (e) => {
    if (!isDragging) return;
    isDragging = false;
    try { bubble.releasePointerCapture(e.pointerId); } catch (_) {}
    if (hasMoved) {
      e.stopPropagation();
      e.preventDefault();
    }
  };

  window.addEventListener('pointerup', stopDrag, { passive: false });

  window.addEventListener('pointercancel', stopDrag, { passive: true });
}

function initFloatingHudDraggable() {
  const hud = document.getElementById('vrmFloatingHud');
  const header = document.getElementById('vrmHudHeader');
  initMiniBubbleDraggable();
  if (!hud || !header) return;

  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let initialLeft = 0;
  let initialTop = 0;

  header.addEventListener('pointerdown', (e) => {
    if (e.target.closest('button')) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = hud.getBoundingClientRect();
    initialLeft = rect.left;
    initialTop = rect.top;
    hud.style.bottom = 'auto';
    hud.style.right = 'auto';
    hud.style.left = initialLeft + 'px';
    hud.style.top = initialTop + 'px';
    header.setPointerCapture(e.pointerId);
    e.preventDefault();
  }, { passive: false });

  window.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    let newLeft = Math.max(10, Math.min(window.innerWidth - hud.offsetWidth - 10, initialLeft + dx));
    let newTop = Math.max(10, Math.min(window.innerHeight - hud.offsetHeight - 10, initialTop + dy));
    hud.style.left = newLeft + 'px';
    hud.style.top = newTop + 'px';
    // Shotgun Window Drag Kinematics: React dynamically to window motion
    const now = Date.now();
    const dt = Math.max(0.016, (now - (window._lastHudDragTime || now)) / 1000);
    const curVx = (e.clientX - (window._lastHudDragX || e.clientX)) / dt;
    const curVy = (e.clientY - (window._lastHudDragY || e.clientY)) / dt;

    window._lastHudDragX = e.clientX;

    window._lastHudDragY = e.clientY;

    window._lastHudDragTime = now;

    window._lastHudDragSpeed = Math.hypot(curVx, curVy);
    // Apply lateral G-force balance inertia to R.U.M.
    rumCurrentInertiaX = THREE.MathUtils.clamp(-curVx * 0.0016, -0.45, 0.45);
    rumCurrentInertiaZ = THREE.MathUtils.clamp(-curVy * 0.0012, -0.35, 0.35);
    // Dynamic tilt angle of Rum leaning to maintain balance as her window is dragged
    if (vrmModel) {
      vrmModel.rotation.z = THREE.MathUtils.clamp(curVx * 0.0005, -0.22, 0.22);
    }
    e.preventDefault();
  }, { passive: false });

  const stopDrag = (e) => {
    if (!isDragging) return;
    isDragging = false;
    try { header.releasePointerCapture(e.pointerId); } catch (_) {}
    const dragSpeed = window._lastHudDragSpeed || 0;
    if (dragSpeed > 600) {
      triggerVrmReaction('SURPRISED');
      if (typeof speakUtterance === 'function') {
        const lines = [
          "Whoa! Hold on Master, where are we floating to?!",
          "Eee! What a fast move! I've got my balance!",
          "Master is moving my whole world across the car!"
        ];
        speakUtterance(lines[Math.floor(Math.random() * lines.length)]);
      }
    }

    window._lastHudDragSpeed = 0;
    rumCurrentInertiaX = 0;
    rumCurrentInertiaZ = 0;
    if (vrmModel) vrmModel.rotation.z = 0;
  };

  window.addEventListener('pointerup', stopDrag, { passive: true });

  window.addEventListener('pointercancel', stopDrag, { passive: true });
}

// [OBSOLETE 2D FACE TOGGLES - Locked to 3D_VRM so 2D face cannot be activated]

function toggleAvatar2d3d() {
  switchAvatarEngine('3D_VRM');
}

function switchAvatarEngine(mode) {
  activeAvatarEngine = '3D_VRM';
  const vrmContainer = document.getElementById('vrmStageContainer');
  const faceCanvas = document.getElementById('waifuFaceCanvas');
  const selector = document.getElementById('cfgAvatarEngine');
  const emotionPill = document.getElementById('waifuEmotionPill');

  if (selector) selector.value = '3D_VRM';
  if (vrmContainer) vrmContainer.style.display = 'flex';
  if (faceCanvas) faceCanvas.style.display = 'none';
  if (!vrmInitialized) {
    initVrmEngine();
  } else {
    resizeVrmToStage();
  }
  if (emotionPill) emotionPill.innerText = "💖 R.U.M. (3D VRM) • DEVOTED TO MASTER";
}

// Auto-initialize 3D VRM Rum on startup
if (document.readyState === 'complete' || document.readyState === 'interactive') {
  setTimeout(initVrmEngine, 200);
} else {

  window.addEventListener('load', () => {
    setTimeout(initVrmEngine, 500);
  });
}

window.addEventListener('resize', () => {
  if (typeof resizeVrmToStage === 'function') resizeVrmToStage();
});

// ============================================================================

// --- PROCEDURAL TEXTURE GENERATORS (Zero network lag, 100% solid & seamless) ---

// ============================================================================

function createWoodPlankTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#4a2e1b';
  ctx.fillRect(0, 0, 512, 512);
  const plankH = 64;
  for (let y = 0; y < 512; y += plankH) {
    const tint = (Math.random() - 0.5) * 18;
    ctx.fillStyle = `rgb(${74 + tint}, ${46 + tint * 0.7}, ${27 + tint * 0.5})`;
    ctx.fillRect(0, y, 512, plankH - 2);
    ctx.strokeStyle = 'rgba(30, 16, 8, 0.25)';
    ctx.lineWidth = 1;
    for (let i = 0; i < 5; i++) {
      ctx.beginPath();
      const gy = y + 8 + Math.random() * (plankH - 16);
      ctx.moveTo(0, gy);
      ctx.bezierCurveTo(128, gy + (Math.random() - 0.5) * 6, 384, gy + (Math.random() - 0.5) * 6, 512, gy);
      ctx.stroke();
    }
    ctx.strokeStyle = '#22140a';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, y + plankH - 1);
    ctx.lineTo(512, y + plankH - 1);
    ctx.stroke();
    const offset = (y / plankH) % 2 === 0 ? 0 : 256;
    ctx.beginPath();
    ctx.moveTo(offset + 180, y);
    ctx.lineTo(offset + 180, y + plankH - 2);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(4, 4);
  return tex;
}

function createTatamiDeckTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext('2d');
  // Rich warm cedar base
  ctx.fillStyle = '#7a4b28';
  ctx.fillRect(0, 0, 512, 512);
  const slatW = 48;
  for (let x = 0; x < 512; x += slatW) {
    const tint = (Math.random() - 0.5) * 18;
    const r = Math.round(Math.min(255, Math.max(0, 140 + tint)));
    const g = Math.round(Math.min(255, Math.max(0, 95 + tint * 0.75)));
    const b = Math.round(Math.min(255, Math.max(0, 56 + tint * 0.55)));
    ctx.fillStyle = `rgb(${r}, ${g}, ${b})`;
    ctx.fillRect(x + 1, 0, slatW - 2, 512);
    // Subtle natural wood grain streaks
    ctx.strokeStyle = 'rgba(60, 32, 14, 0.22)';
    ctx.lineWidth = 1;
    for (let k = 0; k < 5; k++) {
      ctx.beginPath();
      const gx = x + 3 + Math.random() * (slatW - 6);
      ctx.moveTo(gx, 0);
      ctx.lineTo(gx + (Math.random() - 0.5) * 6, 512);
      ctx.stroke();
    }
    // Dark plank groove border
    ctx.strokeStyle = '#381c0c';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x + slatW - 1, 0);
    ctx.lineTo(x + slatW - 1, 512);
    ctx.stroke();
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 4);
  return tex;
}

// ============================================================================

// --- 3D ARCHITECTURAL ROOM + OCEAN BALCONY ENVIRONMENT ---

// ============================================================================

function clearVrmEnvironment() {
  if (!vrmEnvironmentGroup) return;
  while (vrmEnvironmentGroup.children.length > 0) {
    const obj = vrmEnvironmentGroup.children[0];
    vrmEnvironmentGroup.remove(obj);
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach(m => m.dispose());
      } else {
        obj.material.dispose();
      }
    }
  }
  envLights = [];
  vrmOceanMesh = null;
  vrmOceanGeo = null;
  vrmOceanMat = null;
  vrmOceanBasePos = null;
  vrmSkyMesh = null;
  vrmSkyTexture = null;
  vrmSunMesh = null;
  vrmSunGlow = null;
  vrmMoonMesh = null;
  vrmMoonGlow = null;
  vrmStarParticles = null;
  vrmCelestialLight = null;
}

function createCelestialSkyCanvas() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 256;
  return canvas;
}

function updateSkyCanvas(canvas, phase) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  if (phase === 'DAY') {
    grad.addColorStop(0.00, '#0d47a1'); // Deep anime zenith blue
    grad.addColorStop(0.35, '#1e88e5');
    grad.addColorStop(0.70, '#64b5f6');
    grad.addColorStop(0.92, '#bbdefb');
    grad.addColorStop(1.00, '#e3f2fd'); // Soft horizon haze
  } else if (phase === 'GOLDEN_HOUR') {
    grad.addColorStop(0.00, '#1a237e');
    grad.addColorStop(0.30, '#4a148c');
    grad.addColorStop(0.60, '#f57c00');
    grad.addColorStop(0.85, '#ffb300');
    grad.addColorStop(1.00, '#ffe082');
  } else if (phase === 'SUNSET') {
    grad.addColorStop(0.00, '#260633'); // Royal purple twilight zenith
    grad.addColorStop(0.25, '#4a0e4e');
    grad.addColorStop(0.55, '#c2185b'); // Rich crimson
    grad.addColorStop(0.78, '#e65100'); // Blazing orange
    grad.addColorStop(0.92, '#ff6d00');
    grad.addColorStop(1.00, '#ffd54f'); // Molten gold at the ocean waterline
  } else if (phase === 'CIVIL_DUSK' || phase === 'CIVIL_DAWN') {
    grad.addColorStop(0.00, '#0a0e1a');
    grad.addColorStop(0.40, '#1f1a3a');
    grad.addColorStop(0.75, '#4a1c40');
    grad.addColorStop(0.92, '#7b2d42');
    grad.addColorStop(1.00, '#9e4758');
  } else {
    // NIGHT
    grad.addColorStop(0.00, '#02040a'); // Starlit deep space
    grad.addColorStop(0.45, '#060a14');
    grad.addColorStop(0.80, '#0a1224');
    grad.addColorStop(1.00, '#101c36'); // Faint nocturnal ocean mist
  }
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  // Painterly soft cumulus clouds near horizon
  if (phase === 'DAY' || phase === 'GOLDEN_HOUR' || phase === 'SUNSET') {
    ctx.save();
    ctx.fillStyle = (phase === 'SUNSET') ? 'rgba(255, 120, 80, 0.22)' :
                    (phase === 'GOLDEN_HOUR') ? 'rgba(255, 200, 120, 0.22)' :
                    'rgba(255, 255, 255, 0.24)';
    const cloudYs = [h * 0.68, h * 0.74, h * 0.70];
    const cloudXs = [w * 0.20, w * 0.55, w * 0.85];
    const cloudRs = [45, 60, 50];
    for (let c = 0; c < 3; c++) {
      ctx.beginPath();
      ctx.arc(cloudXs[c], cloudYs[c], cloudRs[c], 0, Math.PI * 2);
      ctx.arc(cloudXs[c] + cloudRs[c] * 0.6, cloudYs[c] + 6, cloudRs[c] * 0.7, 0, Math.PI * 2);
      ctx.arc(cloudXs[c] - cloudRs[c] * 0.6, cloudYs[c] + 4, cloudRs[c] * 0.65, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }
}

function createStarfieldParticles() {
  const count = 120;
  const starGeo = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    positions[i * 3 + 0] = (Math.random() - 0.5) * 38.0;
    positions[i * 3 + 1] = vrmBaseY + 2.0 + Math.random() * 14.0;
    positions[i * 3 + 2] = -25.2 + (Math.random() - 0.5) * 0.8;
  }
  starGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const starMat = new THREE.PointsMaterial({
    color: 0xffffff,
    size: 0.16,
    transparent: true,
    opacity: 0.85
  });
  return new THREE.Points(starGeo, starMat);
}

// --- COCKPIT DAY / NIGHT THEME MODE CONTROLLER (AUTO / DAY / NIGHT) ---
let currentCockpitThemeMode = localStorage.getItem('carpi5_theme_mode') || 'AUTO';

function setCockpitThemeMode(mode, silent = false) {
  currentCockpitThemeMode = mode;
  localStorage.setItem('carpi5_theme_mode', mode);
  const badge = document.getElementById('themeModeBadge');
  if (badge) {
    badge.innerText = mode === 'AUTO' ? 'AUTO (SOLAR)' : (mode === 'DAY' ? 'ALWAYS DAY' : 'ALWAYS NIGHT');
    const color = mode === 'NIGHT' ? 'var(--accent-blue)' : (mode === 'DAY' ? 'var(--accent-green)' : 'var(--accent-yellow)');
    badge.style.borderColor = color;
    badge.style.color = color;
  }
  ['btnThemeAuto', 'btnThemeDay', 'btnThemeNight'].forEach(id => {
    const b = document.getElementById(id);
    if (b) b.classList.remove('active');
  });
  if (mode === 'AUTO') {
    document.getElementById('btnThemeAuto')?.classList.add('active');
    updateCelestialVisuals();
    if (!silent) showAiSpeechToast("Theme: Auto (Tracking Solar Ephemeris)");
  } else if (mode === 'DAY') {
    document.getElementById('btnThemeDay')?.classList.add('active');
    document.body.classList.remove('cockpit-night-mode');
    if (!silent) showAiSpeechToast("Theme: Forced Daytime");
  } else if (mode === 'NIGHT') {
    document.getElementById('btnThemeNight')?.classList.add('active');
    document.body.classList.add('cockpit-night-mode');
    if (!silent) showAiSpeechToast("Theme: Forced Night Mode");
  }
}

function updateCelestialVisuals() {
  if (vrmSkyCanvas && vrmSkyTexture) {
    updateSkyCanvas(vrmSkyCanvas, vrmCelestialPhase);
    vrmSkyTexture.needsUpdate = true;
  }
  const isNight = (vrmCelestialPhase === 'NIGHT' || vrmCelestialPhase === 'CIVIL_DUSK' || vrmCelestialPhase === 'CIVIL_DAWN');
  const mode = localStorage.getItem('carpi5_theme_mode') || 'AUTO';
  if (mode === 'DAY') {
    document.body.classList.remove('cockpit-night-mode');
  } else if (mode === 'NIGHT') {
    document.body.classList.add('cockpit-night-mode');
  } else {
    if (isNight) {
      document.body.classList.add('cockpit-night-mode');
    } else {
      document.body.classList.remove('cockpit-night-mode');
    }
  }
  const isSunset = (vrmCelestialPhase === 'SUNSET');
  const isGolden = (vrmCelestialPhase === 'GOLDEN_HOUR');
  if (vrmSunMesh) {
    vrmSunMesh.visible = !isNight;
  }
  if (vrmMoonMesh) {
    vrmMoonMesh.visible = isNight;
  }
  if (vrmStarParticles) {
    vrmStarParticles.visible = isNight;
  }
  // Ocean Water Base Color & Specular
  if (vrmOceanMat) {
    if (isSunset) {
      vrmOceanMat.color.setHex(0xa8341e);
      vrmOceanMat.roughness = 0.12;
      vrmOceanMat.metalness = 0.88;
    } else if (isGolden) {
      vrmOceanMat.color.setHex(0x945e14);
      vrmOceanMat.roughness = 0.14;
      vrmOceanMat.metalness = 0.85;
    } else if (isNight) {
      vrmOceanMat.color.setHex(0x040e1e);
      vrmOceanMat.roughness = 0.18;
      vrmOceanMat.metalness = 0.90;
    } else {
      vrmOceanMat.color.setHex(0x0a4a75);
      vrmOceanMat.roughness = 0.16;
      vrmOceanMat.metalness = 0.82;
    }
  }
  // Directional Celestial Light
  if (vrmCelestialLight) {
    if (isSunset) {
      vrmCelestialLight.color.setHex(0xff5722);
      vrmCelestialLight.intensity = 1.10;
    } else if (isGolden) {
      vrmCelestialLight.color.setHex(0xffa726);
      vrmCelestialLight.intensity = 0.95;
    } else if (isNight) {
      vrmCelestialLight.color.setHex(0x7fa8d6);
      vrmCelestialLight.intensity = 0.35;
    } else {
      vrmCelestialLight.color.setHex(0xfff5e6);
      vrmCelestialLight.intensity = 0.85;
    }
  }
  // Modulate Scene Ambient & Key Lighting based on Time of Day
  if (vrmBaseAmbientLight) {
    if (isNight) {
      vrmBaseAmbientLight.color.setHex(0x1a263e);
      vrmBaseAmbientLight.intensity = 0.45;
    } else if (isSunset) {
      vrmBaseAmbientLight.color.setHex(0x7b2354);
      vrmBaseAmbientLight.intensity = 0.60;
    } else if (isGolden) {
      vrmBaseAmbientLight.color.setHex(0xd48842);
      vrmBaseAmbientLight.intensity = 0.72;
    } else {
      vrmBaseAmbientLight.color.setHex(0xfff0ff);
      vrmBaseAmbientLight.intensity = 0.78;
    }
  }
  if (vrmBaseKeyLight) {
    if (isNight) {
      vrmBaseKeyLight.color.setHex(0x506899);
      vrmBaseKeyLight.intensity = 0.28;
    } else if (isSunset) {
      vrmBaseKeyLight.color.setHex(0xff6e40);
      vrmBaseKeyLight.intensity = 0.75;
    } else if (isGolden) {
      vrmBaseKeyLight.color.setHex(0xffb74d);
      vrmBaseKeyLight.intensity = 0.65;
    } else {
      vrmBaseKeyLight.color.setHex(0xffffff);
      vrmBaseKeyLight.intensity = 0.60;
    }
  }
}

function initSolarEphemerisEngine() {
  fetchSolarEphemeris();
  // Poll ephemeris every 30 minutes
  setInterval(fetchSolarEphemeris, 30 * 60 * 1000);
}

async function fetchSolarEphemeris() {
  try {
    const res = await fetch('/api/solar/ephemeris', { cache: 'no-cache' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (data && data.status === 'success') {
      vrmSolarEphemeris = data;
      vrmCelestialPhase = data.day_phase || 'DAY';
      vrmCelestialDayProgress = (data.day_progress !== undefined) ? data.day_progress : 0.5;
      updateCelestialVisuals();
      return;
    }
  } catch (err) {
    // Offline or daemon initializing - fall back mathematically
  }
  calculateOfflineSolarEphemeris();
}

function calculateOfflineSolarEphemeris() {
  const now = new Date();
  const hours = now.getHours() + (now.getMinutes() / 60);
  const sunrise = 6.5;
  const sunset = 17.0;
  if (hours >= sunrise && hours <= sunset) {
    vrmCelestialDayProgress = (hours - sunrise) / (sunset - sunrise);
    if (vrmCelestialDayProgress < 0.08) vrmCelestialPhase = 'CIVIL_DAWN';
    else if (vrmCelestialDayProgress > 0.88) vrmCelestialPhase = 'SUNSET';
    else if (vrmCelestialDayProgress > 0.75) vrmCelestialPhase = 'GOLDEN_HOUR';
    else vrmCelestialPhase = 'DAY';
  } else {
    vrmCelestialDayProgress = 1.0;
    if (hours > sunset && hours < sunset + 0.6) vrmCelestialPhase = 'CIVIL_DUSK';
    else if (hours > sunrise - 0.6 && hours < sunrise) vrmCelestialPhase = 'CIVIL_DAWN';
    else vrmCelestialPhase = 'NIGHT';
    const nightDuration = 24 - (sunset - sunrise);
    let timeSinceSunset = (hours >= sunset) ? (hours - sunset) : (hours + 24 - sunset);
    vrmCelestialNightProgress = Math.max(0.0, Math.min(1.0, timeSinceSunset / nightDuration));
  }
  updateCelestialVisuals();
}

window.setVrmCelestialPhase = function(phase, progress) {
  if (phase) vrmCelestialPhase = phase.toUpperCase();
  if (progress !== undefined) {
    vrmCelestialDayProgress = progress;
    vrmCelestialNightProgress = progress;
  }
  updateCelestialVisuals();
  console.log('[CELESTIAL] Manually set phase: ' + vrmCelestialPhase + ', progress: ' + progress);
};

function updateGardenOceanAndSky(time, delta) {
  // 1. Undulating Ocean Waves with specular wave normal computation
  if (vrmOceanGeo && vrmOceanBasePos) {
    const pos = vrmOceanGeo.attributes.position;
    const base = vrmOceanBasePos;
    const count = pos.count;
    for (let i = 0; i < count; i++) {
      const bx = base.getX(i);
      const bz = base.getZ(i);
      const waveY = (
        Math.sin(bx * 0.75 + time * 1.8) * 0.048 +
        Math.cos(bz * 0.60 + time * 1.4) * 0.038 +
        Math.sin((bx + bz) * 1.15 + time * 2.2) * 0.024
      );
      pos.setY(i, waveY);
    }
    pos.needsUpdate = true;
    vrmOceanGeo.computeVertexNormals();
  }
  // 2. Position Sun Orb along Day Arc (centered in visible camera frame: x: -5.5 to +5.5)
  if (vrmSunMesh && vrmSunMesh.visible) {
    const sunX = -5.5 + 11.0 * vrmCelestialDayProgress;
    const sunY = (vrmBaseY + 0.42) + Math.sin(vrmCelestialDayProgress * Math.PI) * 8.6;
    vrmSunMesh.position.set(sunX, sunY, -24.8);
    if (vrmCelestialLight) {
      vrmCelestialLight.position.set(sunX, sunY, -24.8);
    }
  }
  // 3. Position Moon Orb along Night Arc (centered in visible camera frame: x: -5.0 to +5.0)
  if (vrmMoonMesh && vrmMoonMesh.visible) {
    const moonX = -5.0 + 10.0 * vrmCelestialNightProgress;
    const moonY = (vrmBaseY + 1.2) + Math.sin(vrmCelestialNightProgress * Math.PI) * 7.6;
    vrmMoonMesh.position.set(moonX, moonY, -24.8);
    if (vrmCelestialLight) {
      vrmCelestialLight.position.set(moonX, moonY, -24.8);
    }
  }
  // 4. Starfield Twinkle
  if (vrmStarParticles && vrmStarParticles.visible) {
    vrmStarParticles.material.opacity = 0.70 + Math.sin(time * 3.2) * 0.25;
  }
}

function setupExteriorCelestialAndOcean(oceanZ = -16.5, oceanY = -0.28) {
  // 1. Real Moving Dynamic Ocean with Undulating Waves
  const oceanWidth = 54.0;
  const oceanDepth = 30.0;
  vrmOceanGeo = new THREE.PlaneGeometry(oceanWidth, oceanDepth, 48, 36);
  vrmOceanGeo.rotateX(-Math.PI / 2);
  vrmOceanBasePos = vrmOceanGeo.attributes.position.clone();
  vrmOceanMat = new THREE.MeshStandardMaterial({
    color: 0x0a4a75,
    roughness: 0.16,
    metalness: 0.82,
    flatShading: true
  });
  vrmOceanMesh = new THREE.Mesh(vrmOceanGeo, vrmOceanMat);
  vrmOceanMesh.position.set(0, vrmBaseY + oceanY, oceanZ);
  vrmOceanMesh.receiveShadow = true;
  vrmEnvironmentGroup.add(vrmOceanMesh);
  // 2. Dynamic Celestial Sky Dome Plane at Horizon (z = -26.5)
  const skyGeo = new THREE.PlaneGeometry(72.0, 36.0);
  vrmSkyCanvas = createCelestialSkyCanvas();
  vrmSkyTexture = new THREE.CanvasTexture(vrmSkyCanvas);
  const skyMat = new THREE.MeshBasicMaterial({ map: vrmSkyTexture });
  vrmSkyMesh = new THREE.Mesh(skyGeo, skyMat);
  vrmSkyMesh.position.set(0, vrmBaseY + 12.0, -26.5);
  vrmEnvironmentGroup.add(vrmSkyMesh);
  // 3. 3D Sun Orb + Radiant Corona Disc
  const sunGeo = new THREE.SphereGeometry(0.65, 20, 20);
  const sunMat = new THREE.MeshBasicMaterial({ color: 0xfffae0 });
  vrmSunMesh = new THREE.Mesh(sunGeo, sunMat);
  const coronaGeo = new THREE.PlaneGeometry(3.6, 3.6);
  const coronaMat = new THREE.MeshBasicMaterial({
    color: 0xff9922,
    transparent: true,
    opacity: 0.50,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide
  });
  vrmSunGlow = new THREE.Mesh(coronaGeo, coronaMat);
  vrmSunMesh.add(vrmSunGlow);
  vrmSunMesh.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmEnvironmentGroup.add(vrmSunMesh);
  // 4. 3D Moon Orb + Soft Lunar Halo
  const moonGeo = new THREE.SphereGeometry(0.52, 20, 20);
  const moonMat = new THREE.MeshStandardMaterial({
    color: 0xecf2f9,
    emissive: 0x90b8f0,
    emissiveIntensity: 0.55,
    roughness: 0.85
  });
  vrmMoonMesh = new THREE.Mesh(moonGeo, moonMat);
  const moonHaloGeo = new THREE.PlaneGeometry(2.6, 2.6);
  const moonHaloMat = new THREE.MeshBasicMaterial({
    color: 0x64b5f6,
    transparent: true,
    opacity: 0.35,
    blending: THREE.AdditiveBlending,
    side: THREE.DoubleSide
  });
  vrmMoonGlow = new THREE.Mesh(moonHaloGeo, moonHaloMat);
  vrmMoonMesh.add(vrmMoonGlow);
  vrmMoonMesh.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmMoonMesh.visible = false;
  vrmEnvironmentGroup.add(vrmMoonMesh);
  // 5. 120 Twinkling Starfield Particles
  vrmStarParticles = createStarfieldParticles();
  vrmEnvironmentGroup.add(vrmStarParticles);
  // 6. Dynamic Directional Celestial Light
  vrmCelestialLight = new THREE.DirectionalLight(0xfff5e6, 0.85);
  vrmCelestialLight.position.set(0, vrmBaseY + 6.0, -24.8);
  vrmCelestialLight.castShadow = true;
  if (vrmCelestialLight.shadow && vrmCelestialLight.shadow.mapSize) {
    vrmCelestialLight.shadow.mapSize.width = 1024;
    vrmCelestialLight.shadow.mapSize.height = 1024;
  }
  vrmEnvironmentGroup.add(vrmCelestialLight);
  envLights.push(vrmCelestialLight);
  updateCelestialVisuals();
}

// ============================================================================
// --- ARCHITECTURAL ROOM WITH STUDIO WINDOWS, OPEN DOOR & OCEAN BALCONY ---
// ============================================================================
let roomWindowMesh = null;
let roomBedMesh = null;
let roomClosetMesh = null;
let roomMirrorMesh = null;
let roomPlantMesh = null;

function defaultRoomDecorationsConfig() {
  return {
    schemaVersion: 2,
    door: true,
    window: true,
    basketball: false,
    plant: false,
    yoshi: false,
    bed: false,
    closet: false,
    mirror: false
  };
}

function loadRoomDecorationsConfig() {
  try {
    const raw = localStorage.getItem('rum_room_decorations');
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && parsed.schemaVersion === 2) {
        return { ...defaultRoomDecorationsConfig(), ...parsed, door: true };
      }
    }
  } catch (e) {}
  const fresh = defaultRoomDecorationsConfig();
  saveRoomDecorationsConfig(fresh);
  return fresh;
}

function saveRoomDecorationsConfig(cfg) {
  try {
    localStorage.setItem('rum_room_decorations', JSON.stringify({ ...cfg, schemaVersion: 2 }));
  } catch (e) {}
}

function buildEmptyRoomEnvironment() {
  clearVrmEnvironment();
  vrmRoomPropsGroup = new THREE.Group();
  vrmEnvironmentGroup.add(vrmRoomPropsGroup);
  // 1. Exterior Moving Ocean, Horizon Sky Dome & Solar/Lunar Ephemeris Arc
  // Instantiated outside the panoramic window & open balcony so it is visible inside and outdoors
  setupExteriorCelestialAndOcean(-16.5, -0.32);
  // 2. Sleek Polished Hardwood Floor (10m wide x 8m deep, Z: -3.50m to +4.50m)
  const floorGeo = new THREE.PlaneGeometry(10, 8);
  const floorTex = createWoodPlankTexture();
  const floorMat = new THREE.MeshStandardMaterial({
    map: floorTex,
    roughness: 0.48,
    metalness: 0.10
  });
  const floor = new THREE.Mesh(floorGeo, floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(0, vrmBaseY - 0.005, 0.50);
  floor.receiveShadow = true;
  floor.userData.isWalkableFloor = true;
  floor.userData.isBalconyFloor = false;
  vrmEnvironmentGroup.add(floor);
  // Wall Material (DoubleSide so exterior face is visible when looking back from the balcony) & Baseboard Trim
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x181e28, roughness: 0.88, side: THREE.DoubleSide });
  const baseboardMat = new THREE.MeshStandardMaterial({ color: 0x0c0f14, roughness: 0.6 });
  // 3. Right Wall (X = +4.5m)
  const sideWallGeo = new THREE.PlaneGeometry(9, 4.0);
  const rightWall = new THREE.Mesh(sideWallGeo, wallMat);
  rightWall.rotation.y = -Math.PI / 2;
  rightWall.position.set(4.5, vrmBaseY + 2.0, 0);
  rightWall.receiveShadow = true;
  rightWall.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(rightWall);
  const rightTrim = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, 9), baseboardMat);
  rightTrim.position.set(4.48, vrmBaseY + 0.06, 0);
  vrmEnvironmentGroup.add(rightTrim);
  // 4. Left Wall (X = -4.5m)
  const leftWall = new THREE.Mesh(sideWallGeo, wallMat);
  leftWall.rotation.y = Math.PI / 2;
  leftWall.position.set(-4.5, vrmBaseY + 2.0, 0);
  leftWall.receiveShadow = true;
  leftWall.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(leftWall);
  const leftTrim = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.12, 9), baseboardMat);
  leftTrim.position.set(-4.48, vrmBaseY + 0.06, 0);
  vrmEnvironmentGroup.add(leftTrim);
  // 5. Back Wall Architecture (Z = -3.5m) with TRUE OPEN DOORWAY (X: -3.01m to -1.99m, H: 2.26m)
  // 5a. Outer Left Wall Segment (X: -4.50m to -3.01m, Width 1.49m, Height 3.6m)
  const leftBackWallOuter = new THREE.Mesh(new THREE.PlaneGeometry(1.49, 3.6), wallMat);
  leftBackWallOuter.position.set(-3.755, vrmBaseY + 1.80, -3.50);
  leftBackWallOuter.receiveShadow = true;
  leftBackWallOuter.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(leftBackWallOuter);
  const leftBackTrimOuter = new THREE.Mesh(new THREE.BoxGeometry(1.49, 0.12, 0.04), baseboardMat);
  leftBackTrimOuter.position.set(-3.755, vrmBaseY + 0.06, -3.48);
  vrmEnvironmentGroup.add(leftBackTrimOuter);
  // 5a-2. Inner Left Wall Segment between doorway & panoramic window (X: -1.99m to -1.30m, Width 0.69m)
  const leftBackWallInner = new THREE.Mesh(new THREE.PlaneGeometry(0.69, 3.6), wallMat);
  leftBackWallInner.position.set(-1.645, vrmBaseY + 1.80, -3.50);
  leftBackWallInner.receiveShadow = true;
  leftBackWallInner.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(leftBackWallInner);
  const leftBackTrimInner = new THREE.Mesh(new THREE.BoxGeometry(0.69, 0.12, 0.04), baseboardMat);
  leftBackTrimInner.position.set(-1.645, vrmBaseY + 0.06, -3.48);
  vrmEnvironmentGroup.add(leftBackTrimInner);
  // 5a-3. Wall Header above Doorway (X: -3.01m to -1.99m, Y: 2.26m to 3.60m, Height 1.34m)
  const doorHeaderWall = new THREE.Mesh(new THREE.PlaneGeometry(1.02, 1.34), wallMat);
  doorHeaderWall.position.set(-2.50, vrmBaseY + 2.93, -3.50);
  doorHeaderWall.receiveShadow = true;
  doorHeaderWall.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(doorHeaderWall);
  // 5b. Right Wall Section (X: +3.20m to +4.5m, Width 1.3m, Height 3.6m)
  const rightBackWall = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 3.6), wallMat);
  rightBackWall.position.set(3.85, vrmBaseY + 1.80, -3.50);
  rightBackWall.receiveShadow = true;
  rightBackWall.userData.isFadableWall = true;
  vrmEnvironmentGroup.add(rightBackWall);
  const rightBackTrim = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.12, 0.04), baseboardMat);
  rightBackTrim.position.set(3.85, vrmBaseY + 0.06, -3.48);
  vrmEnvironmentGroup.add(rightBackTrim);
  // 5c. Top Header Wall Beam (Above panoramic window, X: -1.30m to +3.20m, Height 0.60m)
  const headerWall = new THREE.Mesh(new THREE.PlaneGeometry(4.50, 0.60), wallMat);
  headerWall.position.set(0.95, vrmBaseY + 3.30, -3.50);
  headerWall.receiveShadow = true;
  vrmEnvironmentGroup.add(headerWall);
  // 5d. Lower Floor Wainscoting / Window Sill Ledge (Below panoramic window, Height 0.14m)
  const sillMat = new THREE.MeshStandardMaterial({ color: 0x111620, roughness: 0.5 });
  const windowSill = new THREE.Mesh(new THREE.BoxGeometry(4.52, 0.14, 0.08), sillMat);
  windowSill.position.set(0.95, vrmBaseY + 0.07, -3.48);
  vrmEnvironmentGroup.add(windowSill);

  // --- 6. THE EXACTLY ONE DOOR (Prominently mounted on the Back-Left Wall at X = -2.50m) ---
  const doorGroup = new THREE.Group();
  doorGroup.position.set(-2.50, vrmBaseY, -3.46);
  // Door Frame Casing (Espresso Dark Wood)
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x16110d, roughness: 0.5 });
  const leftCasing = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.30, 0.06), frameMat);
  leftCasing.position.set(-0.55, 1.15, 0);
  const rightCasing = new THREE.Mesh(new THREE.BoxGeometry(0.08, 2.30, 0.06), frameMat);
  rightCasing.position.set(0.55, 1.15, 0);
  const topCasing = new THREE.Mesh(new THREE.BoxGeometry(1.18, 0.08, 0.06), frameMat);
  topCasing.position.set(0, 2.30, 0);
  doorGroup.add(leftCasing);
  doorGroup.add(rightCasing);
  doorGroup.add(topCasing);
  // Inset Wooden Door Panel (Rich Walnut)
  const doorMat = new THREE.MeshStandardMaterial({ color: 0x241810, roughness: 0.42 });
  const doorLeaf = new THREE.Group();
  doorLeaf.position.set(-0.51, 0, 0); // left hinge pivot
  const doorPanel = new THREE.Mesh(new THREE.BoxGeometry(1.02, 2.22, 0.04), doorMat);
  doorPanel.position.set(0.51, 1.11, -0.01);
  doorPanel.castShadow = true;
  doorPanel.receiveShadow = true;
  doorLeaf.add(doorPanel);
  // Door Panel Molding Accents
  const moldingMat = new THREE.MeshStandardMaterial({ color: 0x1c130c, roughness: 0.6 });
  const upperMolding = new THREE.Mesh(new THREE.BoxGeometry(0.80, 0.90, 0.015), moldingMat);
  upperMolding.position.set(0.51, 1.55, 0.015);
  const lowerMolding = new THREE.Mesh(new THREE.BoxGeometry(0.80, 0.70, 0.015), moldingMat);
  lowerMolding.position.set(0.51, 0.55, 0.015);
  doorLeaf.add(upperMolding);
  doorLeaf.add(lowerMolding);
  // Brushed Brass Lever Handle & Rose
  const handleMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.88, roughness: 0.22 });
  const rose = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, 0.015, 16), handleMat);
  rose.rotation.x = Math.PI / 2;
  rose.position.set(0.89, 1.05, 0.02);
  const lever = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.018, 0.025), handleMat);
  lever.position.set(0.95, 1.05, 0.035);
  doorLeaf.add(rose);
  doorLeaf.add(lever);
  // Swing door leaf wide open into the room so R.U.M. can walk straight outside
  doorLeaf.rotation.y = -Math.PI * 0.42;
  doorGroup.add(doorLeaf);
  // Threshold Floor Sill
  const thresholdMat = new THREE.MeshStandardMaterial({ color: 0x221a12, roughness: 0.5 });
  const thresholdStrip = new THREE.Mesh(new THREE.BoxGeometry(1.02, 0.015, 0.08), thresholdMat);
  thresholdStrip.position.set(0, 0.008, 0);
  doorGroup.add(thresholdStrip);
  vrmEnvironmentGroup.add(doorGroup);

  // --- 6.5. TEAKWOOD BALCONY TERRACE OVERLOOKING THE OCEAN ---
  const balconyGroup = new THREE.Group();
  balconyGroup.name = "vrmBalconyTerrace";
  // 6.5a. Teak Wood Decking Platform (Width 5.0m, Depth 4.2m)
  const balconyFloorGeo = new THREE.PlaneGeometry(5.0, 4.2);
  const teakMat = new THREE.MeshStandardMaterial({
    map: createTatamiDeckTexture(),
    color: 0xc28a58,
    roughness: 0.58,
    metalness: 0.06
  });
  const balconyFloor = new THREE.Mesh(balconyFloorGeo, teakMat);
  balconyFloor.rotation.x = -Math.PI / 2;
  balconyFloor.position.set(-2.0, vrmBaseY - 0.005, -5.60);
  balconyFloor.receiveShadow = true;
  balconyFloor.userData.isWalkableFloor = true;
  balconyFloor.userData.isBalconyFloor = true;
  balconyGroup.add(balconyFloor);
  // 6.5b. Heavy Architectural Teak Edge Beam
  const edgeMat = new THREE.MeshStandardMaterial({ color: 0x3d2514, roughness: 0.70 });
  const frontEdgeBeam = new THREE.Mesh(new THREE.BoxGeometry(5.10, 0.14, 0.14), edgeMat);
  frontEdgeBeam.position.set(-2.0, vrmBaseY - 0.07, -7.70);
  balconyGroup.add(frontEdgeBeam);
  // 6.5c. Modern Wrought-Iron Railing with Ocean Overlook (Height 1.08m)
  const railingMat = new THREE.MeshStandardMaterial({ color: 0x0f141c, roughness: 0.35, metalness: 0.85 });
  // Front Outer Rail (Z = -7.68m, Width 5.0m)
  const frontTopRail = new THREE.Mesh(new THREE.BoxGeometry(5.0, 0.05, 0.05), railingMat);
  frontTopRail.position.set(-2.0, vrmBaseY + 1.08, -7.68);
  balconyGroup.add(frontTopRail);
  const frontBottomRail = new THREE.Mesh(new THREE.BoxGeometry(5.0, 0.03, 0.03), railingMat);
  frontBottomRail.position.set(-2.0, vrmBaseY + 0.12, -7.68);
  balconyGroup.add(frontBottomRail);
  // Front Railing Spindles every 22cm
  for (let bx = -4.4; bx <= 0.4; bx += 0.22) {
    const spindle = new THREE.Mesh(new THREE.CylinderGeometry(0.010, 0.010, 0.96, 8), railingMat);
    spindle.position.set(bx, vrmBaseY + 0.60, -7.68);
    balconyGroup.add(spindle);
  }
  // Left Outer Rail (X = -4.50m, Depth 4.2m)
  const leftTopRail = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 4.20), railingMat);
  leftTopRail.position.set(-4.48, vrmBaseY + 1.08, -5.60);
  balconyGroup.add(leftTopRail);
  for (let bz = -3.70; bz >= -7.50; bz -= 0.25) {
    const spindle = new THREE.Mesh(new THREE.CylinderGeometry(0.010, 0.010, 0.96, 8), railingMat);
    spindle.position.set(-4.48, vrmBaseY + 0.60, bz);
    balconyGroup.add(spindle);
  }
  // Right Divider Rail (X = +0.50m, Depth 4.2m)
  const rightTopRail = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 4.20), railingMat);
  rightTopRail.position.set(0.48, vrmBaseY + 1.08, -5.60);
  balconyGroup.add(rightTopRail);
  for (let bz = -3.70; bz >= -7.50; bz -= 0.25) {
    const spindle = new THREE.Mesh(new THREE.CylinderGeometry(0.010, 0.010, 0.96, 8), railingMat);
    spindle.position.set(0.48, vrmBaseY + 0.60, bz);
    balconyGroup.add(spindle);
  }
  vrmEnvironmentGroup.add(balconyGroup);

  // --- 7. GRAND ARCHITECTURAL PANORAMIC PICTURE WINDOW (X: -1.30m to +3.20m, Z: -3.50m) ---
  const winGroup = new THREE.Group();
  winGroup.position.set(0.95, vrmBaseY + 1.57, -3.48);
  const windowFrameMat = new THREE.MeshStandardMaterial({ color: 0x0a0d14, roughness: 0.35, metalness: 0.6 });
  // Top Frame Beam
  const fTop = new THREE.Mesh(new THREE.BoxGeometry(4.56, 0.06, 0.08), windowFrameMat);
  fTop.position.set(0, 1.43, 0);
  winGroup.add(fTop);
  // Bottom Frame Beam
  const fBottom = new THREE.Mesh(new THREE.BoxGeometry(4.56, 0.06, 0.08), windowFrameMat);
  fBottom.position.set(0, -1.43, 0);
  winGroup.add(fBottom);
  // Left & Right Outer Mullions
  const fLeft = new THREE.Mesh(new THREE.BoxGeometry(0.06, 2.86, 0.08), windowFrameMat);
  fLeft.position.set(-2.25, 0, 0);
  winGroup.add(fLeft);
  const fRight = new THREE.Mesh(new THREE.BoxGeometry(0.06, 2.86, 0.08), windowFrameMat);
  fRight.position.set(2.25, 0, 0);
  winGroup.add(fRight);
  // 2 Interior Vertical Mullions dividing window into 3 majestic panoramic bays
  [-0.75, 0.75].forEach(mx => {
    const vMull = new THREE.Mesh(new THREE.BoxGeometry(0.04, 2.86, 0.06), windowFrameMat);
    vMull.position.set(mx, 0, 0);
    winGroup.add(vMull);
  });
  // 1 Horizontal Transom Crossbeam
  const hTransom = new THREE.Mesh(new THREE.BoxGeometry(4.50, 0.035, 0.06), windowFrameMat);
  hTransom.position.set(0, 0.88, 0);
  winGroup.add(hTransom);
  // Transparent Architectural Glass Pane with Specular Highlights
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xc7d2fe,
    roughness: 0.06,
    metalness: 0.90,
    transparent: true,
    opacity: 0.15
  });
  const glassPane = new THREE.Mesh(new THREE.PlaneGeometry(4.48, 2.84), glassMat);
  glassPane.position.set(0, 0, -0.01);
  winGroup.add(glassPane);
  vrmEnvironmentGroup.add(winGroup);
  // 7b. Exterior Balcony Veranda Railing & Ledge (Visible just outside the glass at Z = -3.75m)
  const balconyMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, roughness: 0.5 });
  const balconyLedge = new THREE.Mesh(new THREE.BoxGeometry(4.80, 0.12, 0.70), balconyMat);
  balconyLedge.position.set(0.95, vrmBaseY - 0.06, -3.85);
  vrmEnvironmentGroup.add(balconyLedge);
  // Minimalist Outdoor Glass Balustrade & Dark Metal Railing
  const railingBeam = new THREE.Mesh(new THREE.BoxGeometry(4.80, 0.04, 0.04), windowFrameMat);
  railingBeam.position.set(0.95, vrmBaseY + 0.92, -3.72);
  vrmEnvironmentGroup.add(railingBeam);
  const balustradeGlassMat = new THREE.MeshStandardMaterial({
    color: 0x93c5fd,
    roughness: 0.10,
    metalness: 0.80,
    transparent: true,
    opacity: 0.22
  });
  const balustradeGlass = new THREE.Mesh(new THREE.PlaneGeometry(4.70, 0.86), balustradeGlassMat);
  balustradeGlass.position.set(0.95, vrmBaseY + 0.46, -3.72);
  vrmEnvironmentGroup.add(balustradeGlass);
  // 8. Clean Architectural Ceiling (Y = +3.6m)
  const ceilingGeo = new THREE.PlaneGeometry(10, 9);
  const ceilingMat = new THREE.MeshStandardMaterial({ color: 0x111620, roughness: 0.92 });
  const ceiling = new THREE.Mesh(ceilingGeo, ceilingMat);
  ceiling.rotation.x = Math.PI / 2;
  ceiling.position.set(0, vrmBaseY + 3.6, 0);
  vrmEnvironmentGroup.add(ceiling);
  // Recessed pot light bezels in ceiling
  const potGeo = new THREE.RingGeometry(0.08, 0.14, 20);
  const potMat = new THREE.MeshBasicMaterial({ color: 0x4a5568, side: THREE.DoubleSide });
  const p1 = new THREE.Mesh(potGeo, potMat); p1.rotation.x = Math.PI / 2; p1.position.set(-1.8, vrmBaseY + 3.59, -1.0); vrmEnvironmentGroup.add(p1);
  const p2 = new THREE.Mesh(potGeo, potMat); p2.rotation.x = Math.PI / 2; p2.position.set(1.8, vrmBaseY + 3.59, -1.0); vrmEnvironmentGroup.add(p2);
  const p3 = new THREE.Mesh(potGeo, potMat); p3.rotation.x = Math.PI / 2; p3.position.set(-1.8, vrmBaseY + 3.59, 1.2); vrmEnvironmentGroup.add(p3);
  const p4 = new THREE.Mesh(potGeo, potMat); p4.rotation.x = Math.PI / 2; p4.position.set(1.8, vrmBaseY + 3.59, 1.2); vrmEnvironmentGroup.add(p4);
  // 9. Architectural Lighting
  const keyLight = new THREE.DirectionalLight(0xfff6ea, 1.4);
  keyLight.position.set(2.4, vrmBaseY + 3.4, 3.2);
  keyLight.castShadow = true;
  vrmEnvironmentGroup.add(keyLight);
  envLights.push(keyLight);
  const fillLight = new THREE.PointLight(0xa855f7, 1.2, 9.0, 1.4);
  fillLight.position.set(-2.6, vrmBaseY + 2.8, -1.2);
  vrmEnvironmentGroup.add(fillLight);
  envLights.push(fillLight);
  // Apply active modular props according to user decorations config
  applyRoomDecorations();
}

function buildRoomWindowProp() {
  const group = new THREE.Group();
  group.position.set(0, vrmBaseY, -3.42);
  // Brushed Brass Curtain Rod above panoramic window (spanning X: -1.45m to +3.35m)
  const rodMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.88, roughness: 0.22 });
  const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 4.88, 16), rodMat);
  rod.rotation.z = Math.PI / 2;
  rod.position.set(0.95, 3.08, 0);
  group.add(rod);
  // Brass finials at rod ends
  [-1.50, 3.40].forEach(fx => {
    const finial = new THREE.Mesh(new THREE.SphereGeometry(0.045, 16, 16), rodMat);
    finial.position.set(fx, 3.08, 0);
    group.add(finial);
  });
  // Soft Tailored Floor-to-Ceiling Drapery / Curtains Flanking Window Sides
  const curtainMat = new THREE.MeshStandardMaterial({
    color: 0x334155, // Elegant slate blue / navy linen
    roughness: 0.88,
    metalness: 0.04
  });
  // Left Drapery Panel (gathered at X: -1.26m, falling from Y: 3.06m to 0.02m)
  const leftDrape = new THREE.Mesh(new THREE.BoxGeometry(0.38, 3.04, 0.08), curtainMat);
  leftDrape.position.set(-1.26, 1.54, 0.02);
  group.add(leftDrape);
  // Right Drapery Panel (gathered at X: +3.16m, falling from Y: 3.06m to 0.02m)
  const rightDrape = new THREE.Mesh(new THREE.BoxGeometry(0.38, 3.04, 0.08), curtainMat);
  rightDrape.position.set(3.16, 1.54, 0.02);
  group.add(rightDrape);
  // Decorative Brass Tiebacks
  const tieMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.9, roughness: 0.2 });
  const leftTie = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.012, 12, 24), tieMat);
  leftTie.position.set(-1.22, 1.30, 0.06);
  leftTie.rotation.y = Math.PI / 2;
  group.add(leftTie);
  const rightTie = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.012, 12, 24), tieMat);
  rightTie.position.set(3.12, 1.30, 0.06);
  rightTie.rotation.y = Math.PI / 2;
  group.add(rightTie);
  return group;
}

function buildRoomBedProp() {
  const group = new THREE.Group();
  group.position.set(-2.4, vrmBaseY, -2.1);
  // Dark Platform Base
  const baseMat = new THREE.MeshStandardMaterial({ color: 0x181410, roughness: 0.6 });
  const base = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.28, 1.8), baseMat);
  base.position.set(0, 0.14, 0);
  group.add(base);
  // Headboard
  const hb = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.90, 0.10), baseMat);
  hb.position.set(0, 0.60, -0.85);
  group.add(hb);
  // Plush Mattress
  const matMat = new THREE.MeshStandardMaterial({ color: 0xeeece8, roughness: 0.8 });
  const mat = new THREE.Mesh(new THREE.BoxGeometry(1.95, 0.22, 1.65), matMat);
  mat.position.set(0, 0.39, 0.04);
  group.add(mat);
  // Folded Quilt / Duvet
  const duvetMat = new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.75 });
  const duvet = new THREE.Mesh(new THREE.BoxGeometry(1.97, 0.12, 1.10), duvetMat);
  duvet.position.set(0, 0.47, 0.32);
  group.add(duvet);
  // Pillows
  const pilMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, roughness: 0.9 });
  const pil1 = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.12, 0.40), pilMat);
  pil1.position.set(-0.50, 0.52, -0.55);
  pil1.rotation.x = 0.2;
  const pil2 = new THREE.Mesh(new THREE.BoxGeometry(0.70, 0.12, 0.40), pilMat);
  pil2.position.set(0.50, 0.52, -0.55);
  pil2.rotation.x = 0.2;
  group.add(pil1);
  group.add(pil2);
  return group;
}

function buildRoomClosetProp() {
  const group = new THREE.Group();
  group.position.set(3.8, vrmBaseY, -1.8);
  group.rotation.y = -Math.PI / 2;
  // Armoire Body
  const woodMat = new THREE.MeshStandardMaterial({ color: 0x201812, roughness: 0.5 });
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.35, 0.60), woodMat);
  body.position.set(0, 1.175, 0);
  group.add(body);
  // Twin Door Inset Lines
  const lineMat = new THREE.MeshBasicMaterial({ color: 0x0f0b08 });
  const line = new THREE.Mesh(new THREE.BoxGeometry(0.015, 2.25, 0.01), lineMat);
  line.position.set(0, 1.175, 0.302);
  group.add(line);
  // Vertical Brass Handles
  const hMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.85, roughness: 0.25 });
  const h1 = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.32, 0.025), hMat);
  h1.position.set(-0.06, 1.15, 0.315);
  const h2 = new THREE.Mesh(new THREE.BoxGeometry(0.018, 0.32, 0.025), hMat);
  h2.position.set(0.06, 1.15, 0.315);
  group.add(h1);
  group.add(h2);
  return group;
}

function buildRoomMirrorProp() {
  const group = new THREE.Group();
  group.position.set(3.9, vrmBaseY, 0.8);
  group.rotation.y = -Math.PI / 2;
  // Standing Frame (Champagne Gold)
  const frameMat = new THREE.MeshStandardMaterial({ color: 0xd4af37, metalness: 0.8, roughness: 0.25 });
  const frame = new THREE.Mesh(new THREE.BoxGeometry(0.80, 1.95, 0.06), frameMat);
  frame.position.set(0, 0.98, 0);
  group.add(frame);
  // Reflective Glass Surface
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    metalness: 0.95,
    roughness: 0.05
  });
  const glass = new THREE.Mesh(new THREE.PlaneGeometry(0.70, 1.85), glassMat);
  glass.position.set(0, 0.98, 0.032);
  group.add(glass);
  return group;
}

function buildRoomPlantProp() {
  const group = new THREE.Group();
  group.position.set(2.6, vrmBaseY, -2.6);
  // Ceramic Pot
  const potMat = new THREE.MeshStandardMaterial({ color: 0xf1f5f9, roughness: 0.4 });
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.18, 0.46, 24), potMat);
  pot.position.set(0, 0.23, 0);
  group.add(pot);
  // Soil
  const soilMat = new THREE.MeshStandardMaterial({ color: 0x1f140e, roughness: 0.9 });
  const soil = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.04, 20), soilMat);
  soil.position.set(0, 0.44, 0);
  group.add(soil);
  // Stems & Leaves
  const leafMat = new THREE.MeshStandardMaterial({ color: 0x15803d, roughness: 0.6 });
  for (let i = 0; i < 7; i++) {
    const angle = (i / 7) * Math.PI * 2;
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.18, 12, 8), leafMat);
    leaf.scale.set(1.4, 0.2, 0.8);
    leaf.rotation.y = angle;
    leaf.rotation.z = 0.45;
    leaf.position.set(Math.cos(angle) * 0.22, 0.55 + (i * 0.08), Math.sin(angle) * 0.22);
    group.add(leaf);
  }
  return group;
}

function applyRoomDecorations() {
  if (!vrmRoomPropsGroup) return;
  // Clear existing modular props
  while (vrmRoomPropsGroup.children.length > 0) {
    vrmRoomPropsGroup.remove(vrmRoomPropsGroup.children[0]);
  }
  const cfg = loadRoomDecorationsConfig();
  // 1. Studio Window
  if (cfg.window) {
    roomWindowMesh = buildRoomWindowProp();
    vrmRoomPropsGroup.add(roomWindowMesh);
  }
  // 2. Platform Bed
  if (cfg.bed) {
    roomBedMesh = buildRoomBedProp();
    vrmRoomPropsGroup.add(roomBedMesh);
  }
  // 3. Wardrobe Closet
  if (cfg.closet) {
    roomClosetMesh = buildRoomClosetProp();
    vrmRoomPropsGroup.add(roomClosetMesh);
  }
  // 4. Full-Length Mirror
  if (cfg.mirror) {
    roomMirrorMesh = buildRoomMirrorProp();
    vrmRoomPropsGroup.add(roomMirrorMesh);
  }
  // 5. Potted Plant
  if (cfg.plant) {
    roomPlantMesh = buildRoomPlantProp();
    vrmRoomPropsGroup.add(roomPlantMesh);
  }
  // 6. Yoshi Plush
  if (cfg.yoshi) {
    if (!yoshiModel) {
      loadYoshiPlushProp();
    } else {
      updateYoshiEnvironmentRest();
      if (!vrmScene.children.includes(yoshiModel)) {
        vrmScene.add(yoshiModel);
      }
    }
  } else {
    if (yoshiModel && vrmScene && vrmScene.children.includes(yoshiModel)) {
      vrmScene.remove(yoshiModel);
    }
  }
  // 7. Interactive Basketball
  if (cfg.basketball) {
    createBasketballProp();
    if (basketballMesh && !vrmScene.children.includes(basketballMesh)) {
      vrmScene.add(basketballMesh);
    }
  } else if (basketballMesh && basketballState !== 'DRIBBLING') {
    if (vrmScene.children.includes(basketballMesh)) {
      vrmScene.remove(basketballMesh);
    }
  }
  const dribbleBtn = document.getElementById('btnBasketballAction');
  if (dribbleBtn) {
    dribbleBtn.style.display = cfg.basketball ? '' : 'none';
  }
  // Update Modal Checkboxes and Cards
  syncRoomCustomizerUI(cfg);
}

// ============================================================================

// --- PHASE 5: 3D ROOM CUSTOMIZER & DYNAMIC PROP LOADER ENGINE ---

// ============================================================================
let vrmCustomPropsGroup = null;
let vrmSelectedProp = null;
let vrmSelectionRing = null;
let availableCustomProps = [];

// ============================================================================
// PHASE 6: BIOLOGICAL CONNECTOME FRUIT FLY (Drosophila Melanogaster Simulation)
// Based on FlyWire 2024 Adult Brain Connectome (139,255 Neurons / 54.5M Synapses)
// Architecture:
// 1. Optic Lobe / EMD (T4/T5 Neurons): Wall / obstacle proximity detection
// 2. Giant Fiber (GF) Circuit: High-acceleration escape reflex
// 3. Central Complex (CX) Heading: Saccadic steering & vector navigation
// 4. Perching & Haltere Mechanics: 200 Hz wingbeat oscillation, perching & grooming

// ============================================================================
let connectomeFlyGroup = null;
let connectomeFlyEnabled = true;
let flyLeftWing = null;
let flyRightWing = null;
let flyState = 'FLYING'; // 'FLYING', 'SACCADE', 'PERCHED', 'GROOMING', 'ESCAPE'
let flyStateTimer = 0;
let flyHeading = 0.0;
let flyPitch = 0.0;
let flySpeed = 1.15;
let flyTargetPerch = null;
let flyGroomPhase = 0;
let flyPerchTimer = 0;

function initConnectomeFly() {
  if (connectomeFlyGroup || !vrmScene) return;
  connectomeFlyGroup = new THREE.Group();
  connectomeFlyGroup.name = "ConnectomeFruitFly";
  // Scale: 1.0 (approx 4.5cm visual diorama size so it is visible and lifelike on 1024x600)
  // Scaled to eye-size for visible testing & connectome inspection
  connectomeFlyGroup.scale.set(2.4, 2.4, 2.4);
  // Thorax (chitin dark slate)
  const thoraxGeo = new THREE.SphereGeometry(0.024, 8, 8);
  thoraxGeo.scale(1.0, 0.85, 1.25);
  const thoraxMat = new THREE.MeshStandardMaterial({
    color: 0x22272e,
    roughness: 0.35,
    metalness: 0.65
  });
  const thorax = new THREE.Mesh(thoraxGeo, thoraxMat);
  connectomeFlyGroup.add(thorax);
  // Compound Eyes (bright ruby red)
  const eyeGeo = new THREE.SphereGeometry(0.011, 8, 8);
  const eyeMat = new THREE.MeshStandardMaterial({
    color: 0xef4444,
    roughness: 0.15,
    metalness: 0.85,
    emissive: 0x7f1d1d
  });
  const lEye = new THREE.Mesh(eyeGeo, eyeMat);
  lEye.position.set(-0.015, 0.009, 0.020);
  const rEye = new THREE.Mesh(eyeGeo, eyeMat);
  rEye.position.set(0.015, 0.009, 0.020);
  connectomeFlyGroup.add(lEye, rEye);
  // Abdomen (striped golden-amber/dark segments)
  const abdGeo = new THREE.CylinderGeometry(0.020, 0.009, 0.052, 8);
  abdGeo.rotateX(Math.PI / 2);
  const abdMat = new THREE.MeshStandardMaterial({
    color: 0xd97706,
    roughness: 0.45,
    metalness: 0.25
  });
  const abdomen = new THREE.Mesh(abdGeo, abdMat);
  abdomen.position.set(0, -0.006, -0.038);
  connectomeFlyGroup.add(abdomen);
  // Wings (delicate translucent wings with iridescent shimmer)
  const wingGeo = new THREE.PlaneGeometry(0.032, 0.064);
  wingGeo.translate(0, 0.030, 0);
  wingGeo.rotateX(Math.PI / 2);
  const wingMat = new THREE.MeshPhysicalMaterial({
    color: 0xf0f9ff,
    transparent: true,
    opacity: 0.70,
    roughness: 0.1,
    transmission: 0.9,
    side: THREE.DoubleSide
  });
  flyLeftWing = new THREE.Mesh(wingGeo, wingMat);
  flyLeftWing.position.set(-0.012, 0.018, -0.008);
  flyRightWing = new THREE.Mesh(wingGeo, wingMat);
  flyRightWing.position.set(0.012, 0.018, -0.008);
  connectomeFlyGroup.add(flyLeftWing, flyRightWing);
  // Initial Position: hovering in room near center-right
  connectomeFlyGroup.position.set(0.65, vrmBaseY + 1.25, -0.40);
  flyHeading = Math.PI * 0.8;
  vrmScene.add(connectomeFlyGroup);
  console.log("[CONNECTOME] Biologically simulated fruit fly initialized.");
}

function updateConnectomeFly(delta, time) {
  if (!connectomeFlyEnabled || !connectomeFlyGroup) return;
  const flyPos = connectomeFlyGroup.position;
  if (flyState === 'FLYING' || flyState === 'ESCAPE' || flyState === 'SACCADE') {
    // 1. High-frequency biological wingbeat oscillation (~200 Hz illusion)
    const flapAngle = Math.sin(time * 165) * 0.85;
    if (flyLeftWing) flyLeftWing.rotation.z = flapAngle;
    if (flyRightWing) flyRightWing.rotation.z = -flapAngle;
    // 2. Flight Kinematics
    const curSpeed = (flyState === 'ESCAPE') ? flySpeed * 2.2 : flySpeed;
    const fwdX = -Math.sin(flyHeading) * Math.cos(flyPitch);
    const fwdZ = -Math.cos(flyHeading) * Math.cos(flyPitch);
    const fwdY = Math.sin(flyPitch);
    flyPos.x += fwdX * curSpeed * delta;
    flyPos.y += fwdY * curSpeed * delta;
    flyPos.z += fwdZ * curSpeed * delta;
    // Biological SNN 3D position attractor coupling
    if (latestPipState && latestPipState.position) {
      const p = latestPipState.position;
      flyPos.x += (p.x - flyPos.x) * Math.min(1.0, delta * 3.2);
      flyPos.y += (p.y - flyPos.y) * Math.min(1.0, delta * 3.2);
      flyPos.z += (p.z - flyPos.z) * Math.min(1.0, delta * 3.2);
    }
    // Smooth aerodynamic banked flight: eliminate instant 180 snap glitches
    if (typeof window._flyTargetHeading === 'undefined') window._flyTargetHeading = flyHeading;
    const hDiff = Math.atan2(Math.sin(window._flyTargetHeading - flyHeading), Math.cos(window._flyTargetHeading - flyHeading));
    const turnRate = (flyState === 'ESCAPE' || flyState === 'SACCADE') ? 14.0 : 6.0;
    flyHeading += hDiff * Math.min(1.0, delta * turnRate);
    // Aerodynamic banking roll into turns
    const rollAngle = THREE.MathUtils.clamp(-hDiff * 1.6, -0.75, 0.75);
    connectomeFlyGroup.rotation.set(-flyPitch, flyHeading, rollAngle, 'YXZ');
    // 3. Optomotor Reflex (EMD / T4/T5): Boundary avoidance
    const atWall = (flyPos.x < -2.9 || flyPos.x > 2.4 || flyPos.z < -3.1 || flyPos.z > 1.7 || flyPos.y < vrmBaseY + 0.35 || flyPos.y > vrmBaseY + 2.3);
    if (atWall) {
      // Smooth optomotor torque heading adjustment away from wall

      window._flyTargetHeading = flyHeading + (Math.random() > 0.5 ? 1 : -1) * (Math.PI * 0.55 + Math.random() * 0.35);
      flyPitch = (Math.random() - 0.5) * 0.4;
      flyState = 'SACCADE';
      flyStateTimer = 0.22;
    }
    // 4. Central Complex (CX) Stochastic Heading Saccades
    flyStateTimer -= delta;
    if (flyStateTimer <= 0) {
      if (flyState === 'ESCAPE' || flyState === 'SACCADE') {
        flyState = 'FLYING';
      }
      // Central Complex stochastic steering vector

      window._flyTargetHeading = flyHeading + (Math.random() - 0.5) * 1.5;
      flyPitch = (Math.random() - 0.5) * 0.5;
      flyStateTimer = 0.6 + Math.random() * 1.2;
    }
    // 5. Giant Fiber (GF) Proximity Escape Trigger (if near Rum or moving hand)
    const dToRum = Math.hypot(flyPos.x - vrmRoamCurrentPos.x, flyPos.z - vrmRoamCurrentPos.z);
    if (dToRum < 0.38 && Math.abs(flyPos.y - (vrmBaseY + 1.2)) < 0.45) {
      flyHeading += Math.PI * (0.8 + Math.random() * 0.4);
      flyPitch = 0.6;
      flyState = 'ESCAPE';
      flyStateTimer = 0.7;
    }
    // 6. Natural Perching Chance (seeking landing surface)
    if (time > flyPerchTimer) {
      // Choose a perch target (coffee table, railing, or mat)
      let perchTarget = { x: 0.0, y: vrmBaseY + 0.05, z: -1.75 }; // balcony rail
      if (vrmCustomPropsGroup && vrmCustomPropsGroup.children.length > 0) {
        const randProp = vrmCustomPropsGroup.children[Math.floor(Math.random() * vrmCustomPropsGroup.children.length)];
        if (randProp.visible) {
          perchTarget = {
            x: randProp.position.x,
            y: randProp.position.y + 0.45 * randProp.scale.y,
            z: randProp.position.z
          };
        }
      }
      flyTargetPerch = perchTarget;
      flyPerchTimer = time + 22.0 + Math.random() * 15.0;
    }
    if (flyTargetPerch) {
      const dPerch = flyPos.distanceTo(new THREE.Vector3(flyTargetPerch.x, flyTargetPerch.y, flyTargetPerch.z));
      if (dPerch < 0.12) {
        // Touch down!
        flyPos.set(flyTargetPerch.x, flyTargetPerch.y, flyTargetPerch.z);
        flyState = 'PERCHED';
        if (typeof attachPipDropperToRum === 'function') attachPipDropperToRum();
        flyStateTimer = 4.5 + Math.random() * 5.0;
        flyTargetPerch = null;
      }
    }
  } else if (flyState === 'PERCHED' || flyState === 'GROOMING') {
    // Fold wings back flat along abdomen
    if (flyLeftWing) flyLeftWing.rotation.set(0.08, 0.14, 0.06);
    if (flyRightWing) flyRightWing.rotation.set(0.08, -0.14, -0.06);
    // Micro leg/head grooming twitches
    flyGroomPhase += delta * 7.5;
    connectomeFlyGroup.rotation.y += Math.sin(flyGroomPhase) * 0.02;
    flyStateTimer -= delta;
    if (flyStateTimer <= 0) {
      // Take off again!
      flyPitch = 0.55;
      if (typeof detachPipDropperFromRum === 'function') {
        setTimeout(detachPipDropperFromRum, 3500);
      }
      flyHeading = Math.random() * Math.PI * 2;
      flyState = 'FLYING';
      flyStateTimer = 1.0;
    }
  }
}

function toggleConnectomeFly() {
  connectomeFlyEnabled = !connectomeFlyEnabled;
  if (connectomeFlyGroup) {
    connectomeFlyGroup.visible = connectomeFlyEnabled;
  }
  const btn = document.getElementById('btnConnectomeFlyToggle');
  if (btn) {
    btn.innerHTML = connectomeFlyEnabled ? '🪰 FLY: ON' : '🪰 FLY: OFF';
    btn.style.borderColor = connectomeFlyEnabled ? '#38bdf8' : 'rgba(255,255,255,0.2)';
    btn.style.color = connectomeFlyEnabled ? '#38bdf8' : 'var(--text-secondary)';
  }
  showAiSpeechToast(connectomeFlyEnabled ? '🪰 Connectome Fruit Fly active' : 'Fruit fly dismissed');
}

function initCustomPropsGroup() {
  if (!vrmScene) return;
  if (!vrmCustomPropsGroup) {
    vrmCustomPropsGroup = new THREE.Group();
    vrmScene.add(vrmCustomPropsGroup);
  }
  // Neon glowing selection ring flat on the floor
  if (!vrmSelectionRing) {
    const ringGeo = new THREE.RingGeometry(0.35, 0.42, 32);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0xc084fc,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.85
    });
    vrmSelectionRing = new THREE.Mesh(ringGeo, ringMat);
    vrmSelectionRing.rotation.x = -Math.PI / 2;
    vrmSelectionRing.position.y = vrmBaseY + 0.005;
    vrmSelectionRing.visible = false;
    vrmScene.add(vrmSelectionRing);
  }
  loadCustomRoomLayout();
}

function switchRoomEditorTab(tab) {
  const propsTab = document.getElementById('roomEditorPropsTab');
  const fixturesTab = document.getElementById('roomEditorFixturesTab');
  const btnProps = document.getElementById('tabBtnCustomProps');
  const btnFixtures = document.getElementById('tabBtnFixtures');
  if (tab === 'PROPS') {
    if (propsTab) propsTab.style.display = 'flex';
    if (fixturesTab) fixturesTab.style.display = 'none';
    if (btnProps) {
      btnProps.style.background = 'rgba(168,85,247,0.18)';
      btnProps.style.borderBottom = '2px solid var(--accent-purple)';
      btnProps.style.color = '#fff';
    }
    if (btnFixtures) {
      btnFixtures.style.background = 'transparent';
      btnFixtures.style.borderBottom = '2px solid transparent';
      btnFixtures.style.color = 'var(--text-secondary)';
    }
  } else {
    if (propsTab) propsTab.style.display = 'none';
    if (fixturesTab) fixturesTab.style.display = 'flex';
    if (btnProps) {
      btnProps.style.background = 'transparent';
      btnProps.style.borderBottom = '2px solid transparent';
      btnProps.style.color = 'var(--text-secondary)';
    }
    if (btnFixtures) {
      btnFixtures.style.background = 'rgba(168,85,247,0.18)';
      btnFixtures.style.borderBottom = '2px solid var(--accent-purple)';
      btnFixtures.style.color = '#fff';
    }
  }
}

function rescanCustomPropsCatalog() {
  const badge = document.getElementById('roomPropsCountBadge');
  const grid = document.getElementById('customPropsCatalogGrid');
  if (badge) badge.innerText = 'SCANNING...';
  fetch('/api/models/custom_props')
    .then(r => r.json())
    .then(data => {
      availableCustomProps = data.props || [];
      if (badge) badge.innerText = `${availableCustomProps.length} DETECTED`;
      if (!grid) return;
      grid.innerHTML = '';
      if (availableCustomProps.length === 0) {
        grid.innerHTML = `<div style="grid-column:1/-1; padding:16px; text-align:center; color:var(--text-secondary); font-size:12px; background:rgba(255,255,255,0.02); border:1px dashed #334155; border-radius:10px;">

          No 3D models found yet.<br>

          <span style="color:#a0b8d0;">Drop <b>.obj</b> or <b>.gltf</b> files into <code>/storage/models/props/</code> or onto any USB drive!</span>

        </div>`;
        return;
      }
      availableCustomProps.forEach(prop => {
        const card = document.createElement('div');
        card.style.cssText = 'background:rgba(255,255,255,0.04); border:1px solid #334155; border-radius:10px; padding:10px; display:flex; flex-direction:column; justify-content:space-between; gap:8px;';
        const isObj = (prop.format === 'obj');
        const badgeColor = isObj ? 'var(--accent-orange)' : 'var(--accent-green)';
        const badgeBg = isObj ? 'rgba(255,107,0,0.15)' : 'rgba(0,230,118,0.15)';
        card.innerHTML = `

          <div style="display:flex; justify-content:space-between; align-items:flex-start;">

            <div style="font-size:12px; font-weight:800; color:#fff; word-break:break-word;">${prop.name}</div>

            <span style="font-size:9px; font-weight:800; color:${badgeColor}; background:${badgeBg}; padding:2px 6px; border-radius:6px; border:1px solid ${badgeColor};">${prop.format.toUpperCase()}</span>

          </div>

          <div style="display:flex; justify-content:space-between; align-items:center;">

            <span style="font-size:10px; color:var(--text-secondary);">${prop.size_formatted || ''}</span>

            <button class="cluster-action-btn" onclick="spawnCustomProp(${JSON.stringify(prop).replace(/"/g, '&quot;')}, true)" style="padding:4px 10px; font-size:11px; font-weight:800; border-color:var(--accent-purple); color:var(--accent-purple); height:32px;">
              ➕ PLACE
            </button>
          </div>
        `;

        grid.appendChild(card);

      });

    })

    .catch(err => {

      console.warn('[PROPS] Error scanning custom props:', err);

      if (badge) badge.innerText = 'OFFLINE';

    });

}

function loadCustomRoomLayout() {

  if (!vrmCustomPropsGroup) return;

  fetch('/api/models/room_layout')

    .then(r => r.json())

    .then(layout => {

      // Clear existing custom placed props

      while (vrmCustomPropsGroup.children.length > 0) {

        vrmCustomPropsGroup.remove(vrmCustomPropsGroup.children[0]);

      }

      vrmSelectedProp = null;

      if (vrmSelectionRing) vrmSelectionRing.visible = false;

      const props = layout.props || [];

      props.forEach(p => {

        if (p.id === 'prop_yoshi_default' && yoshiModel) return;

        spawnCustomProp(p, false);

      });

      updatePlacedPropsUI();

    })

    .catch(err => {

      console.warn('[PROPS] Error loading room layout:', err);

    });

}

function spawnCustomProp(propDef, isNew = false) {

  if (!vrmScene || !vrmCustomPropsGroup) return;

  const propId = propDef.id || ('prop_' + Date.now());

  const format = (propDef.format || 'obj').toLowerCase();

  const url = propDef.url || propDef.modelUrl || propDef.direct_url;

  function onModelLoaded(meshRoot) {

    meshRoot.userData = {

      id: propId,

      name: propDef.name || 'Custom Prop',

      format: format,

      url: url,

      modelUrl: url

    };

    // Set position

    if (propDef.position && Array.isArray(propDef.position)) {

      meshRoot.position.set(propDef.position[0], propDef.position[1], propDef.position[2]);

    } else {

      // Default spawn: slight offset in front

      const offsetCount = vrmCustomPropsGroup.children.length;

      meshRoot.position.set(-0.8 + (offsetCount * 0.4), vrmBaseY, 0.4);

    }

    // Set rotation

    if (propDef.rotation && Array.isArray(propDef.rotation)) {

      meshRoot.rotation.set(propDef.rotation[0], propDef.rotation[1], propDef.rotation[2]);

    } else {

      meshRoot.rotation.set(0, 0, 0);

    }

    // Set scale

    if (propDef.scale && Array.isArray(propDef.scale)) {

      meshRoot.scale.set(propDef.scale[0], propDef.scale[1], propDef.scale[2]);

    } else {

      // Auto-normalize bounding size to approx 0.85m if no scale specified

      const bbox = new THREE.Box3().setFromObject(meshRoot);

      const size = bbox.getSize(new THREE.Vector3());

      const maxDim = Math.max(size.x, size.y, size.z);

      if (maxDim > 2.5 || maxDim < 0.2) {

        const targetScale = 0.85 / (maxDim || 1.0);

        meshRoot.scale.set(targetScale, targetScale, targetScale);

      } else {

        meshRoot.scale.set(1.0, 1.0, 1.0);

      }

    }

    // Traverse meshes for shadows and nice standard materials

    meshRoot.traverse(node => {

      if (node.isMesh) {

        node.castShadow = true;

        node.receiveShadow = true;

        node.frustumCulled = false;

        if (!node.material || node.material.type === 'MeshBasicMaterial' || (node.material.color && node.material.color.getHex() === 0xffffff && !node.material.map)) {

          node.material = new THREE.MeshStandardMaterial({

            color: (node.material && node.material.color && node.material.color.getHex() !== 0xffffff) ? node.material.color : 0x2e384d,

            roughness: 0.45,

            metalness: 0.35

          });

        }

      }

    });

    applyHighQualityTextureFiltering(meshRoot);

    vrmCustomPropsGroup.add(meshRoot);

    updatePlacedPropsUI();

    if (isNew) {

      selectCustomProp(meshRoot);

      if (typeof speakUtterance === 'function') {

        speakUtterance(`Placed ${propDef.name} into our room, Master!`);

      }

      showAiSpeechToast(`Placed ${propDef.name} in Room`);

    }

  }

  // Load based on format

  if (format === 'obj' && typeof THREE.OBJLoader !== 'undefined') {

    const mtlUrl = url.replace(/\.obj$/i, '.mtl');

    if (typeof THREE.MTLLoader !== 'undefined') {

      const mtlLoader = new THREE.MTLLoader();

      mtlLoader.load(

        mtlUrl,

        (materials) => {

          materials.preload();

          const objLoader = new THREE.OBJLoader();

          objLoader.setMaterials(materials);

          objLoader.load(url, onModelLoaded, undefined, (err) => {

            console.warn('[OBJLoader] Fallback without materials:', err);

            const fbLoader = new THREE.OBJLoader();

            fbLoader.load(url, onModelLoaded);

          });

        },

        undefined,

        (err) => {

          // No MTL file, load OBJ with standard shader

          const objLoader = new THREE.OBJLoader();

          objLoader.load(url, onModelLoaded);

        }

      );

    } else {

      const loader = new THREE.OBJLoader();

      loader.load(url, onModelLoaded);

    }

  } else if ((format === 'gltf' || format === 'glb') && typeof THREE.GLTFLoader !== 'undefined') {

    const loader = new THREE.GLTFLoader();

    loader.load(

      url,

      gltf => onModelLoaded(gltf.scene || gltf.scenes[0]),

      undefined,

      err => console.error('[GLTFLoader] Error loading prop:', url, err)

    );

  } else {

    console.warn('[PROPS] Unknown or unsupported format:', format, url);

  }

}

function selectCustomProp(propMesh) {

  vrmSelectedProp = propMesh;

  const inspector = document.getElementById('inspectorControlsGroup');

  const title = document.getElementById('inspectorPropTitle');

  const coords = document.getElementById('inspectorPropCoords');

  const btnCall = document.getElementById('btnCallRumToProp');

  const btnDelete = document.getElementById('btnDeleteSelectedProp');

  if (!propMesh) {

    if (vrmSelectionRing) vrmSelectionRing.visible = false;

    if (inspector) inspector.style.display = 'none';

    if (title) title.innerText = 'SELECTED PROP: NONE';

    if (coords) coords.innerText = 'Tap any model in the catalog or touch a prop in the room to edit';

    if (btnCall) btnCall.style.display = 'none';

    if (btnDelete) btnDelete.style.display = 'none';

    return;

  }

  const name = (propMesh.userData && propMesh.userData.name) || 'Custom Prop';

  if (title) title.innerText = `SELECTED: ${name.toUpperCase()}`;

  if (coords) coords.innerText = `Pos: (${propMesh.position.x.toFixed(2)}, ${propMesh.position.y.toFixed(2)}, ${propMesh.position.z.toFixed(2)}) • Scale: ${propMesh.scale.x.toFixed(2)}x`;

  if (inspector) inspector.style.display = 'flex';

  if (btnCall) btnCall.style.display = 'inline-block';

  if (btnDelete) btnDelete.style.display = 'inline-block';

  // Position holographic selection ring below prop

  if (vrmSelectionRing) {

    vrmSelectionRing.position.set(propMesh.position.x, vrmBaseY + 0.005, propMesh.position.z);

    vrmSelectionRing.scale.set(propMesh.scale.x, propMesh.scale.z, 1.0);

    vrmSelectionRing.visible = true;

  }

  updatePlacedPropsUI();

}

function moveSelectedProp(dx, dz) {

  if (!vrmSelectedProp) return;

  vrmSelectedProp.position.x = Math.max(-3.2, Math.min(3.2, vrmSelectedProp.position.x + dx));

  vrmSelectedProp.position.z = Math.max(-3.0, Math.min(2.8, vrmSelectedProp.position.z + dz));

  if (vrmSelectionRing) {

    vrmSelectionRing.position.x = vrmSelectedProp.position.x;

    vrmSelectionRing.position.z = vrmSelectedProp.position.z;

  }

  const coords = document.getElementById('inspectorPropCoords');

  if (coords) onRoomEnvironmentChanged(vrmSelectedProp, 'moved');

  coords.innerText = `Pos: (${vrmSelectedProp.position.x.toFixed(2)}, ${vrmSelectedProp.position.y.toFixed(2)}, ${vrmSelectedProp.position.z.toFixed(2)}) • Scale: ${vrmSelectedProp.scale.x.toFixed(2)}x`;

}

function elevateSelectedProp(dy) {

  if (!vrmSelectedProp) return;

  vrmSelectedProp.position.y = Math.max(vrmBaseY, Math.min(vrmBaseY + 2.5, vrmSelectedProp.position.y + dy));

  const coords = document.getElementById('inspectorPropCoords');

  if (coords) onRoomEnvironmentChanged(vrmSelectedProp, 'moved');

  coords.innerText = `Pos: (${vrmSelectedProp.position.x.toFixed(2)}, ${vrmSelectedProp.position.y.toFixed(2)}, ${vrmSelectedProp.position.z.toFixed(2)}) • Scale: ${vrmSelectedProp.scale.x.toFixed(2)}x`;

}

function snapSelectedPropToFloor() {

  if (!vrmSelectedProp) return;

  vrmSelectedProp.position.y = vrmBaseY;

  const coords = document.getElementById('inspectorPropCoords');

  if (coords) onRoomEnvironmentChanged(vrmSelectedProp, 'moved');

  coords.innerText = `Pos: (${vrmSelectedProp.position.x.toFixed(2)}, ${vrmSelectedProp.position.y.toFixed(2)}, ${vrmSelectedProp.position.z.toFixed(2)}) • Scale: ${vrmSelectedProp.scale.x.toFixed(2)}x`;

}

function rotateSelectedProp(deg) {

  if (!vrmSelectedProp) return;

  vrmSelectedProp.rotation.y += deg * (Math.PI / 180);

}

function scaleSelectedProp(factor) {

  if (!vrmSelectedProp) return;

  const newScale = Math.max(0.2, Math.min(4.5, vrmSelectedProp.scale.x * factor));

  vrmSelectedProp.scale.set(newScale, newScale, newScale);

  if (vrmSelectionRing) {

    vrmSelectionRing.scale.set(newScale, newScale, 1.0);

  }

  const coords = document.getElementById('inspectorPropCoords');

  if (coords) onRoomEnvironmentChanged(vrmSelectedProp, 'moved');

  coords.innerText = `Pos: (${vrmSelectedProp.position.x.toFixed(2)}, ${vrmSelectedProp.position.y.toFixed(2)}, ${vrmSelectedProp.position.z.toFixed(2)}) • Scale: ${vrmSelectedProp.scale.x.toFixed(2)}x`;

}

function deleteSelectedProp() {

  if (!vrmSelectedProp || !vrmCustomPropsGroup) return;

  const name = (vrmSelectedProp.userData && vrmSelectedProp.userData.name) || 'Prop';

  vrmCustomPropsGroup.remove(vrmSelectedProp);

  selectCustomProp(null);

  updatePlacedPropsUI();

  showAiSpeechToast(`Removed ${name} from room`);

}

function clearAllCustomProps() {

  if (!vrmCustomPropsGroup) return;

  while (vrmCustomPropsGroup.children.length > 0) {

    vrmCustomPropsGroup.remove(vrmCustomPropsGroup.children[0]);

  }

  selectCustomProp(null);

  updatePlacedPropsUI();

  showAiSpeechToast('Cleared all custom room props');

}

function callRumToSelectedProp() {

  if (!vrmSelectedProp) return;

  const name = (vrmSelectedProp.userData && vrmSelectedProp.userData.name) || 'this';

  const targetX = THREE.MathUtils.clamp(vrmSelectedProp.position.x, -2.8, 2.3);

  const targetZ = THREE.MathUtils.clamp(vrmSelectedProp.position.z + 0.65, -3.0, 1.6);

  vrmRoamTargetPos = { x: targetX, z: targetZ };

  const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;

  const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;

  vrmRoamTargetRotY = Math.atan2(-dx, -dz);

  vrmRoamState = 'TURNING';

  vrmRoamEnabled = true;

  if (typeof speakUtterance === 'function') {

    speakUtterance(`Coming right over to inspect ${name}, Master!`);

  }

  showAiSpeechToast(`R.U.M. walking to ${name}...`);

  closeRoomCustomizerModal();

}

function saveRoomLayoutToBackend() {

  if (!vrmCustomPropsGroup) return;

  const propsToSave = [];

  vrmCustomPropsGroup.children.forEach((mesh, idx) => {

    const ud = mesh.userData || {};

    propsToSave.push({

      id: ud.id || `prop_${idx}`,

      name: ud.name || 'Custom Prop',

      format: ud.format || 'obj',

      modelUrl: ud.url || ud.modelUrl || '',

      url: ud.url || ud.modelUrl || '',

      position: [mesh.position.x, mesh.position.y, mesh.position.z],

      rotation: [mesh.rotation.x, mesh.rotation.y, mesh.rotation.z],

      scale: [mesh.scale.x, mesh.scale.y, mesh.scale.z]

    });

  });

  const payload = {

    version: 1,

    last_updated: new Date().toISOString(),

    props: propsToSave

  };

  fetch('/api/models/room_layout', {

    method: 'POST',

    headers: { 'Content-Type': 'application/json' },

    body: JSON.stringify(payload)

  })

    .then(r => r.json())

    .then(data => {

      showAiSpeechToast('💾 Room layout saved permanently!');

      const banner = document.getElementById('roomSaveSuccessBanner');

      if (banner) {

        banner.style.display = 'flex';

        setTimeout(() => { banner.style.display = 'none'; }, 4500);

      }

      if (typeof speakUtterance === 'function') {

        speakUtterance('Room layout saved, Master! Everything is right where you want it.');

      }

    })

    .catch(err => {

      console.warn('[PROPS] Error saving room layout:', err);

      showAiSpeechToast('⚠️ Error saving room layout to backend');

    });

}

function updatePlacedPropsUI() {

  const container = document.getElementById('placedPropsPillsContainer');

  if (!container || !vrmCustomPropsGroup) return;

  container.innerHTML = '';

  if (vrmCustomPropsGroup.children.length === 0) {

    container.innerHTML = '<span style="font-size:11px; color:var(--text-secondary);">No custom props placed yet. Select a model above to spawn!</span>';

    return;

  }

  vrmCustomPropsGroup.children.forEach(mesh => {

    const ud = mesh.userData || {};

    const name = ud.name || 'Prop';

    const isSelected = (mesh === vrmSelectedProp);

    const pill = document.createElement('button');

    pill.className = 'cluster-action-btn';

    pill.style.cssText = `padding:4px 10px; font-size:11px; font-weight:800; border-radius:12px; ${isSelected ? 'background:var(--accent-purple); color:#fff; border-color:var(--accent-purple);' : 'border-color:#475569; color:#cbd5e1;'}`;

    pill.innerText = `🎯 ${name}`;

    pill.onclick = () => selectCustomProp(mesh);

    container.appendChild(pill);

  });

}

function syncRoomCustomizerUI(cfg) {

  const items = ['basketball', 'window', 'bed', 'closet', 'mirror', 'plant', 'yoshi'];

  items.forEach(k => {

    const cap = k.charAt(0).toUpperCase() + k.slice(1);

    const chk = document.getElementById('chkRoom' + cap);

    const card = document.getElementById('cardRoom' + cap);

    const isChecked = !!cfg[k];

    if (chk) chk.checked = isChecked;

    if (card) {

      if (isChecked) card.classList.add('active');

      else card.classList.remove('active');

    }

  });

}

function openRoomCustomizerModal() {

  const modal = document.getElementById('roomCustomizerModal');

  if (!modal) return;

  syncRoomCustomizerUI(loadRoomDecorationsConfig());

  rescanCustomPropsCatalog();

  updatePlacedPropsUI();

  modal.style.display = 'flex';

}

function closeRoomCustomizerModal() {

  const modal = document.getElementById('roomCustomizerModal');

  if (modal) modal.style.display = 'none';

}

function toggleRoomItem(key) {

  const cfg = loadRoomDecorationsConfig();

  cfg[key] = !cfg[key];

  saveRoomDecorationsConfig(cfg);

  applyRoomDecorations();

}

function clearAllRoomItems() {
  const cfg = defaultRoomDecorationsConfig();
  saveRoomDecorationsConfig(cfg);
  applyRoomDecorations();
  speakUtterance('All props cleared! Just our empty room with the studio windows, open door, and balcony, Master!');
  setWaifuEmotion('HAPPY', '🛋️ PURE EMPTY ROOM');
}

function setVrmEnvironment() {
  currentEnvironmentName = 'ROOM';
  try { localStorage.setItem('vrmEnvironment', 'ROOM'); } catch (e) {}
  buildEmptyRoomEnvironment();
  updateWorldButtonLabel();
}

function cycleVrmEnvironment() {
  setVrmEnvironment('ROOM');
}

function updateWorldButtonLabel() {
  const btn = document.getElementById('btnVrmWorldToggle');
  if (btn) btn.innerText = '🛋️ ROOM';
}

function getEnvironmentSurfaceElevation(x, z) {
  return 0.0;
}

function getEnvironmentYoshiPos() {
  return { pos: [0.48, vrmBaseY + 0.16, 0.22], rot: [0, 3.0, 0], scale: 1.35 };
}

function updateYoshiEnvironmentRest() {

  if (!yoshiModel || isHoldingYoshi) return;

  const cfg = getEnvironmentYoshiPos();

  yoshiModel.position.set(cfg.pos[0], cfg.pos[1], cfg.pos[2]);

  yoshiModel.rotation.set(cfg.rot[0], cfg.rot[1], cfg.rot[2]);

  yoshiModel.scale.set(cfg.scale, cfg.scale, cfg.scale);

}

function loadYoshiPlushProp() {

  if (typeof THREE === 'undefined' || !vrmScene) return;

  const loader = new THREE.GLTFLoader();

  const yoshiUrl = 'models/environment/props/yoshi/scene.gltf';

  loader.load(

    yoshiUrl,

    (gltf) => {

      yoshiModel = gltf.scene;

      updateYoshiEnvironmentRest();

      yoshiModel.traverse((node) => {

        if (node.isMesh) {

          node.castShadow = true;

          node.receiveShadow = true;

          node.frustumCulled = false;

        }

      });

      vrmScene.add(yoshiModel);

      console.log('[Yoshi] Yoshi plushie placed in room successfully!');

    },

    (progress) => {},

    (err) => {

      console.warn('[Yoshi] Yoshi model load note:', err);

    }

  );

}

// ============================================================================

// --- AUTONOMOUS ROAMING ENGINE (Natural walking, gestures & interaction awareness) ---

// ============================================================================

function startRoamWalkAnimation() {

  if (!vrmMixer) return;

  const clip = vrmaClips['walk_loop'] || vrmaClips['action_walk'];

  if (!clip) return;

  if (!vrmRoamWalkAction) {

    vrmRoamWalkAction = vrmMixer.clipAction(clip);

    vrmRoamWalkAction.setLoop(THREE.LoopRepeat, Infinity);

    vrmRoamWalkAction.timeScale = 0.85;

  }

  vrmRoamWalkAction.reset();

  vrmRoamWalkAction.enabled = true;

  vrmRoamWalkAction.setEffectiveWeight(1.0);

  vrmRoamWalkAction.play();

  vrmaActiveName = 'walk_loop';

  vrmActionEndTime = Date.now() + 60000;

  if (vrmaIdleAction) {

    vrmaIdleAction.crossFadeTo(vrmRoamWalkAction, 0.35, false);

  }

}

function stopRoamWalkAnimation() {

  if (!vrmMixer || !vrmRoamWalkAction) return;

  if (vrmaIdleAction) {

    vrmaIdleAction.enabled = true;

    vrmaIdleAction.setEffectiveWeight(1.0);

    vrmaIdleAction.play();

    vrmRoamWalkAction.crossFadeTo(vrmaIdleAction, 0.40, false);

  } else {

    vrmRoamWalkAction.stop();

  }

  if (vrmaActiveName === 'walk_loop') {

    vrmaActiveName = null;

    vrmActionEndTime = 0;

  }

}

// ============================================================================

// PHASE 6: R.U.M. SPATIAL MEMORY & ENVIRONMENTAL CHANGE DETECTION

// ============================================================================

let rumSpatialMemory = {

  knownProps: {},

  lastNoticeTime: 0

};

function onRoomEnvironmentChanged(prop, changeType) {

  const now = Date.now();

  if (now - rumSpatialMemory.lastNoticeTime < 4500) return; // Debounce notices

  rumSpatialMemory.lastNoticeTime = now;

  const propName = (prop && prop.userData && prop.userData.name) || 'the furniture';

  const actionMessages = {

    'placed': `Master! You added the ${propName} to my room! Let me go check it out!`,

    'moved': `Ooh! You moved the ${propName}! It looks so nice over there!`,

    'rotated': `Adjusting the ${propName}? The layout looks fantastic!`,

    'scaled': `I like the new size of the ${propName}!`,

    'deleted': `Opening up more floor space! I love how spacious the room feels!`,

    'saved': `Room layout saved! I love how you've styled my space, Master!`
  };
  const speechText = actionMessages[changeType] || `I noticed the room changed, Master!`;
  showAiSpeechToast(`R.U.M. noticed: ${propName} ${changeType}!`);
  if (typeof speakUtterance === 'function' && currentAiPersona === 'RUM') {
    speakUtterance(speechText);
  }
  // Walk over to inspect newly placed or moved furniture
  if (prop && (changeType === 'placed' || changeType === 'moved')) {
    setTimeout(() => {
      if (typeof vrmRoamTargetPos !== 'undefined') {
        vrmRoamTargetPos = {
          x: THREE.MathUtils.clamp(prop.position.x, -2.8, 2.3),
          z: THREE.MathUtils.clamp(prop.position.z + 0.65, -3.0, 1.6)
        };
        const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;
        const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;
        vrmRoamTargetRotY = Math.atan2(-dx, -dz);
        vrmRoamState = 'TURNING';
        vrmRoamEnabled = true;
      }
    }, 1500);
  }
}

function isPointInWalkableZone(x, z) {
  const inRoom = (x >= -3.15 && x <= 2.55 && z >= -3.15 && z <= 1.85);
  const inDoorway = (Math.abs(x - ROOM_DOOR_X) <= 0.36 && z >= -4.15 && z <= -2.95);
  const inBalcony = (x >= -4.05 && x <= 0.05 && z >= -7.15 && z <= -3.95);
  return inRoom || inDoorway || inBalcony;
}

function clampWalkableDestination(x, z, isBalcony) {
  if (isBalcony || z < ROOM_WALL_Z) {
    return {
      x: THREE.MathUtils.clamp(x, -3.95, -0.05),
      z: THREE.MathUtils.clamp(z, -7.05, -4.15)
    };
  }
  return {
    x: THREE.MathUtils.clamp(x, -3.10, 2.50),
    z: THREE.MathUtils.clamp(z, -3.10, 1.80)
  };
}

function walkRumToPoint(targetX, targetZ, opts = {}) {
  const isOutdoor = !!opts.isBalcony || targetZ < ROOM_WALL_Z;
  const clamped = clampWalkableDestination(targetX, targetZ, isOutdoor);
  const curIsOutdoor = vrmRoamCurrentPos.z < ROOM_WALL_Z;
  const destIsOutdoor = clamped.z < ROOM_WALL_Z;
  const queue = [];

  if (!curIsOutdoor && destIsOutdoor) {
    queue.push({ x: ROOM_DOOR_X, z: -2.85, name: 'Doorway Threshold', faceOcean: false });
    queue.push({ x: ROOM_DOOR_X, z: -4.20, name: 'Balcony Entry', faceOcean: false });
  } else if (curIsOutdoor && !destIsOutdoor) {
    queue.push({ x: ROOM_DOOR_X, z: -4.20, name: 'Balcony Entry', faceOcean: false });
    queue.push({ x: ROOM_DOOR_X, z: -2.85, name: 'Doorway Threshold', faceOcean: false });
  }

  queue.push({
    x: clamped.x,
    z: clamped.z,
    name: opts.name || (destIsOutdoor ? 'Ocean Balcony' : 'Room Floor'),
    faceOcean: opts.faceOcean !== undefined ? !!opts.faceOcean : destIsOutdoor
  });

  vrmRoamWaypointsQueue = queue;
  vrmManualWalkActive = (opts.manual !== false);
  const firstStep = vrmRoamWaypointsQueue.shift();
  vrmRoamCurrentWaypoint = firstStep;
  vrmRoamTargetPos = { x: firstStep.x, z: firstStep.z };
  const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;
  const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;
  vrmRoamTargetRotY = Math.atan2(-dx, -dz);
  vrmRoamState = 'TURNING';
  vrmRoamEnabled = true;
  updateRoamButtonLabel();
}

function walkRumOutsideToBalcony() {
  walkRumToPoint(-2.20, -6.50, { name: 'Ocean Balcony', faceOcean: true, isBalcony: true, manual: true });
  showAiSpeechToast('R.U.M. walking outside through the door onto the balcony...');
}

function walkRumInsideRoom() {
  walkRumToPoint(0.0, 0.2, { name: 'Room Center', faceOcean: false, isBalcony: false, manual: true });
  showAiSpeechToast('R.U.M. walking back inside...');
}

window.walkRumToPoint = walkRumToPoint;
window.walkRumOutsideToBalcony = walkRumOutsideToBalcony;
window.walkRumInsideRoom = walkRumInsideRoom;

function checkRumCollisionObstacle(nextX, nextZ) {
  // 1. Interior room, open doorway corridor (X = -2.50), and outdoor teakwood balcony bounds
  if (!isPointInWalkableZone(nextX, nextZ)) {
    return { name: nextZ < ROOM_WALL_Z ? 'Balcony Railing' : 'Room Wall Boundary' };
  }
  // 2. Placed custom props collision check
  if (vrmCustomPropsGroup && vrmCustomPropsGroup.children.length > 0) {
    for (let i = 0; i < vrmCustomPropsGroup.children.length; i++) {
      const p = vrmCustomPropsGroup.children[i];
      if (!p.visible) continue;
      const pScale = Math.max(p.scale.x, p.scale.z, 0.35);
      const safeRadius = Math.max(0.40, pScale * 0.42);
      const d = Math.hypot(nextX - p.position.x, nextZ - p.position.z);
      if (d < safeRadius) {
        return { name: (p.userData && p.userData.name) || 'Furniture Item' };
      }
    }
  }
  return null;
}

function updateAutonomousRoaming(delta, isSpeaking, isReacting, isActionActive, dancing, isSpeedPanic) {
  const isDriverInteracting = isSpeaking || isReacting || isSpeedPanic || dancing;
  const isGazeRetained = (Date.now() < rumGazeRetentionUntil);
  if (!vrmRoamEnabled) {
    vrmManualWalkActive = false;
  }
  if (!vrmManualWalkActive && (!vrmRoamEnabled || isDriverInteracting || isGazeRetained)) {
    if (vrmRoamState === 'WALKING') {
      stopRoamWalkAnimation();
    }
    vrmRoamState = 'IDLE';
    vrmRoamWaypointsQueue = [];
    // Smoothly turn to face driver/master (Math.PI)
    let diff = THREE.MathUtils.euclideanModulo(Math.PI - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.02) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 3.8);
    } else {
      vrmRoamCurrentRotY = Math.PI;
    }
    vrmNextRoamTime = Date.now() + 8500;
    return;
  }
  const now = Date.now();
  if (vrmRoamState === 'IDLE') {
    if (vrmRoamCurrentWaypoint && vrmRoamCurrentWaypoint.faceOcean && !isDriverInteracting && !isGazeRetained) {
      vrmRoamCurrentRotY = 0.0;
    }
    if (now >= vrmNextRoamTime) {
      const candidates = VRM_ROAM_WAYPOINTS.filter(wp => {
        const d = Math.hypot(wp.x - vrmRoamCurrentPos.x, wp.z - vrmRoamCurrentPos.z);
        return d > 0.25;
      });
      const wp = candidates[Math.floor(Math.random() * candidates.length)] || VRM_ROAM_WAYPOINTS[0];
      walkRumToPoint(wp.x, wp.z, { name: wp.name, faceOcean: wp.faceOcean, isBalcony: wp.z < ROOM_WALL_Z, manual: false });
    }
  } else if (vrmRoamState === 'TURNING') {
    let diff = THREE.MathUtils.euclideanModulo(vrmRoamTargetRotY - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.08) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 3.8);
    } else {
      vrmRoamCurrentRotY = vrmRoamTargetRotY;
      vrmRoamState = 'WALKING';
      startRoamWalkAnimation();
    }
  } else if (vrmRoamState === 'WALKING') {
    const dx = vrmRoamTargetPos.x - vrmRoamCurrentPos.x;
    const dz = vrmRoamTargetPos.z - vrmRoamCurrentPos.z;
    const dist = Math.hypot(dx, dz);
    if (dist > 0.045) {
      // Keep R.U.M. facing forward directly along her travel path
      const targetAngle = Math.atan2(-dx, -dz);
      let diff = THREE.MathUtils.euclideanModulo(targetAngle - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
      vrmRoamCurrentRotY += diff * Math.min(1.0, delta * 3.5);
      const walkSpeed = 0.36;
      const step = Math.min(dist, walkSpeed * delta);
      const nextX = vrmRoamCurrentPos.x + (dx / dist) * step;
      const nextZ = vrmRoamCurrentPos.z + (dz / dist) * step;
      const obstacle = checkRumCollisionObstacle(nextX, nextZ);
      if (obstacle) {
        stopRoamWalkAnimation();
        vrmRoamWaypointsQueue = [];
        vrmManualWalkActive = false;
        vrmRoamState = 'ARRIVED';
        vrmNextRoamTime = Date.now() + 2500;
        vrmRoamTargetRotY = Math.PI;
        if (vrmaClips['pose_shy_wave']) {
          playVrmAction('pose_shy_wave', 2200, true);
        }
        showAiSpeechToast(`R.U.M. sensed edge: ${obstacle.name}`);
      } else {
        vrmRoamCurrentPos.x = nextX;
        vrmRoamCurrentPos.z = nextZ;
      }
    } else {
      vrmRoamCurrentPos.x = vrmRoamTargetPos.x;
      vrmRoamCurrentPos.z = vrmRoamTargetPos.z;
      if (vrmRoamWaypointsQueue.length > 0) {
        const nextWp = vrmRoamWaypointsQueue.shift();
        vrmRoamCurrentWaypoint = nextWp;
        vrmRoamTargetPos = { x: nextWp.x, z: nextWp.z };
      } else {
        stopRoamWalkAnimation();
        vrmManualWalkActive = false;
        vrmRoamState = 'ARRIVED';
        if (vrmRoamCurrentWaypoint && vrmRoamCurrentWaypoint.faceOcean) {
          // Turn to gaze out at the ocean horizon (rotation.y = 0.0 faces -Z)
          vrmRoamTargetRotY = 0.0;
        } else {
          // Face forward toward master / driver
          vrmRoamTargetRotY = Math.PI;
          const roll = Math.random();
          if (roll < 0.22 && vrmaClips['pose_shy_wave']) {
            playVrmAction('pose_shy_wave', 3500, true);
          } else if (roll < 0.40 && vrmaClips['greeting_wave_right']) {
            playVrmAction('greeting_wave_right', 3000, true);
          } else if (roll < 0.55 && vrmaClips['model_pose']) {
            playVrmAction('model_pose', 3200, true);
          }
        }
        vrmNextRoamTime = Date.now() + 8000 + Math.random() * 7000;
      }
    }
  } else if (vrmRoamState === 'ARRIVED') {
    let diff = THREE.MathUtils.euclideanModulo(vrmRoamTargetRotY - vrmRoamCurrentRotY + Math.PI, Math.PI * 2) - Math.PI;
    if (Math.abs(diff) > 0.04) {
      vrmRoamCurrentRotY += Math.sign(diff) * Math.min(Math.abs(diff), delta * 2.8);
    } else {
      vrmRoamCurrentRotY = vrmRoamTargetRotY;
      if (now >= vrmNextRoamTime) {
        vrmRoamState = 'IDLE';
      }
    }
  }
}

function toggleVrmRoaming() {
  vrmRoamEnabled = !vrmRoamEnabled;
  localStorage.setItem('vrmRoamEnabled', vrmRoamEnabled ? 'true' : 'false');
  if (!vrmRoamEnabled) {
    if (vrmRoamState === 'WALKING') {
      stopRoamWalkAnimation();
    }
    vrmRoamState = 'IDLE';
    vrmRoamTargetRotY = Math.PI;
  } else {
    vrmNextRoamTime = Date.now() + 2500;
  }
  updateRoamButtonLabel();
}

function updateRoamButtonLabel() {
  const btn = document.getElementById('btnVrmRoamToggle');
  if (btn) {
    btn.innerText = vrmRoamEnabled ? '🚶 ROAM: ON' : '🧍 STAY';
    btn.style.borderColor = vrmRoamEnabled ? '#22c55e' : '#64748b';
    btn.style.color = vrmRoamEnabled ? '#4ade80' : '#94a3b8';
  }
}

function toggleRemRumAvatar() {
  const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));
  const newModel = isRem ? 'Rum.vrm' : 'Rem.vrm';
  currentVrmModelName = newModel;
  localStorage.setItem('vrmCurrentAvatar', newModel);
  loadRumVrmModel(newModel);
  updateModelButtonLabel();
}

function updateModelButtonLabel() {
  const btn = document.getElementById('btnVrmModelToggle');
  const hudTitle = document.getElementById('vrmHudTitle');
  const emotionPill = document.getElementById('waifuEmotionPill');
  const isRem = (currentVrmModelName.includes('Rem') || currentVrmModelName.toLowerCase().includes('rem'));
  if (btn) {
    btn.innerText = isRem ? '💙 REM' : '💜 RUM';
    btn.style.borderColor = isRem ? '#38bdf8' : '#c084fc';
    btn.style.color = isRem ? '#38bdf8' : '#c084fc';
  }
  if (hudTitle) {
    hudTitle.innerHTML = isRem ? '<span>💙</span> REM • SHOTGUN' : '<span>💜</span> RUM • SHOTGUN';
  }
  if (emotionPill) {
    emotionPill.innerText = isRem ? '💙 REM (3D VRM) • DEVOTED TO MASTER' : '💜 RUM (3D VRM) • PLAYFUL SISTER';
  }
}

function initAvatarPokeRaycaster(canvas) {
  if (!canvas || !vrmCamera) return;
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  // Mouse wheel zoom
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const d = Math.sign(e.deltaY) * 0.08;
    vrmZoomMultiplier = Math.max(0.65, Math.min(1.85, vrmZoomMultiplier + d));
  }, { passive: false });
  // Double click / tap reset zoom
  canvas.addEventListener('dblclick', () => {
    vrmZoomMultiplier = 1.0;
  });
  // Touch pinch-to-zoom for touchscreen
  let touchDist = 0;
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      touchDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
    }
  }, { passive: true });
  canvas.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2 && touchDist > 0) {
      const curDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const ratio = touchDist / curDist;
      vrmZoomMultiplier = Math.max(0.65, Math.min(1.85, vrmZoomMultiplier * (ratio > 1 ? 1.025 : 0.975)));
      touchDist = curDist;
    }
  }, { passive: true });

  let tapStartX = 0;
  let tapStartY = 0;

  canvas.addEventListener('pointerdown', (e) => {
    tapStartX = e.clientX;
    tapStartY = e.clientY;
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, vrmCamera);

    // 0. Check if user tapped Basketball
    if (basketballMesh && vrmScene && vrmScene.children.includes(basketballMesh)) {
      const ballHits = raycaster.intersectObjects(basketballMesh.children, true);
      if (ballHits.length > 0) {
        triggerBasketballDribbleAction();
        return;
      }
    }
    // 1. Check if user tapped Yoshi Plush
    if (yoshiModel && vrmScene && vrmScene.children.includes(yoshiModel)) {
      const yoshiHits = raycaster.intersectObjects(yoshiModel.children, true);
      if (yoshiHits.length > 0) {
        triggerYoshiPlushInteraction();
        return;
      }
    }
  });

  // 2. Quick tap/click (< 8px drag) checks avatar bone touch zones first, then room/balcony walkable floor
  canvas.addEventListener('pointerup', (e) => {
    if (Math.hypot(e.clientX - tapStartX, e.clientY - tapStartY) > 8) return;
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, vrmCamera);

    if (vrmModel) {
      const hits = raycaster.intersectObjects(vrmModel.children, true);
      if (hits.length > 0) {
        const zoneKey = detectAvatarTouchZone(hits[0].point);
        triggerAvatarPokeReaction(zoneKey);
        return;
      }
    }

    if (!vrmEnvironmentGroup) return;
    const walkableFloors = [];
    vrmEnvironmentGroup.traverse(obj => {
      if (obj.isMesh && obj.userData && obj.userData.isWalkableFloor) {
        walkableFloors.push(obj);
      }
    });
    if (!walkableFloors.length) return;
    const floorHits = raycaster.intersectObjects(walkableFloors, false);
    if (floorHits.length > 0) {
      const hit = floorHits[0];
      const isBalcony = !!(hit.object.userData && hit.object.userData.isBalconyFloor);
      walkRumToPoint(hit.point.x, hit.point.z, {
        isBalcony,
        name: isBalcony ? 'Outdoor Balcony' : 'Room Floor',
        faceOcean: isBalcony
      });
    }
  });
}

const DEFAULT_TOUCH_INTERACTIONS = {
  head_top: {
    emotion: 'HAPPY',
    hud_label: '😊 HAPPY • HEADPAT RECEIVED',
    animations: ['greeting', 'pose_shy_wave'],
    duration_ms: 3200,
    lines: ['Ehehe! That feels nice, {driver_address}! Headpats make me so happy!']
  },
  mouth: {
    emotion: 'SURPRISED',
    hud_label: '😛 BOOP! • PLAYFUL GIGGLE',
    animations: ['pose_shy_wave', 'amusement'],
    duration_ms: 3000,
    lines: ['Hey! {driver_address}, did you just boop my face?!']
  },
  shoulders: {
    emotion: 'HAPPY',
    hud_label: '💜 READY • CO-PILOT CHECK',
    animations: ['greeting_wave_right', 'show_body'],
    duration_ms: 3000,
    lines: ['Right beside you, {driver_address}! Let us check those gauges!']
  },
  arms: {
    emotion: 'EXCITED',
    hud_label: '💪 READY • ARM BUDDY',
    animations: ['greeting_wave_right'],
    duration_ms: 3000,
    lines: ['Ready on co-pilot duty, {driver_address}!']
  },
  hands: {
    emotion: 'EXCITED',
    hud_label: '🙌 HIGH FIVE!',
    animations: ['greeting_wave_right', 'peace'],
    duration_ms: 2800,
    lines: ['High five, {driver_address}!']
  },
  stomach: {
    emotion: 'DEVOTED',
    hud_label: '😂 GIGGLING • TICKLE SPOT',
    animations: ['amusement'],
    duration_ms: 3400,
    lines: ['Whoa! That tickles, {driver_address}! Keep both hands on the wheel!']
  },
  legs: {
    emotion: 'EXCITED',
    hud_label: '✨ BOUNCY • READY TO GO',
    animations: ['action_jump'],
    duration_ms: 3000,
    lines: ['Ready to go for a spin, {driver_address}!']
  },
  feet: {
    emotion: 'EXCITED',
    hud_label: '👟 READY FOR HYPERDRIVE',
    animations: ['action_jump'],
    duration_ms: 3000,
    lines: ['One, two! Ready to jump into hyperdrive, {driver_address}!']
  },
  back: {
    emotion: 'SURPRISED',
    hud_label: '👀 PEEKABOO • BEHIND YOU',
    animations: ['pose_side_glance', 'greeting'],
    duration_ms: 3200,
    lines: ['Whoa! {driver_address}, you snuck up behind me!']
  },

  // ===== NEW ZONES Don't Remove or Touch!
  butt: {
    emotion: 'FLIRTY',
    hud_label: '🍑 TOUCHED • PLAYFUL',
    animations: ['pose_shy_wave', 'amusement', 'spin'],
    duration_ms: 3400,
    lines: [
      'Hey… careful back there.',
      'That tickles a little…',
      'You really went for it, huh?',
      'Mmm… bold hands.'
    ]
  },
  groin: {
    emotion: 'FLIRTY',
    hud_label: '🔥 TOUCHED • REACTING',
    animations: ['pose_lean_in', 'amusement'],
    duration_ms: 3600,
    lines: [
      'Whoa… bold move.',
      'That’s a sensitive spot…',
      'You’re getting handsy today.',
      'Easy there…'
    ]
  }
};

const _lastTouchChoiceIdx = {};
let _lastAvatarPokeAt = 0;

function getBoneWorldPos(boneName) {
  const node = (vrmBones && vrmBones[boneName]) || (vrmHumanoidMap && vrmHumanoidMap[boneName]);
  if (!node || typeof node.getWorldPosition !== 'function') return null;
  const v = new THREE.Vector3();
  node.getWorldPosition(v);
  return v;
}

function isHitOnModelBackSide(hitPoint) {
  if (!vrmModel) return false;
  const anchor = getBoneWorldPos('chest') || getBoneWorldPos('spine') || getBoneWorldPos('hips');
  const cx = anchor ? anchor.x : vrmModel.position.x;
  const cz = anchor ? anchor.z : vrmModel.position.z;
  const rotY = vrmModel.rotation.y || 0;
  // In VRM world space: rotY = PI faces +Z (camera), rotY = 0 faces -Z
  const fwdX = -Math.sin(rotY);
  const fwdZ = -Math.cos(rotY);
  const dx = hitPoint.x - cx;
  const dz = hitPoint.z - cz;
  return (dx * fwdX + dz * fwdZ) < -0.025;
}

function detectAvatarTouchZone(hitPoint) {
  if (!vrmModel || !hitPoint) return 'shoulders';
  vrmModel.updateMatrixWorld(true);
  const isBack = isHitOnModelBackSide(hitPoint);

  const boneZonePairs = [
    ['head', 'head'],
    ['neck', 'neck'],
    ['upperChest', 'upperChest'],
    ['chest', 'chest'],
    ['spine', 'spine'],
    ['hips', 'hips'],
    ['leftShoulder', 'shoulders'],
    ['rightShoulder', 'shoulders'],
    ['leftUpperArm', 'arms'],
    ['leftLowerArm', 'arms'],
    ['rightUpperArm', 'arms'],
    ['rightLowerArm', 'arms'],
    ['leftHand', 'hands'],
    ['rightHand', 'hands'],
    ['leftUpperLeg', 'legs'],
    ['leftLowerLeg', 'legs'],
    ['rightUpperLeg', 'legs'],
    ['rightLowerLeg', 'legs'],
    ['leftFoot', 'feet'],
    ['leftToes', 'feet'],
    ['rightFoot', 'feet'],
    ['rightToes', 'feet']
  ];

  let bestBone = null;
  let bestPos = null;
  let bestDist = Infinity;

  for (let i = 0; i < boneZonePairs.length; i++) {
    const bName = boneZonePairs[i][0];
    const bPos = getBoneWorldPos(bName);
    if (!bPos) continue;
    const d = hitPoint.distanceTo(bPos);
    if (d < bestDist) {
      bestDist = d;
      bestBone = boneZonePairs[i][1];
      bestPos = bPos;
    }
  }

  if (bestBone) {
    if (bestBone === 'head') {
      if (hitPoint.y >= bestPos.y + 0.035) return 'head_top';
      return isBack ? 'head_top' : 'mouth';
    }
    if (bestBone === 'neck') {
      if (!isBack && hitPoint.y >= bestPos.y + 0.015) return 'mouth';
      return isBack ? 'back' : 'shoulders';
    }
    if (bestBone === 'upperChest' || bestBone === 'chest') {
      return isBack ? 'back' : 'shoulders';
    }

    // ===== NEW: Don't Touch
    if (bestBone === 'hips') {
      // Back side of hips → butt
      if (isBack) return 'butt';
      // Front side of hips / lower torso → groin
      return 'groin';
    }

    if (bestBone === 'spine') {
      return isBack ? 'back' : 'stomach';
    }

    return bestBone;
  }

  // Fallback using relative height (works even with imperfect bone mapping)
  const box = new THREE.Box3().setFromObject(vrmModel);
  const relY = (hitPoint.y - box.min.y) / Math.max(0.1, box.max.y - box.min.y);

  if (relY >= 0.86) return 'head_top';
  if (relY >= 0.76) return isBack ? 'head_top' : 'mouth';
  if (relY >= 0.56) return isBack ? 'back' : 'shoulders';
  if (relY >= 0.48) return isBack ? 'back' : 'stomach';

  // ===== NEW: Mid-lower body range. Don't Touch!
  if (relY >= 0.28 && relY <= 0.48) {
    return isBack ? 'butt' : 'groin';
  }

  if (relY >= 0.10) return 'legs';
  return 'feet';
}

function getActivePersonaData() {
  const pKey = (typeof currentAiSettings !== 'undefined' && currentAiSettings.personality) ? currentAiSettings.personality : 'RUM';
  const personas = (typeof window !== 'undefined' && window.allPersonas) ? window.allPersonas : null;
  return (personas && personas[pKey]) ? personas[pKey] : null;
}

function isTouchZoneBanned(zoneKey) {
  if (!zoneKey) return false;
  const key = String(zoneKey).toLowerCase().trim();
  const personaData = getActivePersonaData();
  if (!personaData) return false;

  if (Array.isArray(personaData.banned_touch_zones)) {
    const isListed = personaData.banned_touch_zones.some(z => String(z || '').toLowerCase().trim() === key);
    if (isListed) return true;
  }
  if (personaData.touch_interactions && Object.prototype.hasOwnProperty.call(personaData.touch_interactions, key)) {
    const entry = personaData.touch_interactions[key];
    if (entry === null || entry === false || (typeof entry === 'object' && (entry.enabled === false || entry.banned === true))) {
      return true;
    }
  }
  return false;
}

function getPersonaTouchZoneConfig(zoneKey) {
  const personaData = getActivePersonaData();
  const configured = (personaData && personaData.touch_interactions && personaData.touch_interactions[zoneKey])
    ? personaData.touch_interactions[zoneKey]
    : null;
  return configured || DEFAULT_TOUCH_INTERACTIONS[zoneKey] || null;
}

function pickNonRepeatingEntry(cacheKey, list) {
  if (!Array.isArray(list) || list.length === 0) return null;
  if (list.length === 1) return list[0];
  const prevIdx = _lastTouchChoiceIdx[cacheKey];
  let idx = Math.floor(Math.random() * list.length);
  if (idx === prevIdx) {
    idx = (idx + 1 + Math.floor(Math.random() * (list.length - 1))) % list.length;
  }
  _lastTouchChoiceIdx[cacheKey] = idx;
  return list[idx];
}

function formatTouchLineText(templateText) {
  const addr = (typeof getDriverDisplayAddress === 'function') ? getDriverDisplayAddress() : 'Master';
  return String(templateText || '').replace(/\{driver_address\}/g, addr);
}

function triggerAvatarPokeReaction(zoneOrRelY) {
  let zoneKey = zoneOrRelY;
  if (typeof zoneOrRelY === 'number') {
    if (zoneOrRelY >= 0.85) zoneKey = 'head_top';
    else if (zoneOrRelY >= 0.76) zoneKey = 'mouth';
    else if (zoneOrRelY >= 0.52) zoneKey = 'shoulders';
    else if (zoneOrRelY >= 0.28) zoneKey = 'stomach';
    else if (zoneOrRelY >= 0.10) zoneKey = 'legs';
    else zoneKey = 'feet';
  }

  if (isTouchZoneBanned(zoneKey)) {
    return;
  }

  const now = Date.now();
  if (now - _lastAvatarPokeAt < 900) return;
  _lastAvatarPokeAt = now;

  const cfg = getPersonaTouchZoneConfig(zoneKey) || DEFAULT_TOUCH_INTERACTIONS.shoulders;
  const entry = pickNonRepeatingEntry(`line:${zoneKey}`, cfg.lines || []);
  const isObj = entry && typeof entry === 'object';
  const rawText = isObj ? (entry.text || '') : (entry || '');
  const animList = (isObj && entry.animation)
    ? [entry.animation]
    : (Array.isArray(entry && entry.animations) ? entry.animations : (Array.isArray(cfg.animations) ? cfg.animations : (cfg.animation ? [cfg.animation] : [])));
  const chosenAnim = pickNonRepeatingEntry(`anim:${zoneKey}`, animList) || 'greeting';
  const durationMs = Number((isObj && entry.duration_ms) || cfg.duration_ms || 3200);
  const emotion = (isObj && entry.emotion) || cfg.emotion || 'HAPPY';
  const hudLabel = (isObj && entry.hud_label) || cfg.hud_label || '';

  playVrmAction(chosenAnim, durationMs, true);
  setWaifuEmotion(emotion, hudLabel || undefined);
  const spoken = formatTouchLineText(rawText);
  if (spoken) {
    if (typeof showAiSpeechToast === 'function') showAiSpeechToast(spoken);
    speakUtterance(spoken, emotion);
  }
}

window.detectAvatarTouchZone = detectAvatarTouchZone;
window.isTouchZoneBanned = isTouchZoneBanned;
window.triggerAvatarPokeReaction = triggerAvatarPokeReaction;

// --- UNIVERSAL VRM HUMANOID BONE-PARENTED PROPS RIG ---

function createMultimeterProp() {
  if (multimeterPropGroup) return multimeterPropGroup;
  const group = new THREE.Group();
  group.name = "prop_multimeter";
  // Rugged Yellow Protective Holster
  const yellowCaseMat = new THREE.MeshStandardMaterial({
    color: 0xf5b000,
    roughness: 0.45,
    metalness: 0.1
  });
  const yellowCase = new THREE.Mesh(
    new THREE.BoxGeometry(0.065, 0.115, 0.032),
    yellowCaseMat
  );
  group.add(yellowCase);
  // Dark Grey Inner Bezel
  const faceMat = new THREE.MeshStandardMaterial({
    color: 0x222226,
    roughness: 0.6,
    metalness: 0.2
  });
  const faceplate = new THREE.Mesh(
    new THREE.BoxGeometry(0.055, 0.105, 0.005),
    faceMat
  );
  faceplate.position.set(0, 0, 0.016);
  group.add(faceplate);
  // Glowing High-Contrast LCD Screen
  const lcdCanvas = document.createElement('canvas');
  lcdCanvas.width = 128;
  lcdCanvas.height = 64;
  const ctx = lcdCanvas.getContext('2d');
  ctx.fillStyle = '#062024';
  ctx.fillRect(0, 0, 128, 64);
  ctx.fillStyle = '#00f0ff';
  ctx.font = 'bold 24px monospace';
  ctx.fillText('14.2V', 16, 36);
  ctx.font = '12px monospace';
  ctx.fillStyle = '#00a8b5';
  ctx.fillText('DC AUTO', 16, 54);
  const lcdTex = new THREE.CanvasTexture(lcdCanvas);
  const lcdMat = new THREE.MeshStandardMaterial({
    map: lcdTex,
    emissive: 0x00d0e0,
    emissiveMap: lcdTex,
    emissiveIntensity: 0.75,
    roughness: 0.2
  });
  const lcdScreen = new THREE.Mesh(
    new THREE.PlaneGeometry(0.045, 0.026),
    lcdMat
  );
  lcdScreen.position.set(0, 0.032, 0.019);
  group.add(lcdScreen);
  // Rotary Selector Dial
  const dialMat = new THREE.MeshStandardMaterial({
    color: 0x111113,
    roughness: 0.3,
    metalness: 0.4
  });
  const dial = new THREE.Mesh(
    new THREE.CylinderGeometry(0.012, 0.012, 0.006, 16),
    dialMat
  );
  dial.rotation.x = Math.PI / 2;
  dial.position.set(0, -0.006, 0.019);
  group.add(dial);
  // Red & Black Test Probes
  const redMat = new THREE.MeshStandardMaterial({ color: 0xdd2222, roughness: 0.3 });
  const blackMat = new THREE.MeshStandardMaterial({ color: 0x181818, roughness: 0.3 });
  const chromeMat = new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.9, roughness: 0.1 });
  // Red probe lead
  const redProbe = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.055, 12), redMat);
  redProbe.rotation.x = Math.PI / 2;
  redProbe.position.set(0.015, -0.050, 0.035);
  const redTip = new THREE.Mesh(new THREE.ConeGeometry(0.002, 0.015, 8), chromeMat);
  redTip.rotation.x = -Math.PI / 2;
  redTip.position.set(0, 0.035, 0);
  redProbe.add(redTip);
  group.add(redProbe);
  // Black probe lead
  const blackProbe = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.055, 12), blackMat);
  blackProbe.rotation.x = Math.PI / 2;
  blackProbe.position.set(-0.015, -0.050, 0.035);
  const blackTip = new THREE.Mesh(new THREE.ConeGeometry(0.002, 0.015, 8), chromeMat);
  blackTip.rotation.x = -Math.PI / 2;
  blackTip.position.set(0, 0.035, 0);
  blackProbe.add(blackTip);
  group.add(blackProbe);
  group.scale.set(1.0, 1.0, 1.0);
  multimeterPropGroup = group;
  return group;
}

function createPipDropperProp() {
  if (pipDropperPropGroup) return pipDropperPropGroup;
  const group = new THREE.Group();
  group.name = "prop_pip_dropper";
  // Clear Glass Pipette Barrel
  const glassMat = new THREE.MeshStandardMaterial({
    color: 0xddf0ff,
    transparent: true,
    opacity: 0.55,
    roughness: 0.1,
    metalness: 0.1
  });
  const barrel = new THREE.Mesh(
    new THREE.CylinderGeometry(0.006, 0.0025, 0.09, 16),
    glassMat
  );
  barrel.position.set(0, 0, 0);
  group.add(barrel);
  // Amber Sugar Water Column inside
  const nectarMat = new THREE.MeshStandardMaterial({
    color: 0xffaa00,
    emissive: 0xff8800,
    emissiveIntensity: 0.35,
    transparent: true,
    opacity: 0.85,
    roughness: 0.2
  });
  const nectarColumn = new THREE.Mesh(
    new THREE.CylinderGeometry(0.004, 0.0018, 0.055, 12),
    nectarMat
  );
  nectarColumn.position.set(0, -0.012, 0);
  group.add(nectarColumn);
  // Rubber Squeeze Bulb at Top
  const bulbMat = new THREE.MeshStandardMaterial({
    color: 0xcc2929,
    roughness: 0.55,
    metalness: 0.05
  });
  const bulb = new THREE.Mesh(
    new THREE.SphereGeometry(0.012, 16, 16),
    bulbMat
  );
  bulb.scale.set(1.0, 1.35, 1.0);
  bulb.position.set(0, 0.052, 0);
  group.add(bulb);
  // Warm Amber Sugar Water Droplet at Tip
  const dropMat = new THREE.MeshStandardMaterial({
    color: 0xffbb22,
    emissive: 0xffaa00,
    emissiveIntensity: 0.65,
    roughness: 0.1
  });
  const droplet = new THREE.Mesh(
    new THREE.SphereGeometry(0.003, 12, 12),
    dropMat
  );
  droplet.position.set(0, -0.048, 0);
  group.add(droplet);
  group.scale.set(1.0, 1.0, 1.0);
  pipDropperPropGroup = group;
  return group;
}

function attachMultimeterToRum() {
  if (isHoldingMultimeter) return;
  detachPipDropperFromRum();
  const meter = createMultimeterProp();
  if (attachPropToVrmHand(meter, 'rightHand')) {
    meter.position.set(0.02, -0.035, 0.065);
    meter.rotation.set(0.4, 0.2, -0.1);
    isHoldingMultimeter = true;
  }
}

function detachMultimeterFromRum() {
  if (!isHoldingMultimeter || !multimeterPropGroup) return;
  detachPropFromVrmHand(multimeterPropGroup);
  if (multimeterPropGroup.parent) multimeterPropGroup.parent.remove(multimeterPropGroup);
  isHoldingMultimeter = false;
}

function attachPipDropperToRum() {
  if (isHoldingDropper) return;
  detachMultimeterFromRum();
  const dropper = createPipDropperProp();
  if (attachPropToVrmHand(dropper, 'rightHand')) {
    dropper.position.set(0.015, -0.04, 0.075);
    dropper.rotation.set(0.85, 0.1, 0.0);
    isHoldingDropper = true;
  }
}

function detachPipDropperFromRum() {
  if (!isHoldingDropper || !pipDropperPropGroup) return;
  detachPropFromVrmHand(pipDropperPropGroup);
  if (pipDropperPropGroup.parent) pipDropperPropGroup.parent.remove(pipDropperPropGroup);
  isHoldingDropper = false;
}

function attachPropToVrmHand(propObject, boneName = 'rightHand') {
  if (!propObject) return false;
  const bone = (vrmBones && vrmBones[boneName]) || (vrmHumanoidMap && vrmHumanoidMap[boneName]);
  if (bone) {
    bone.add(propObject);
    propObject.position.set(0.0, -0.05, 0.08);
    propObject.rotation.set(0, 0, 0);
    return true;
  }
  return false;
}

function detachPropFromVrmHand(propObject) {
  if (!propObject) return;
  const worldPos = new THREE.Vector3();
  const worldQuat = new THREE.Quaternion();
  propObject.getWorldPosition(worldPos);
  propObject.getWorldQuaternion(worldQuat);
  vrmScene.add(propObject);
  propObject.position.copy(worldPos);
  propObject.quaternion.copy(worldQuat);
}

function triggerYoshiPlushInteraction() {
  if (!yoshiModel) return;
  isHoldingYoshi = !isHoldingYoshi;
  if (isHoldingYoshi) {
    playVrmAction('pose_v_sign', 4000);
    setWaifuEmotion('HAPPY', '🦖 YOSHI TIME! • BEST FRIENDS');
    speakUtterance('Yay! Master, look at my Yoshi plushie! He loves riding shotgun in the car too!');
    attachPropToVrmHand(yoshiModel, 'rightHand');
  } else {
    detachPropFromVrmHand(yoshiModel);
    playVrmAction('greeting', 3000);
    setWaifuEmotion('DEVOTED', '🦖 YOSHI RESTING');
    speakUtterance('Okay! Let us put Yoshi right here so he can watch the road with us!');
    updateYoshiEnvironmentRest();
  }
}

// ============================================================================

// --- 3D INTERACTIVE BASKETBALL WITH REAL GRAVITY & BOUNCE PHYSICS ---
// g = -9.8 m/s^2, restitution = 0.78, harmonic hand dribbling, arc shot/toss

// ============================================================================
let basketballMesh = null;
let basketballState = 'REST'; // 'REST', 'DRIBBLING', 'TOSS'
let basketballPos = new THREE.Vector3(0.48, vrmBaseY + 0.12, 0.22);
let basketballVel = new THREE.Vector3(0, 0, 0);
let basketballDribbleTimer = 0;
const BASKETBALL_RADIUS = 0.12;
const BASKETBALL_RESTITUTION = 0.78;
const BASKETBALL_GRAVITY = -9.8;

function createBasketballTexture() {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext('2d');
  // Base basketball warm orange leather
  ctx.fillStyle = '#d35400';
  ctx.fillRect(0, 0, 512, 256);
  // Leather pebbled grain dots
  ctx.fillStyle = 'rgba(0, 0, 0, 0.12)';
  for (let x = 0; x < 512; x += 4) {
    for (let y = 0; y < 256; y += 4) {
      if ((x + y) % 8 === 0) {
        ctx.fillRect(x + (Math.random() * 2), y + (Math.random() * 2), 1.5, 1.5);
      }
    }
  }
  // Black molded rubber seams
  ctx.strokeStyle = '#111111';
  ctx.lineWidth = 6;
  ctx.lineCap = 'round';
  // Equator horizontal seam
  ctx.beginPath();
  ctx.moveTo(0, 128);
  ctx.lineTo(512, 128);
  ctx.stroke();
  // Vertical meridians
  ctx.beginPath();
  ctx.moveTo(128, 0);
  ctx.lineTo(128, 256);
  ctx.moveTo(256, 0);
  ctx.lineTo(256, 256);
  ctx.moveTo(384, 0);
  ctx.lineTo(384, 256);
  ctx.stroke();
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function createBasketballProp() {
  if (basketballMesh) return;
  const group = new THREE.Group();
  const ballTex = createBasketballTexture();
  const ballMat = new THREE.MeshStandardMaterial({
    map: ballTex,
    roughness: 0.62,
    metalness: 0.05
  });
  const sphere = new THREE.Mesh(new THREE.SphereGeometry(BASKETBALL_RADIUS, 32, 32), ballMat);
  sphere.castShadow = true;
  group.add(sphere);
  // Black 3D rib rings for tactile visual depth
  const seamMat = new THREE.MeshBasicMaterial({ color: 0x111111 });
  const seam1 = new THREE.Mesh(new THREE.TorusGeometry(BASKETBALL_RADIUS + 0.001, 0.003, 8, 32), seamMat);
  const seam2 = new THREE.Mesh(new THREE.TorusGeometry(BASKETBALL_RADIUS + 0.001, 0.003, 8, 32), seamMat);
  seam2.rotation.x = Math.PI / 2;
  const seam3 = new THREE.Mesh(new THREE.TorusGeometry(BASKETBALL_RADIUS + 0.001, 0.003, 8, 32), seamMat);
  seam3.rotation.y = Math.PI / 2;
  group.add(seam1);
  group.add(seam2);
  group.add(seam3);
  group.position.set(0.48, vrmBaseY + BASKETBALL_RADIUS, 0.22);
  basketballMesh = group;
  if (vrmScene) vrmScene.add(basketballMesh);
}

function triggerBasketballDribbleAction() {
  if (!basketballMesh) createBasketballProp();
  if (basketballState === 'REST') {
    basketballState = 'DRIBBLING';
    basketballDribbleTimer = 0;
    playVrmAction('pose_v_sign', 4000);
    setWaifuEmotion('HAPPY', '🏀 DRIBBLING • CROSSOVER');
    speakUtterance('Check this out, Master! Smooth hardwood crossover bounce!');
  } else if (basketballState === 'DRIBBLING') {
    // Transition to high arc shot / toss!
    basketballState = 'TOSS';
    basketballVel.set(0.25, 3.4, -0.6);
    playVrmAction('wave', 3500);
    setWaifuEmotion('EXCITED', '🏀 THREE POINTER! SWOOSH');
    speakUtterance('From three-point range! Swoosh! High arc shot!');
  } else {
    // Catch / Reset
    basketballState = 'REST';
    basketballVel.set(0, 0, 0);
    basketballMesh.position.set(0.48, vrmBaseY + BASKETBALL_RADIUS, 0.22);
    setWaifuEmotion('DEVOTED', '🏀 BALL AT REST');
  }
}

function triggerBasketballInteraction() {
  triggerBasketballDribbleAction();
}

function updateBasketballPhysics(delta) {
  if (!basketballMesh) return;
  const floorY = vrmBaseY + BASKETBALL_RADIUS;
  if (basketballState === 'DRIBBLING') {
    basketballDribbleTimer += delta * 11.0;
    const phase = basketballDribbleTimer % Math.PI;
    const bounceHeight = Math.sin(phase) * 0.58;
    // Universal Humanoid Hand Tracking: Bind basketball dribble to rightHand bone world coordinates
    const rightHand = (vrmBones && vrmBones.rightHand) || (vrmHumanoidMap && vrmHumanoidMap.rightHand);
    let targetX = vrmRoamCurrentPos.x + 0.36;
    let targetZ = vrmRoamCurrentPos.z + 0.26;
    if (rightHand && typeof rightHand.getWorldPosition === 'function') {
      const handWorldPos = new THREE.Vector3();
      rightHand.getWorldPosition(handWorldPos);
      if (Math.hypot(handWorldPos.x - vrmRoamCurrentPos.x, handWorldPos.z - vrmRoamCurrentPos.z) < 1.2) {
        targetX = handWorldPos.x;
        targetZ = handWorldPos.z + 0.06;
      }
      if (bounceHeight > 0.45) {
        // Hand hovers and guides downward
        rightHand.rotation.x = -0.3;
        rightHand.rotation.z = 0.2;
      }
    }
    basketballMesh.position.x = targetX;
    basketballMesh.position.z = targetZ;
    basketballMesh.position.y = floorY + bounceHeight;
    basketballMesh.rotation.x += delta * 7.5;
  } else if (basketballState === 'TOSS') {
    // Real Gravity Integration
    basketballVel.y += BASKETBALL_GRAVITY * delta;
    basketballMesh.position.x += basketballVel.x * delta;
    basketballMesh.position.y += basketballVel.y * delta;
    basketballMesh.position.z += basketballVel.z * delta;
    // Rotational spin
    basketballMesh.rotation.x += delta * 6.5;
    basketballMesh.rotation.y += delta * 2.8;
    // Wall Bounces (X between -3.8 and 3.8, Z between -3.2 and 3.2)
    if (basketballMesh.position.x < -3.8) {
      basketballMesh.position.x = -3.8;
      basketballVel.x = -basketballVel.x * 0.72;
    } else if (basketballMesh.position.x > 3.8) {
      basketballMesh.position.x = 3.8;
      basketballVel.x = -basketballVel.x * 0.72;
    }
    if (basketballMesh.position.z < -3.2) {
      basketballMesh.position.z = -3.2;
      basketballVel.z = -basketballVel.z * 0.72;
    } else if (basketballMesh.position.z > 3.2) {
      basketballMesh.position.z = 3.2;
      basketballVel.z = -basketballVel.z * 0.72;
    }
    // Floor Impact & Restitution Bounce
    if (basketballMesh.position.y <= floorY) {
      basketballMesh.position.y = floorY;
      basketballVel.y = -basketballVel.y * BASKETBALL_RESTITUTION;
      basketballVel.x *= 0.86;
      basketballVel.z *= 0.86;
      // When bounce energy dissipates, settle into restful state
      if (Math.abs(basketballVel.y) < 0.16) {
        basketballVel.set(0, 0, 0);
        basketballState = 'REST';
      }
    }
  } else {
    // REST state: firmly anchored to hardwood floor
    basketballMesh.position.y = floorY;
  }
}

function minimizeFloatingCompanion() {

  window.isCompanionMinimizedByUser = true;

  const hud = document.getElementById('vrmFloatingHud');

  const mini = document.getElementById('vrmMiniBubble');

  if (!hud) return;

  if (mini) {

    if (hud.style.left && hud.style.top && hud.style.left !== 'auto') {

      mini.style.left = Math.max(10, Math.min(window.innerWidth - 180, parseInt(hud.style.left, 10) + 40)) + 'px';

      mini.style.top = Math.max(10, Math.min(window.innerHeight - 60, parseInt(hud.style.top, 10) + 270)) + 'px';

      mini.style.bottom = 'auto';

      mini.style.right = 'auto';

    } else {

      mini.style.bottom = '24px';

      mini.style.right = '24px';

      mini.style.left = 'auto';

      mini.style.top = 'auto';

    }

    mini.style.display = 'flex';

  }

  hud.style.display = 'none';

  const pill = document.getElementById('rumMinHudPill');

  if (pill) {

    pill.classList.add('glow-pulse');

    setTimeout(() => pill.classList.remove('glow-pulse'), 1500);

  }

}

function expandFloatingCompanion() {

  window.isCompanionMinimizedByUser = false;

  const hud = document.getElementById('vrmFloatingHud');

  const mini = document.getElementById('vrmMiniBubble');

  if (mini) mini.style.display = 'none';

  if (!hud) return;

  if (mini && mini.style.left && mini.style.top && mini.style.left !== 'auto') {

    const leftVal = Math.max(10, Math.min(window.innerWidth - 260, parseInt(mini.style.left, 10) - 40));

    const topVal = Math.max(10, Math.min(window.innerHeight - 340, parseInt(mini.style.top, 10) - 270));

    hud.style.left = leftVal + 'px';

    hud.style.top = topVal + 'px';

    hud.style.bottom = 'auto';

    hud.style.right = 'auto';

  } else {

    hud.style.bottom = '60px';

    hud.style.right = '20px';

    hud.style.left = 'auto';

    hud.style.top = 'auto';

  }

  popOutFloatingCompanion(true);

}

function floatCompanionShotgun(isAuto = false) {

  popOutFloatingCompanion(isAuto);

}

function dismissFloatingHud() {

  isShotgunAutoPopped = false;

  window.isCompanionMinimizedByUser = false;

  const mini = document.getElementById('vrmMiniBubble');

  if (mini) mini.style.display = 'none';

  dockCompanionToAi();

}

function toggleRumHudFromPill() {

  const hud = document.getElementById('vrmFloatingHud');

  const mini = document.getElementById('vrmMiniBubble');

  const isHudShowing = (hud && hud.style.display !== 'none');

  const isMiniShowing = (mini && mini.style.display !== 'none');

  if (!isHudShowing && !isMiniShowing) {

    if (currentScreen === 'ai') {

      navigateTo('home');

    }

    popOutFloatingCompanion();

  } else if (isHudShowing) {

    minimizeFloatingCompanion();

  } else {

    expandFloatingCompanion();

  }

}

function toggleAiChatMinimize() {
  const container = document.getElementById('screenAI');
  const pill = document.getElementById('btnRestoreChatPill');
  if (!container) return;
  const isClosed = container.classList.contains('chat-closed');
  if (isClosed) {
    // Restore chat panel
    container.classList.remove('chat-closed');
    if (pill) pill.style.display = 'none';
    setAiLayoutMode('SPLIT');
    if (typeof vrmFramingMode !== 'undefined') vrmFramingMode = 'FULL_BODY';
  } else {
    // Minimize chat to view full 3D room
    container.classList.add('chat-closed');
    if (pill) pill.style.display = 'inline-flex';
    setAiLayoutMode('ROOM');
    if (typeof vrmFramingMode !== 'undefined') vrmFramingMode = 'ROOM';
  }
  if (typeof snapCameraToCurrentFraming === 'function') snapCameraToCurrentFraming();
  if (typeof resizeVrmToStage === 'function') resizeVrmToStage();
}

window.toggleAiChatMinimize = toggleAiChatMinimize;

// --- DYNAMIC CAMERA OCCLUSION FADING (RAYCAST WALL DITHERING) ---
const _occRaycaster = new THREE.Raycaster();
let _occFadeCandidateMeshes = [];
let _occLastScanTime = 0;

function updateCameraOcclusionFading() {
  if (!vrmCamera || !currentVrm || !currentVrm.scene || !vrmEnvironmentGroup) return;
  const now = Date.now();
  if (now - _occLastScanTime > 1500) {
    _occLastScanTime = now;
    _occFadeCandidateMeshes = [];
    vrmEnvironmentGroup.traverse(child => {
      if (child.isMesh && child.userData && child.userData.isFadableWall) {
        _occFadeCandidateMeshes.push(child);
      }
    });
  }
  if (!_occFadeCandidateMeshes.length) return;
  const targetPos = new THREE.Vector3();
  if (currentVrm.humanoid && currentVrm.humanoid.getNormalizedBoneNode('chest')) {
    currentVrm.humanoid.getNormalizedBoneNode('chest').getWorldPosition(targetPos);
  } else {
    currentVrm.scene.getWorldPosition(targetPos);
    targetPos.y += 0.85;
  }
  const camPos = vrmCamera.position;
  const dir = new THREE.Vector3().subVectors(targetPos, camPos);
  const dist = dir.length();
  if (dist < 0.2) return;
  dir.normalize();
  _occRaycaster.set(camPos, dir);
  _occRaycaster.far = Math.max(0.1, dist - 0.20);
  const hits = _occRaycaster.intersectObjects(_occFadeCandidateMeshes, false);
  const hitSet = new Set(hits.map(h => h.object));
  // Fade hit walls smoothly to 0.22 opacity
  for (let i = 0; i < _occFadeCandidateMeshes.length; i++) {
    const mesh = _occFadeCandidateMeshes[i];
    if (!mesh.material) continue;
    if (!mesh.userData.origMatSetup) {
      mesh.userData.origMatSetup = true;
      mesh.userData.origOpacity = mesh.material.opacity !== undefined ? mesh.material.opacity : 1.0;
      mesh.userData.origTransparent = mesh.material.transparent || false;
    }
    if (hitSet.has(mesh)) {
      mesh.material.transparent = true;
      mesh.material.opacity = THREE.MathUtils.lerp(mesh.material.opacity, 0.22, 0.18);
    } else if (mesh.material.opacity < 0.98) {
      mesh.material.opacity = THREE.MathUtils.lerp(mesh.material.opacity, 1.0, 0.18);
      if (mesh.material.opacity >= 0.98) {
        mesh.material.opacity = 1.0;
        mesh.material.transparent = mesh.userData.origTransparent;
      }
    }
  }
}
