"""
pedal_commander.py - Bluetooth Low Energy (BLE) Controller for Pedal Commander
Controls Pedal Commander throttle maps (ECO, CITY, SPORT, SPORT+) and sensitivity (-4 to +4)
via modern BlueZ BLE GATT (`bleak` async client with dynamic characteristic discovery, falling
back cleanly to `gatttool`), plus optional I2C MCP4725 DAC output and truthful offline reporting.
"""

import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "pedal_commander.json"

DEFAULT_MAC_ADDRESS = "18:62:E4:46:73:8B"
DEFAULT_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
HANDLE_VALUE = "0x0012"
HANDLE_NOTIFY = "0x0013"
MCP4725_I2C_CANDIDATES = (0x60, 0x61)

MODES = {
    "ECO": 0,
    "CITY": 1,
    "SPORT": 2,
    "SPORT+": 3,
    "SPORT_PLUS": 3,
}
MODE_BY_IDX = {0: "ECO", 1: "CITY", 2: "SPORT", 3: "SPORT+"}


def decode_rx_packet(raw_bytes: bytes) -> Dict[str, Any]:
    """
    Decode Pedal Commander BLE RX notification frames (binary `AA <mode> <sens> <chk> 55`
    or ASCII `MODE:<mode>:<sens>` / `PC:<mode>:<level>`).
    """
    result: Dict[str, Any] = {
        "valid": False,
        "kind": "unknown",
        "mode": None,
        "level": None,
        "raw_hex": raw_bytes.hex(),
        "raw_text": "",
    }
    if not raw_bytes:
        return result

    # 1. Binary 5-byte frame: AA <mode_idx> <sens_idx> <checksum> 55
    for idx in range(0, max(0, len(raw_bytes) - 4)):
        if raw_bytes[idx] == 0xAA and raw_bytes[idx + 4] == 0x55:
            mode_idx = raw_bytes[idx + 1]
            sens_idx = raw_bytes[idx + 2]
            chk = raw_bytes[idx + 3]
            if ((0xAA + mode_idx + sens_idx) & 0xFF) == chk and mode_idx in MODE_BY_IDX and 0 <= sens_idx <= 8:
                result.update({
                    "valid": True,
                    "kind": "binary_ack",
                    "mode": MODE_BY_IDX[mode_idx],
                    "level": sens_idx - 4,
                })
                return result

    # 2. ASCII line status frames
    try:
        txt = raw_bytes.decode("ascii", errors="ignore").strip()
    except Exception:
        txt = ""
    result["raw_text"] = txt
    if txt:
        m = re.search(r"(?:MODE|PC)[:=](ECO|CITY|SPORT\+?|SPORT_PLUS)[:=]([+-]?\d+)", txt, re.IGNORECASE)
        if m:
            norm_m = m.group(1).upper().replace("_PLUS", "+")
            raw_lvl = int(m.group(2))
            level = (raw_lvl - 4) if ("MODE:" in txt.upper() and 0 <= raw_lvl <= 8 and "+" not in m.group(2) and "-" not in m.group(2)) else max(-4, min(4, raw_lvl))
            result.update({"valid": True, "kind": "ascii_status", "mode": norm_m, "level": level})
        elif any(tok in txt.upper() for tok in ("OK", "AUTH", "READY")):
            result.update({"valid": True, "kind": "ascii_ack"})
    return result


