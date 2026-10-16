"""The URL action's value is sent as the request body.

It used to be dropped: performUrlAction queued the value as the payload but
set neither isJson nor isUrlEncoded, and makeRestCall only sends a body when
one of them is set. The editor stores the value as parsed JSON when it parses,
so JSON goes out as JSON and any other text as a form body, exactly as typed.
"""
import http.server
import json
import threading
import unittest

import _support  # noqa: F401
import rest
from sequenceAction import SequenceAction

BAND = "0453652AC05F80"


class EncodeBodyTests(unittest.TestCase):
    def test_no_value_sends_no_body(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.assertEqual(SequenceAction.encodeUrlBody(value), (None, False, False))

    def test_json_goes_out_as_json(self):
        for value in ({"on": True, "bri": 128}, [1, 2], 5, True):
            with self.subTest(value=value):
                body, isJson, isUrlEncoded = SequenceAction.encodeUrlBody(value)
                self.assertEqual(json.loads(body), value)
                self.assertEqual((isJson, isUrlEncoded), (True, False))

    def test_other_text_goes_out_as_typed_form_data(self):
        self.assertEqual(SequenceAction.encodeUrlBody("band=04AB&source=reader"),
                         ("band=04AB&source=reader", False, True))


class PerformTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.original = rest.RestQueue.makeRestCallAsync
        rest.RestQueue.makeRestCallAsync = lambda _self, *a, **k: self.sent.append(a)

    def tearDown(self):
        rest.RestQueue.makeRestCallAsync = self.original

    def test_a_json_value_is_queued_as_a_json_body_with_the_band_filled_in(self):
        action = SequenceAction.new_action_url("http://host/tap", "POST", {"band": "{band_id}"})
        self.assertTrue(action.performAction(None, None, band_id=BAND))
        url, method, body, isJson, isUrlEncoded = self.sent[0]
        self.assertEqual((url, method, isJson, isUrlEncoded), ("http://host/tap", "POST", True, False))
        self.assertEqual(json.loads(body), {"band": BAND})

    def test_a_text_value_is_queued_as_a_form_body(self):
        action = SequenceAction.new_action_url("http://host/tap", "POST", "band={band_id}")
        action.performAction(None, None, band_id=BAND)
        self.assertEqual(self.sent[0][2:], (f"band={BAND}", False, True))

    def test_no_value_queues_no_body(self):
        SequenceAction.new_action_url("http://host/win&PL=75").performAction(None, None)
        self.assertEqual(self.sent[0][2:], (None, False, False))


class FakeHttp:
    def __init__(self):
        self.requests = []

    def request(self, **kwargs):
        self.requests.append(kwargs)


class MakeRestCallTests(unittest.TestCase):
    def setUp(self):
        self.original = rest.RestHelpers._http_obj
        self.http = rest.RestHelpers._http_obj = FakeHttp()

    def tearDown(self):
        rest.RestHelpers._http_obj = self.original

    def test_a_text_body_is_sent_as_utf8(self):
        rest.RestHelpers.makeRestCall("http://host/", "POST", "name=Zoë ✨", isUrlEncoded=True)
        request = self.http.requests[0]
        self.assertEqual(request["body"], "name=Zoë ✨".encode("utf-8"))
        self.assertIn("x-www-form-urlencoded", request["headers"]["Content-Type"])


class RealHttpServerTest(unittest.TestCase):
    """End to end over a socket - needs the real httplib2, as on a Pi."""

    @classmethod
    def setUpClass(cls):
        try:
            import httplib2
            httplib2.Http
        except (ImportError, AttributeError):
            raise unittest.SkipTest("httplib2 is not installed")
        if not hasattr(rest.RestHelpers._http_obj, "request"):
            raise unittest.SkipTest("httplib2 is stubbed")

    def setUp(self):
        received = self.received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                received.append((self.headers.get("Content-Type"), self.rfile.read(length)))
                self.send_response(204)
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/tap"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def send(self, data):
        body, isJson, isUrlEncoded = SequenceAction.encodeUrlBody(data)
        rest.RestHelpers.makeRestCall(self.url, "POST", body, isJson, isUrlEncoded)

    def test_a_json_body_arrives_as_json(self):
        self.send({"band": BAND})
        contentType, body = self.received[0]
        self.assertTrue(contentType.startswith("application/json"))
        self.assertEqual(json.loads(body), {"band": BAND})

    def test_a_form_body_arrives_as_typed(self):
        self.send(f"band={BAND}&source=reader")
        contentType, body = self.received[0]
        self.assertTrue(contentType.startswith("application/x-www-form-urlencoded"))
        self.assertEqual(body, f"band={BAND}&source=reader".encode())


if __name__ == "__main__":
    unittest.main()
