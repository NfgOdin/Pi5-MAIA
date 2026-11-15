"""Automated smoke tests for modularized CarPi5 HTTP route dispatchers."""

import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from routes import dispatch_get, dispatch_head, dispatch_post


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
        latest_frame=SimpleNamespace(speed_mph=0.0),
        latest_thermal_data=None,
        is_music_playing=False,
        obd_reader=SimpleNamespace(connected=False, status_message="Offline", dyno=dyno),
        simulator=SimpleNamespace(dyno=dyno),
        gps=SimpleNamespace(get_telemetry=lambda: {"dragy": {}, "g_forces": {}, "speed_mph": 0.0, "road_grade_pct": 0.0}),
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
        ),
        trip_logger=SimpleNamespace(reset_current_trip=lambda: None),
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

    def test_unmatched_routes_fall_through(self):
        h = DummyHandler()
        self.assertFalse(dispatch_get(h, urlparse("/api/status"), self.state))
        self.assertFalse(dispatch_post(h, urlparse("/api/ai/chat"), self.state))


if __name__ == "__main__":
    unittest.main()
