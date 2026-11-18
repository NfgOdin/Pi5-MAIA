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
  const rawQuery = input ? input.value.trim() : '';
  const query = rawQuery.toLowerCase();
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
    return;
  }

  const baseLat = (currentGpsData && currentGpsData.lat) || 33.3942;
  const baseLon = (currentGpsData && currentGpsData.lon) || -110.7865;
  fetch(`/api/nav/search?q=${encodeURIComponent(rawQuery)}&lat=${encodeURIComponent(baseLat)}&lon=${encodeURIComponent(baseLon)}`)
    .then(r => r.json())
    .then(data => {
      const results = (data && Array.isArray(data.results)) ? data.results : [];
      if (results.length > 0) {
        const hit = results[0];
        calculateAndRenderRoute(hit.lat, hit.lon, hit.name);
      } else if (data && data.error === 'offline_graph_missing') {
        if (typeof showAiSpeechToast === 'function') {
          showAiSpeechToast('⚠️ Offline Arizona map database not built yet (tools/build_az_nav_db.py).');
        }
      } else if (typeof showAiSpeechToast === 'function') {
        showAiSpeechToast(`⚠️ No offline destination found for "${rawQuery}". Try a bookmark or tap map.`);
      }
    })
    .catch(e => console.error('[NAV] Offline place search error:', e));
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
      if (nav.status === 'error' || nav.error || !nav.is_navigating) {
        isNavigatingActive = false;
        if (typeof showAiSpeechToast === 'function') {
          showAiSpeechToast(`⚠️ ${nav.message || 'Offline route unavailable.'}`);
        }
        return;
      }
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
  if (remDistEl) remDistEl.innerText = (nav.remaining_distance_miles !== undefined && nav.remaining_distance_miles !== null) ? nav.remaining_distance_miles : '--';
  if (etaEl) etaEl.innerText = (nav.estimated_minutes !== undefined && nav.estimated_minutes !== null) ? nav.estimated_minutes : '--';
  if (speedLimitEl) speedLimitEl.innerText = (nav.speed_limit_mph !== undefined && nav.speed_limit_mph !== null) ? nav.speed_limit_mph : '--';
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

// ==========================================

// 🧭 LEAFLET MAP & DRAGY TELEMETRY ENGINE

// ==========================================

let leafletMap = null;

let carMarker = null;

let currentGpsData = null;

let currentMapTileLayer = null;

let currentMapTheme = 'dark'; // 'dark' | 'streets' | 'satellite'

function toggleMapTheme() {

  if (!leafletMap) return;

  if (currentMapTheme === 'dark') {

    currentMapTheme = 'streets';

  } else if (currentMapTheme === 'streets') {

    currentMapTheme = 'satellite';

  } else {

    currentMapTheme = 'dark';

  }

  if (currentMapTileLayer) {

    leafletMap.removeLayer(currentMapTileLayer);

  }

  const apiBase = window.location.origin.startsWith('http') ? '' : 'http://127.0.0.1:8080';

  const url = `${apiBase}/api/maps/tiles/${currentMapTheme}/{z}/{x}/{y}.png`;

  currentMapTileLayer = L.tileLayer(url, {

    maxZoom: 19,

    attribution: currentMapTheme === 'streets'

      ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

      : '&copy; Esri &mdash; National Geographic, DeLorme, NAVTEQ'

  }).addTo(leafletMap);

  const btn = document.getElementById('mapThemeBtn');

  if (btn) {

    if (currentMapTheme === 'dark') btn.innerHTML = '🌙 DARK';

    else if (currentMapTheme === 'streets') btn.innerHTML = '🗺️ STREETS';

    else btn.innerHTML = '🛰️ SATELLITE';

  }

}

