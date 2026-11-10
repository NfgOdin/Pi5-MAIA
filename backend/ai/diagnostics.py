"""
diagnostics.py - Plain-English Diagnostic Trouble Code (DTC) Knowledge Base
Translates Dodge Dart & 1.4L Turbo MultiAir engine trouble codes into
actionable, non-jargon explanations and repair recommendations.
"""

from typing import Dict, Any, Optional

DART_14T_DTC_DATABASE: Dict[str, Dict[str, str]] = {
    "P0299": {
        "title": "Turbocharger Underboost Condition",
        "severity": "Medium",
        "severity_badge": "SAFE TO DRIVE GENTLY",
        "severity_color": "#ffaa00",
        "description": "The manifold absolute pressure (MAP) sensor measured less boost pressure than the Magneti Marelli ECU targeted.",
        "common_causes": "1. Loose silicone intercooler clamp under front bumper.\n2. Torn rubber diaphragm on factory Pierburg diverter valve.\n3. Vacuum line leak to wastegate solenoid (N75).",
        "advice": "Safe to finish your trip. Avoid heavy acceleration. Inspect the driver's side intercooler hose clamp behind the bumper fog light bezel."
    },
    "P0234": {
        "title": "Turbocharger Overboost Condition",
        "severity": "High",
        "severity_badge": "POTENTIAL ENGINE RISK",
        "severity_color": "#ff3344",
        "description": "The turbo produced boost pressure exceeding the safe factory limit (spiking past 21 PSI).",
        "common_causes": "1. Stuck wastegate actuator arm.\n2. Failed wastegate control solenoid valve.\n3. Split or melted wastegate actuator vacuum hose.",
        "advice": "Do not go full throttle! Drive with light pedal pressure to prevent overboost fuel-cuts and ringland stress."
    },
    "P0300": {
        "title": "Random / Multiple Cylinder Misfire",
        "severity": "High",
        "severity_badge": "INSPECT PROMPTLY",
        "severity_color": "#ff3344",
        "description": "Combustion failure detected across multiple cylinders. If flashing, unburned fuel is entering the catalytic converter.",
        "common_causes": "1. Fouled spark plugs (1.4T requires NGK Iridium at 0.024-0.026\" gap).\n2. MultiAir actuator oil starvation from overdue oil changes.\n3. Ignition coil pack boots arcing to cylinder head.",
        "advice": "If Check Engine light is solid: drive home gently. If Check Engine light is blinking: pull over immediately and shut off engine."
    },
    "P0302": {
        "title": "Cylinder 2 Misfire Detected",
        "severity": "Medium-High",
        "severity_badge": "REPLACE PLUG / COIL",
        "severity_color": "#ff7700",
        "description": "Cylinder #2 failed to complete a proper combustion stroke.",
        "common_causes": "1. Worn cylinder #2 spark plug or burnt electrode.\n2. Failing Bosch/Mopar ignition coil pack on cylinder #2.\n3. MultiAir hydraulic solenoid sticking on intake valve #2.",
        "advice": "Swap coil pack #2 with cylinder #1. If code moves to P0301, replace the coil. Check spark plug gap (0.026 inch)."
    },
    "P0128": {
        "title": "Coolant Temp Below Thermostat Regulating Temp",
        "severity": "Low",
        "severity_badge": "SAFE TO DRIVE",
        "severity_color": "#00b0ff",
        "description": "The engine is taking longer than expected to reach full operating temperature (185°F).",
        "common_causes": "1. Thermostat rubber gasket deteriorated, sticking valve open.\n2. Defective engine coolant temperature sensor.\n3. Air pocket in cooling system.",
        "advice": "Completely safe to drive home. Your cabin heater will take longer to blow hot air. Replace thermostat housing this weekend."
    },
    "P0520": {
        "title": "Engine Oil Pressure Sensor Circuit Malfunction",
        "severity": "Critical",
        "severity_badge": "CHECK OIL DIPSTICK NOW",
        "severity_color": "#ff1744",
        "description": "Oil pressure switch circuit failed. MultiAir valve actuation depends entirely on high oil pressure.",
        "common_causes": "1. Extremely low engine oil level (MultiAir will cease running).\n2. Failed Chrysler oil pressure sending unit (very common failure).\n3. Damaged sensor harness near oil filter housing.",
        "advice": "Shut engine off and check oil dipstick! If oil level is full, the sensor sending unit has likely failed."
    },
    "P1066": {
        "title": "MultiAir Cylinder 1 Solenoid Valve Switch-Off Timing",
        "severity": "High",
        "severity_badge": "CHECK 5W-40 OIL & SCREEN",
        "severity_color": "#ff3344",
        "description": "The UniAir electro-hydraulic intake valve actuator on Cylinder 1 detected abnormal solenoid response timing.",
        "common_causes": "1. Incorrect oil viscosity (requires strictly SAE 5W-40 Full Synthetic MS-12991).\n2. Clogged MultiAir actuator oil supply micro-screen (Mopar 55238665).\n3. Low engine oil level aerating the hydraulic brick.",
        "advice": "Verify oil level on dipstick immediately, change to fresh 5W-40 Euro full synthetic oil, and inspect the MultiAir filter screen."
    }
}

class DiagnosticManager:
    def __init__(self):
        self.db = DART_14T_DTC_DATABASE

    def explain_code(self, code: str) -> Dict[str, Any]:
        code = str(code or "UNKNOWN").strip().upper()
        if code in self.db:
            entry = self.db[code]
            return {
                "code": code,
                "found": True,
                "title": entry["title"],
                "severity": entry["severity"],
                "severity_badge": entry.get("severity_badge", "INSPECT"),
                "severity_color": entry.get("severity_color", "#ffaa00"),
                "description": entry["description"],
                "common_causes": entry["common_causes"],
                "advice": entry["advice"],
                "spoken_summary": f"Diagnostic code {code}: {entry['title']}. {entry['advice']}",
                "full_details": f"{entry['description']} Common causes: {entry['common_causes']}"
            }
        
        return {
            "code": code,
            "found": False,
            "title": "Generic Powertrain Code",
            "severity": "Unknown",
            "severity_badge": "INSPECT VEHICLE",
            "severity_color": "#ffaa00",
            "description": f"Standard OBD-II trouble code {code}.",
            "common_causes": "Check Dodge Dart factory service manual for circuit wiring.",
            "advice": "Scan using a dealership-level scan tool to read freeze-frame data.",
            "spoken_summary": f"Detected diagnostic trouble code {code}. Check vehicle service manual for details.",
            "full_details": "No specific Dodge Dart 1.4T bulletin matched in local database."
        }
