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
import time
import threading
from typing import Dict, Any, Optional

try:
    from gpiozero import PWMOutputDevice, Button
    GPIOZERO_AVAILABLE = True
except ImportError:
    GPIOZERO_AVAILABLE = False


class FanController:
    """Controls a 4-wire PWM fan (Delta AFB0812SH or compatible) on Raspberry Pi 5."""

    def __init__(self, pwm_pin: int = 12, tach_pin: int = 24, pwm_freq_hz: int = 25000):
        self.is_linux = sys.platform.startswith("linux")
        self.pwm_pin = pwm_pin
        self.tach_pin = tach_pin
        self.pwm_freq_hz = pwm_freq_hz

        # State
        self.mode = "AUTO"  # "AUTO" or "MANUAL"
        self.duty_cycle_pct = 20.0  # 0.0 to 100.0%
        self.target_rpm = 0
        self.actual_rpm = 0
        self.last_temp_c = 45.0
        self.hardware_active = False

        # Internal objects
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
        """Initializes gpiozero PWM output at 25kHz and tachometer input."""
        if not self.is_linux or not GPIOZERO_AVAILABLE:
            print(f"[FAN] Running in virtual emulation mode (Linux={self.is_linux}, gpiozero={GPIOZERO_AVAILABLE})")
            self.hardware_active = False
            return

        try:
            # Standard PC 4-wire fans require 25 kHz PWM frequency
            self.pwm_device = PWMOutputDevice(
                pin=self.pwm_pin,
                frequency=self.pwm_freq_hz,
                initial_value=self.duty_cycle_pct / 100.0
            )

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
            self.hardware_active = False

    def _on_tach_pulse(self):
        """Tachometer interrupt callback: 2 pulses per revolution."""
        self.pulse_count += 1

    def _calculate_rpm(self) -> int:
        """Calculates RPM based on pulses accumulated since last read."""
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
        """Reads Raspberry Pi 5 SoC core temperature in Celsius."""
        if self.is_linux:
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    return round(float(f.read().strip()) / 1000.0, 1)
            except Exception:
                pass
        return 48.0  # Emulation baseline

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
        """Sets fan duty cycle (0.0 to 100.0%)."""
        pct = max(0.0, min(100.0, float(pct)))
        with self.lock:
            self.duty_cycle_pct = pct
            if self.hardware_active and self.pwm_device:
                try:
                    self.pwm_device.value = pct / 100.0
                except Exception as e:
                    print(f"[FAN] Error updating PWM hardware: {e}")

        # Update simulated RPM for preview/emulation
        # Delta AFB0812SH max rated speed is ~4000 RPM
        if not self.hardware_active:
            self.actual_rpm = int((pct / 100.0) * 4000)
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
        """Returns comprehensive fan telemetry and diagnostic metrics."""
        temp_c = self._read_soc_temperature()
        temp_f = round(temp_c * 9.0 / 5.0 + 32.0, 1)
        rpm = self._calculate_rpm() if self.hardware_active else self.actual_rpm

        return {
            "mode": self.mode,
            "duty_cycle_pct": round(self.duty_cycle_pct, 1),
            "actual_rpm": rpm,
            "temp_c": temp_c,
            "temp_f": temp_f,
            "hardware_active": self.hardware_active,
            "pwm_pin": self.pwm_pin,
            "tach_pin": self.tach_pin,
            "pwm_freq_hz": self.pwm_freq_hz,
            "fan_model": "Delta AFB0812SH",
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
        """Starts the background thermal management thread."""
        if not self.running:
            self.running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="FanControllerThread")
            self.monitor_thread.start()

    def stop(self):
        """Stops the controller and releases GPIO resources."""
        self.running = False
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