function initOrUpdateMap() {

  setTimeout(() => {

    const mapDiv = document.getElementById('liveMapCanvas');

    if (!mapDiv) return;

    if (!leafletMap && typeof L !== 'undefined') {

      const initialLat = (currentGpsData && currentGpsData.lat) || 33.4484;

      const initialLon = (currentGpsData && currentGpsData.lon) || -112.0740;

      leafletMap = L.map('liveMapCanvas', {

        center: [initialLat, initialLon],

        zoom: 15,

        zoomControl: false,

        attributionControl: false

      });

      const apiBase = window.location.origin.startsWith('http') ? '' : 'http://127.0.0.1:8080';

      const tileUrl = `${apiBase}/api/maps/tiles/${currentMapTheme}/{z}/{x}/{y}.png`;

      currentMapTileLayer = L.tileLayer(tileUrl, {

        maxZoom: 19,

        attribution: currentMapTheme === 'streets'

          ? '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

          : '&copy; Esri &mdash; National Geographic, DeLorme, NAVTEQ'

      }).addTo(leafletMap);

      const carIcon = L.divIcon({

        className: 'car-heading-marker',

        html: `<div id="carIconHeading" style="width:28px; height:28px; border-radius:50%; background:rgba(0,176,255,0.3); border:2px solid #00b0ff; box-shadow:0 0 12px #00b0ff; display:flex; align-items:center; justify-content:center; transition:transform 0.3s ease;">
                 <div style="width:0; height:0; border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:12px solid #fff;"></div>
               </div>`,

        iconSize: [28, 28],

        iconAnchor: [14, 14]

      });

      carMarker = L.marker([initialLat, initialLon], { icon: carIcon }).addTo(leafletMap);

      leafletMap.on('click', (e) => {
        calculateAndRenderRoute(e.latlng.lat, e.latlng.lng, 'Pinned Destination');
      });
    }

    

    if (leafletMap) {

      leafletMap.invalidateSize();

      if (currentGpsData && currentGpsData.lat && currentGpsData.lon && currentGpsData.fix) {

        leafletMap.panTo([currentGpsData.lat, currentGpsData.lon]);

        if (carMarker) carMarker.setLatLng([currentGpsData.lat, currentGpsData.lon]);

      }

    }

  }, 200);

}

function recenterMap() {

  if (leafletMap && currentGpsData && currentGpsData.lat && currentGpsData.lon) {

    leafletMap.setView([currentGpsData.lat, currentGpsData.lon], 16);

  }

}

