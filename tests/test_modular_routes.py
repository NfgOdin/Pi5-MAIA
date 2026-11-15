"""Automated smoke tests for modularized CarPi5 HTTP route dispatchers."""

import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import dispatch_get, dispatch_head, dispatch_post
from routes import system_routes


class DummyHandler:
    """Minimal HTTP handler double capturing status, headers, and JSON response body."""

    def __init__(self, body: dict = None):
        raw = json.dumps(body).encode("utf-8") if body is not None else b""
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.wfile = io.BytesIO()
        self.status = None
        self.resp_headers = {}
        self.error = None

    def send_response(self, status):
        self.status = status

    def send_header(self, k, v):
        self.resp_headers[k] = v

    def end_headers(self):
        pass

    def send_error(self, code, msg=""):
        self.error = (code, msg)

    def json_body(self):
        return json.loads(self.wfile.getvalue().decode("utf-8"))


def make_dummy_state():
    dyno = SimpleNamespace(
        current_whp=120.5,
        current_wtq=140.2,
        peak_whp=160.0,
        peak_wtq=184.0,
        peak_whp_rpm=5500,
        peak_wtq_rpm=3200,
        wastegate_health_pct=92.0,
        latest_spool_gradient=9.8,
        recent_spool_runs=[],
        latest_shift_score=95.0,
        latest_shift_type="CRISP",
        latest_shift_delta=120,
        total_shift_score=95.0,
        total_shift_count=1,
        shift_history=[],
        estimated_oil_temp_f=190.4,
        multiair_status="WARM_OPTIMAL",
    )
    return SimpleNamespace(
        telemetry_mode="SIM",
        lock=threading.Lock(),
        latest_ui_action=None,
        latest_frame=SimpleNamespace(speed_mph=0.0),
        last_frame={"rpm": 900, "boost_psi": -8.2, "coolant_temp_f": 192, "speed_mph": 0, "engine_load_pct": 18.0, "pedal_pos_pct": 10.0},
        latest_thermal_data=None,
        is_music_playing=False,
        save_settings=lambda cfg: None,
        obd_reader=SimpleNamespace(connected=False, status_message="Offline", dyno=dyno, active_dtcs=[], clear_dtcs=lambda: None),
        simulator=SimpleNamespace(
            dyno=dyno,
            active_dtcs=["P0299"],
            inject_dtc=lambda code: None,
            clear_dtcs=lambda: None,
        ),
        copilot=SimpleNamespace(
            diagnostics=SimpleNamespace(explain_code=lambda c: {"code": c, "title": "Turbo Underboost"}),
            announced_dtcs={"P0299"},
        ),
        gps=SimpleNamespace(
            get_telemetry=lambda: {"dragy": {}, "g_forces": {}, "speed_mph": 0.0, "road_grade_pct": 0.0},
            arm_staging=lambda tree: {"status": "ok", "state": "STAGED", "tree": tree},
            reset_dragy=lambda: {"status": "ok", "state": "IDLE"},
        ),
        thermal_model=SimpleNamespace(step=lambda spd: {"brakes": {"status": "OPTIMAL"}, "tires": {}}),
        lap_timer=SimpleNamespace(
            get_status=lambda: {"state": "IDLE"},
            get_tracks=lambda: [{"id": "pinal_pass"}],
            arm=lambda: None,
            start_manual=lambda: None,
            stop=lambda: None,
            reset=lambda: None,
            set_track=lambda tid: None,
        ),
        phone=SimpleNamespace(
            get_status=lambda: {"state": "IDLE", "connected": False},
            kinship=SimpleNamespace(
                get_contacts=lambda: [{"id": "1", "name": "Mom"}],
                add_or_update_contact=lambda c: c,
                delete_contact=lambda cid: cid == "1",
            ),
            history=[],
            dial=lambda num: bool(num),
            answer_call=lambda: True,
            end_call=lambda: True,
            start_call_screening=lambda: True,
            toggle_mute=lambda: True,
            trigger_incoming_call=lambda n: None,
            update_screening_transcript=lambda t: None,
        ),
        sms=SimpleNamespace(
            get_threads=lambda: {"5551234": []},
            get_thread=lambda num: [{"text": "hi"}] if num == "5551234" else [],
            send_sms=lambda rec, txt: {"recipient": rec, "text": txt},
            receive_sms=lambda snd, txt: {"sender": snd, "text": txt},
        ),
        router=SimpleNamespace(
            get_navigation_status=lambda lat, lon: {"is_navigating": False},
            get_bookmarks=lambda: [{"id": "dest_home"}],
            speed_engine=SimpleNamespace(snap_to_road=lambda lat, lon: {"road_name": "US-60", "speed_limit_mph": 55}),
            calculate_route=lambda s1, s2, d1, d2, name: {"destination_name": name, "polyline": []},
            stop_navigation=lambda: None,
            update_position=lambda lat, lon, spd: {"is_navigating": False},
        ),
        settings={},
        avrcp_player=SimpleNamespace(
            current_track={"title": "Test"},
            playback_status="paused",
            update_track=lambda **kw: None,
            set_status=lambda st: None,
        ),
        audio=SimpleNamespace(
            _is_currently_ducking=False,
            is_speaking=False,
            cache_mgr=SimpleNamespace(get_stats=lambda: {"entries": 10}),
            get_cache_stats=lambda: {"size_mb": 4.2, "max_mb": 200},
            calculate_downsize_impact=lambda mb: {"target_mb": mb, "prune_count": 0},
            set_cache_limit=lambda mb: {"max_mb": mb},
            clear_cache=lambda: {"entries": 0},
        ),
        wifi=SimpleNamespace(
            get_status=lambda: {"connected": True, "ssid": "HomeNet"},
            scan_networks=lambda: [{"ssid": "HomeNet", "signal": 80}],
            get_saved=lambda: ["HomeNet"],
            connect=lambda ssid, pw=None, auto=True: {"status": "ok", "ssid": ssid},
            forget=lambda ssid: {"status": "ok", "forgotten": ssid},
            clear_all=lambda: {"status": "ok"},
            set_always_on=lambda enabled: {"status": "ok", "always_on": bool(enabled)},
        ),
        bluetooth=SimpleNamespace(
            config={"auto_route_audio": True},
            get_status=lambda: {"powered": True, "connected_device": None},
            scan_devices=lambda: [],
            get_paired=lambda: [],
            connect_device=lambda mac: {"status": "ok", "mac": mac},
            disconnect_device=lambda mac: {"status": "ok", "mac": mac},
            remove_device=lambda mac: {"status": "ok", "mac": mac},
            set_discoverable=lambda enable: {"status": "ok", "discoverable": bool(enable)},
            get_audio_devices=lambda: {"sinks": [], "sources": []},
            set_auto_route=lambda enabled: None,
            set_audio_sink=lambda sink=None: {"status": "ok", "sink": sink},
            set_audio_source=lambda source=None: {"status": "ok", "source": source},
        ),
        pedal_commander=SimpleNamespace(
            get_status=lambda: {"mode": "SPORT", "level": 2, "connected": False},
            set_curve=lambda mode, level, pin=None: {"status": "ok", "mode": mode, "level": level},
            set_pin=lambda pin: None,
        ),
        sys_monitor=SimpleNamespace(
            current_brightness=85,
            get_system_health=lambda: {"cpu_temp_c": 42.0},
            get_detailed_hardware_specs=lambda: {"model": "Raspberry Pi 5", "ram_total_gb": 8.0},
            set_brightness=lambda val: None,
        ),
        gesture_ctrl=SimpleNamespace(get_status=lambda: {"enabled": False}),
        gpio=SimpleNamespace(
            get_pins_status=lambda: [{"bcm": 17, "state": 0}],
            get_relays_status=lambda: [{"bcm": 17, "active": False}],
            toggle_pin=lambda bcm: None,
            set_pin=lambda bcm, st: None,
            set_pwm=lambda bcm, duty: None,
            pulse_pin=lambda bcm, dur: None,
            transmit_morse=lambda bcm, msg: None,
        ),
        rom_mgr=SimpleNamespace(
            scan_roms=lambda: [{"name": "Mario", "platform": "snes"}],
            launch_game=lambda path, plat=None: {"status": "ok", "rom": path},
        ),
        trip_logger=SimpleNamespace(
            current_trip_id=7,
            retention_days=30,
            reset_current_trip=lambda: None,
            get_trip_telemetry=lambda tid: [{"rpm": 2100}] if tid == 7 else [],
            get_recent_trips=lambda limit=20: [{"id": 7, "miles": 12.4}],
            get_lifetime_stats=lambda: {"total_trips": 1},
            get_manifest_html=lambda tid: "<html>Trip 7</html>" if tid == 7 else None,
            get_trip_csv_bytes=lambda tid: (b"rpm\n2100\n", "trip_7.csv") if tid == 7 else (None, ""),
            get_trip_zip_path=lambda tid: (None, ""),
            get_settings=lambda: {"auto_archive": True},
            update_settings=lambda data: data,
            set_retention_days=lambda days: days,
            export_and_zip_trip=lambda tid, is_interim=False: f"/tmp/trip_{tid}.zip",
            clear_all_trips=lambda: True,
            delete_trip=lambda tid: tid == 7,
        ),
    )


