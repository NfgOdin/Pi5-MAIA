// ============================================================================
// PHASE 18: CANYON RUN LAP TIMER & BRAKE/TIRE THERMAL DEGRADATION STUDIO
// ============================================================================
let activeCanyonTrackId = 'pinal_pass';

function updateCanyonAndThermalUI(thermal, lap_timer) {
  if (thermal && thermal.tires) {
    const tTemps = thermal.tires.temperatures_f || {};
    const tGrip = thermal.tires.grip_pct || {};

    ['FL', 'FR', 'RL', 'RR'].forEach(c => {
      const tempEl = document.getElementById(`tireTemp${c}`);
      const gripEl = document.getElementById(`tireGrip${c}`);
      const boxEl = document.getElementById(`tireBox${c}`);
      if (tempEl && tTemps[c] !== undefined) {
        tempEl.innerText = `${Math.round(tTemps[c])}°F`;
        if (tTemps[c] > 200) {
          tempEl.style.color = '#ff3344';
          if (boxEl) boxEl.style.borderColor = '#ff3344';
        } else if (tTemps[c] >= 155) {
          tempEl.style.color = '#00e676';
          if (boxEl) boxEl.style.borderColor = '#00e676';
        } else {
          tempEl.style.color = '#38bdf8';
          if (boxEl) boxEl.style.borderColor = '#223244';
        }
      }
      if (gripEl && tGrip[c] !== undefined) {
        gripEl.innerText = `${Math.round(tGrip[c])}% Grip`;
      }
    });

    const overallEl = document.getElementById('canyonOverallGrip');
    if (overallEl && thermal.tires.overall_grip_pct !== undefined) {
      overallEl.innerText = `${Math.round(thermal.tires.overall_grip_pct)}% GRIP`;
    }
  }

  if (thermal && thermal.brakes) {
    const fRotorEl = document.getElementById('canyonFrontRotorTemp');
    const rRotorEl = document.getElementById('canyonRearRotorTemp');
    const fadeValEl = document.getElementById('canyonPadFadeVal');
    const fadeBarEl = document.getElementById('canyonPadFadeBar');
    const statusBadge = document.getElementById('canyonThermalStatusBadge');

    if (fRotorEl && thermal.brakes.front_rotor_temp_f !== undefined) {
      fRotorEl.innerText = `${Math.round(thermal.brakes.front_rotor_temp_f)}°F`;
      fRotorEl.style.color = thermal.brakes.front_rotor_temp_f > 600
        ? '#ff3344'
        : (thermal.brakes.front_rotor_temp_f > 400 ? '#ffab00' : '#00e676');
    }
    if (rRotorEl && thermal.brakes.rear_rotor_temp_f !== undefined) {
      rRotorEl.innerText = `${Math.round(thermal.brakes.rear_rotor_temp_f)}°F`;
    }
    if (fadeValEl && thermal.brakes.pad_fade_pct !== undefined) {
      const pct = Math.round(thermal.brakes.pad_fade_pct);
      fadeValEl.innerText = `${pct}% Fade`;
      if (fadeBarEl) fadeBarEl.style.width = `${pct}%`;
    }
    if (statusBadge && thermal.brakes.status) {
      statusBadge.innerText = thermal.brakes.status;
      if (thermal.brakes.status === 'DANGER') {
        statusBadge.style.color = '#ff3344';
        statusBadge.style.borderColor = '#ff3344';
        statusBadge.style.background = 'rgba(255,51,68,0.2)';
      } else if (thermal.brakes.status === 'CAUTION') {
        statusBadge.style.color = '#ffab00';
        statusBadge.style.borderColor = '#ffab00';
        statusBadge.style.background = 'rgba(255,171,0,0.2)';
      } else {
        statusBadge.style.color = '#00e676';
        statusBadge.style.borderColor = '#00e676';
        statusBadge.style.background = 'rgba(0,230,118,0.15)';
      }
    }
  }

  if (lap_timer) {
    const curTimeEl = document.getElementById('canyonCurrentLapTime');
    const bestTimeEl = document.getElementById('canyonBestLapTime');
    const distBadge = document.getElementById('canyonTrackDistanceBadge');
    const calloutEl = document.getElementById('canyonRumCallout');

    if (curTimeEl && lap_timer.formatted_current) curTimeEl.innerText = lap_timer.formatted_current;
    if (bestTimeEl && lap_timer.formatted_best) bestTimeEl.innerText = lap_timer.formatted_best;
    if (distBadge && lap_timer.distance_miles) {
      distBadge.innerText = `${lap_timer.distance_miles} MILES • ${lap_timer.total_sectors} SECTORS`;
    }

    const splits = lap_timer.sector_splits || [];
    const deltas = lap_timer.sector_deltas || [];
    const topSpds = lap_timer.sector_top_speeds || [];
    const maxGs = lap_timer.sector_max_lat_g || [];

    for (let i = 1; i <= 3; i++) {
      const splitEl = document.getElementById(`canyonSplitS${i}`);
      const deltaEl = document.getElementById(`canyonDeltaS${i}`);
      const spdEl = document.getElementById(`canyonTopSpeedS${i}`);
      const gEl = document.getElementById(`canyonMaxGS${i}`);

      if (splitEl && splits[i - 1] !== undefined) {
        const s = splits[i - 1];
        const m = Math.floor(s / 60);
        const remS = s % 60;
        splitEl.innerText = `${m.toString().padStart(2, '0')}:${remS.toFixed(2).padStart(5, '0')}`;
      }
      if (deltaEl && deltas[i - 1] !== undefined) {
        const d = deltas[i - 1];
        if (d === 0) {
          deltaEl.innerText = 'PAR';
          deltaEl.style.color = '#64748b';
        } else if (d < 0) {
          deltaEl.innerText = `${d.toFixed(2)}s`;
          deltaEl.style.color = '#00e676';
        } else {
          deltaEl.innerText = `+${d.toFixed(2)}s`;
          deltaEl.style.color = '#ff3344';
        }
      }
      if (spdEl && topSpds[i - 1] !== undefined) spdEl.innerText = Math.round(topSpds[i - 1]);
      if (gEl && maxGs[i - 1] !== undefined) gEl.innerText = maxGs[i - 1].toFixed(2);
    }

    if (calloutEl) {
      if (lap_timer.state === 'RUNNING') {
        calloutEl.innerText = `R.U.M.: Active in Sector ${lap_timer.current_sector} of ${lap_timer.total_sectors}! Keep your apex smooth, Dad!`;
      } else if (lap_timer.state === 'FINISHED') {
        calloutEl.innerText = `R.U.M.: Checkered flag on ${lap_timer.track_name}! Great run, Dad!`;
      }
    }
  }
}

function armCanyonTimer() {
  fetch('/api/telemetry/lap_timer/arm', { method: 'POST' })
    .then(r => r.json())
    .then(() => showAiSpeechToast('Canyon Lap Timer Armed! Staged for start gate.'));
}

function stopCanyonTimer() {
  fetch('/api/telemetry/lap_timer/stop', { method: 'POST' })
    .then(r => r.json())
    .then(() => showAiSpeechToast('Canyon Lap Timer Stopped.'));
}

function resetCanyonTimer() {
  fetch('/api/telemetry/lap_timer/reset', { method: 'POST' })
    .then(r => r.json())
    .then(() => {
      showAiSpeechToast('Lap timer reset.');
      const curTimeEl = document.getElementById('canyonCurrentLapTime');
      if (curTimeEl) curTimeEl.innerText = '00:00.00';
    });
}

function changeCanyonTrack(trackId) {
  activeCanyonTrackId = trackId;
  fetch('/api/telemetry/lap_timer/select', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ track_id: trackId })
  })
    .then(r => r.json())
    .then(() => showAiSpeechToast(`Selected Route: ${trackId}`));
}
