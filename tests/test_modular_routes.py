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

    def test_persona_schema_and_hot_discovery(self):
        from ai.llm_client import load_personas_from_dir, LLMClient

        personas = load_personas_from_dir()
        for pid in ("RUM", "MAIA", "ODIN"):
            self.assertIn(pid, personas)
            p = personas[pid]
            for req_key in ("voice_engine", "kokoro_voice", "pitch_factor", "tts_pitch", "acknowledgments_folder", "boot_splash_title", "boot_splash_subtitle"):
                self.assertIn(req_key, p, f"{pid} missing {req_key}")
            vd = p.get("vrm_defaults", {})
            for vkey in ("model_file", "scale", "framing_mode", "default_idle", "night_sit_idle", "walk_clip", "sleeve_bones", "spring_physics_scale", "accent_color", "bubble_bg", "glow_color"):
                self.assertIn(vkey, vd, f"{pid}.vrm_defaults missing {vkey}")
            self.assertIn("coolant_high", p.get("copilot_callouts", {}), f"{pid} missing copilot_callouts")
            self.assertIn("head_top", p.get("touch_interactions", {}), f"{pid} missing touch_interactions")

        # R.U.M. & O.D.I.N. ban butt/groin; M.A.I.A. explicitly keeps adult touch zones
        self.assertIn("butt", personas["RUM"].get("banned_touch_zones", []))
        self.assertIn("butt", personas["ODIN"].get("banned_touch_zones", []))
        self.assertIn("butt", personas["MAIA"].get("touch_interactions", {}))

        # Hot-discovery: dropping a temporary JSON picks up via load_personas_from_dir without daemon restart
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            custom_path = Path(tmpdir) / "testbot.json"
            custom_path.write_text(json.dumps({
                "id": "TESTBOT",
                "name": "TestBot",
                "full_name": "Test Companion",
                "vrm_defaults": {"model_file": "Rum.vrm", "accent_color": "#22c55e"},
            }), encoding="utf-8")
            loaded = load_personas_from_dir(tmpdir)
            self.assertIn("TESTBOT", loaded)
            self.assertEqual(loaded["TESTBOT"]["acknowledgments_folder"], "testbot")

    def test_persona_switch_audio_autosync(self):
        from ai.llm_client import LLMClient, load_personas_from_dir
        from hardware.audio_player import AudioPlayer

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            cfg_path = Path(tmpdir) / "ai_settings.json"
            llm = LLMClient.__new__(LLMClient)
            llm.config_file = str(cfg_path)
            llm.personas = load_personas_from_dir()
            llm.settings = {
                "personality": "RUM",
                "tts_engine": "KOKORO",
                "kokoro_voice": "af_bella",
                "tts_pitch": 1.28,
                "pitch_factor": 1.28,
                "acknowledgments_folder": "rum",
            }
            # Switching to ODIN auto-applies ODIN audio profile
            llm.save_settings({"personality": "ODIN"})
            self.assertEqual(llm.settings["personality"], "ODIN")
            self.assertEqual(llm.settings["tts_engine"], "PIPER")
            self.assertEqual(llm.settings["kokoro_voice"], "am_adam")
            self.assertAlmostEqual(float(llm.settings["tts_pitch"]), 0.94, places=2)
            self.assertEqual(llm.settings["acknowledgments_folder"], "odin")

            ap = AudioPlayer.__new__(AudioPlayer)
            ap.tts_engine = "KOKORO"
            ap.kokoro_voice = "af_nicole"
            ap.pitch_factor = 1.18
            ap.elevenlabs_api_key = ""
            ap.elevenlabs_voice_id = "cgSgspJ2msm6clMCkdW9"
            ap.acknowledgments_folder = ""
            ap.configure_tts(llm.settings)
            self.assertEqual(ap.tts_engine, "PIPER")
            self.assertEqual(ap.acknowledgments_folder, "odin")

            # Manual tweak afterwards sticks without reverting
            llm.save_settings({"kokoro_voice": "af_heart", "tts_pitch": 1.07})
            self.assertEqual(llm.settings["kokoro_voice"], "af_heart")
            self.assertAlmostEqual(float(llm.settings["tts_pitch"]), 1.07, places=2)

    def test_copilot_uses_persona_callouts(self):
        from ai.copilot import AICopilot

        engine = AICopilot(driver_name="Commander")
        engine.last_spoken_time = 0.0

        class StubLLM:
            def __init__(self, p):
                self._p = p
            def get_active_persona(self):
                return self._p

        engine.set_llm_client(StubLLM({
            "id": "ODIN",
            "name": "O.D.I.N.",
            "copilot_callouts": {
                "coolant_high": "Tactical alert {coolant}F for {driver_address}!",
                "coolant_high_hud": "ODIN TEMP {coolant}F",
            },
        }))
        ev = engine.evaluate_frame({"coolant_temp_f": 225.0, "connected": True}, dt=0.04)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["speech"], "Tactical alert 225F for Commander!")
        self.assertEqual(ev["hud_message"], "ODIN TEMP 225F")

    def test_legacy_2d_and_waifu_purge(self):
        ui_root = BACKEND_DIR.parent / "ui" / "web_preview"
        forbidden = [
            "initWaifuTalkingHead",
            "waifuFaceCanvas",
            "renderMiniDtcWaifu",
            "waifuStage",
            "waifuEmotionPill",
            "setWaifuEmotion",
            "triggerWaifuTouch",
            "toggleAvatar2d3d",
            "switchAvatarEngine",
            ".chat-bubble.maia",
            "maia_avatar.jpg",
        ]
        for path in list(ui_root.glob("*.html")) + list(ui_root.glob("*.css")) + list(ui_root.glob("*.js")) + list((ui_root / "js").glob("*.js")):
            txt = path.read_text(encoding="utf-8", errors="replace")
            for tok in forbidden:
                self.assertNotIn(tok, txt, f"Found legacy 2D/waifu symbol {tok} in {path}")

    def test_persona_builder_crud_and_default_uniqueness(self):
        from ai.llm_client import LLMClient, load_personas_from_dir
        import ai.llm_client as llm_mod

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            p_dir = Path(tmpdir) / "personas"
            p_dir.mkdir(parents=True, exist_ok=True)
            cfg_path = Path(tmpdir) / "ai_settings.json"
            # Seed 1 default persona in temp dir
            (p_dir / "rum.json").write_text(json.dumps({
                "id": "RUM",
                "name": "R.U.M.",
                "voice_engine": "KOKORO",
                "kokoro_voice": "af_bella",
                "pitch_factor": 1.28,
                "default": True,
                "vrm_defaults": {"model_file": "Rum.vrm"},
            }), encoding="utf-8")

            llm = LLMClient.__new__(LLMClient)
            llm.config_file = str(cfg_path)
            llm._persona_dir_override = str(p_dir)
            llm.personas = load_personas_from_dir(str(p_dir))
            llm.settings = {"personality": "RUM", "driver_title": "Dad", "driver_name": ""}

            orig_global = dict(llm_mod.PERSONALITIES)
            try:
                # Create & set default + active on new kid-safe persona LUMI (trying adult zones gets stripped)
                res_save = llm.save_persona({
                    "id": "lumi!",
                    "name": "Lumi",
                    "age_spirit": "8",
                    "default": True,
                    "voice_engine": "KOKORO",
                    "kokoro_voice": "af_sky",
                    "pitch_factor": 1.22,
                    "touch_interactions": {"butt": {"lines": ["nope"]}, "head_top": {"lines": ["Yay!"]}},
                    "vrm_defaults": {"model_file": "Rem.vrm", "accent_color": "#22c55e"},
                }, set_active=True)
                self.assertEqual(res_save["status"], "ok")
                self.assertEqual(res_save["persona"]["id"], "LUMI")
                self.assertIn("butt", res_save["persona"]["banned_touch_zones"])
                self.assertNotIn("butt", res_save["persona"]["touch_interactions"])
                self.assertEqual(llm.settings["personality"], "LUMI")
                self.assertEqual(llm.settings["kokoro_voice"], "af_sky")

                # RUM should have had default cleared when LUMI set default=True
                rum_disk = json.loads((p_dir / "rum.json").read_text(encoding="utf-8"))
                self.assertFalse(rum_disk["default"])

                # Autofill returns wake words & greetings for a custom persona
                auto_fields = llm.autofill_persona_fields({"name": "Nova", "age_spirit": "tactical"})
                self.assertIn("hey nova", auto_fields["wake_words"]["prefixes"])

                # Delete LUMI -> auto-falls back to RUM; cannot delete last remaining RUM
                res_del = llm.delete_persona("LUMI")
                self.assertEqual(res_del["status"], "ok")
                self.assertEqual(res_del["active_persona"], "RUM")
                res_last = llm.delete_persona("RUM")
                self.assertEqual(res_last["status"], "error")
            finally:
                llm_mod.PERSONALITIES = orig_global

    def test_asset_pic_and_vrm_upload_validation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            orig_base = getattr(self.state, "base_dir", None)
            self.state.base_dir = tmpdir
            try:
                # Reject traversal / bad extension
                h_bad = DummyHandler()
                h_bad.rfile = io.BytesIO(b"evil")
                h_bad.headers = {"Content-Length": "4"}
                dispatch_post(h_bad, urlparse("/api/models/avatars/upload?name=../../evil.exe"), self.state)
                self.assertEqual(h_bad.status, 400)

                # Accept valid .vrm upload
                h_vrm = DummyHandler()
                h_vrm.rfile = io.BytesIO(b"glTF_VRM_DATA")
                h_vrm.headers = {"Content-Length": "13"}
                dispatch_post(h_vrm, urlparse("/api/models/avatars/upload?name=CustomGirl.vrm"), self.state)
                self.assertEqual(h_vrm.status, 200)
                self.assertTrue((Path(tmpdir) / "models" / "avatars" / "CustomGirl.vrm").exists())

                # Accept valid .png upload and list via /api/assets/pics
                h_pic = DummyHandler()
                h_pic.rfile = io.BytesIO(b"\x89PNG\r\n\x1a\n")
                h_pic.headers = {"Content-Length": "8"}
                dispatch_post(h_pic, urlparse("/api/assets/pics/upload?name=lumi.png"), self.state)
                self.assertEqual(h_pic.status, 200)

                h_list = DummyHandler()
                self.assertTrue(dispatch_get(h_list, urlparse("/api/assets/pics"), self.state))
                self.assertIn("assets/pics/lumi.png", h_list.json_body()["pics"])
            finally:
                self.state.base_dir = orig_base

    def test_speak_temporary_voice_preview_and_voices_route(self):
        configured_calls = []
        self.state.audio.tts_engine = "KOKORO"
        self.state.audio.kokoro_voice = "af_bella"
        self.state.audio.pitch_factor = 1.28
        self.state.audio.configure_tts = lambda cfg: configured_calls.append(dict(cfg))

        h_voices = DummyHandler()
        self.assertTrue(dispatch_get(h_voices, urlparse("/api/ai/voices"), self.state))
        self.assertIn("af_nicole", h_voices.json_body()["kokoro_voices"])

        h_spk = DummyHandler({
            "text": "Voice preview check!",
            "tts_engine": "PIPER",
            "kokoro_voice": "am_adam",
            "tts_pitch": 0.94,
        })
        self.assertTrue(dispatch_post(h_spk, urlparse("/api/ai/speak"), self.state))
        self.assertEqual(len(configured_calls), 2)
        self.assertEqual(configured_calls[0]["kokoro_voice"], "am_adam")
        self.assertEqual(configured_calls[1]["kokoro_voice"], "af_bella")

    def test_kokoro_voice_blend_parsing_and_speed(self):
        from hardware.audio_player import AudioPlayer

        class FakeKokoro:
            def get_voices(self):
                return ["af_sky", "af_heart", "af_bella"]

            def get_voice_style(self, name):
                return {"af_sky": 10.0, "af_heart": 20.0, "af_bella": 30.0}[name]

        fk = FakeKokoro()
        self.assertEqual(AudioPlayer.resolve_kokoro_voice_arg(fk, "af_heart"), "af_heart")
        self.assertEqual(AudioPlayer.resolve_kokoro_voice_arg(fk, "unknown_voice"), "af_bella")
        blended = AudioPlayer.resolve_kokoro_voice_arg(fk, "af_sky:0.65+af_heart:0.35")
        self.assertAlmostEqual(blended, 13.5, places=4)

        player = AudioPlayer()
        player.configure_tts({
            "kokoro_voice": "af_sky:0.65+af_heart:0.35",
            "speech_speed": 0.97,
            "tts_pitch": 1.12,
        })
        self.assertEqual(player.kokoro_voice, "af_sky:0.65+af_heart:0.35")
        self.assertAlmostEqual(player.speech_speed, 0.97, places=2)
        self.assertAlmostEqual(player.pitch_factor, 1.12, places=2)

        player.configure_tts({"speech_speed": 2.5})
        self.assertAlmostEqual(player.speech_speed, 1.25, places=2)
        player.configure_tts({"speech_speed": 0.2})
        self.assertAlmostEqual(player.speech_speed, 0.75, places=2)

        rum_cfg = json.loads((BACKEND_DIR.parent / "config" / "personas" / "rum.json").read_text(encoding="utf-8"))
        self.assertTrue(isinstance(rum_cfg["kokoro_voice"], str) and len(rum_cfg["kokoro_voice"]) > 0)
        if "+" in rum_cfg["kokoro_voice"]:
            parts = [p.split(":") for p in rum_cfg["kokoro_voice"].split("+")]
            self.assertTrue(all(len(p) == 2 and float(p[1]) > 0 for p in parts))
        self.assertTrue(0.75 <= float(rum_cfg["speech_speed"]) <= 1.25)
        self.assertAlmostEqual(float(rum_cfg["pitch_factor"]), float(rum_cfg["tts_pitch"]), places=2)
        self.assertTrue(0.5 <= float(rum_cfg["tts_pitch"]) <= 2.0)

    def test_system_monitor_rtc_status(self):
        from hardware.system_monitor import SystemMonitor

        mon = SystemMonitor()
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "battery_voltage").write_text("3650000\n", encoding="utf-8")
            (p / "charging_voltage").write_text("3000000\n", encoding="utf-8")
            (p / "date").write_text("2026-11-17\n", encoding="utf-8")
            (p / "time").write_text("18:00:00\n", encoding="utf-8")

            rtc = mon.get_rtc_status(rtc_dir=str(p))
            self.assertTrue(rtc["present"])
            self.assertAlmostEqual(rtc["battery_voltage_v"], 3.65, places=2)
            self.assertAlmostEqual(rtc["charging_voltage_v"], 3.0, places=2)
            self.assertTrue(rtc["charging_enabled"])
            self.assertEqual(rtc["status"], "charging_ready")
            self.assertEqual(rtc["rtc_time"], "2026-11-17 18:00:00 UTC")

        missing = mon.get_rtc_status(rtc_dir=str(BACKEND_DIR / "nonexistent_rtc_dir"))
        self.assertFalse(missing["present"])
        self.assertEqual(missing["status"], "unavailable")
        self.assertFalse(missing["charging_enabled"])

    def test_offline_osm_routing_and_speed_limits(self):
        tools_dir = str(BACKEND_DIR.parent / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from build_az_nav_db import build_graph_from_ways
        from navigation.router import NavigationRouter

        # Missing DB truthfully reports offline_graph_missing & no fake curves
        missing_router = NavigationRouter(db_path=BACKEND_DIR / "nonexistent_az_nav.db")
        no_route = missing_router.calculate_route(33.3942, -110.7865, 33.4010, -110.7920, "Test")
        self.assertFalse(no_route["is_navigating"])
        self.assertFalse(no_route["graph_ready"])
        self.assertEqual(no_route["error"], "offline_graph_missing")
        self.assertEqual(no_route["polyline"], [])
        snap_missing = missing_router.speed_engine.snap_to_road(33.3942, -110.7865)
        self.assertFalse(snap_missing["snapped"])
        self.assertIsNone(snap_missing["speed_limit_mph"])

        # Compile realistic miniature Globe AZ graph: Broad St -> (right) Russell Rd -> (left) US-60 E
        nodes = {
            1: (33.3940, -110.7900),
            2: (33.3940, -110.7860),
            3: (33.3940, -110.7820),  # Broad St E intersection
            4: (33.3900, -110.7820),  # South along Russell Rd
            5: (33.3860, -110.7820),  # Russell Rd South intersection
            6: (33.3860, -110.7750),  # East on US-60
        }
        ways = [
            {"id": 10, "tags": {"highway": "primary", "name": "Broad St", "maxspeed": "25 mph"}, "refs": [1, 2, 3]},
            {"id": 11, "tags": {"highway": "secondary", "name": "Russell Rd", "maxspeed": "35 mph"}, "refs": [3, 4, 5]},
            {"id": 12, "tags": {"highway": "trunk", "name": "US-60 E", "maxspeed": "55 mph"}, "refs": [5, 6]},
        ]
        places = [
            {"name": "Copper Hills Diner", "kind": "poi", "category": "amenity:restaurant", "lat": 33.3862, "lon": -110.7752, "subtitle": "Globe Dining"}
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test_az.db"
            stats = build_graph_from_ways(nodes, ways, places, db_file)
            self.assertGreaterEqual(stats["nodes"], 4)
            self.assertGreaterEqual(stats["edges"], 6)

            router = NavigationRouter(db_path=db_file)
            orig_router = getattr(self.state, "router", None)
            self.state.router = router
            try:
                snap_us60 = router.speed_engine.snap_to_road(33.3860, -110.7785)
                self.assertTrue(snap_us60["snapped"])
                self.assertEqual(snap_us60["road_name"], "US-60 E")
                self.assertEqual(snap_us60["speed_limit_mph"], 55)
                self.assertEqual(snap_us60["maxspeed_source"], "osm_tag")

                route = router.calculate_route(33.3940, -110.7899, 33.3860, -110.7751, "Copper Hills Diner")
                self.assertEqual(route["status"], "ok")
                self.assertTrue(route["is_navigating"])
                self.assertGreaterEqual(len(route["polyline"]), 5)
                m_types = [m["type"] for m in route["maneuvers"]]
                self.assertEqual(m_types[0], "depart")
                self.assertIn("turn-right", m_types)
                self.assertIn("turn-left", m_types)
                self.assertEqual(m_types[-1], "arrive")

                h_search = DummyHandler()
                self.assertTrue(dispatch_get(h_search, urlparse("/api/nav/search?q=Copper&lat=33.394&lon=-110.786"), self.state))
                self.assertEqual(h_search.status, 200)
                self.assertEqual(h_search.json_body()["results"][0]["name"], "Copper Hills Diner")
            finally:
                self.state.router = orig_router

    def test_pedal_commander_ble_protocol_and_offline_truth(self):
        from hardware.pedal_commander import PedalCommanderController, decode_rx_packet

        # Verify binary & ASCII RX frame decoding
        chk = (0xAA + 3 + 7) & 0xFF  # SPORT+ (3), +3 (sens=7)
        dec = decode_rx_packet(bytes([0xAA, 3, 7, chk, 0x55]))
        self.assertTrue(dec["valid"])
        self.assertEqual(dec["mode"], "SPORT+")
        self.assertEqual(dec["level"], 3)

        orig_inst = PedalCommanderController._instance
        orig_pc = getattr(self.state, "pedal_commander", None)
        try:
            PedalCommanderController._instance = None
            with tempfile.TemporaryDirectory() as tmpdir:
                cfg_p = Path(tmpdir) / "pc.json"
                ctrl = PedalCommanderController(config_path=cfg_p, auto_start_worker=False)
                self.state.pedal_commander = ctrl

                res_off = ctrl.set_curve("CITY", -1)
                self.assertFalse(res_off["connected"])
                self.assertFalse(res_off["sent"])
                self.assertEqual(res_off["status"], "offline")

                ctrl._on_ble_rx(bytes([0xAA, 2, 6, (0xAA + 2 + 6) & 0xFF, 0x55]))
                self.assertTrue(ctrl.ack_verified)
                self.assertEqual(ctrl.current_mode, "SPORT")
                self.assertEqual(ctrl.current_level, 2)

                h_cfg = DummyHandler({"mac": "AA:BB:CC:11:22:33", "pin": "654321"})
                self.assertTrue(dispatch_post(h_cfg, urlparse("/api/pedal_commander/config"), self.state))
                self.assertEqual(h_cfg.json_body()["mac"], "AA:BB:CC:11:22:33")
                saved = json.loads(cfg_p.read_text(encoding="utf-8"))
                self.assertEqual(saved["pin"], "654321")

                h_scan = DummyHandler()
                self.assertTrue(dispatch_get(h_scan, urlparse("/api/pedal_commander/scan"), self.state))
                self.assertEqual(h_scan.status, 200)
                devs = h_scan.json_body()["devices"]
                self.assertIsInstance(devs, list)
                if not sys.platform.startswith("linux"):
                    self.assertEqual(devs, [])
        finally:
            PedalCommanderController._instance = orig_inst
            self.state.pedal_commander = orig_pc

    def test_dual_pi_telephony_sms_and_fs_bridge(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import fs_manager
        from telephony.phone_manager import PhoneManager, Pi3AndroidBridgeClient
        from telephony.sms_manager import SMSManager

        bridge_calls = {"dial": [], "sms": []}

        class MockPi3Bridge(BaseHTTPRequestHandler):
            def log_message(self, *args):
                return

            def _send(self, obj):
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                p = urlparse(self.path)
                if p.path == "/status":
                    self._send({
                        "status": "ok",
                        "adb_connected": True,
                        "tether_active": True,
                        "phone_model": "Pixel_8",
                        "battery_pct": 88,
                        "call_state": "IDLE",
                    })
                elif p.path == "/sms/list":
                    self._send({
                        "status": "ok",
                        "messages": [{"id": "m101", "address": "5559990000", "body": "Drive safe Dad!", "date_ms": 1700000000000, "direction": "INBOUND", "read": True}],
                    })
                elif p.path == "/contacts":
                    self._send({"status": "ok", "contacts": [{"name": "Uncle Steven", "phone": "5559990000"}]})
                elif p.path == "/fs/list":
                    self._send({
                        "status": "ok",
                        "path": "pi3://sdcard/Download",
                        "items": [{"name": "notes.txt", "path": "pi3://sdcard/Download/notes.txt", "is_dir": False, "type": "text", "size_bytes": 12}],
                    })
                elif p.path == "/fs/read":
                    self._send({"status": "ok", "path": "pi3://sdcard/Download/notes.txt", "name": "notes.txt", "content": "Tune rev2"})
                elif p.path == "/host/devices":
                    self._send({
                        "status": "ok",
                        "devices": [
                            {"id": "loc_pi3_home", "name": "Pi 3 Home (~)", "label": "PI 3 HOME", "path": "pi3-fs://home", "mount_point": "pi3-fs://home", "icon": "🥧", "free_gb": 12.4, "total_gb": 29.0, "is_removable": False, "host": "pi3", "status": "READY"},
                            {"id": "pi3_usb_THUMB", "name": "Pi 3 USB (THUMB)", "label": "PI3 USB (THUMB)", "path": "pi3-fs://root/media/nfgodin/THUMB", "mount_point": "pi3-fs://root/media/nfgodin/THUMB", "icon": "💾", "free_gb": 7.2, "total_gb": 16.0, "is_removable": True, "host": "pi3", "status": "MOUNTED"},
                        ],
                    })
                elif p.path == "/host/list":
                    self._send({
                        "status": "ok",
                        "path": "pi3-fs://home",
                        "items": [{"name": "dashcam.mp4", "path": "pi3-fs://root/home/nfgodin/dashcam.mp4", "is_dir": False, "type": "video", "size_bytes": 2048}],
                    })
                elif p.path == "/host/read":
                    self._send({"status": "ok", "path": "pi3-fs://root/home/nfgodin/readme.txt", "name": "readme.txt", "content": "Pi 3 storage online"})

            def do_POST(self):
                ln = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(ln).decode("utf-8")) if ln else {}
                p = urlparse(self.path)
                if p.path == "/call/dial":
                    bridge_calls["dial"].append(body.get("number"))
                    self._send({"status": "ok", "dialed": True})
                elif p.path == "/sms/send":
                    bridge_calls["sms"].append(body)
                    self._send({"status": "ok", "sent": True, "transport": "kdeconnect"})
                else:
                    self._send({"status": "ok", "answered": True, "ended": True})

        srv = ThreadingHTTPServer(("127.0.0.1", 0), MockPi3Bridge)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()

        orig_shared = Pi3AndroidBridgeClient._shared_instance
        orig_phone_inst = PhoneManager._instance
        orig_sms_inst = SMSManager._instance
        orig_state_phone = getattr(self.state, "phone", None)
        orig_state_sms = getattr(self.state, "sms", None)
        try:
            # Verify offline failure truthfulness when bridge unreachable
            offline_client = Pi3AndroidBridgeClient(base_url="http://127.0.0.1:9")
            PhoneManager._instance = None
            SMSManager._instance = None
            Pi3AndroidBridgeClient._shared_instance = offline_client
            with tempfile.TemporaryDirectory() as tmpdir:
                pm_off = PhoneManager(
                    bridge_client=offline_client,
                    kinship_file=Path(tmpdir) / "kinship_off.json",
                    history_file=Path(tmpdir) / "history_off.json",
                )
                self.assertFalse(pm_off.dial("5551112222"))

                # Connect to mock Pi 3 ADB bridge
                live_client = Pi3AndroidBridgeClient(base_url=f"http://127.0.0.1:{port}")
                Pi3AndroidBridgeClient._shared_instance = live_client
                PhoneManager._instance = None
                SMSManager._instance = None
                pm = PhoneManager(
                    bridge_client=live_client,
                    kinship_file=Path(tmpdir) / "kinship.json",
                    history_file=Path(tmpdir) / "history.json",
                )
                sm = SMSManager(bridge_client=live_client, storage_file=Path(tmpdir) / "sms.json")
                sm.set_dependencies(None, None, pm.kinship)
                self.state.phone = pm
                self.state.sms = sm

                st = pm.get_status()
                self.assertTrue(st["connected"])
                self.assertTrue(st["android_usb_connected"])
                self.assertEqual(st["device_name"], "Pixel_8")

                h_sync = DummyHandler({})
                self.assertTrue(dispatch_post(h_sync, urlparse("/api/phone/sync"), self.state))
                self.assertGreaterEqual(h_sync.json_body()["sms_sync"]["synced"], 1)

                h_dial = DummyHandler({"number": "5559990000"})
                self.assertTrue(dispatch_post(h_dial, urlparse("/api/phone/dial"), self.state))
                self.assertTrue(h_dial.json_body()["dialed"])
                self.assertIn("5559990000", bridge_calls["dial"])

                h_sms = DummyHandler({"recipient": "5559990000", "text": "On my way"})
                self.assertTrue(dispatch_post(h_sms, urlparse("/api/sms/send"), self.state))
                self.assertEqual(h_sms.json_body()["message"]["delivery_status"], "sent")

                devs = fs_manager.detect_usb_drives()
                self.assertTrue(any(d.get("path") == "pi3://sdcard" and d.get("is_phone") for d in devs))
                self.assertTrue(any(d.get("path") == "pi3-fs://home" and d.get("host") == "pi3" for d in devs))
                self.assertTrue(any(d.get("path") == "pi3-fs://root/media/nfgodin/THUMB" and d.get("is_removable") for d in devs))
                listing = fs_manager.list_directory("pi3://sdcard/Download")
                self.assertEqual(listing["items"][0]["name"], "notes.txt")
                txt = fs_manager.read_text_file("pi3://sdcard/Download/notes.txt")
                self.assertEqual(txt["content"], "Tune rev2")
                h_list = fs_manager.list_directory("pi3-fs://home")
                self.assertEqual(h_list["items"][0]["name"], "dashcam.mp4")
                h_txt = fs_manager.read_text_file("pi3-fs://root/home/nfgodin/readme.txt")
                self.assertEqual(h_txt["content"], "Pi 3 storage online")
        finally:
            srv.shutdown()
            srv.server_close()
            Pi3AndroidBridgeClient._shared_instance = orig_shared
            PhoneManager._instance = orig_phone_inst
            SMSManager._instance = orig_sms_inst
            self.state.phone = orig_state_phone
            self.state.sms = orig_state_sms

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

    def test_privacy_inventory_and_selective_wipe(self):
        from types import SimpleNamespace
        from ai.rag_memory import RagMemoryEngine
        from ai.memory_manager import MemoryManager
        from telephony.phone_manager import PhoneManager, Pi3AndroidBridgeClient
        from telephony.sms_manager import SMSManager

        orig_phone_inst = PhoneManager._instance
        orig_sms_inst = SMSManager._instance
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp = Path(tmpdir)
                (tmp / "storage" / "tts_cache").mkdir(parents=True)
                (tmp / "storage" / "tts_cache" / "phrase1.wav").write_bytes(b"RIFF0000")
                (tmp / "storage" / "trip_archives").mkdir(parents=True)
                (tmp / "storage" / "trip_archives" / "trip_1.zip").write_bytes(b"PK\x03\x04")
                (tmp / "storage" / "logs").mkdir(parents=True)
                (tmp / "storage" / "logs" / "app.log").write_text("log line\n", encoding="utf-8")
                (tmp / "backend" / "ai").mkdir(parents=True)
                (tmp / "backend" / "ai" / "google_oauth_tokens.json").write_text('{"token":"abc"}', encoding="utf-8")
                (tmp / "backend" / "bluetooth_saved.json").write_text('{"mac":"AA:BB"}', encoding="utf-8")
                (tmp / "ui" / "web_preview").mkdir(parents=True)
                (tmp / "ui" / "web_preview" / "last_speech.wav").write_bytes(b"RIFF")

                rag = RagMemoryEngine(db_path=tmp / "storage" / "rag_memory.db")
                rag.add_document("factory_oil", "manual", "Dart Oil", "Pennzoil 5W-40 MS-12991")
                rag.add_document("user_note_1", "custom_note", "My Note", "Remember tire torque")
                mem = MemoryManager(memory_file=str(tmp / "backend" / "ai" / "ai_memory.json"))
                PhoneManager._instance = None
                SMSManager._instance = None
                pm = PhoneManager(
                    bridge_client=Pi3AndroidBridgeClient(base_url="http://127.0.0.1:9"),
                    kinship_file=tmp / "config" / "family_kinship.json",
                    history_file=tmp / "storage" / "call_history.json",
                )
                pm.kinship.add_or_update_contact({"id": "c_1", "name": "Mom", "kinship": "Nanny", "phone": "9285550101"})
                sm = SMSManager(bridge_client=Pi3AndroidBridgeClient(base_url="http://127.0.0.1:9"), storage_file=tmp / "storage" / "sms.json")
                sm.threads["9285550101"] = [{"id": "s1", "text": "Hi"}]
                sm._save()

                class DummyAudio:
                    def __init__(self):
                        self._speech_clips = {1: b"WAV"}
                        self._speech_visemes = {1: {"rms": [0.5]}}
                    def get_cache_stats(self):
                        return {"cached_phrases": 1}
                    def stop_speaking(self):
                        return 1
                    def clear_cache(self):
                        for f in (tmp / "storage" / "tts_cache").glob("*"):
                            f.unlink()
                        return {"cleared": 1}
                    def clear_voice_clips_and_ram(self):
                        self._speech_clips.clear()
                        self._speech_visemes.clear()
                        return {"cache": self.clear_cache(), "ring_clips_cleared": 1}

                class DummyTrips:
                    def get_recent_trips(self, limit=10):
                        return [{"id": 1}]
                    def clear_all_trips(self):
                        return True

                fake_state = SimpleNamespace(
                    base_dir=tmp,
                    rag=rag,
                    llm=SimpleNamespace(memory_mgr=mem, speech_log=[{"speech": "Hello"}]),
                    audio=DummyAudio(),
                    phone=pm,
                    sms=sm,
                    trip_logger=DummyTrips(),
                )

                h_inv = DummyHandler()
                self.assertTrue(dispatch_get(h_inv, urlparse("/api/privacy/inventory"), fake_state))
                inv = h_inv.json_body()["inventory"]
                self.assertGreaterEqual(inv["ai_memory"]["facts"], 1)
                self.assertEqual(inv["phone_accounts"]["contacts"], 1)
                self.assertTrue(inv["phone_accounts"]["oauth_linked"])

                # Wipe ONLY ai_memory + voice_clips first
                h_wipe1 = DummyHandler({"categories": ["ai_memory", "voice_clips"]})
                self.assertTrue(dispatch_post(h_wipe1, urlparse("/api/privacy/wipe"), fake_state))
                self.assertEqual(h_wipe1.json_body()["status"], "ok")
                self.assertEqual(rag.get_driver_facts(), [])
                self.assertEqual(rag.get_recent_diary_entries(), [])
                self.assertEqual(fake_state.llm.speech_log, [])
                self.assertFalse((tmp / "ui" / "web_preview" / "last_speech.wav").exists())
                # Phone & factory manuals/maintenance must remain intact!
                self.assertEqual(len(pm.kinship.get_contacts()), 1)
                self.assertGreaterEqual(len(rag.get_maintenance_status()["items"]), 1)
                self.assertGreaterEqual(len(rag.search("Pennzoil", top_k=2, threshold=0.0)), 1)

                # Re-opening RagMemoryEngine must NOT re-seed wiped facts/diary!
                rag_reopened = RagMemoryEngine(db_path=tmp / "storage" / "rag_memory.db")
                self.assertEqual(rag_reopened.get_driver_facts(), [])
                self.assertEqual(rag_reopened.get_recent_diary_entries(), [])

                # Now wipe phone_accounts + trips_logs
                h_wipe2 = DummyHandler({"categories": ["phone_accounts", "trips_logs"]})
                self.assertTrue(dispatch_post(h_wipe2, urlparse("/api/privacy/wipe"), fake_state))
                inv_after = h_wipe2.json_body()["inventory"]
                self.assertEqual(inv_after["phone_accounts"]["contacts"], 0)
                self.assertEqual(inv_after["phone_accounts"]["sms_messages"], 0)
                self.assertFalse(inv_after["phone_accounts"]["oauth_linked"])
                self.assertEqual(inv_after["trips_logs"]["archive_files"], 0)
                self.assertEqual(inv_after["trips_logs"]["log_files"], 0)
        finally:
            PhoneManager._instance = orig_phone_inst
            SMSManager._instance = orig_sms_inst

    def test_hybrid_rag_web_search_and_auto_memory(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from ai.rag_memory import RagMemoryEngine
        from ai.web_search import is_ephemeral_query, should_search_web

        # 1. Trigger & ephemeral filtering
        trig1, q1 = should_search_web("Look up Garrett GT1446 max turbocharger PSI")
        self.assertTrue(trig1)
        self.assertIn("Garrett GT1446", q1)
        self.assertFalse(is_ephemeral_query(q1))

        trig2, q2 = should_search_web("What is the weather in Payson AZ right now?")
        self.assertTrue(trig2)
        self.assertTrue(is_ephemeral_query(q2))

        trig3, _ = should_search_web("What is my boost right now?")
        self.assertFalse(trig3)

        # 2. Hybrid RAG (BM25 + vector) + retrieve_unified_living_memory includes rag_documents
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            rag = RagMemoryEngine(db_path=tmp / "rag_test.db")
            rag.add_document("trip_1", "TRIP_LOG", "Payson Canyon Run", "Cruised Highway 87 at 17.5 PSI boost cleanly.")
            rag.add_document("part_1", "CUSTOM_NOTE", "MultiAir Solenoid Screen", "Mopar PN-998877-DART filter screen check.")
            hits = rag.search("PN-998877-DART", top_k=2, threshold=0.20)
            self.assertGreaterEqual(len(hits), 1)
            self.assertEqual(hits[0]["doc_id"], "part_1")
            factory_hits = rag.search("55238665", top_k=2, threshold=0.20)
            self.assertTrue(any(h["doc_id"] == "spec_multiair_screen" for h in factory_hits))

            unified = rag.retrieve_unified_living_memory("How was our Payson Highway 87 drive?", max_tokens=400)
            self.assertIn("Payson Canyon Run", unified)

            # 3. Conversational auto-memory extractor
            saved = rag.extract_and_store_chat_memories("Remember that I only run ethanol-free 91 octane", "Got it!")
            self.assertGreaterEqual(len(saved), 1)
            facts = rag.get_driver_facts()
            self.assertTrue(any("ethanol-free 91 octane" in f["value"] for f in facts))

            # 4. End-to-end mocked web search + learned_web_knowledge save + delete route
            from ai.llm_client import LLMClient
            ai_cfg = tmp / "ai_settings.json"
            ai_cfg.write_text('{"mode": "BUILTIN"}', encoding="utf-8")
            llm = LLMClient(config_file=str(ai_cfg))
            learned_tmp = tmp / "learned_web_knowledge.json"
            learned_tmp.write_text('{"version": "1.0", "learned_facts": []}', encoding="utf-8")
            llm.set_rag_engine(rag)
            llm.settings["mode"] = "BUILTIN"
            llm._learned_knowledge_path = lambda: str(learned_tmp)

            def _mock_search(query, timeout=4.5, max_results=3):
                return {
                    "status": "ok",
                    "query": query,
                    "summary": "Garrett GT1446: Twin-scroll ball/journal turbocharger rated around 22 PSI peak.",
                    "sources": [{"title": "Garrett GT1446", "snippet": "Rated around 22 PSI peak.", "url": "https://example.com"}],
                    "error": None,
                }

            with patch("ai.llm_client.search_web_snippets", side_effect=_mock_search):
                res = llm.chat_with_action("Look up Garrett GT1446 peak boost")
            self.assertIn("22 PSI", res["reply"])
            self.assertTrue(res["meta"]["web_searched"])
            self.assertEqual(res["meta"]["web_status"], "ok")
            self.assertEqual(len(res["meta"]["learned_saved"]), 1)

            # Ephemeral weather should NOT be saved permanently
            with patch("ai.llm_client.search_web_snippets", side_effect=lambda q, **kw: {
                "status": "ok", "query": q, "summary": "Sunny 72F in Payson.", "sources": [{"title": "Weather", "snippet": "Sunny 72F in Payson.", "url": ""}], "error": None
            }):
                res_w = llm.chat_with_action("What is the weather in Payson?")
            self.assertEqual(res_w["meta"]["learned_saved"], [])

            h_get = DummyHandler()
            self.assertTrue(dispatch_get(h_get, urlparse("/api/ai/memory/learned"), SimpleNamespace(llm=llm)))
            self.assertEqual(len(h_get.json_body()["learned_facts"]), 1)

            h_del = DummyHandler({"index": 0})
            self.assertTrue(dispatch_post(h_del, urlparse("/api/ai/memory/learned/delete"), SimpleNamespace(llm=llm)))
            self.assertEqual(h_del.json_body()["status"], "ok")
            self.assertEqual(llm.get_learned_facts(), [])

    def test_manual_pdf_ingestion_wipe_preservation_and_routes(self):
        from unittest.mock import patch
        from ai.rag_memory import RagMemoryEngine
        from ai.web_search import should_search_web

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            rag = RagMemoryEngine(db_path=tmp / "rag_manuals.db")
            mdir = tmp / "manuals"
            mdir.mkdir()
            (mdir / "CarPi5_Complete_System_Manual.md").write_text(
                "# Audio System\n" + ("CarPi5 runs Kokoro-82M neural TTS and all-MiniLM-L6-v2 ONNX embeddings cleanly on Cortex-A76 cores.\n" * 4)
                + "\n# OBD-II Telemetry\n" + ("Real Dodge Dart MultiAir 1.4T boost and coolant PIDs flow over native SocketCAN or ELM327 serial adapter.\n" * 4),
                encoding="utf-8",
            )
            fake_pdf = mdir / "2013-Dodge-Dart-OM.pdf"
            fake_pdf.write_bytes(b"%PDF-1.4 mock")

            paged_pdf_text = (
                "Table of Contents\nIntroduction ..... 1\n"
                + "\f"
                + "Fuses and Relays — Interior Junction Box\nFuse F94 controls the 12V console cigar lighter power outlet (20 Amp Yellow Mini).\n"
                + ("Fuse F95 protects the front USB media hub and auxiliary audio jack circuit at 15 Amps.\n" * 3)
            )
            with patch.object(RagMemoryEngine, "_extract_manual_text", side_effect=lambda p: paged_pdf_text if p.suffix == ".pdf" else p.read_text(encoding="utf-8")):
                res1 = rag.ingest_manuals_directory(manuals_dir=str(mdir))
                self.assertEqual(res1["indexed_files"], 2)
                self.assertGreaterEqual(res1["total_chunks"], 2)

                # Idempotent cache check on second call (mtime/size unchanged)
                res2 = rag.ingest_manuals_directory(manuals_dir=str(mdir))
                self.assertEqual(res2["indexed_files"], 0)
                self.assertEqual(res2["cached_files"], 2)

                # Hybrid search surfaces page-labeled Dodge Dart Owner's Manual chunk
                fuse_hits = rag.search("Which fuse controls the cigar lighter F94?", top_k=3, threshold=0.25)
                self.assertGreaterEqual(len(fuse_hits), 1)
                self.assertEqual(fuse_hits[0]["category"], "dodge_dart_manual")
                self.assertIn("p.2", fuse_hits[0]["title"])

                # High-confidence manual hit suppresses redundant web lookup, while explicit lookup still triggers web
                self.assertFalse(should_search_web("What fuse is F94 cigar lighter?", best_manual_score=0.65)[0])
                self.assertTrue(should_search_web("Look up Dodge Dart F94 fuse online", best_manual_score=0.65)[0])

                # Privacy wipe erases personal facts/web notes while preserving indexed Dodge Dart & CarPi5 manuals
                rag.set_driver_fact("preference", "coffee", "Black coffee")
                rag.add_document("web_9", "LEARNED_WEB", "Web Entry", "Ephemeral learned web entry")
                wiped = rag.wipe_ai_memory()
                self.assertGreaterEqual(wiped["facts"], 1)
                status_after = rag.get_manual_index_status()
                self.assertEqual(status_after["file_count"], 2)
                self.assertGreaterEqual(len(rag.search("F94 cigar lighter", top_k=2, threshold=0.20)), 1)

                # Route dispatch checks: GET /api/ai/manuals/status & POST /api/ai/manuals/reindex
                st_h = DummyHandler()
                self.assertTrue(dispatch_get(st_h, urlparse("/api/ai/manuals/status"), SimpleNamespace(rag=rag)))
                self.assertEqual(st_h.json_body()["file_count"], 2)

                re_h = DummyHandler({"force": False})
                with patch.object(rag, "ingest_manuals_directory", return_value={"status": "ok", "total_chunks": 4, "file_count": 2}) as m_ing:
                    self.assertTrue(dispatch_post(re_h, urlparse("/api/ai/manuals/reindex"), SimpleNamespace(rag=rag)))
                    m_ing.assert_called_once_with(force=False)
                self.assertEqual(re_h.json_body()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
