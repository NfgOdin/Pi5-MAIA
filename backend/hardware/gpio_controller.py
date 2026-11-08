"""
gpio_controller.py - Hardware GPIO & PWM Controller for Raspberry Pi 5
Derived from and 100% compatible with O.D.I.N. gpio_page.py architecture.
Uses gpiozero + LGPIOFactory (RP1 chip compatible on Pi 5 / Debian Bookworm & Trixie).
Provides:
- 40-Pin header mapping with live state, mode (OUT, PWM, IN), and duty cycle
- Hardware PWM (duty cycle 0.0 - 1.0) on GPIO 12, 13, 18, 19
- 12V Automotive Relays (Aux lights, Underglow, Radar/Cam, Intercooler Sprayer)
- Morse code beacon transmitter
- Persistent pin state saved to config/gpio_state.json
- Graceful virtual emulation fallback for Windows/development
"""

import os
import sys
import json
import time
import threading
from typing import Dict, List, Any, Optional

# Standard 40-Pin Raspberry Pi Header Definition
PIN_MAP_40 = [
    {"pin": 1, "name": "3.3V Power", "type": "power", "bcm": None, "state": True, "mode": "PWR", "pwm": False},
    {"pin": 2, "name": "5V Power", "type": "power", "bcm": None, "state": True, "mode": "PWR", "pwm": False},
    {"pin": 3, "name": "GPIO 2 (SDA)", "type": "gpio", "bcm": 2, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 4, "name": "5V Power", "type": "power", "bcm": None, "state": True, "mode": "PWR", "pwm": False},
    {"pin": 5, "name": "GPIO 3 (SCL)", "type": "gpio", "bcm": 3, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 6, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 7, "name": "GPIO 4", "type": "gpio", "bcm": 4, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 8, "name": "GPIO 14 (TXD)", "type": "gpio", "bcm": 14, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 9, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 10, "name": "GPIO 15 (RXD)", "type": "gpio", "bcm": 15, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 11, "name": "GPIO 17 (Relay 1: Aux Lights)", "type": "gpio", "bcm": 17, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 12, "name": "GPIO 18 (Beacon / PWM0)", "type": "gpio", "bcm": 18, "state": False, "mode": "PWM", "pwm": True},
    {"pin": 13, "name": "GPIO 27 (Relay 2: Underglow)", "type": "gpio", "bcm": 27, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 14, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 15, "name": "GPIO 22 (Relay 3: Radar/Cam)", "type": "gpio", "bcm": 22, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 16, "name": "GPIO 23 (Relay 4: Aux Sprayer)", "type": "gpio", "bcm": 23, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 17, "name": "3.3V Power", "type": "power", "bcm": None, "state": True, "mode": "PWR", "pwm": False},
    {"pin": 18, "name": "GPIO 24", "type": "gpio", "bcm": 24, "state": False, "mode": "IN", "pwm": False},
    {"pin": 19, "name": "GPIO 10 (MOSI)", "type": "gpio", "bcm": 10, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 20, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 21, "name": "GPIO 9 (MISO)", "type": "gpio", "bcm": 9, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 22, "name": "GPIO 25", "type": "gpio", "bcm": 25, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 23, "name": "GPIO 11 (SCLK)", "type": "gpio", "bcm": 11, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 24, "name": "GPIO 8 (CE0)", "type": "gpio", "bcm": 8, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 25, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 26, "name": "GPIO 7 (CE1)", "type": "gpio", "bcm": 7, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 27, "name": "ID_SD (I2C EEPROM)", "type": "system", "bcm": 0, "state": False, "mode": "SYS", "pwm": False},
    {"pin": 28, "name": "ID_SC (I2C EEPROM)", "type": "system", "bcm": 1, "state": False, "mode": "SYS", "pwm": False},
    {"pin": 29, "name": "GPIO 5", "type": "gpio", "bcm": 5, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 30, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 31, "name": "GPIO 6", "type": "gpio", "bcm": 6, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 32, "name": "GPIO 12", "type": "gpio", "bcm": 12, "state": False, "mode": "IN", "pwm": False},
    {"pin": 33, "name": "GPIO 13 (PWM1)", "type": "gpio", "bcm": 13, "state": False, "mode": "PWM", "pwm": True},
    {"pin": 34, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 35, "name": "GPIO 19 (PWM1)", "type": "gpio", "bcm": 19, "state": False, "mode": "PWM", "pwm": True},
    {"pin": 36, "name": "GPIO 16", "type": "gpio", "bcm": 16, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 37, "name": "GPIO 26", "type": "gpio", "bcm": 26, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 38, "name": "GPIO 20", "type": "gpio", "bcm": 20, "state": False, "mode": "OUT", "pwm": False},
    {"pin": 39, "name": "Ground", "type": "ground", "bcm": None, "state": False, "mode": "GND", "pwm": False},
    {"pin": 40, "name": "GPIO 21", "type": "gpio", "bcm": 21, "state": False, "mode": "OUT", "pwm": False}
]

