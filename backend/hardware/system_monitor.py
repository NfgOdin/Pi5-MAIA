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
import glob
import subprocess
from typing import Dict, Any, Optional, List

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

    def get_detailed_hardware_specs(self) -> Dict[str, Any]:
        """Comprehensive hardware telemetry audit for Raspberry Pi 5 & connected accessories."""
        # 1. CPU & Cores
        core_pcts = []
        total_cpu_pct = 0.0
        if PSUTIL_AVAILABLE:
            try:
                core_pcts = psutil.cpu_percent(interval=None, percpu=True)
                total_cpu_pct = psutil.cpu_percent(interval=None)
            except Exception:
                pass

        core_freqs = []
        if self.is_linux:
            freq_files = sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"))
            for i, p in enumerate(freq_files):
                try:
                    with open(p, "r") as f:
                        khz = int(f.read().strip())
                        mhz = round(khz / 1000.0, 1)
                except Exception:
                    mhz = 2400.0
                pct = core_pcts[i] if i < len(core_pcts) else 0.0
                core_freqs.append({
                    "id": i,
                    "pct": pct,
                    "freq_mhz": mhz,
                    "freq_ghz": round(mhz / 1000.0, 2)
                })

        if not core_freqs:
            for i in range(4):
                pct = core_pcts[i] if i < len(core_pcts) else 0.0
                core_freqs.append({
                    "id": i,
                    "pct": pct,
                    "freq_mhz": 2400.0,
                    "freq_ghz": 2.40
                })

        # 2. SoC & Vcgencmd Telemetry
        temp_c = self.get_soc_temperature()
        voltage_v = 0.8621
        v3d_mhz = 960.0
        core_mhz = 910.0
        arm_mhz = 2400.0
        gpu_mem_mb = 8
        arm_mem_mb = 1016

        if self.is_linux:
            try:
                out = subprocess.check_output(["vcgencmd", "measure_volts", "core"], stderr=subprocess.DEVNULL).decode()
                if "volt=" in out:
                    voltage_v = round(float(out.split("=")[1].replace("V", "").strip()), 4)
            except Exception:
                pass

            try:
                out = subprocess.check_output(["vcgencmd", "measure_clock", "v3d"], stderr=subprocess.DEVNULL).decode()
                if "frequency(" in out:
                    hz = int(out.split("=")[1].strip())
                    v3d_mhz = round(hz / 1000000.0, 1)
            except Exception:
                pass

            try:
                out = subprocess.check_output(["vcgencmd", "measure_clock", "core"], stderr=subprocess.DEVNULL).decode()
                if "frequency(" in out:
                    hz = int(out.split("=")[1].strip())
                    core_mhz = round(hz / 1000000.0, 1)
            except Exception:
                pass

            try:
                out = subprocess.check_output(["vcgencmd", "measure_clock", "arm"], stderr=subprocess.DEVNULL).decode()
                if "frequency(" in out:
                    hz = int(out.split("=")[1].strip())
                    arm_mhz = round(hz / 1000000.0, 1)
            except Exception:
                pass

            try:
                out = subprocess.check_output(["vcgencmd", "get_mem", "gpu"], stderr=subprocess.DEVNULL).decode()
                if "gpu=" in out:
                    gpu_mem_mb = int(out.split("=")[1].replace("M", "").strip())
            except Exception:
                pass

            try:
                out = subprocess.check_output(["vcgencmd", "get_mem", "arm"], stderr=subprocess.DEVNULL).decode()
                if "arm=" in out:
                    arm_mem_mb = int(out.split("=")[1].replace("M", "").strip())
            except Exception:
                pass

        throttling = self.get_throttled_status()

        # 3. RAM & Swap
        ram_total = 8192
        ram_used = 0
        ram_free = 8192
        ram_pct = 0.0
        swap_total = 2048
        swap_used = 0
        swap_pct = 0.0

        if PSUTIL_AVAILABLE:
            try:
                vm = psutil.virtual_memory()
                ram_total = int(vm.total / (1024 * 1024))
                ram_used = int(vm.used / (1024 * 1024))
                ram_free = int(vm.available / (1024 * 1024))
                ram_pct = vm.percent

                sm = psutil.swap_memory()
                swap_total = int(sm.total / (1024 * 1024))
                swap_used = int(sm.used / (1024 * 1024))
                swap_pct = sm.percent
            except Exception:
                pass

        # 4. Storage / Disk
        storage_total_gb = 64.0
        storage_used_gb = 14.0
        storage_free_gb = 50.0
        storage_pct = 22.0

        if PSUTIL_AVAILABLE:
            try:
                du = psutil.disk_usage('/')
                storage_total_gb = round(du.total / (1024**3), 1)
                storage_used_gb = round(du.used / (1024**3), 1)
                storage_free_gb = round(du.free / (1024**3), 1)
                storage_pct = du.percent
            except Exception:
                pass

        # 5. Hailo-10H / Hailo-8 NPU Hardware Audit
        hailo_detected = False
        hailo_nodes = []
        if self.is_linux:
            hailo_devs = glob.glob("/dev/hailo*")
            if hailo_devs:
                hailo_detected = True
                hailo_nodes = hailo_devs
            else:
                try:
                    lspci_out = subprocess.check_output(["lspci", "-nn"], stderr=subprocess.DEVNULL).decode()
                    if "1e60:" in lspci_out.lower() or "hailo" in lspci_out.lower():
                        hailo_detected = True
                except Exception:
                    pass

        # 6. Attached USB Devices
        usb_devices = []
        if self.is_linux:
            try:
                lsusb_out = subprocess.check_output(["lsusb"], stderr=subprocess.DEVNULL).decode().strip().splitlines()
                for line in lsusb_out:
                    if "root hub" not in line.lower():
                        parts = line.split("ID ")
                        name = parts[1].strip() if len(parts) > 1 else line.strip()
                        usb_devices.append(name)
            except Exception:
                pass

        # 7. Network Interfaces
        interfaces = []
        if PSUTIL_AVAILABLE:
            try:
                net_addrs = psutil.net_if_addrs()
                net_stats = psutil.net_if_stats()
                for iface, addrs in net_addrs.items():
                    if iface == "lo":
                        continue
                    ip_v4 = next((a.address for a in addrs if a.family.name == "AF_INET"), "None")
                    is_up = net_stats[iface].isup if iface in net_stats else False
                    speed = net_stats[iface].speed if iface in net_stats else 0
                    interfaces.append({
                        "name": iface,
                        "ip": ip_v4,
                        "is_up": is_up,
                        "speed_mbps": speed
                    })
            except Exception:
                pass

        uptime_sec = int(time.time() - self.start_time)
        hours = uptime_sec // 3600
        mins = (uptime_sec % 3600) // 60

        return {
            "board": "Raspberry Pi 5 Model B Rev 1.0 (8GB RAM)",
            "uptime_str": f"{hours}h {mins}m",
            "uptime_sec": uptime_sec,
            "soc": {
                "model": "Broadcom BCM2712 Quad-Core Cortex-A76",
                "arch": "ARMv8.2-A (64-Bit TSMC 16nm)",
                "temp_c": temp_c,
                "temp_f": round(temp_c * 9.0 / 5.0 + 32.0, 1),
                "voltage_v": voltage_v,
                "arm_clock_mhz": arm_mhz,
                "arm_clock_ghz": round(arm_mhz / 1000.0, 2),
                "throttled_hex": throttling.get("raw_hex", "0x0"),
                "is_throttled": throttling.get("is_throttled", False),
                "under_voltage": throttling.get("under_voltage", False),
                "status_text": "Nominal (Full Performance)" if not throttling.get("is_throttled") and not throttling.get("under_voltage") else "Throttling Active"
            },
            "cpu": {
                "core_count": 4,
                "total_pct": round(total_cpu_pct, 1),
                "cores": core_freqs
            },
            "gpu": {
                "model": "Broadcom VideoCore VII (12-Core 3D Engine)",
                "v3d_clock_mhz": v3d_mhz,
                "core_clock_mhz": core_mhz,
                "gpu_mem_mb": gpu_mem_mb,
                "arm_mem_mb": arm_mem_mb,
                "apis": "Vulkan 1.3 / OpenGL ES 3.1 / DRM-KMS",
                "driver": "Mesa V3D"
            },
            "npu": {
                "detected": hailo_detected,
                "model": "Hailo-10H M.2 HAT+ (40 TOPS)" if hailo_detected else "Hailo-10H / Hailo-8 M.2 HAT+ (Supported)",
                "status": "ONLINE - ACCELERATION ACTIVE" if hailo_detected else "SLOT READY (PCIe Gen 3.0 HAT+ Unpopulated)",
                "tops_capacity": "40 TOPS INT8 / FP16" if hailo_detected else "40 TOPS (Hailo-10H) / 26 TOPS (Hailo-8)",
                "onboard_ram": "8 GB Dedicated LPDDR4X" if hailo_detected else "8 GB LPDDR4X (Hailo-10H spec)",
                "target": "Local LLM Inference, Computer Vision, Real-Time Audio AI",
                "price_estimate": "$200 M.2 HAT+",
                "nodes": hailo_nodes if hailo_nodes else ["/dev/hailo0 (Pending Hardware Plug)"]
            },
            "ram": {
                "total_mb": ram_total,
                "used_mb": ram_used,
                "free_mb": ram_free,
                "pct": ram_pct,
                "swap_total_mb": swap_total,
                "swap_used_mb": swap_used,
                "swap_pct": swap_pct
            },
            "storage": {
                "total_gb": storage_total_gb,
                "used_gb": storage_used_gb,
                "free_gb": storage_free_gb,
                "pct": storage_pct
            },
            "peripherals": {
                "usb_devices": usb_devices,
                "interfaces": interfaces,
                "screen": "1024x600 In-Dash Capacitive Touch (Goodix I2C/USB)",
                "brightness_pct": self.current_brightness
            }
        }