class ModularRouteDispatchTest(unittest.TestCase):
    def setUp(self):
        self.state = make_dummy_state()

    def test_telephony_routes(self):
        for path in ("/api/phone/status", "/api/phone/contacts", "/api/phone/history", "/api/sms/threads"):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        h = DummyHandler({"number": "5551234"})
        self.assertTrue(dispatch_post(h, urlparse("/api/phone/dial"), self.state))
        self.assertTrue(h.json_body()["dialed"])

        h = DummyHandler({"recipient": "5551234", "text": "omw"})
        self.assertTrue(dispatch_post(h, urlparse("/api/sms/send"), self.state))
        self.assertEqual(h.json_body()["message"]["text"], "omw")

    def test_navigation_routes(self):
        for path in ("/api/nav/status?lat=33.39&lon=-110.78", "/api/nav/bookmarks", "/api/nav/speed_limit", "/api/gps", "/api/drag/status"):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        h = DummyHandler({"dest_name": "Work"})
        self.assertTrue(dispatch_post(h, urlparse("/api/nav/route"), self.state))
        self.assertEqual(h.json_body()["route"]["destination_name"], "Work")

        h = DummyHandler()
        self.assertFalse(dispatch_head(h, urlparse("/api/status")))

    def test_telemetry_and_media_routes(self):
        for path in (
            "/api/telemetry/mode",
            "/api/telemetry/dyno",
            "/api/telemetry/spool_health",
            "/api/telemetry/shift_quality",
            "/api/telemetry/multiair_health",
            "/api/telemetry/thermal",
            "/api/telemetry/lap_timer",
            "/api/telemetry/lap_timer/tracks",
            "/api/media/player/status",
            "/api/audio/duck_status",
            "/api/tts/stats",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        for path, body in (
            ("/api/media/player/control", {"action": "play"}),
            ("/api/avrcp/action", {"action": "pause"}),
            ("/api/cockpit/action", {"command": "reset_trip"}),
            ("/api/telemetry/lap_timer/arm", {}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

    def test_sprint2_telemetry_and_audio_routes(self):
        for path in (
            "/api/dtc/lookup?code=P0299",
            "/api/dtc/inject?code=P0299",
            "/api/dtc/status",
            "/api/dtc/clear",
            "/api/drag/stage?tree_type=PRO",
            "/api/drag/reset",
            "/api/audio/devices",
            "/api/audio/cache",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        for path, body in (
            ("/api/telemetry/mode", {"mode": "TEST", "test_mode": True}),
            ("/api/drag/stage", {"tree_type": "SPORTSMAN"}),
            ("/api/drag/reset", {}),
            ("/api/audio/output", {"sink": "alsa_output.test", "auto_route": False}),
            ("/api/audio/input", {"source": "alsa_input.test"}),
            ("/api/audio/cache/limit", {"limit_mb": 512}),
            ("/api/audio/cache/clear", {}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)
        self.assertEqual(self.state.telemetry_mode, "TEST")
        self.assertEqual(self.state.settings["tts_cache_limit_mb"], 512)

    def test_connectivity_routes(self):
        for path in (
            "/api/wifi/status",
            "/api/wifi/scan",
            "/api/wifi/saved",
            "/api/bluetooth/status",
            "/api/bluetooth/devices",
            "/api/bluetooth/scan",
            "/api/bluetooth/paired",
            "/api/pedal_commander/status",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        for path, body in (
            ("/api/wifi/connect", {"ssid": "HomeNet", "password": "secret"}),
            ("/api/wifi/forget", {"ssid": "HomeNet"}),
            ("/api/wifi/clear", {}),
            ("/api/wifi/always_on", {"enabled": True}),
            ("/api/bluetooth/connect", {"mac": "AA:BB:CC:DD:EE:FF"}),
            ("/api/bluetooth/disconnect", {"mac": "AA:BB:CC:DD:EE:FF"}),
            ("/api/bluetooth/remove", {"mac": "AA:BB:CC:DD:EE:FF"}),
            ("/api/bluetooth/discoverable", {"enable": True}),
            ("/api/pedal_commander/set", {"mode": "SPORT+", "level": 3}),
            ("/api/pedal_commander/pin", {"pin": "1234"}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

    def test_hardware_routes(self):
        for path in (
            "/api/system/health",
            "/api/system/detailed_specs",
            "/api/hardware/specs",
            "/api/system/fan",
            "/api/system/brightness",
            "/api/gesture/status",
            "/api/gpio/pins",
            "/api/gpio/relays",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        for path, body in (
            ("/api/system/brightness", {"brightness": 70}),
            ("/api/system/fan", {}),
            ("/api/gesture/trigger", {"gesture": "WAVE"}),
            ("/api/gpio/toggle", {"bcm": 17}),
            ("/api/gpio/set", {"bcm": 17, "state": True}),
            ("/api/gpio/pwm", {"bcm": 18, "duty_cycle": 0.4}),
            ("/api/gpio/pulse", {"bcm": 18, "duration": 0.2}),
            ("/api/gpio/morse", {"bcm": 18, "message": "SOS"}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)
        self.assertEqual(self.state.latest_ui_action["gesture"], "WAVE")

    def test_storage_trips_and_system_routes(self):
        for path in (
            "/api/fs/devices",
            "/api/storage/devices",
            "/api/trips/telemetry?id=7",
            "/api/trips/recent",
            "/api/trips/stats",
            "/api/trips/manifest?id=7",
            "/api/trips/csv?id=7",
            "/api/trips/settings",
            "/api/trips/retention",
            "/api/games/roms",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        for path, body in (
            ("/api/trips/archive_now", {}),
            ("/api/trips/settings", {"auto_archive": True}),
            ("/api/trips/clear", {}),
            ("/api/trips/delete", {"id": 7}),
            ("/api/trips/retention", {"retention_days": 14}),
            ("/api/games/launch", {"rom_path": "/roms/mario.sfc", "platform": "snes"}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch.object(system_routes, "LOGS_DIR", Path(tmpdir)):
                h = DummyHandler({"source": "TestUI", "message": "Sample error"})
                self.assertTrue(dispatch_post(h, urlparse("/api/logs/client_error"), self.state))
                self.assertEqual(h.status, 200)
                self.assertEqual(h.json_body()["status"], "recorded")

                h2 = DummyHandler()
                self.assertTrue(dispatch_get(h2, urlparse("/api/logs/view?type=ui"), self.state))
                self.assertEqual(h2.status, 200)
                self.assertIn("Sample error", h2.wfile.getvalue().decode("utf-8"))

    def test_unmatched_routes_fall_through(self):
        h = DummyHandler()
        self.assertFalse(dispatch_get(h, urlparse("/api/status"), self.state))
        self.assertFalse(dispatch_post(h, urlparse("/api/ai/chat"), self.state))
        self.assertFalse(dispatch_post(h, urlparse("/api/models/room_layout"), self.state))


if __name__ == "__main__":
    unittest.main()
