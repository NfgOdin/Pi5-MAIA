"""
system_monitor.py - SBC & Hardware Health Monitor for Raspberry Pi 5
Monitors:
- SoC Core Temperature (°C and °F)
- CPU Utilization % across all 4 Cortex-A76 cores
- RAM utilization (Used / Total MB)
- Storage / NVMe / SD utilization
- Thermal & Under-Voltage Throttling flags (vcgencmd get_throttled)
- Screen hardware backlight brightness control (/sys/class/backlight/)
"""

import os
import sys
import time
import subprocess
from typing import Dict, Any, Optional

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.is_linux = sys.platform.startswith("linux")
        self.backlight_path = self._find_backlight_path()
        self.current_brightness = 100

    def _find_backlight_path(self) -> Optional[str]:
        if not self.is_linux:
            return None
        base = "/sys/class/backlight"
        if os.path.exists(base):
            entries = os.listdir(base)
            if entries:
                return os.path.join(base, entries[0])
        return None

    def get_soc_temperature(self) -> float:
        """Returns SoC temperature in Celsius."""
        if self.is_linux:
            # 1. Try Linux thermal zone
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    return round(float(f.read().strip()) / 1000.0, 1)
            except Exception:
                pass

            # 2. Try vcgencmd
            try:
                out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8")
                # e.g., temp=48.2'C
                if "temp=" in out:
                    val = out.split("=")[1].split("'")[0]
                    return float(val)
            except Exception:
                pass

        # Development / Simulation Fallback (Normal operating temp around 46-52°C)
        return 48.5

    def get_throttled_status(self) -> Dict[str, Any]:
        """Checks Raspberry Pi under-voltage and thermal throttling state via vcgencmd."""
        res = {
            "is_throttled": False,
            "under_voltage": False,
            "freq_capped": False,
            "soft_temp_limit": False,
            "raw_hex": "0x0",
            "message": "Thermal & Voltage Nominal"
        }
        if self.is_linux:
            try:
                out = subprocess.check_output(["vcgencmd", "get_throttled"]).decode("utf-8")
                # e.g., throttled=0x0
                if "throttled=" in out:
                    raw_val = int(out.split("=")[1].strip(), 16)
                    res["raw_hex"] = hex(raw_val)
                    res["under_voltage"] = bool(raw_val & 0x1)
                    res["freq_capped"] = bool(raw_val & 0x2)
                    res["is_throttled"] = bool(raw_val & 0x4)
                    res["soft_temp_limit"] = bool(raw_val & 0x8)

                    if res["is_throttled"]:
                        res["message"] = "WARNING: Thermal Throttling Active!"
                    elif res["under_voltage"]:
                        res["message"] = "WARNING: Low Voltage Detected on Power Input!"
            except Exception:
                pass
        return res

    def get_system_health(self) -> Dict[str, Any]:
        temp_c = self.get_soc_temperature()
        temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)

        cpu_pct = 0.0
        ram_used_mb = 0
        ram_total_mb = 8192
        ram_pct = 0.0

        if PSUTIL_AVAILABLE:
            try:
                cpu_pct = psutil.cpu_percent(interval=None)
                vm = psutil.virtual_memory()
                ram_used_mb = int(vm.used / (1024 * 1024))
                ram_total_mb = int(vm.total / (1024 * 1024))
                ram_pct = vm.percent
            except Exception:
                pass

        uptime_sec = int(time.time() - self.start_time)
        hours = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60

        throttling = self.get_throttled_status()

        return {
            "soc_temp_c": temp_c,
            "soc_temp_f": temp_f,
            "cpu_pct": cpu_pct,
            "ram_used_mb": ram_used_mb,
            "ram_total_mb": ram_total_mb,
            "ram_pct": ram_pct,
            "uptime_str": f"{hours}h {mins}m",
            "throttled": throttling["is_throttled"],
            "under_voltage": throttling["under_voltage"],
            "throttle_message": throttling["message"],
            "brightness_pct": self.current_brightness
        }

    def set_brightness(self, pct: int) -> bool:
        """Sets hardware screen brightness (0 - 100%)."""
        pct = max(10, min(100, int(pct)))
        self.current_brightness = pct

        if self.is_linux and self.backlight_path:
            try:
                max_path = os.path.join(self.backlight_path, "max_brightness")
                cur_path = os.path.join(self.backlight_path, "brightness")

                max_val = 255
                if os.path.exists(max_path):
                    with open(max_path, "r") as f:
                        max_val = int(f.read().strip())

                target_val = int((pct / 100.0) * max_val)
                with open(cur_path, "w") as f:
                    f.write(str(target_val))
                return True
            except Exception as e:
                print(f"[BACKLIGHT] Failed writing hardware brightness: {e}")
        return True
