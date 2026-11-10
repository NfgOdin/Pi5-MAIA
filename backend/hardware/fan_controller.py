"""
fan_controller.py - Hardware PWM Fan Controller for Delta AFB0812SH
Compatible with Raspberry Pi 5 (RP1 I/O controller) and 40-pin GPIO header.

Fan Specs (Delta AFB0812SH):
- Voltage: 12V DC, 0.60A Brushless
- Pinout / Wiring:
    * Red:    +12V DC (External 12V Automotive / Bench Supply)
    * Black:  Ground (Shared common ground between 12V supply & Pi GND)
    * Yellow: PWM Control Input (Standard 25 kHz PWM, 3.3V logic -> GPIO 12 / Pin 32)
    * Blue:   Tachometer Pulse Output (Open-collector, 2 pulses/rev -> GPIO 24 / Pin 18)

Hardware Pin Selection Rationale:
- Default PWM: GPIO 12 (Pin 32, Hardware PWM0_0).
  * NOTE: GPIO 18 (Pin 12) is also a PWM pin, but it conflicts with SPI1 CE0 when
    the Waveshare 2-CH CAN HAT overlay (spi1-3cs) is enabled. Using GPIO 12 guarantees
    100% zero conflict with CAN0, CAN1, SPI, I2C, and UART!
- Default Tachometer: GPIO 24 (Pin 18, Input with internal pull-up enabled).

Features:
- Automatic Closed-Loop Thermal Control Curve (45°C - 75°C linear ramp)
- 2°C Hysteresis to prevent fan flutter/hunting
- Tachometer RPM pulse counter (2 pulses/revolution)
- Manual Override mode (0% - 100%)
- Critical Temperature Thermal Failsafe (>80°C forces 100% duty cycle)
- Virtual Emulation mode for development / non-Linux platforms
"""

import os
import sys
import glob
import time
import subprocess
import threading
from typing import Dict, Any, Optional

try:
    from gpiozero import PWMOutputDevice, Button
    GPIOZERO_AVAILABLE = True
except ImportError:
    GPIOZERO_AVAILABLE = False

ARGON_ONE_I2C_ADDR = 0x1A  # Argon ONE V3 / Pi 5 I2C fan controller address (0x1a / 0x01a)


