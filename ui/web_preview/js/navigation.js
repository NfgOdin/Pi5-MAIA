// ============================================================================
// PHASE 11: OFFLINE TURN-BY-TURN ROUTE NAVIGATION & SPEED LIMIT HUD ENGINE
// ============================================================================
let isNavigatingActive = false;
let activeRoutePolyline = null;
let activeDestMarker = null;

const NAV_BOOKMARKS = {
  dest_home: { name: 'Home', lat: 33.3942, lon: -110.7865 },
  dest_gas: { name: 'Chevron Gas Station', lat: 33.4025, lon: -110.8150 },
  dest_food: { name: 'Safeway & Deli', lat: 33.4010, lon: -110.7920 },
  dest_pass: { name: 'Pinal Mountain Pass', lat: 33.2850, lon: -110.8800 },
  dest_lake: { name: 'Roosevelt Lake Marina', lat: 33.6600, lon: -111.1200 }
};

function routeToBookmark(bookmarkId) {
  const b = NAV_BOOKMARKS[bookmarkId];
  if (!b) return;
  calculateAndRenderRoute(b.lat, b.lon, b.name);
}

function submitStartRoute() {
  const input = document.getElementById('navDestinationInput');
  const query = input ? input.value.trim().toLowerCase() : '';
  if (!query) return;

  let matched = null;
  for (const k in NAV_BOOKMARKS) {
    if (NAV_BOOKMARKS[k].name.toLowerCase().includes(query) || query.includes(k.replace('dest_', ''))) {
      matched = NAV_BOOKMARKS[k];
      break;
    }
  }

  if (matched) {
    calculateAndRenderRoute(matched.lat, matched.lon, matched.name);
  } else {
    const baseLat = (currentGpsData && currentGpsData.lat) || 33.3942;
    const baseLon = (currentGpsData && currentGpsData.lon) || -110.7865;
    calculateAndRenderRoute(baseLat + 0.032, baseLon - 0.028, input.value.trim());
  }
}

function calculateAndRenderRoute(destLat, destLon, destName) {
  const startLat = (currentGpsData && currentGpsData.lat) || 33.3942;
  const startLon = (currentGpsData && currentGpsData.lon) || -110.7865;

  fetch('/api/nav/route', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      start_lat: startLat,
      start_lon: startLon,
      dest_lat: destLat,
      dest_lon: destLon,
      dest_name: destName
    })
  })
    .then(r => r.json())
    .then(d => {
      const nav = d.route || {};
      renderActiveRoute(nav, destLat, destLon, destName);
    })
    .catch(e => console.error('[NAV] Route calculation error:', e));
}

function renderActiveRoute(nav, destLat, destLon, destName) {
  isNavigatingActive = true;

  if (activeRoutePolyline && leafletMap) {
    leafletMap.removeLayer(activeRoutePolyline);
    activeRoutePolyline = null;
  }
  if (activeDestMarker && leafletMap) {
    leafletMap.removeLayer(activeDestMarker);
    activeDestMarker = null;
  }

  const polylineCoords = nav.polyline || [];
  if (polylineCoords.length > 0 && leafletMap && typeof L !== 'undefined') {
    activeRoutePolyline = L.polyline(polylineCoords, {
      color: '#00f0ff',
      weight: 6,
      opacity: 0.85,
      lineJoin: 'round'
    }).addTo(leafletMap);

    const destIcon = L.divIcon({
      className: 'dest-flag-marker',
      html: '<div style="font-size:26px; text-shadow:0 0 10px #000;">🏁</div>',
      iconSize: [30, 30],
      iconAnchor: [15, 25]
    });
    activeDestMarker = L.marker([destLat, destLon], { icon: destIcon }).addTo(leafletMap);

    leafletMap.fitBounds(activeRoutePolyline.getBounds(), { padding: [60, 60] });
  }

  const hud = document.getElementById('navTurnByTurnHud');
  if (hud) hud.style.display = 'block';

  updateTurnByTurnHud(nav, destName);
}

function updateTurnByTurnHud(nav, destName) {
  const m = nav.current_maneuver;
  const iconEl = document.getElementById('navManeuverIcon');
  const distEl = document.getElementById('navManeuverDistance');
  const streetEl = document.getElementById('navNextStreet');
  const instrEl = document.getElementById('navManeuverInstruction');
  const destNameEl = document.getElementById('navDestNameText');
  const remDistEl = document.getElementById('navRemainingDistMiles');
  const etaEl = document.getElementById('navEtaMinutes');
  const speedLimitEl = document.getElementById('navSpeedLimitNum');

  if (m) {
    if (distEl) {
      const ft = nav.distance_to_next_turn_ft || m.distance_ft || 500;
      distEl.innerText = ft >= 5280 ? `${(ft / 5280).toFixed(1)} MI` : `${ft} FT`;
    }
    if (streetEl) streetEl.innerText = m.street || nav.current_road || 'Main Road';
    if (instrEl) instrEl.innerText = m.instruction || 'Continue straight';

    if (iconEl) {
      const type = (m.type || '').toLowerCase();
      if (type.includes('left')) iconEl.innerText = '↰';
      else if (type.includes('right')) iconEl.innerText = '↱';
      else if (type.includes('arrive')) iconEl.innerText = '🏁';
      else iconEl.innerText = '⬆';
    }
  }

  if (destNameEl) destNameEl.innerText = destName || nav.destination_name || 'Destination';
  if (remDistEl) remDistEl.innerText = nav.remaining_distance_miles || '1.0';
  if (etaEl) etaEl.innerText = nav.estimated_minutes || '2';
  if (speedLimitEl) speedLimitEl.innerText = nav.speed_limit_mph || 45;
}

function updateNavigationProgress(lat, lon, speed) {
  fetch('/api/nav/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon, speed })
  })
    .then(r => r.json())
    .then(d => {
      const update = d.update;
      if (!update) return;
      if (!update.is_navigating) {
        if (update.arrived) {
          showAiSpeechToast(`Arrived at ${update.destination || 'destination'}!`);
        }
        stopActiveRoute();
        return;
      }
      updateTurnByTurnHud(update, update.destination_name);
    })
    .catch(e => console.error('[NAV] Progress update error:', e));
}

function stopActiveRoute() {
  isNavigatingActive = false;
  fetch('/api/nav/stop', { method: 'POST' }).catch(() => {});

  if (activeRoutePolyline && leafletMap) {
    leafletMap.removeLayer(activeRoutePolyline);
    activeRoutePolyline = null;
  }
  if (activeDestMarker && leafletMap) {
    leafletMap.removeLayer(activeDestMarker);
    activeDestMarker = null;
  }

  const hud = document.getElementById('navTurnByTurnHud');
  if (hud) hud.style.display = 'none';

  const input = document.getElementById('navDestinationInput');
  if (input) input.value = '';
}