# Quick 12V Automotive Relays Preset Definitions
RELAY_PRESETS = [
    {"id": "relay1", "bcm": 17, "name": "Aux Fog Lights", "icon": "💡", "desc": "Front high-output LED driving pods"},
    {"id": "relay2", "bcm": 27, "name": "Ambient Underglow", "icon": "✨", "desc": "Exterior chassis & interior footwell LEDs"},
    {"id": "relay3", "bcm": 22, "name": "Radar & Dashcam", "icon": "📹", "desc": "Hardwired windshield power accessories"},
    {"id": "relay4", "bcm": 23, "name": "Intercooler Sprayer", "icon": "❄️", "desc": "MultiAir water injection / aux cooling"}
]

# Morse Code Dictionary
MORSE_CODE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..', '0': '-----', '1': '.----', '2': '..---',
    '3': '...--', '4': '....-', '5': '.....', '6': '-....', '7': '--...',
    '8': '---..', '9': '----.', ' ': '/'
}

class GpioController:
    def __init__(self, state_file: Optional[str] = None):
        self.is_linux = sys.platform.startswith("linux")
        self.hardware_active = False
        self.state_file = state_file or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gpio_state.json")
        self.pin_states: Dict[int, bool] = {}
        self.pin_modes: Dict[int, str] = {}         # "OUT", "PWM", "IN"
        self.pin_duty_cycles: Dict[int, float] = {}  # 0.0 to 1.0
        self.active_devices: Dict[int, Any] = {}
        self.morse_thread: Optional[threading.Thread] = None
        self.morse_running = False
        self.lock = threading.Lock()

        # Initialize pin structures
        for p in PIN_MAP_40:
            if p["bcm"] is not None:
                bcm = p["bcm"]
                self.pin_states[bcm] = False
                self.pin_modes[bcm] = p["mode"]
                self.pin_duty_cycles[bcm] = 0.0

        self._init_hardware()
        self.load_persistent_states()

    def _init_hardware(self):
        """Initializes gpiozero with LGPIOFactory on Linux (Raspberry Pi 5 RP1 compatible)."""
        if self.is_linux:
            try:
                import gpiozero
                from gpiozero.pins.lgpio import LGPIOFactory
                gpiozero.Device.pin_factory = LGPIOFactory()
                self.hardware_active = True
                print("[GPIO] Hardware GPIO initialized via gpiozero + LGPIOFactory (Pi 5 RP1 native).")
            except Exception as e:
                print(f"[GPIO] Real hardware GPIO unavailable ({e}). Virtual emulation active.")
                self.hardware_active = False
        else:
            print("[GPIO] Running in dev environment. Virtual GPIO emulation active.")
            self.hardware_active = False

    def get_pins_status(self) -> List[Dict[str, Any]]:
        """Returns the full 40-pin header map with live state and PWM duty cycle."""
        with self.lock:
            pins_copy = []
            for p in PIN_MAP_40:
                item = dict(p)
                bcm = item["bcm"]
                if bcm is not None:
                    item["state"] = self.pin_states.get(bcm, False)
                    item["mode"] = self.pin_modes.get(bcm, "OUT")
                    item["duty_cycle"] = round(self.pin_duty_cycles.get(bcm, 0.0), 3)
                pins_copy.append(item)
            return pins_copy

    def get_relays_status(self) -> List[Dict[str, Any]]:
        """Returns status of the 4 dedicated automotive relays."""
        with self.lock:
            relays = []
            for r in RELAY_PRESETS:
                r_copy = dict(r)
                bcm = r["bcm"]
                r_copy["state"] = self.pin_states.get(bcm, False)
                relays.append(r_copy)
            return relays

    def set_pin(self, bcm: int, state: bool) -> bool:
        """Sets a specific BCM pin HIGH (True) or LOW (False)."""
        bcm = int(bcm)
        state = bool(state)

        with self.lock:
            self.pin_states[bcm] = state
            self.pin_modes[bcm] = "OUT"
            self.pin_duty_cycles[bcm] = 1.0 if state else 0.0

            if self.hardware_active:
                try:
                    from gpiozero import LED, PWMLED
                    if bcm in self.active_devices:
                        dev = self.active_devices[bcm]
                        if isinstance(dev, PWMLED):
                            dev.close()
                            del self.active_devices[bcm]

                    if bcm not in self.active_devices:
                        self.active_devices[bcm] = LED(bcm)
                    
                    if state:
                        self.active_devices[bcm].on()
                    else:
                        self.active_devices[bcm].off()
                except Exception as e:
                    print(f"[GPIO] Hardware write error on BCM {bcm}: {e}")

        self.save_persistent_states()
        print(f"[GPIO] BCM {bcm} set to {'HIGH' if state else 'LOW'}")
        return True

    def toggle_pin(self, bcm: int) -> bool:
        cur = self.pin_states.get(bcm, False)
        return self.set_pin(bcm, not cur)

    def set_pwm(self, bcm: int, duty_cycle: float) -> bool:
        """Sets PWM duty cycle (0.0 to 1.0) on a pin."""
        bcm = int(bcm)
        duty_cycle = max(0.0, min(1.0, float(duty_cycle)))

        with self.lock:
            self.pin_modes[bcm] = "PWM"
            self.pin_duty_cycles[bcm] = duty_cycle
            self.pin_states[bcm] = duty_cycle > 0.0

            if self.hardware_active:
                try:
                    from gpiozero import LED, PWMLED
                    if bcm in self.active_devices:
                        dev = self.active_devices[bcm]
                        if isinstance(dev, LED):
                            dev.close()
                            del self.active_devices[bcm]

                    if bcm not in self.active_devices:
                        self.active_devices[bcm] = PWMLED(bcm)
                    
                    self.active_devices[bcm].value = duty_cycle
                except Exception as e:
                    print(f"[GPIO] PWM error on BCM {bcm}: {e}")

        self.save_persistent_states()
        print(f"[GPIO] BCM {bcm} set to PWM {int(duty_cycle * 100)}%")
        return True

    def pulse_pin(self, bcm: int, duration_sec: float = 0.5):
        """Temporarily energizes a pin then de-energizes it."""
        def _pulse():
            self.set_pin(bcm, True)
            time.sleep(duration_sec)
            self.set_pin(bcm, False)
        threading.Thread(target=_pulse, daemon=True).start()

    def transmit_morse(self, text: str, bcm: int = 18, dot_duration: float = 0.08):
        """Transmits Morse code via hardware pin / beacon LED."""
        if self.morse_running:
            self.morse_running = False
            if self.morse_thread:
                self.morse_thread.join(timeout=1.0)

        def _worker():
            self.morse_running = True
            dash = dot_duration * 3
            inter_elem = dot_duration
            inter_letter = dot_duration * 3
            word_gap = dot_duration * 7

            for char in text.upper():
                if not self.morse_running:
                    break
                code = MORSE_CODE.get(char)
                if not code:
                    time.sleep(inter_letter)
                    continue
                if code == '/':
                    time.sleep(word_gap)
                    continue

                for symbol in code:
                    if not self.morse_running:
                        break
                    self.set_pin(bcm, True)
                    time.sleep(dot_duration if symbol == '.' else dash)
                    self.set_pin(bcm, False)
                    time.sleep(inter_elem)

                time.sleep(inter_letter)

            self.morse_running = False

        self.morse_thread = threading.Thread(target=_worker, daemon=True)
        self.morse_thread.start()

    def load_persistent_states(self):
        """Loads saved pin configurations from gpio_state.json (ODIN parity)."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for bcm_str, info in data.items():
                        bcm = int(bcm_str)
                        if bcm in self.pin_states:
                            mode = info.get("mode", "OUT")
                            state = info.get("state", False)
                            duty = float(info.get("duty_cycle", 0.0))
                            if mode == "PWM":
                                self.set_pwm(bcm, duty)
                            else:
                                self.set_pin(bcm, state)
                print("[GPIO] Restored persistent pin states from file.")
            except Exception as e:
                print(f"[GPIO] Error loading persistent state: {e}")

    def save_persistent_states(self):
        """Saves current pin states to gpio_state.json."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_file)), exist_ok=True)
            saved = {}
            for bcm, state in self.pin_states.items():
                saved[str(bcm)] = {
                    "mode": self.pin_modes.get(bcm, "OUT"),
                    "state": state,
                    "duty_cycle": self.pin_duty_cycles.get(bcm, 0.0)
                }
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(saved, f, indent=2)
        except Exception as e:
            print(f"[GPIO] Error saving persistent state: {e}")