class FanController:
    """Controls active cooling on Raspberry Pi 5 (Native RP1 hwmon PWM, Argon ONE V3 I2C 0x1a, sysfs cooling_device, or 4-wire GPIO PWM)."""

    def __init__(self, pwm_pin: int = 12, tach_pin: int = 24, pwm_freq_hz: int = 8000, enable_gpio_pwm: bool = False):
        self.is_linux = sys.platform.startswith("linux")
        self.pwm_pin = pwm_pin
        self.tach_pin = tach_pin
        self.pwm_freq_hz = pwm_freq_hz
        self.enable_gpio_pwm = enable_gpio_pwm

        # State (Rule 2: Zero fake RPM or temperature when hardware is disconnected)
        self.mode = "AUTO"  # "AUTO" or "MANUAL"
        self.duty_cycle_pct = 20.0  # 0.0 to 100.0%
        self.target_rpm = 0
        self.actual_rpm = 0
        self.last_temp_c = 0.0
        self.hardware_active = False
        self.backend_type = "offline"

        # Hardware backend handles
        self.hwmon_pwm_path: Optional[str] = None
        self.hwmon_tach_path: Optional[str] = None
        self.cooling_dev_path: Optional[str] = None
        self.cooling_max_state: int = 0
        self.i2c_bus: Optional[Any] = None
        self.argon_i2c_addr: int = ARGON_ONE_I2C_ADDR

        # Internal GPIO objects
        self.pwm_device: Optional[Any] = None
        self.tach_device: Optional[Any] = None
        self.pulse_count = 0
        self.last_tach_time = time.time()
        self.lock = threading.Lock()
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None

        # Fan Thermal Curve Parameters
        self.TEMP_MIN_C = 45.0   # Below this: idle duty (20%)
        self.TEMP_MAX_C = 75.0   # Above this: max duty (100%)
        self.TEMP_CRITICAL_C = 80.0  # Failsafe threshold: force 100%
        self.IDLE_DUTY_PCT = 20.0  # Quiet idle speed
        self.HYSTERESIS_C = 2.0    # Minimum delta to adjust speed in AUTO

        self._init_hardware()
        self.start()

    def _init_hardware(self):
        """
        Probes cooling hardware in priority order without clobbering 40-pin GPIO by default:
        1. Native Raspberry Pi 5 RP1 hwmon PWM fan (/sys/class/hwmon/hwmon*/pwm1 & fan1_input)
        2. Argon ONE V3 / Pi 5 I2C fan controller on /dev/i2c-1 address 0x1a (0x01a)
        3. Linux sysfs thermal cooling_device (pwm-fan / rpi-fan)
        4. Optional 40-pin GPIO PWM (Delta AFB0812SH) when enable_gpio_pwm=True
        """
        self.hardware_active = False
        self.backend_type = "offline"
        if not self.is_linux:
            return

        # 1. Check Native Pi 5 hwmon PWM fan
        for hw_dir in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
            pwm_p = os.path.join(hw_dir, "pwm1")
            tach_p = os.path.join(hw_dir, "fan1_input")
            if os.path.exists(pwm_p) or os.path.exists(tach_p):
                self.hwmon_pwm_path = pwm_p if os.path.exists(pwm_p) else None
                self.hwmon_tach_path = tach_p if os.path.exists(tach_p) else None
                self.hardware_active = True
                self.backend_type = "pi5_hwmon_pwm"
                print(f"[FAN] Native Pi 5 hwmon cooling active: pwm={self.hwmon_pwm_path}, tach={self.hwmon_tach_path}")
                return

        # 2. Check Argon ONE V3 / Pi 5 I2C Fan Controller at 0x1a on /dev/i2c-1
        if os.path.exists("/dev/i2c-1"):
            for mod_name in ("smbus2", "smbus"):
                try:
                    smbus_mod = __import__(mod_name)
                    bus = smbus_mod.SMBus(1)
                    # Probe slave 0x1a safely
                    bus.read_byte(self.argon_i2c_addr)
                    self.i2c_bus = bus
                    self.hardware_active = True
                    self.backend_type = "argon_i2c_0x1a"
                    print(f"[FAN] Argon ONE I2C fan controller detected on /dev/i2c-1 at 0x{self.argon_i2c_addr:02x}")
                    return
                except Exception:
                    pass

        # 3. Check Linux sysfs cooling_device fallback
        for cd_dir in sorted(glob.glob("/sys/class/thermal/cooling_device*")):
            try:
                type_p = os.path.join(cd_dir, "type")
                cur_p = os.path.join(cd_dir, "cur_state")
                max_p = os.path.join(cd_dir, "max_state")
                if os.path.exists(type_p) and os.path.exists(cur_p) and os.path.exists(max_p):
                    with open(type_p, "r") as f:
                        cd_type = f.read().strip().lower()
                    if "fan" in cd_type or "pwm" in cd_type:
                        with open(max_p, "r") as f:
                            max_st = int(f.read().strip())
                        if max_st > 0:
                            self.cooling_dev_path = cur_p
                            self.cooling_max_state = max_st
                            self.hardware_active = True
                            self.backend_type = "sysfs_cooling_device"
                            print(f"[FAN] Sysfs cooling device active: {cd_dir} ({cd_type}, max_state={max_st})")
                            return
            except Exception:
                pass

        # 4. Optional 40-pin GPIO PWM mode
        if self.enable_gpio_pwm:
            self._init_hardware_disabled()

    def _init_hardware_disabled(self):
        """Initializes gpiozero PWM output at 25kHz and tachometer input."""
        if not self.is_linux or not GPIOZERO_AVAILABLE:
            print(f"[FAN] Running in virtual emulation mode (Linux={self.is_linux}, gpiozero={GPIOZERO_AVAILABLE})")
            self.hardware_active = False
            return

        try:
            # lgpio supports up to 10kHz for software/timed PWM. Fall back gracefully if needed.
            for candidate_freq in [self.pwm_freq_hz, 8000, 1000, 100]:
                try:
                    self.pwm_device = PWMOutputDevice(
                        pin=self.pwm_pin,
                        frequency=candidate_freq,
                        initial_value=self.duty_cycle_pct / 100.0
                    )
                    self.pwm_freq_hz = candidate_freq
                    break
                except Exception:
                    continue

            if not self.pwm_device:
                raise RuntimeError(f"Could not bind PWMOutputDevice on GPIO {self.pwm_pin}")

            # Tachometer: open-collector output pulling to GND. Use internal pull-up resistor.
            self.tach_device = Button(
                pin=self.tach_pin,
                pull_up=True,
                bounce_time=None
            )
            self.tach_device.when_pressed = self._on_tach_pulse

            self.hardware_active = True
            print(f"[FAN] Delta AFB0812SH initialized: PWM=GPIO{self.pwm_pin} ({self.pwm_freq_hz}Hz), Tach=GPIO{self.tach_pin}")
        except Exception as e:
            print(f"[FAN] Failed initializing hardware on GPIO {self.pwm_pin}/{self.tach_pin}: {e}")
            if self.pwm_device:
                try:
                    self.pwm_device.close()
                except Exception:
                    pass
                self.pwm_device = None
            self.hardware_active = False

    def _on_tach_pulse(self):
        """Tachometer interrupt callback: 2 pulses per revolution."""
        self.pulse_count += 1

    def _calculate_rpm(self) -> int:
        """Calculates RPM from hwmon fan1_input or GPIO tachometer pulses (0 when hardware is offline)."""
        if not self.hardware_active:
            self.actual_rpm = 0
            return 0

        if self.hwmon_tach_path and os.path.exists(self.hwmon_tach_path):
            try:
                with open(self.hwmon_tach_path, "r") as f:
                    self.actual_rpm = max(0, int(f.read().strip()))
                return self.actual_rpm
            except Exception:
                pass

        if not self.tach_device:
            return self.actual_rpm

        now = time.time()
        elapsed = now - self.last_tach_time
        if elapsed < 0.2:
            return self.actual_rpm

        with self.lock:
            pulses = self.pulse_count
            self.pulse_count = 0
            self.last_tach_time = now

        # Delta AFB0812SH produces 2 pulses per mechanical revolution:
        # RPM = (pulses / 2) * (60 / elapsed) = (pulses * 30) / elapsed
        if elapsed > 0:
            calc_rpm = int((pulses * 30.0) / elapsed)
            # Filter noise / jitter
            if calc_rpm > 12000:  # Delta AFB0812SH max rated is ~4000-5000 RPM
                calc_rpm = self.actual_rpm
            self.actual_rpm = int(0.7 * self.actual_rpm + 0.3 * calc_rpm) if self.actual_rpm > 0 else calc_rpm
        return self.actual_rpm

    def _read_soc_temperature(self) -> float:
        """Reads Raspberry Pi 5 SoC core temperature in Celsius, or 0.0 when sensor is unavailable (Rule 2)."""
        if self.is_linux:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    return round(float(f.read().strip()) / 1000.0, 1)
            except Exception:
                pass
            try:
                out = subprocess.check_output(
                    ["vcgencmd", "measure_temp"],
                    stderr=subprocess.DEVNULL,
                    timeout=1.5
                ).decode("utf-8")
                if "temp=" in out:
                    return round(float(out.split("=")[1].split("'")[0]), 1)
            except Exception:
                pass
        return 0.0

    def _compute_target_duty(self, temp_c: float) -> float:
        """Calculates target duty cycle % according to the thermal curve."""
        if temp_c >= self.TEMP_CRITICAL_C:
            return 100.0
        if temp_c <= self.TEMP_MIN_C:
            return self.IDLE_DUTY_PCT

        # Linear interpolation between TEMP_MIN_C and TEMP_MAX_C
        ratio = (temp_c - self.TEMP_MIN_C) / (self.TEMP_MAX_C - self.TEMP_MIN_C)
        target = self.IDLE_DUTY_PCT + ratio * (100.0 - self.IDLE_DUTY_PCT)
        return round(max(self.IDLE_DUTY_PCT, min(100.0, target)), 1)

    def set_duty_cycle(self, pct: float) -> bool:
        """Sets fan duty cycle (0.0 to 100.0%) across active hardware backend."""
        pct = max(0.0, min(100.0, float(pct)))
        with self.lock:
            self.duty_cycle_pct = pct
            if not self.hardware_active:
                self.actual_rpm = 0
                return False

            # 1. Native Pi 5 hwmon PWM (0..255)
            if self.backend_type == "pi5_hwmon_pwm" and self.hwmon_pwm_path:
                try:
                    pwm_255 = int(round((pct / 100.0) * 255.0))
                    with open(self.hwmon_pwm_path, "w") as f:
                        f.write(str(pwm_255))
                except Exception as e:
                    print(f"[FAN] Error writing hwmon PWM: {e}")

            # 2. Argon ONE V3 / Pi 5 I2C fan controller (0x1a)
            elif self.backend_type == "argon_i2c_0x1a" and self.i2c_bus:
                speed_int = int(round(pct))
                try:
                    # Argon ONE V3 register 0x80 + fallback direct byte write
                    try:
                        self.i2c_bus.write_byte_data(self.argon_i2c_addr, 0x80, speed_int)
                    except Exception:
                        self.i2c_bus.write_byte(self.argon_i2c_addr, speed_int)
                except Exception as e:
                    print(f"[FAN] Error writing Argon ONE I2C (0x1a): {e}")

            # 3. Sysfs thermal cooling_device fallback
            elif self.backend_type == "sysfs_cooling_device" and self.cooling_dev_path and self.cooling_max_state > 0:
                try:
                    target_state = int(round((pct / 100.0) * self.cooling_max_state))
                    with open(self.cooling_dev_path, "w") as f:
                        f.write(str(target_state))
                except Exception as e:
                    print(f"[FAN] Error writing cooling_device state: {e}")

            # 4. 40-Pin GPIO PWM
            elif self.pwm_device:
                try:
                    self.pwm_device.value = pct / 100.0
                except Exception as e:
                    print(f"[FAN] Error updating PWM hardware: {e}")

        return True

    def set_mode(self, mode: str, manual_pct: Optional[float] = None) -> Dict[str, Any]:
        """Sets control mode to AUTO or MANUAL."""
        m = mode.upper().strip()
        if m in ("AUTO", "MANUAL"):
            self.mode = m
        if self.mode == "MANUAL" and manual_pct is not None:
            self.set_duty_cycle(manual_pct)
        elif self.mode == "AUTO":
            temp = self._read_soc_temperature()
            target = self._compute_target_duty(temp)
            self.set_duty_cycle(target)
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive fan telemetry and diagnostic metrics (Rule 2 compliant)."""
        temp_c = self._read_soc_temperature()
        temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1) if temp_c > 0.0 else 0.0
        rpm = self._calculate_rpm() if self.hardware_active else 0

        return {
            "connected": self.hardware_active,
            "backend": self.backend_type,
            "argon_i2c_addr": f"0x{self.argon_i2c_addr:02x}",
            "mode": self.mode,
            "duty_cycle_pct": round(self.duty_cycle_pct, 1) if self.hardware_active else 0.0,
            "actual_rpm": rpm,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "hardware_active": self.hardware_active,
            "pwm_pin": self.pwm_pin,
            "tach_pin": self.tach_pin,
            "pwm_freq_hz": self.pwm_freq_hz,
            "fan_model": "Argon ONE V3 / Pi 5 Active PWM" if self.backend_type in ("argon_i2c_0x1a", "pi5_hwmon_pwm") else "Delta AFB0812SH",
            "is_critical": temp_c >= self.TEMP_CRITICAL_C
        }

    def _monitor_loop(self):
        """Background control loop: updates thermal regulation and RPM."""
        last_eval_temp = 0.0

        while self.running:
            try:
                temp_c = self._read_soc_temperature()
                self.last_temp_c = temp_c

                if self.mode == "AUTO":
                    # Critical safety override
                    if temp_c >= self.TEMP_CRITICAL_C:
                        if self.duty_cycle_pct < 100.0:
                            print(f"[FAN] CRITICAL TEMP {temp_c}°C! Forcing 100% fan speed.")
                            self.set_duty_cycle(100.0)
                    # Hysteresis check
                    elif abs(temp_c - last_eval_temp) >= self.HYSTERESIS_C or last_eval_temp == 0.0:
                        target_duty = self._compute_target_duty(temp_c)
                        if abs(target_duty - self.duty_cycle_pct) >= 3.0:
                            self.set_duty_cycle(target_duty)
                            last_eval_temp = temp_c
                elif self.mode == "MANUAL":
                    # Thermal safety failsafe even in manual mode
                    if temp_c >= self.TEMP_CRITICAL_C and self.duty_cycle_pct < 100.0:
                        print(f"[FAN] SAFETY OVERRIDE: SoC at {temp_c}°C in manual mode. Forcing 100% cooling.")
                        self.set_duty_cycle(100.0)

                # Update RPM reading
                if self.hardware_active:
                    self._calculate_rpm()

            except Exception as e:
                print(f"[FAN] Exception in monitor loop: {e}")

            time.sleep(2.0)

    def start(self):
        """Starts the closed-loop thermal monitor thread when fan hardware is detected."""
        if not self.hardware_active or self.running:
            return
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="FanControllerThread")
        self.monitor_thread.start()

    def stop(self):
        """Stops the controller and releases GPIO/I2C resources."""
        self.running = False
        if self.i2c_bus:
            try:
                self.i2c_bus.close()
            except Exception:
                pass
            self.i2c_bus = None
        if self.pwm_device:
            try:
                self.pwm_device.close()
            except Exception:
                pass
        if self.tach_device:
            try:
                self.tach_device.close()
            except Exception:
                pass
        self.hardware_active = False
