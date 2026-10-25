"""Check transcript order, session boundaries, and the local Groq endpoint."""

import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import wave
from pathlib import Path
from unittest.mock import patch

from groq_bridge import Handler, ThreadingHTTPServer, Transcript, has_speech, merge_text


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.transcript = Transcript(self.temporary.name)
        self.transcript.begin()

    def test_results_keep_request_order(self):
        first, second = self.transcript.reserve(), self.transcript.reserve()
        self.transcript.complete(second, "world. This is live.")
        self.assertEqual(self.transcript.value["text"], "")
        self.transcript.complete(first, "Hello world.")
        self.assertEqual(self.transcript.value["text"], "Hello world. This is live.")
        self.assertEqual(self.transcript.value["pending"], 0)

    def test_late_result_cannot_enter_a_new_session(self):
        old = self.transcript.reserve()
        self.transcript.begin()
        self.transcript.complete(old, "Old dictation")
        self.assertEqual(self.transcript.value["text"], "")

    def test_finish_uses_voxtype_final_text(self):
        ticket = self.transcript.reserve()
        self.transcript.complete(ticket, "A partial sentence")
        self.transcript.finish("The full, corrected sentence.")
        self.transcript.complete(ticket, "A late result")
        self.assertEqual(self.transcript.value["text"], "The full, corrected sentence.")
        self.assertEqual(self.transcript.value["phase"], "done")
        self.assertEqual(self.transcript.path.stat().st_mode & 0o777, 0o600)

    def test_overlap_keeps_unicode_and_punctuation(self):
        self.assertEqual(merge_text("Hello, world!", "WORLD here."), "Hello, world! here.")
        self.assertEqual(merge_text("مرحبا بك", "بك اليوم"), "مرحبا بك اليوم")


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.api_key = "test-key"
        self.server.transcript = Transcript(self.temporary.name)
        self.server.transcript.begin()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, path, body, authorized=True, content_type="application/json"):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        headers = {"Content-Type": content_type}
        if authorized:
            headers["Authorization"] = "Bearer test-key"
        connection.request("POST", path, body, headers)
        response = connection.getresponse()
        value = json.loads(response.read())
        connection.close()
        return response.status, value

    @staticmethod
    def audio_body(amplitude=0):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(int(amplitude).to_bytes(2, "little", signed=True) * 3200)
        body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'
        return body + audio.getvalue() + b"\r\n--test--\r\n"

    def test_endpoint_requires_authorization(self):
        self.assertEqual(self.request("/session/begin", b"{}", authorized=False)[0], 401)

    def test_silence_uses_no_cloud_request(self):
        body = self.audio_body()
        content_type = "multipart/form-data; boundary=test"
        self.assertFalse(has_speech(body, content_type))
        with patch("groq_bridge.urllib.request.urlopen") as upstream:
            self.assertEqual(self.request("/v1/audio/transcriptions", body, content_type=content_type), (200, {"text": ""}))
            upstream.assert_not_called()

    def test_cloud_result_updates_live_preview(self):
        response = io.BytesIO(b'{"text": "A live sentence."}')
        with patch("groq_bridge.urllib.request.urlopen", return_value=response) as upstream:
            status, value = self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
            self.assertEqual((status, value), (200, {"text": "A live sentence."}))
            self.assertEqual(self.server.transcript.value["text"], "A live sentence.")
            self.assertEqual(upstream.call_args.args[0].full_url, "https://api.groq.com/openai/v1/audio/transcriptions")

    def test_rate_limit_has_a_clear_message(self):
        failure = urllib.error.HTTPError("https://api.groq.com", 429, "rate limit", {}, None)
        with patch("groq_bridge.urllib.request.urlopen", side_effect=failure):
            status, value = self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
            self.assertEqual(status, 429)
            self.assertEqual(value["error"], "Groq rate limit reached. Try again shortly.")
            self.assertEqual(self.server.transcript.value["pending"], 0)


if __name__ == "__main__":
    unittest.main()
