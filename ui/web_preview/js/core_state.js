// CarPi5 UI Module: Shared Core State & Cross-Module Utilities

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatClockTime(date = new Date(), includeSeconds = false) {
  if (is24HourClock) {
    const opts = { hour: '2-digit', minute: '2-digit', hour12: false };
    if (includeSeconds) opts.second = '2-digit';
    return date.toLocaleTimeString([], opts);
  } else {
    let hours = date.getHours();
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    if (includeSeconds) {
      const seconds = String(date.getSeconds()).padStart(2, '0');
      return `${hours}:${minutes}:${seconds} ${ampm}`;
    }
    return `${hours}:${minutes} ${ampm}`;
  }
}

// --- 1. SENSOR DEFINITIONS & STATE ---

const SENSORS = {
  speed: { id: "speed", name: "Vehicle Speed", unit: "MPH", min: 0, max: 140, color: "#00b0ff" },
  boost: { id: "boost", name: "Turbo Boost", unit: "PSI", min: -25, max: 22, color: "#00e676" },
  rpm: { id: "rpm", name: "Engine RPM", unit: "RPM", min: 0, max: 7000, color: "#ffcc00" },
  coolant: { id: "coolant", name: "MultiAir Temp", unit: "°F", min: 60, max: 240, color: "#ff7700" },
  load: { id: "load", name: "Engine Load", unit: "%", min: 0, max: 100, color: "#ff5252" },
  throttle: { id: "throttle", name: "Throttle Pos", unit: "%", min: 0, max: 100, color: "#b388ff" },
  timing: { id: "timing", name: "Timing Advance", unit: "°", min: -10, max: 40, color: "#e040fb" },
  afr: { id: "afr", name: "Air/Fuel Ratio", unit: ":1", min: 10, max: 20, color: "#69f0ae" },
  iat: { id: "iat", name: "Intake Air Temp", unit: "°F", min: 50, max: 160, color: "#00e5ff" },
  volts: { id: "volts", name: "Battery Volts", unit: "V", min: 10, max: 16, color: "#00e676" },
  mpg: { id: "mpg", name: "Fuel Economy", unit: "MPG", min: 0, max: 60, color: "#00e676" },
  fuel_level: { id: "fuel_level", name: "Fuel Level", unit: "%", min: 0, max: 100, color: "#40c4ff" },
  ambient: { id: "ambient", name: "Ambient Temp", unit: "°F", min: 0, max: 130, color: "#ffd740" },
  pedal: { id: "pedal", name: "Pedal Position", unit: "%", min: 0, max: 100, color: "#7c4dff" },
  runtime: { id: "runtime", name: "Engine Runtime", unit: "min", min: 0, max: 180, color: "#64ffda" },
  baro: { id: "baro", name: "Baro Pressure", unit: "kPa", min: 60, max: 110, color: "#ffab40" }
};

// Global App State
let currentScreen = "home";
let currentLayout = 3; // Default 3 gauges (Speed, Boost, RPM)
let currentSlots = [
  "speed", "boost", "rpm", "coolant",
  "load", "throttle", "timing", "afr",
  "iat", "volts", "mpg", "fuel_level",
  "ambient", "pedal", "runtime", "baro"
];
// Restore saved preferences
try {
  const savedLayout = localStorage.getItem('carpi5_layout');
  if (savedLayout) currentLayout = parseInt(savedLayout, 10) || 3;
  const savedSlots = localStorage.getItem('carpi5_slots');
  if (savedSlots) {
    const parsed = JSON.parse(savedSlots);
    if (Array.isArray(parsed) && parsed.length > 0) {
      for (let i = 0; i < parsed.length; i++) {
        if (parsed[i] && SENSORS[parsed[i]]) currentSlots[i] = parsed[i];
      }
    }
  }
} catch (e) {}
let isKph = false;
let currentVoiceMode = "COPILOT";
let activeGraphSensor = null;
let currentAiSettings = {
  mode: "BUILTIN",
  personality: "RUM",
  driver_title: "Dad",
  driver_name: "",
  driver_moniker: "",
  tailscale_ip: "100.x.y.z",
  tailscale_port: 11434,
  ollama_model: "llama3.2:3b",
  api_key: ""
};

function getDriverDisplayAddress() {
  const title = (currentAiSettings.driver_title || "").trim();
  const name = (currentAiSettings.driver_name || currentAiSettings.driver_moniker || "").trim();
  if (title && name) return `${title} ${name}`;
  if (name) return name;
  if (title) return title;
  return "Master";
}

// Time-Series Historical Buffer (stores last 60 seconds of data @ 2Hz = 120 samples per sensor)
const HISTORY_LENGTH = 120;
const historyBuffers = {};
Object.keys(SENSORS).forEach(k => {
  historyBuffers[k] = [];
  historyBuffers[k]._lastTime = 0;
});

// Screensaver & Idle Timer State
let screensaverTimer = null;
let screensaverInterval = null;
let lastInteractionTime = Date.now();
const screensaverImages = [
  "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?auto=format&fit=crop&w=1920&q=90",
  "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?auto=format&fit=crop&w=1920&q=90"
];
let currentImageIdx = 0;

// Media Player State
const PLAYLIST = [
  { title: "Turbo Highway Star (Synthwave Edit)", artist: "CarPi5 In-Console Audio", duration: 225 },
  { title: "Nightcall MultiAir Drift", artist: "Kavinsky & C635", duration: 260 },
  { title: "1.4L Boost Anthem (Italian FIRE)", artist: "R.U.M. Synthetics", duration: 198 }
];
let currentTrackIdx = 0;
let isPlaying = true;
let trackElapsedSeconds = 84;
let mediaPlayInterval = null;