class BleUartWorker:
    """Manages persistent GATT connection via `bleak` (preferred) or `gatttool` fallback."""

    def __init__(
        self,
        mac: str = DEFAULT_MAC_ADDRESS,
        char_uuid: str = DEFAULT_CHAR_UUID,
        on_rx: Optional[Callable[[bytes], None]] = None,
    ):
        self.mac = mac
        self.char_uuid = (char_uuid or DEFAULT_CHAR_UUID).lower()
        self.on_rx = on_rx
        self.transport = "uninitialized"
        self.proc: Optional[subprocess.Popen] = None
        self.connected = False
        self.cmd_queue: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.running = True
        self.last_status = "Disconnected"
        self.last_rx = ""
        self.discovered_uuids: List[str] = []

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _emit_rx(self, payload: bytes) -> None:
        self.last_rx = payload.hex()
        if self.on_rx:
            try:
                self.on_rx(payload)
            except Exception:
                pass

    def _run_loop(self) -> None:
        try:
            import bleak  # noqa: F401
            has_bleak = True
        except Exception:
            has_bleak = False

        if has_bleak:
            self.transport = "bleak"
            try:
                asyncio.run(self._bleak_main())
                return
            except Exception as e:
                print(f"[PEDAL COMMANDER] bleak worker fallback note: {e}", flush=True)

        self.transport = "gatttool"
        self._gatttool_loop()

    async def _bleak_main(self) -> None:
        from bleak import BleakClient

        while self.running:
            try:
                self.last_status = f"Scanning/Connecting {self.mac} via BlueZ..."
                async with BleakClient(self.mac, timeout=8.0) as client:
                    if not client.is_connected:
                        self.connected = False
                        await asyncio.sleep(3.0)
                        continue

                    tx_uuid = None
                    rx_uuid = None
                    uuids: List[str] = []
                    for svc in client.services:
                        for ch in svc.characteristics:
                            cu = ch.uuid.lower()
                            uuids.append(cu)
                            props = set(ch.properties or [])
                            if self.char_uuid in cu or "ffe1" in cu:
                                if "write" in props or "write-without-response" in props:
                                    tx_uuid = cu
                                if "notify" in props or "indicate" in props:
                                    rx_uuid = cu
                    if not tx_uuid:
                        for svc in client.services:
                            for ch in svc.characteristics:
                                props = set(ch.properties or [])
                                if ("write" in props or "write-without-response" in props) and not tx_uuid:
                                    tx_uuid = ch.uuid.lower()
                                if ("notify" in props or "indicate" in props) and not rx_uuid:
                                    rx_uuid = ch.uuid.lower()

                    self.discovered_uuids = uuids[:20]
                    if rx_uuid:
                        await client.start_notify(rx_uuid, lambda _h, data: self._emit_rx(bytes(data)))

                    self.connected = True
                    self.last_status = f"Connected via bleak ({tx_uuid or 'no-tx'})"
                    while self.running and client.is_connected:
                        try:
                            kind, val = self.cmd_queue.get_nowait()
                            raw = bytes.fromhex(val) if kind == "hex" else str(val).encode("ascii", errors="ignore")
                            if tx_uuid:
                                await client.write_gatt_char(tx_uuid, raw, response=False)
                        except queue.Empty:
                            await asyncio.sleep(0.15)
            except Exception as e:
                self.connected = False
                self.last_status = f"BLE Offline ({e})"
            await asyncio.sleep(3.0)

    def _gatttool_loop(self) -> None:
        while self.running:
            if not shutil.which("gatttool"):
                self.connected = False
                self.last_status = "Disconnected (bleak & gatttool unavailable)"
                time.sleep(10.0)
                continue

            try:
                subprocess.run(
                    ["pkill", "-f", f"gatttool.*{self.mac}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0,
                )
                time.sleep(0.3)

                self.proc = subprocess.Popen(
                    ["gatttool", "-b", self.mac, "-t", "public", "-I"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                threading.Thread(target=self._gatttool_stdout_reader, daemon=True).start()
                if self.proc and self.proc.stdin:
                    self.proc.stdin.write("connect\n")
                    self.proc.stdin.flush()

                while self.running and self.proc and self.proc.poll() is None:
                    try:
                        kind, val = self.cmd_queue.get(timeout=1.0)
                        hex_payload = val if kind == "hex" else "".join(f"{ord(c):02x}" for c in str(val))
                        cmd_line = val if kind == "raw_cmd" else f"char-write-cmd {HANDLE_VALUE} {hex_payload}"
                        if self.proc and self.proc.poll() is None and self.proc.stdin:
                            self.proc.stdin.write(cmd_line + "\n")
                            self.proc.stdin.flush()
                    except queue.Empty:
                        pass
            except Exception as e:
                self.last_status = f"BLE link error: {e}"
                self.connected = False
            finally:
                if self.proc and self.proc.poll() is None:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self.connected = False
            time.sleep(3.0)

    def _gatttool_stdout_reader(self) -> None:
        while self.proc and self.proc.poll() is None:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                if "Connection successful" in line:
                    self.connected = True
                    self.last_status = "Connected via gatttool"
                    self.cmd_queue.put(("raw_cmd", f"char-write-req {HANDLE_NOTIFY} 0100"))
                elif "Disconnected" in line or "Error" in line:
                    self.connected = False
                    self.last_status = line
                elif "Notification" in line or "value:" in line:
                    m = re.search(r"value:\s*([0-9a-fA-F\s]+)$", line)
                    if m:
                        try:
                            raw = bytes.fromhex(m.group(1).replace(" ", ""))
                            self._emit_rx(raw)
                        except Exception:
                            self.last_rx = line
                    else:
                        self.last_rx = line
            except Exception:
                break
        self.connected = False

    def send_hex(self, hex_payload: str) -> None:
        self.cmd_queue.put(("hex", hex_payload))

    def send_ascii(self, text_str: str) -> None:
        self.cmd_queue.put(("ascii", text_str))

    def close(self) -> None:
        self.running = False
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass


class PedalCommanderController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config_path: Optional[Path] = None, auto_start_worker: bool = True):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.mac = DEFAULT_MAC_ADDRESS
        self.char_uuid = DEFAULT_CHAR_UUID
        self.current_mode = "SPORT"
        self.current_level = 2
        self.last_ack = "Offline (BLE Disconnected)"
        self.ack_verified = False
        self.pin = ""
        self.rx_log: Deque[Dict[str, Any]] = deque(maxlen=25)
        self._worker: Optional[BleUartWorker] = None
        self._i2c_bus: Optional[Any] = None
        self._dac_addr: Optional[int] = None
        self._dac_connected = False

        self._load_config()

        if auto_start_worker and sys.platform.startswith("linux"):
            self._init_i2c_dac()
            self._start_worker()

    def _load_config(self) -> None:
        if self.config_path.exists():
            try:
                cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.mac = str(cfg.get("mac") or DEFAULT_MAC_ADDRESS).strip().upper()
                self.char_uuid = str(cfg.get("char_uuid") or DEFAULT_CHAR_UUID).strip().lower()
                self.pin = str(cfg.get("pin") or "").strip()
                norm_mode = str(cfg.get("mode") or "SPORT").upper().replace("_PLUS", "+")
                if norm_mode in MODES:
                    self.current_mode = norm_mode
                self.current_level = max(-4, min(4, int(cfg.get("level", 2))))
            except Exception:
                pass

    def _save_config(self) -> None:
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(
                    {
                        "mac": self.mac,
                        "char_uuid": self.char_uuid,
                        "pin": self.pin,
                        "mode": self.current_mode,
                        "level": self.current_level,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[PEDAL COMMANDER] Config save error: {e}", flush=True)

    def _start_worker(self) -> None:
        if self._worker:
            self._worker.close()
        self._worker = BleUartWorker(self.mac, self.char_uuid, on_rx=self._on_ble_rx)

    def _on_ble_rx(self, raw_bytes: bytes) -> None:
        parsed = decode_rx_packet(raw_bytes)
        entry = {
            "ts": round(time.time(), 2),
            "raw_hex": parsed["raw_hex"],
            "kind": parsed["kind"],
            "valid": parsed["valid"],
            "mode": parsed["mode"],
            "level": parsed["level"],
        }
        self.rx_log.append(entry)
        if parsed["valid"]:
            self.ack_verified = True
            if parsed["mode"] in MODES:
                self.current_mode = parsed["mode"]
            if parsed["level"] is not None:
                self.current_level = max(-4, min(4, int(parsed["level"])))
            self.last_ack = f"BLE RX Confirmed: {self.current_mode} ({self.current_level:+d})"
            self._save_config()

    def _init_i2c_dac(self) -> None:
        if not os.path.exists("/dev/i2c-1"):
            return
        for mod_name in ("smbus2", "smbus"):
            try:
                smbus_mod = __import__(mod_name)
                bus = smbus_mod.SMBus(1)
                for addr in MCP4725_I2C_CANDIDATES:
                    try:
                        bus.read_byte(addr)
                        self._i2c_bus = bus
                        self._dac_addr = addr
                        self._dac_connected = True
                        return
                    except Exception:
                        continue
                bus.close()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        ble_conn = bool(self._worker and self._worker.connected)
        is_conn = bool(ble_conn or self._dac_connected)
        transport = self._worker.transport if self._worker else ("i2c_dac" if self._dac_connected else "offline")
        if ble_conn:
            status_text = f"CONNECTED ({transport.upper()} {self.mac})"
        elif self._dac_connected and self._dac_addr is not None:
            status_text = f"CONNECTED (I2C MCP4725 0x{self._dac_addr:02x})"
        else:
            status_text = f"OFFLINE (BLE DISCONNECTED • {self.mac})"
        return {
            "mac": self.mac,
            "char_uuid": self.char_uuid,
            "connected": is_conn,
            "ble_connected": ble_conn,
            "dac_connected": self._dac_connected,
            "transport": transport,
            "mode": self.current_mode,
            "level": self.current_level,
            "pin_configured": bool(self.pin),
            "ack_verified": self.ack_verified,
            "last_ack": self.last_ack,
            "status_text": status_text,
            "rx_log": list(self.rx_log)[-8:],
        }

    def update_config(
        self,
        mac: Optional[str] = None,
        pin: Optional[str] = None,
        char_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        mac_changed = False
        if mac is not None and str(mac).strip():
            clean_mac = str(mac).strip().upper()
            if clean_mac != self.mac:
                self.mac = clean_mac
                mac_changed = True
        if char_uuid is not None and str(char_uuid).strip():
            self.char_uuid = str(char_uuid).strip().lower()
        if pin is not None:
            self.pin = str(pin).strip()
        self._save_config()

        if mac_changed and sys.platform.startswith("linux"):
            self.ack_verified = False
            self._start_worker()
        if pin and self._worker and self._worker.connected:
            self.set_pin(self.pin)

        return {"status": "ok", **self.get_status()}

    def scan_ble_devices(self, timeout_s: float = 4.0) -> Dict[str, Any]:
        """Discover nearby BLE peripherals cleanly; returns empty list offline/non-Linux."""
        if not sys.platform.startswith("linux"):
            return {
                "status": "offline",
                "connected": False,
                "devices": [],
                "message": "BLE GATT scanning requires Raspberry Pi 5 Linux BlueZ.",
            }
        try:
            from bleak import BleakScanner

            async def _scan():
                found = await BleakScanner.discover(timeout=timeout_s)
                out = []
                for d in found:
                    name = d.name or "Unknown BLE Device"
                    out.append({
                        "mac": d.address.upper(),
                        "name": name,
                        "rssi": getattr(d, "rssi", None),
                        "likely_pedal_commander": any(k in name.upper() for k in ("PEDAL", "HMSoft", "PC-", "PC_")),
                    })
                out.sort(key=lambda x: (not x["likely_pedal_commander"], -(x["rssi"] if x["rssi"] is not None else -120)))
                return out

            devices = asyncio.run(_scan())
            return {"status": "ok", "connected": True, "devices": devices}
        except Exception as e:
            return {
                "status": "error",
                "connected": False,
                "devices": [],
                "message": f"BLE scan unavailable ({e})",
            }

    def set_pin(self, pin: str) -> None:
        self.pin = str(pin).strip()
        self._save_config()
        if self._worker and self._worker.connected and self.pin:
            self._worker.send_ascii(f"AUTH:{self.pin}\r\n")
            self._worker.send_ascii(f"{self.pin}\r\n")

    def set_curve(self, mode: str, level: int, pin: Optional[str] = None) -> Dict[str, Any]:
        norm_mode = mode.upper().replace("PLUS", "+").replace("_+", "+")
        if norm_mode not in MODES:
            return {"status": "error", "connected": False, "sent": False, "message": f"Invalid mode '{mode}'."}

        clamped_level = max(-4, min(4, int(level)))
        self.current_mode = norm_mode
        self.current_level = clamped_level
        if pin is not None and str(pin).strip():
            self.pin = str(pin).strip()
        self._save_config()

        mode_idx = MODES[norm_mode]
        sens_idx = clamped_level + 4
        ble_conn = bool(self._worker and self._worker.connected)
        sent = False

        if ble_conn and self._worker:
            chk = (0xAA + mode_idx + sens_idx) & 0xFF
            bin_hex = f"aa{mode_idx:02x}{sens_idx:02x}{chk:02x}55"
            self._worker.send_hex(bin_hex)
            self._worker.send_ascii(f"PC:{norm_mode}:{clamped_level:+d}\r\n")
            sent = True
            self.last_ack = f"Sent {norm_mode} ({clamped_level:+d}) via BLE UART"

        if self._dac_connected and self._i2c_bus and self._dac_addr is not None:
            try:
                step_idx = mode_idx * 9 + sens_idx
                dac_val = max(0, min(4095, int(round((step_idx / 35.0) * 4095.0))))
                self._i2c_bus.write_i2c_block_data(self._dac_addr, (dac_val >> 8) & 0x0F, [dac_val & 0xFF])
                sent = True
                self.last_ack = f"Sent {norm_mode} ({clamped_level:+d}) to MCP4725 DAC"
            except Exception:
                self._dac_connected = False

        if not sent:
            self.last_ack = f"Offline (BLE Disconnected) • Target {norm_mode} ({clamped_level:+d}) saved"

        is_conn = bool(ble_conn or self._dac_connected)
        return {
            "status": "ok" if sent else "offline",
            "connected": is_conn,
            "mode": self.current_mode,
            "level": self.current_level,
            "sent": sent,
            "ack_verified": self.ack_verified,
            "message": (
                f"Pedal Commander curve transmitted: {norm_mode} {clamped_level:+d}"
                if sent else
                f"Pedal Commander BLE offline ({self.mac} not connected); target {norm_mode} {clamped_level:+d} saved."
            ),
        }
