"""
pedal_commander.py - Bluetooth Low Energy (BLE) Controller for Pedal Commander
Controls Pedal Commander throttle maps (ECO, CITY, SPORT, SPORT+) and sensitivity (-4 to +4)
via direct BLE GATT UART (HM-10/CC254x chipset at 18:62:E4:46:73:8B).

Direct GATT Handle 0x0012 (Characteristic 0xFFE1) / 0x0013 (Descriptor 0x2902).
"""

import os
import sys
import time
import shutil
import threading
import subprocess
import queue
from typing import Dict, Any, Optional

MAC_ADDRESS = "18:62:E4:46:73:8B"
HANDLE_VALUE = "0x0012"
HANDLE_NOTIFY = "0x0013"
MCP4725_I2C_CANDIDATES = (0x60, 0x61)

MODES = {
    "ECO": 0,
    "CITY": 1,
    "SPORT": 2,
    "SPORT+": 3,
    "SPORT_PLUS": 3
}

class BleUartWorker:
    """Manages persistent GATT connection to Pedal Commander HM-10 BLE module."""
    def __init__(self, mac=MAC_ADDRESS):
        self.mac = mac
        self.proc: Optional[subprocess.Popen] = None
        self.connected = False
        self.cmd_queue = queue.Queue()
        self.running = True
        self.last_status = "Disconnected"
        self.last_rx = ""
        self.lock = threading.Lock()
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def _run_loop(self):
        while self.running:
            if not shutil.which("gatttool"):
                self.connected = False
                self.last_status = "Disconnected (gatttool unavailable)"
                time.sleep(10.0)
                continue

            try:
                # Cleanup any stale gatttool processes first (with strict timeout)
                subprocess.run(
                    ['pkill', '-f', f'gatttool.*{self.mac}'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2.0
                )
                time.sleep(0.3)

                print(f"[PEDAL COMMANDER] Connecting to BLE module {self.mac} via gatttool...", flush=True)
                self.proc = subprocess.Popen(
                    ['gatttool', '-b', self.mac, '-t', 'public', '-I'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                reader_thread = threading.Thread(target=self._stdout_reader, daemon=True)
                reader_thread.start()

                # Send connect
                if self.proc and self.proc.stdin:
                    self.proc.stdin.write('connect\n')
                    self.proc.stdin.flush()

                # Command loop while connected
                while self.running and self.proc and self.proc.poll() is None:
                    try:
                        cmd_line = self.cmd_queue.get(timeout=1.5)
                        if self.proc and self.proc.poll() is None and self.proc.stdin:
                            self.proc.stdin.write(cmd_line + '\n')
                            self.proc.stdin.flush()
                            print(f"[PEDAL COMMANDER] Sent command: {cmd_line.strip()}", flush=True)
                    except queue.Empty:
                        # Periodic connection heartbeat / read
                        pass

            except Exception as e:
                print(f"[PEDAL COMMANDER] BLE worker exception: {e}", flush=True)
                self.connected = False
            finally:
                if self.proc and self.proc.poll() is None:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass

            self.connected = False
            time.sleep(3.0)

    def _stdout_reader(self):
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
                    self.last_status = "Connected"
                    print(f"[PEDAL COMMANDER] Successfully connected to {self.mac}!", flush=True)
                    # Enable notifications on handle 0x0013
                    self.cmd_queue.put(f"char-write-req {HANDLE_NOTIFY} 0100")
                elif "Disconnected" in line or "Error" in line:
                    self.connected = False
                    self.last_status = line
                    print(f"[PEDAL COMMANDER] Link status: {line}", flush=True)
                elif "Notification" in line or "value:" in line:
                    self.last_rx = line
                    print(f"[PEDAL COMMANDER] RX Notification: {line}", flush=True)
            except Exception:
                break
        self.connected = False

    def send_hex(self, hex_payload: str):
        # Write via char-write-cmd (write without response) and char-write-req
        self.cmd_queue.put(f"char-write-cmd {HANDLE_VALUE} {hex_payload}")

    def send_ascii(self, text_str: str):
        hex_data = "".join(f"{ord(c):02x}" for c in text_str)
        self.cmd_queue.put(f"char-write-cmd {HANDLE_VALUE} {hex_data}")

    def close(self):
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

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.current_mode = "SPORT"
        self.current_level = 2
        self.last_ack = "Standby (Disconnected)"
        self.pin = ""
        self._worker: Optional[BleUartWorker] = None
        self._i2c_bus: Optional[Any] = None
        self._dac_addr: Optional[int] = None
        self._dac_connected = False

        if sys.platform.startswith("linux"):
            self._init_i2c_dac()
            self._worker = BleUartWorker(MAC_ADDRESS)

    def _init_i2c_dac(self):
        """Probes optional I2C MCP4725 12-bit DAC (0x60 / 0x61) on /dev/i2c-1."""
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
                        print(f"[PEDAL COMMANDER] MCP4725 I2C DAC detected at 0x{addr:02x}", flush=True)
                        return
                    except Exception:
                        continue
                bus.close()
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        ble_conn = bool(self._worker and self._worker.connected)
        is_conn = bool(ble_conn or self._dac_connected)
        if ble_conn:
            status_text = f"CONNECTED (BLE UART {MAC_ADDRESS})"
        elif self._dac_connected and self._dac_addr is not None:
            status_text = f"CONNECTED (I2C MCP4725 DAC 0x{self._dac_addr:02x})"
        else:
            status_text = "DISCONNECTED (STANDBY)"
        return {
            "mac": MAC_ADDRESS,
            "connected": is_conn,
            "ble_connected": ble_conn,
            "dac_connected": self._dac_connected,
            "mode": self.current_mode,
            "level": self.current_level,
            "pin_configured": bool(self.pin),
            "last_ack": self.last_ack,
            "status_text": status_text
        }

    def set_pin(self, pin: str):
        """Sets the 6-digit authentication PIN / serial number if required by the unit."""
        self.pin = str(pin).strip()
        if self._worker and self._worker.connected and self.pin:
            # Send authentication handshake frames
            self._worker.send_ascii(f"AUTH:{self.pin}\r\n")
            self._worker.send_ascii(f"{self.pin}\r\n")
            print(f"[PEDAL COMMANDER] Sent authentication PIN handshake: {self.pin}", flush=True)

    def set_curve(self, mode: str, level: int, pin: Optional[str] = None) -> Dict[str, Any]:
        norm_mode = mode.upper().replace("PLUS", "+")
        if norm_mode not in MODES:
            return {"status": "error", "connected": False, "message": f"Invalid mode '{mode}'. Choose ECO, CITY, SPORT, SPORT+"}

        clamped_level = max(-4, min(4, int(level)))
        self.current_mode = norm_mode
        self.current_level = clamped_level

        if pin:
            self.set_pin(pin)

        mode_idx = MODES[norm_mode]
        # Map -4..+4 to 0..8
        sens_idx = clamped_level + 4

        ble_conn = bool(self._worker and self._worker.connected)
        sent = False

        if ble_conn and self._worker:
            # Construct standard Pedal Commander BLE frames:
            # 1. Binary Frame: AA <mode_idx> <sens_idx> <checksum> 55
            chk = (0xAA + mode_idx + sens_idx) & 0xFF
            bin_hex = f"aa{mode_idx:02x}{sens_idx:02x}{chk:02x}55"
            self._worker.send_hex(bin_hex)

            # 2. Text Command Frame: PC:<mode>:<level>\r\n
            txt_cmd = f"PC:{norm_mode}:{clamped_level:+d}\r\n"
            self._worker.send_ascii(txt_cmd)

            # 3. Direct Mode Code Frame: MODE:<mode>:<sens_idx>\r\n
            self._worker.send_ascii(f"MODE:{norm_mode}:{sens_idx}\r\n")

            sent = True
            self.last_ack = f"Transmitted {norm_mode} ({clamped_level:+d}) to HM-10 UART"
            print(f"[PEDAL COMMANDER] Broadcasted curve: {norm_mode} {clamped_level:+d} (Packet: {bin_hex})", flush=True)

        if self._dac_connected and self._i2c_bus and self._dac_addr is not None:
            try:
                # 12-bit MCP4725 fast-mode write (0..4095 mapped across 36 steps: 4 modes * 9 levels)
                step_idx = mode_idx * 9 + sens_idx  # 0..35
                dac_val = max(0, min(4095, int(round((step_idx / 35.0) * 4095.0))))
                self._i2c_bus.write_i2c_block_data(self._dac_addr, (dac_val >> 8) & 0x0F, [dac_val & 0xFF])
                sent = True
                self.last_ack = f"Transmitted {norm_mode} ({clamped_level:+d}) to MCP4725 DAC (0x{self._dac_addr:02x})"
            except Exception as e:
                print(f"[PEDAL COMMANDER] MCP4725 DAC write error: {e}", flush=True)
                self._dac_connected = False

        if not sent:
            self.last_ack = f"Offline (Hardware Disconnected - Target {norm_mode} {clamped_level:+d} Saved)"

        is_conn = bool(ble_conn or self._dac_connected)
        return {
            "status": "ok" if sent else "offline",
            "connected": is_conn,
            "mode": self.current_mode,
            "level": self.current_level,
            "sent": sent,
            "message": (
                f"Pedal Commander curve updated to {norm_mode} {clamped_level:+d}"
                if sent else
                f"Pedal Commander hardware offline (connected: false); saved target {norm_mode} {clamped_level:+d}"
            )
        }