function updateGpsAndDragyUI(gps) {

  if (!gps) return;

  currentGpsData = gps;

  // Home card badge

  const homeBadge = document.getElementById('homeGpsBadge');

  if (homeBadge) {

    const fixText = gps.fix ? `🛰️ GPS: LOCKED (${gps.sats})` : `🛰️ SATS: ${gps.sats_in_view || 0}`;

    homeBadge.textContent = fixText;

    homeBadge.style.color = gps.fix ? 'var(--accent-green)' : 'var(--accent-blue)';

    homeBadge.style.borderColor = gps.fix ? 'var(--accent-green)' : 'var(--accent-blue)';

  }

  // Maps top HUD

  const navFixBadge = document.getElementById('navFixBadge');

  if (navFixBadge) {

    navFixBadge.textContent = gps.fix ? '3D FIX LOCKED' : (gps.sats_in_view > 0 ? 'ACQUIRING...' : 'SEARCHING SATS');

    navFixBadge.style.color = gps.fix ? '#00e676' : '#ffab00';

    navFixBadge.style.background = gps.fix ? 'rgba(0,230,118,0.15)' : 'rgba(255,171,0,0.15)';

    navFixBadge.style.borderColor = gps.fix ? '#00e676' : '#ffab00';

  }

  const navSatsCount = document.getElementById('navSatsCount');

  if (navSatsCount) navSatsCount.textContent = `🛰️ ${gps.sats || 0} Locked (${gps.sats_in_view || 0} in view)`;

  const navGpsSpeed = document.getElementById('navGpsSpeed');

  if (navGpsSpeed) navGpsSpeed.textContent = (gps.speed_mph || 0.0).toFixed(1);

  const navHeadingVal = document.getElementById('navHeadingVal');

  if (navHeadingVal) navHeadingVal.textContent = `${Math.round(gps.heading || 0)}°`;

  const navCardinal = document.getElementById('navCardinal');

  if (navCardinal) navCardinal.textContent = gps.heading_cardinal || 'N';

  const navAltitude = document.getElementById('navAltitude');

  if (navAltitude) navAltitude.textContent = gps.altitude_ft ? Math.round(gps.altitude_ft) : '--';

  const navCoords = document.getElementById('navCoords');

  if (navCoords) {

    if (gps.lat && gps.lon) {

      navCoords.textContent = `${gps.lat.toFixed(5)}°N, ${gps.lon.toFixed(5)}°W`;

    } else {

      navCoords.textContent = 'Waiting for satellite fix...';

    }

  }

  // Update Leaflet Car Position & Rotation

  if (leafletMap && carMarker && gps.lat && gps.lon && gps.fix) {

    carMarker.setLatLng([gps.lat, gps.lon]);

    const headingElem = document.getElementById('carIconHeading');

    if (headingElem && typeof gps.heading === 'number') {

      headingElem.style.transform = `rotate(${gps.heading}deg)`;

    }

    if (isNavigatingActive && gps.lat && gps.lon) {
      updateNavigationProgress(gps.lat, gps.lon, gps.speed_mph || 0.0);
    }
  }

  // DRAGY PERFORMANCE METRICS

  const d = gps.dragy;

  if (d) {

    const badge = document.getElementById('dragyStateBadge');

    if (badge) {

      badge.textContent = d.state || 'IDLE';

      if (d.state === 'STAGED') {

        badge.style.color = '#00e676';

        badge.style.background = 'rgba(0,230,118,0.15)';

        badge.style.borderColor = '#00e676';

      } else if (d.state === 'ACCELERATING') {

        badge.style.color = '#ff3d00';

        badge.style.background = 'rgba(255,61,0,0.15)';

        badge.style.borderColor = '#ff3d00';

      } else {

        badge.style.color = '#00b0ff';

        badge.style.background = 'rgba(0,176,255,0.15)';

        badge.style.borderColor = '#00b0ff';

      }

    }

    const t060 = document.getElementById('dragy060');

    if (t060) t060.textContent = d.time_0_60 ? `${d.time_0_60.toFixed(2)}s` : '--';

    const t60ft = document.getElementById('dragy60ft');

    if (t60ft) t60ft.textContent = d.time_60ft ? `${d.time_60ft.toFixed(2)}s` : '--';

    const t18mi = document.getElementById('dragy18mi');

    if (t18mi) t18mi.textContent = d.time_1_8mi ? `${d.time_1_8mi.toFixed(2)}s` : '--';

    const s18mph = document.getElementById('dragy18mph');

    if (s18mph) s18mph.textContent = d.speed_1_8mi ? `@ ${d.speed_1_8mi.toFixed(1)} MPH` : '@ -- MPH';

    const t14mi = document.getElementById('dragy14mi');

    if (t14mi) t14mi.textContent = d.time_1_4mi ? `${d.time_1_4mi.toFixed(2)}s` : '--';

    const s14mph = document.getElementById('dragy14mph');

    if (s14mph) s14mph.textContent = d.speed_1_4mi ? `@ ${d.speed_1_4mi.toFixed(1)} MPH` : '@ -- MPH';

    const liveTimer = document.getElementById('dragyLiveTimer');

    if (liveTimer) liveTimer.textContent = `${(d.current_run_time || 0.0).toFixed(2)}s`;

    const peakG = document.getElementById('dragyPeakG');

    if (peakG) peakG.textContent = `${(d.peak_g || 0.0).toFixed(2)} G`;

  }

}
