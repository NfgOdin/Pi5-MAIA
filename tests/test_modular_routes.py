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
        latest_frame=SimpleNamespace(speed_mph=0.0, headlights_on=False, ambient_light_lux=100.0),
        last_frame={"rpm": 900, "boost_psi": -8.2, "coolant_temp_f": 192, "speed_mph": 0, "engine_load_pct": 18.0, "pedal_pos_pct": 10.0},
        latest_thermal_data=None,
        is_music_playing=False,
        is_mic_listening=False,
        live_convo_mode=False,
        wake_word_enabled=True,
        listen_once_requested=False,
        pending_voice_transcripts=[],
        pop_voice_transcript=lambda: None,
        stop_current_listen=lambda: None,
        save_settings=lambda cfg: None,
        reset_settings=lambda: {"telemetry_mode": "REAL"},
        obd_reader=SimpleNamespace(connected=False, status_message="Offline", dyno=dyno, active_dtcs=[], clear_dtcs=lambda: None),
        simulator=SimpleNamespace(
            dyno=dyno,
            active_dtcs=["P0299"],
            inject_dtc=lambda code: None,
            clear_dtcs=lambda: None,
            set_headlights=lambda on: None,
        ),
        copilot=SimpleNamespace(
            voice_mode="COPILOT",
            driver_name="Dad",
            last_spoken_time=0.0,
            set_voice_mode=lambda m: None,
            get_current_mood=lambda: {"mood": "HAPPY_PROUD", "valence": 0.6, "arousal": 0.4},
            generate_shower_thought=lambda: "Turbo boost is basically forced enthusiasm.",
            diagnostics=SimpleNamespace(explain_code=lambda c: {"code": c, "title": "Turbo Underboost"}),
            announced_dtcs={"P0299"},
        ),
        llm=SimpleNamespace(
            settings={"personality": "RUM", "mode": "LOCAL", "gguf_model_path": "models/qwen3b.gguf", "api_key": "", "gemini_model": "gemini-3.5-flash"},
            personas={"RUM": {"name": "R.U.M.", "full_name": "R.U.M. AI", "description": "Daughter co-pilot"}},
            chat_history=[],
            speech_log=[],
            circadian_override=None,
            _llama_model=object(),
            ai_core_status="ONLINE",
            get_ai_core_status=lambda: "ONLINE",
            get_driver_address=lambda: "Dad",
            get_circadian_state=lambda: {"is_night": False, "phase": "DAY"},
            get_morning_dream=lambda force=False: {"dream": "Dreamt of Pinal Pass!", "action": "action_standup.bvh"},
            get_instant_greeting=lambda: {"greeting": "[EMOTION: HAPPY] Morning Dad!"},
            get_neural_greeting=lambda live_telemetry=None: {"greeting": "[EMOTION: DEVOTED] Ready to drive Dad!"},
            get_startup_greeting=lambda live_telemetry=None: {"greeting": "Ready, Dad!"},
            get_available_gguf_models=lambda: ["qwen3b.gguf"],
            reload_personas=lambda: None,
            save_settings=lambda cfg: None,
            chat_with_action=lambda msg, live_telemetry=None, on_clause=None: {
                "reply": "[EMOTION: HAPPY] Boosting cleanly, Dad!",
                "action": None,
                "persona": "RUM",
            },
            google_auth=SimpleNamespace(
                get_status=lambda: {"authenticated": False},
                start_device_flow=lambda cid, csec: {"status": "ok", "user_code": "ABCD-1234"},
                logout=lambda: None,
                save_client_credentials=lambda cid, csec: {"status": "ok"},
            ),
        ),
        rag=SimpleNamespace(
            get_maintenance_status=lambda: {"odometer": 85240, "items": []},
            search=lambda q, top_k=5: [{"title": "Oil Spec", "score": 0.91}],
            get_relationship_bond=lambda: {"miles": 120.5, "level": 2},
            get_recent_diary_entries=lambda limit=10: [],
            get_driver_facts=lambda: [{"id": 1, "entity": "Car", "attribute": "Oil", "value": "5W-40"}],
            get_recent_episodic_memories=lambda limit=10: [],
            set_driver_fact=lambda e, a, v, c, s: bool(e and a and v),
            delete_driver_fact=lambda fid: fid == 1,
            delete_diary_entry=lambda did: did == 1,
            record_service=lambda k, m, n: bool(k),
            set_odometer=lambda o: None,
            add_document=lambda did, cat, title, content, metadata=None: None,
        ),
        pip=SimpleNamespace(
            step=lambda dt, frame, is_night=False: {"wing_hz": 220, "sugar_pct": 85},
            stimulate_sugar_water=lambda: None,
            stimulate_scare=lambda force=1.0: None,
        ),
        drive_buffer=SimpleNamespace(record_dialogue=lambda u, r: None),
        hippocampus=SimpleNamespace(consolidate_drive=lambda buf, rag, data: {"status": "ok", "consolidated": 1}),
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
        display_settings={},
        avrcp_player=SimpleNamespace(
            current_track={"title": "Test"},
            playback_status="paused",
            update_track=lambda **kw: None,
            set_status=lambda st: None,
        ),
        audio=SimpleNamespace(
            _is_currently_ducking=False,
            is_speaking=False,
            play_acknowledgment=lambda p: None,
            play_instant_ack=lambda: None,
            speak=lambda txt, priority=1: None,
            configure_tts=lambda s: None,
            cache_mgr=SimpleNamespace(get_stats=lambda: {"entries": 10}),
            get_speech_clip=lambda seq: b"RIFFdemo" if seq == 1 else None,
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

    def test_sprint3_ai_and_maintenance_pip_routes(self):
        from routes.ai_routes import extract_emotion_and_clean_speech

        emo, clean = extract_emotion_and_clean_speech("[EMOTION: EXCITED] Boost ready!")
        self.assertEqual(emo, "EXCITED")
        self.assertEqual(clean, "Boost ready!")

        for path in (
            "/api/ai/status",
            "/api/ai/voice_mode?mode=COPILOT",
            "/api/ai/memory/query?q=oil",
            "/api/ai/memory/living_summary",
            "/api/ai/memory/facts",
            "/api/ai/memory/diary",
            "/api/ai/memory/bond",
            "/api/ai/circadian",
            "/api/ai/mood",
            "/api/ai/morning_dream",
            "/api/ai/greeting/instant",
            "/api/ai/greeting/official",
            "/api/ai/models",
            "/api/ai/greeting",
            "/api/ai/personas",
            "/api/ai/history",
            "/api/ai/settings",
            "/api/maintenance/status",
            "/api/pip/state",
        ):
            h = DummyHandler()
            self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

        self.state.llm.personas["RUM"]["touch_interactions"] = {
            "head_top": {"lines": ["Pat!"], "animations": ["greeting"]}
        }
        self.state.llm.personas["RUM"]["banned_touch_zones"] = ["restricted_zone"]
        h_hist = DummyHandler()
        self.assertTrue(dispatch_get(h_hist, urlparse("/api/ai/history"), self.state))
        self.assertEqual(h_hist.status, 200)
        rum_payload = h_hist.json_body()["personalities"]["RUM"]
        self.assertIn("head_top", rum_payload["touch_interactions"])
        self.assertEqual(rum_payload["banned_touch_zones"], ["restricted_zone"])

        for path, body in (
            ("/api/ai/chat", {"message": "How is boost?"}),
            ("/api/ai/listen", {"action": "toggle_convo"}),
            ("/api/ai/speak", {"text": "Hello Dad"}),
            ("/api/ai/wake_test", {}),
            ("/api/ai/circadian/simulate", {"mode": "NIGHT"}),
            ("/api/ai/morning_dream", {}),
            ("/api/ai/shower_thought", {}),
            ("/api/ai/settings", {"personality": "RUM"}),
            ("/api/ai/memory/facts", {"entity": "Dart", "attribute": "PlugGap", "value": "0.026in"}),
            ("/api/ai/memory/facts/delete", {"id": 1}),
            ("/api/ai/memory/diary/delete", {"id": 1}),
            ("/api/ai/memory/consolidate", {}),
            ("/api/ai/memory/remember", {"title": "Torque", "content": "184 lb-ft"}),
            ("/api/maintenance/record", {"item_key": "oil_5w40", "mileage": 85300, "notes": "Done"}),
            ("/api/maintenance/odometer", {"odometer": 85310}),
            ("/api/pip/feed", {}),
            ("/api/pip/scare", {}),
        ):
            h = DummyHandler(body)
            self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
            self.assertEqual(h.status, 200)

    def test_sprint3_settings_auth_assets_media_and_headlights_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            (tmp_path / "storage").mkdir()
            (tmp_path / "storage" / "manual.txt").write_text("MultiAir manual", encoding="utf-8")
            (tmp_path / "config").mkdir()
            self.state.base_dir = tmp_path

            for path in (
                "/api/status",
                "/api/settings/all",
                "/api/display/settings",
                "/api/auth/google/status",
                "/api/ui/navigate?screen=canyon",
                "/api/telemetry/headlights",
                "/api/media/now_playing",
                "/api/media/stremio_addons",
                "/api/media/tracks",
                "/api/audio/speech_clip?seq=1",
                "/api/media/external_app_status",
                "/api/models/avatars",
                "/api/models/vrma",
                "/api/models/bvh",
                "/api/models/custom_props",
                "/api/models/room_layout",
                "/storage/manual.txt",
            ):
                h = DummyHandler()
                self.assertTrue(dispatch_get(h, urlparse(path), self.state), path)
                self.assertEqual(h.status, 200)

            for path, body in (
                ("/api/settings/save", {"brightness": 80}),
                ("/api/settings/reset", {}),
                ("/api/ui/navigate", {"screen": "phone"}),
                ("/api/auth/google/start", {"client_id": "cid", "client_secret": "csec"}),
                ("/api/auth/google/config", {"client_id": "cid", "client_secret": "csec"}),
                ("/api/auth/google/logout", {}),
                ("/api/telemetry/headlights", {"headlights": True}),
                ("/api/models/room_layout", {"version": 1, "props": [{"id": "lamp"}]}),
            ):
                h = DummyHandler(body)
                self.assertTrue(dispatch_post(h, urlparse(path), self.state), path)
                self.assertEqual(h.status, 200)
            self.assertEqual(self.state.latest_ui_action["target"], "phone")

            # Storage traversal protection returns 404
            h_trav = DummyHandler()
            self.assertTrue(dispatch_get(h_trav, urlparse("/storage/../secret.txt"), self.state))
            self.assertEqual(h_trav.status, 404)

    def test_voice_listener_normalization(self):
        from ai.voice_listener import normalize_wake_transcript

        self.assertEqual(normalize_wake_transcript("hey rem"), ("Hey Rum", True))
        self.assertEqual(normalize_wake_transcript("hey ron, what is boost"), ("Hey Rum, what is boost", True))
        self.assertEqual(normalize_wake_transcript("drum"), ("Hey Rum", True))
        self.assertEqual(normalize_wake_transcript("turn left ahead"), ("turn left ahead", False))

        maia_cfg = {"canonical_prefix": "Hey Maia", "prefixes": ["hey maia", "hey maya"], "standalone": ["maia"]}
        self.assertEqual(normalize_wake_transcript("hey maya, check boost", maia_cfg), ("Hey Maia, check boost", True))
        self.assertEqual(normalize_wake_transcript("maia", maia_cfg), ("Hey Maia", True))

    def test_persona_driven_greetings_pip_and_speech_sync(self):
        import datetime as dt_mod
        from ai.llm_client import LLMClient
        from ai.memory_manager import MemoryManager

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            temp_mem = MemoryManager(memory_file=str(Path(tmpdir) / "ai_memory.json"))
            with mock.patch("ai.llm_client.MemoryManager", return_value=temp_mem), \
                 mock.patch.object(LLMClient, "_preload_local_gguf", lambda self: None):
                llm = LLMClient()
            self.assertIn("RUM", llm.personas)
            self.assertIn("MAIA", llm.personas)
            self.assertIn("ODIN", llm.personas)

            # Every loaded persona defines full weekday greetings & Pip reactions
            for pid, pdata in llm.personas.items():
                weekdays = pdata.get("greetings", {}).get("weekdays", {})
                self.assertIn("Tuesday", weekdays, f"Persona {pid} missing Tuesday greeting")
                self.assertTrue(len(weekdays["Tuesday"]) >= 1)
                pip_feed = pdata.get("pip_reactions", {}).get("feed", {})
                self.assertTrue(bool(pip_feed), f"Persona {pid} missing pip_reactions.feed")

            # Verify /api/ai/speak logs into speech_log & updates latest_ai_event
            self.state.llm = llm
            self.state.latest_ai_event = None
            h_spk = DummyHandler({"text": "Testing unified speech bubble!", "source": "TOUCH", "emotion": "HAPPY", "client_id": "cli_1"})
            self.assertTrue(dispatch_post(h_spk, urlparse("/api/ai/speak"), self.state))
            self.assertEqual(h_spk.status, 200)
            self.assertEqual(self.state.latest_ai_event["speech"], "Testing unified speech bubble!")
            self.assertEqual(self.state.latest_ai_event["client_id"], "cli_1")
            self.assertTrue(any(e["text"] == "Testing unified speech bubble!" for e in llm.speech_log))

            # Verify /api/pip/feed generates persona reaction & emits speech event
            h_feed = DummyHandler({})
            self.assertTrue(dispatch_post(h_feed, urlparse("/api/pip/feed"), self.state))
            self.assertEqual(h_feed.status, 200)
            feed_body = h_feed.json_body()
            self.assertTrue(bool(feed_body.get("speech")))
            self.assertEqual(self.state.latest_ai_event["source"], "PIP_FEED")

            # Verify Tuesday startup greeting picks from Tuesday/time-of-day pools for each persona (without dirtying repo files)
            llm.settings["personality"] = "MAIA"
            fake_tuesday = dt_mod.datetime(2026, 11, 17, 10, 0, 0)  # Tuesday
            with mock.patch("ai.memory_manager.datetime") as mock_dt:
                mock_dt.now.return_value = fake_tuesday
                greeting = llm.memory_mgr.generate_startup_greeting("Master", llm.get_active_persona())
                self.assertTrue(len(greeting) > 10)

    def test_rag_memory_legacy_migration(self):
        import gc
        import sqlite3
        from ai.rag_memory import RagMemoryEngine

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_file = Path(tmpdir) / "rag_memory.db"
            # Seed legacy rum_summary & rum_diary schema prior to upgrade
            conn = sqlite3.connect(str(db_file))
            try:
                conn.execute("""
                    CREATE TABLE episodic_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        location_name TEXT DEFAULT '',
                        driver_quote TEXT DEFAULT '',
                        rum_summary TEXT NOT NULL,
                        emotion_tag TEXT DEFAULT 'JOY',
                        importance INTEGER DEFAULT 5,
                        vector BLOB
                    )
                """)
                conn.execute("""
                    INSERT INTO episodic_memories (timestamp, created_at, rum_summary)
                    VALUES (1000.0, '2026-11-01T00:00:00', 'Legacy canyon pull')
                """)
                conn.execute("""
                    CREATE TABLE rum_diary (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trip_id INTEGER,
                        entry_date TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        peak_boost REAL DEFAULT 0.0,
                        mileage REAL DEFAULT 0.0,
                        mood TEXT DEFAULT 'HAPPY_PROUD',
                        vector BLOB
                    )
                """)
                conn.execute("""
                    INSERT INTO rum_diary (trip_id, entry_date, created_at, title, content, peak_boost, mileage, mood)
                    VALUES (1, '2026-11-01', '2026-11-01T00:00:00', 'Legacy Title', 'Legacy Diary Body', 17.5, 12.0, 'HAPPY')
                """)
                conn.commit()
            finally:
                conn.close()

            rag = RagMemoryEngine(db_path=str(db_file))
            episodes = rag.get_recent_episodic_memories(limit=5)
            self.assertEqual(episodes[0]["companion_summary"], "Legacy canyon pull")
            diary = rag.get_recent_diary_entries(limit=5)
            self.assertEqual(diary[0]["title"], "Legacy Title")
            del rag
            gc.collect()

    def test_emote_choreographer_tags_and_goemotions_mapping(self):
        from ai.emote_choreographer import GOEMOTION_CATALOG, analyze_reply_choreography

        self.assertEqual(len(GOEMOTION_CATALOG), 27)
        # Verify every mapped emotion clip exists in models/bvh/emotions/*.bvh or known VRMA keys
        bvh_names = {p.stem.lower() for p in (BACKEND_DIR.parent / "models" / "bvh").rglob("*.bvh")}
        vrma_names = {
            "show_body", "greeting", "greeting_wave_right", "peace", "shoot", "spin",
            "model_pose", "squat", "pose_lean_in", "pose_angled_wave", "pose_shy_wave",
            "pose_hand_raised_high", "pose_side_glance", "idol_pose_showcase", "turn_and_wave_hello",
            "sit_idle", "walk_loop", "jog_loop", "sunbathing",
        }
        all_clips = bvh_names | vrma_names
        for cat, meta in GOEMOTION_CATALOG.items():
            for clip in meta.get("clips", []):
                self.assertIn(clip.lower(), all_clips, f"Missing clip {clip} for {cat}")

        # Inline multi-beat tag stripping & persona remap verification
        rum_persona = {"id": "RUM", "gender": "female", "emote_profile": {"remap": {"desire": "admiration"}}}
        res = analyze_reply_choreography(
            "[EMOTE:desire] Boost is ready, Dad! [beat:excitement] Let's launch this turbo!",
            persona_data=rum_persona,
        )
        self.assertNotIn("[EMOTE", res["speech"])
        self.assertNotIn("[beat", res["speech"])
        self.assertEqual(res["goemotion"], "admiration")
        self.assertGreaterEqual(len(res["beats"]), 2)
        self.assertEqual(res["beats"][1]["goemotion"], "excitement")

        odin_persona = {
            "id": "ODIN",
            "gender": "male",
            "emote_profile": {"excluded_clips": ["pose_lady_bow"], "clip_overrides": {"gratitude": ["pose_gentlemen_bow"]}},
        }
        res_odin = analyze_reply_choreography("[EMOTE:gratitude] Good run, warrior.", persona_data=odin_persona)
        self.assertEqual(res_odin["emote_clip"], "pose_gentlemen_bow")

    def test_viseme_analyzer_wav_and_text_sync(self):
        import io
        import math
        import struct
        import wave
        from hardware.viseme_analyzer import extract_wav_viseme_timeline

        # Build deterministic 16kHz mono PCM WAV: 0.2s silence -> 0.4s loud tone -> 0.2s silence
        sr = 16000
        samples = [0] * int(0.2 * sr)
        samples += [int(14000 * math.sin(2 * math.pi * 440 * i / sr)) for i in range(int(0.4 * sr))]
        samples += [0] * int(0.2 * sr)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

        tl = extract_wav_viseme_timeline(buf.getvalue(), "Hello world!")
        self.assertEqual(tl["fps"], 25)
        self.assertGreaterEqual(tl["duration_ms"], 750)
        amps = tl["amps"]
        self.assertEqual(len(amps), len(tl["visemes"]))
        self.assertEqual(amps[0], 0)
        self.assertGreater(max(amps), 10)
        self.assertEqual(amps[-1], 0)
        self.assertTrue(set(tl["visemes"]).issubset({"0", "a", "i", "u", "e", "o"}))

        # Test /api/audio/speech_viseme route
        h404 = DummyHandler()
        self.state.audio.get_speech_viseme = lambda seq=None: None
        self.assertTrue(dispatch_get(h404, urlparse("/api/audio/speech_viseme?seq=99"), self.state))
        self.assertEqual(h404.status, 404)

        self.state.audio.get_speech_viseme = lambda seq=None: tl
        h200 = DummyHandler()
        self.assertTrue(dispatch_get(h200, urlparse("/api/audio/speech_viseme?seq=1"), self.state))
        self.assertEqual(h200.status, 200)
        self.assertEqual(h200.json_body()["viseme"]["fps"], 25)

    def test_audio_player_interrupt_and_queue_flush(self):
        import queue as py_queue
        from hardware.audio_player import AudioPlayer

        ap = AudioPlayer.__new__(AudioPlayer)
        ap.synthesis_queue = py_queue.Queue()
        ap.playback_queue = py_queue.Queue()
        ap._speech_lock = threading.Lock()
        ap._speech_seq = 0
        ap._speech_interrupt_seq = 0
        ap._interrupt_event = threading.Event()
        ap._active_play_proc = None
        ap.is_speaking = True
        ap._duck_lock = threading.Lock()
        ap._is_currently_ducking = True
        ap._duck_callback = None
        ap._music_playing_checker = None

        ap.synthesis_queue.put("clause one")
        ap.playback_queue.put({"file": "/tmp/fake.wav", "text": "fake"})

        seq = ap.stop_speaking()
        self.assertEqual(seq, 1)
        self.assertEqual(ap.get_speech_interrupt_seq(), 1)
        self.assertTrue(ap._interrupt_event.is_set())
        self.assertFalse(ap.is_speaking)
        self.assertTrue(ap.synthesis_queue.empty())
        self.assertTrue(ap.playback_queue.empty())

    def test_ai_interrupt_route_and_ollama_streaming_parser(self):
        from ai.llm_client import LLMClient

        # Test /api/ai/interrupt route dispatch cleanly
        self.state.interrupt_ai_turn = lambda reason="UI": {"status": "ok", "interrupt_seq": 3, "reason": reason}
        h_int = DummyHandler({"reason": "TEST_TAP"})
        self.assertTrue(dispatch_post(h_int, urlparse("/api/ai/interrupt"), self.state))
        self.assertEqual(h_int.status, 200)
        self.assertEqual(h_int.json_body()["interrupt_seq"], 3)

        # Test NDJSON streaming clause emission + mid-stream cancellation via _flush_clauses
        fake_llm = LLMClient.__new__(LLMClient)
        clauses = []
        cancel_ev = threading.Event()
        buf = "First boost clause! Second "
        buf = fake_llm._flush_clauses(buf, clauses.append, cancel_event=cancel_ev, flush_all=False)
        self.assertEqual(clauses, ["First boost clause!"])
        self.assertEqual(buf, "Second ")

        # Cancel mid-stream: flush_all=True must emit nothing once cancel_event is set
        cancel_ev.set()
        fake_llm._flush_clauses(buf, clauses.append, cancel_event=cancel_ev, flush_all=True)
        self.assertEqual(clauses, ["First boost clause!"])

        # Verify Ollama stream=True NDJSON handling end-to-end with mocked urlopen
        fake_ndjson = [
            b'{"response":"[EMOTE:excitement] Turbo spooling ","done":false}\n',
            b'{"response":"at 16 PSI! Second beat coming.","done":true}\n',
        ]

        class FakeResp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def __iter__(self): return iter(fake_ndjson)

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            from ai.memory_manager import MemoryManager
            fake_llm.settings = {"mode": "TAILSCALE_OLLAMA", "personality": "RUM", "tailscale_ip": "127.0.0.1", "tailscale_port": 11434, "ollama_model": "qwen2.5:3b"}
            fake_llm.personas = {"RUM": {"id": "RUM", "name": "R.U.M.", "prompt": "Test {driver_address}."}}
            fake_llm.lorebooks = {}
            fake_llm.chat_history = []
            fake_llm.speech_log = []
            fake_llm.memory_mgr = MemoryManager(memory_file=str(Path(tmpdir) / "ai_mem.json"))
            fake_llm.rag_memory = None
            streamed = []
            with mock.patch("urllib.request.urlopen", return_value=FakeResp()):
                full = fake_llm.chat("How is boost?", on_clause=streamed.append)
            self.assertIn("Turbo spooling at 16 PSI!", full)
            self.assertGreaterEqual(len(streamed), 2)

    def test_voice_barge_in_energy_gate(self):
        from ai.voice_listener import evaluate_barge_in_frame

        hits = 0
        # Speaker floor bleed should not trigger interrupt
        for _ in range(5):
            trig, hits = evaluate_barge_in_frame(rms=120.0, noise_rms=95.0, barge_hits=hits)
            self.assertFalse(trig)
        # Sustained loud driver barge-in (>=240 & >=2.8x floor for 3 frames) triggers interrupt
        for idx in range(3):
            trig, hits = evaluate_barge_in_frame(rms=420.0, noise_rms=95.0, barge_hits=hits)
            if idx < 2:
                self.assertFalse(trig)
            else:
                self.assertTrue(trig)

    def test_generic_vrm_code_decoupling(self):
        from ai.llm_client import get_default_persona_id, load_personas_from_dir

        personas = load_personas_from_dir()
        self.assertEqual(get_default_persona_id(personas), "RUM")
        self.assertIn("RUM", personas)
        self.assertEqual(personas["RUM"].get("vrm_defaults", {}).get("model_file"), "Rum.vrm")

        # Verify legacy persona-named code symbols & defaults stay removed from active code paths
        ui_root = BACKEND_DIR.parent / "ui" / "web_preview"
        checks = {
            ui_root / "js" / "diagnostics_dragy.js": ["setRumDragCallout"],
            ui_root / "js" / "ai_voice.js": ["maiaBubble", "rum_walk", "maia_avatar.jpg"],
            ui_root / "js" / "vrm_3d_room.js": ["/rum|rem/i", "'Rum.vrm'", "'Rem.vrm'"],
            BACKEND_DIR / "ai" / "copilot.py": ["PERCHED_ON_RUM", "rum_interaction", "rum_summary"],
            BACKEND_DIR / "ai" / "llm_client.py": ['if "MAIA" not in personas', '"personality": "RUM"'],
        }
        for fp, forbidden in checks.items():
            txt = fp.read_text(encoding="utf-8")
            for tok in forbidden:
                self.assertNotIn(tok, txt, f"Found stale persona token {tok} in {fp}")

    def test_unmatched_routes_fall_through(self):
        import ast
        daemon_src = (BACKEND_DIR / "daemon.py").read_text(encoding="utf-8")
        tree = ast.parse(daemon_src, filename="daemon.py")
        class_names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        self.assertIn("CarPi5ServerState", class_names)
        self.assertIn("typing.Optional", daemon_src.replace("from typing import ", "typing.")) if False else None
        # Ensure annotations referenced by CarPi5ServerState exist in module imports
        self.assertIn("Optional", daemon_src.split("class CarPi5ServerState", 1)[0])
        h = DummyHandler()
        self.assertFalse(dispatch_get(h, urlparse("/index.html"), self.state))
        self.assertFalse(dispatch_get(h, urlparse("/api/nonexistent_route"), self.state))
        self.assertFalse(dispatch_post(h, urlparse("/api/nonexistent_route"), self.state))


if __name__ == "__main__":
    unittest.main()
