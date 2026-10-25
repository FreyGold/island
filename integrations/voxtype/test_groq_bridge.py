"""Check transcript order, session boundaries, and the local Groq endpoint."""

import http.client
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import wave
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from unittest.mock import patch

from groq_bridge import Handler, ThreadingHTTPServer, Transcript, finalize, groq_form, has_speech, merge_text, transcription_text, trim_silence, filter_standalone_thanks


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
        self.assertEqual(merge_text("Hello, world!", "WORLD here."), "Hello, world here.")
        self.assertEqual(merge_text("مرحبا بك", "بك اليوم"), "مرحبا بك اليوم")

    def test_new_context_corrects_an_early_sentence_end(self):
        for punctuation in (".", "!", "?"):
            with self.subTest(punctuation=punctuation):
                self.assertEqual(
                    merge_text("I want to understand the importance" + punctuation, "The importance of this change."),
                    "I want to understand the importance of this change.",
                )

    def test_real_question_and_proper_name_are_kept(self):
        self.assertEqual(merge_text("How are you?", "Are you? I am fine."), "How are you? I am fine.")
        self.assertEqual(merge_text("I use VoxType.", "Voxtype to record."), "I use VoxType to record.")

    def test_context_uses_only_earlier_results_in_the_same_session(self):
        first, second, third = (self.transcript.reserve() for _ in range(3))
        self.transcript.complete(third, "A future result.")
        self.transcript.complete(first, "Some earlier words.")
        self.assertEqual(self.transcript.context_for(second), "Some earlier words.")
        self.transcript.begin()
        self.assertEqual(self.transcript.context_for(second), "")

    def test_incomplete_or_failed_session_keeps_native_output(self):
        ticket = self.transcript.reserve()
        self.assertEqual(self.transcript.finalize("Native text."), "Native text.")
        self.transcript.complete(ticket, "Preview text.", error="Request failed.")
        self.assertEqual(self.transcript.finalize("Native text."), "Native text.")


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
        self.assertEqual(self.request("/session/finalize", b'{"text":"hello"}', authorized=False)[0], 401)

    def test_final_output_uses_corrected_preview(self):
        first, second = self.server.transcript.reserve(), self.server.transcript.reserve()
        self.server.transcript.complete(first, "I want the sentence.")
        self.server.transcript.complete(second, "The sentence to continue.")
        native = "I want the sentence. The sentence to continue."
        port = self.server.server_address[1]
        self.assertEqual(finalize(native, "test-key", port), "I want the sentence to continue.")
        self.server.transcript.finish("An earlier dictation.")
        self.assertEqual(finalize(native, "test-key", port), native)

    def test_finalize_failure_keeps_original_input(self):
        with patch("groq_bridge.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            self.assertEqual(finalize("Keep this dictation.", "test-key", 1), "Keep this dictation.")

    def test_silence_uses_no_cloud_request(self):
        body = self.audio_body()
        content_type = "multipart/form-data; boundary=test"
        self.assertFalse(has_speech(body, content_type))
        with patch("groq_bridge.urllib.request.urlopen") as upstream:
            self.assertEqual(self.request("/v1/audio/transcriptions", body, content_type=content_type), (200, {"text": ""}))
            upstream.assert_not_called()

    def test_cloud_result_updates_live_preview(self):
        response = io.BytesIO(b'{"text": "A live sentence."}')
        with patch("groq_bridge.has_speech", return_value=True), patch("groq_bridge.urllib.request.urlopen", return_value=response) as upstream:
            status, value = self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
            self.assertEqual((status, value), (200, {"text": "A live sentence."}))
            self.assertEqual(self.server.transcript.value["text"], "A live sentence.")
            self.assertEqual(upstream.call_args.args[0].full_url, "https://api.groq.com/openai/v1/audio/transcriptions")
            self.assertIn(b"verbose_json", upstream.call_args.args[0].data)

    def test_cloud_request_includes_recent_context(self):
        first = self.server.transcript.reserve()
        self.server.transcript.complete(first, "The Island plugin uses VoxType.")
        with patch("groq_bridge.has_speech", return_value=True), patch("groq_bridge.urllib.request.urlopen", return_value=io.BytesIO(b'{"text":"VoxType to record."}')) as upstream:
            self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
            request = upstream.call_args.args[0]
            message = BytesParser(policy=default).parsebytes(("Content-Type: " + request.headers["Content-type"] + "\r\n\r\n").encode() + request.data)
            prompts = [part.get_payload(decode=True).decode() for part in message.iter_parts() if part.get_param("name", header="content-disposition") == "prompt"]
            self.assertEqual(prompts, ["The Island plugin uses VoxType."])

    def test_recent_context_keeps_the_configured_prompt(self):
        body = self.audio_body()[:-len(b"--test--\r\n")] + b'--test\r\nContent-Disposition: form-data; name="prompt"\r\n\r\nIsland, VoxType.\r\n--test--\r\n'
        data, content_type = groq_form(body, "multipart/form-data; boundary=test", "Some recent words.")
        message = BytesParser(policy=default).parsebytes(("Content-Type: " + content_type + "\r\n\r\n").encode() + data)
        prompts = [part.get_payload(decode=True).decode() for part in message.iter_parts() if part.get_param("name", header="content-disposition") == "prompt"]
        self.assertEqual(prompts, ["Island, VoxType.\nSome recent words."])

    def test_rate_limit_has_a_clear_message(self):
        failure = urllib.error.HTTPError("https://api.groq.com", 429, "rate limit", {}, None)
        self.addCleanup(failure.close)
        with patch("groq_bridge.has_speech", return_value=True), patch("groq_bridge.urllib.request.urlopen", side_effect=failure):
            status, value = self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
            self.assertEqual(status, 429)
            self.assertEqual(value["error"], "Groq rate limit reached. Try again shortly.")
            self.assertEqual(self.server.transcript.value["pending"], 0)

    def test_repeated_tail_audio_does_not_call_groq(self):
        self.server.transcript.overlap_seconds = 0.5
        previous = self.server.transcript.reserve()
        self.server.transcript.complete(previous, "Previous sentence.")
        body = SpeechFilterTests.multipart(SpeechFilterTests.speech_audio(0, 20, 180))
        with patch("groq_bridge.webrtcvad.Vad") as detector, patch("groq_bridge.urllib.request.urlopen") as upstream:
            detector.return_value.is_speech.return_value = True
            self.assertEqual(self.request("/v1/audio/transcriptions", body, content_type="multipart/form-data; boundary=test"), (200, {"text": ""}))
            upstream.assert_not_called()
        self.assertEqual(self.server.transcript.value["text"], "Previous sentence.")

    def test_confident_standalone_thanks_never_reaches_voxtype(self):
        previous = self.server.transcript.reserve()
        self.server.transcript.complete(previous, "Keep the actual dictation.")
        response = io.BytesIO(json.dumps({"text": "Thank you.", "segments": [
            {"text": "Thank you.", "no_speech_prob": 0.01, "avg_logprob": -0.1},
        ]}).encode())
        with patch("groq_bridge.has_speech", return_value=True), patch("groq_bridge.urllib.request.urlopen", return_value=response):
            result = self.request("/v1/audio/transcriptions", self.audio_body(600), content_type="multipart/form-data; boundary=test")
        self.assertEqual(result, (200, {"text": ""}))
        self.assertEqual(self.server.transcript.value["text"], "Keep the actual dictation.")


class SpeechFilterTests(unittest.TestCase):
    def test_standalone_thanks_is_blocked_with_any_case_or_punctuation(self):
        for text in ("Thank you.", "thank you", " THANK YOU! ", '“Thank you.”'):
            with self.subTest(text=text):
                self.assertEqual(filter_standalone_thanks(text), "")

    def test_thanks_inside_real_sentences_is_preserved(self):
        for text in ("Tell him thank you.", "No, thank you.", "Thank you for the help."):
            with self.subTest(text=text):
                self.assertEqual(filter_standalone_thanks(text), text)

    def test_standalone_thanks_can_be_enabled_explicitly(self):
        self.assertEqual(filter_standalone_thanks("Thank you.", allow=True), "Thank you.")

    @staticmethod
    def speech_audio(leading_frames, speech_frames, trailing_frames):
        audio = io.BytesIO()
        raw = b"\0\0" * (320 * leading_frames) + (600).to_bytes(2, "little", signed=True) * (320 * speech_frames) + b"\0\0" * (320 * trailing_frames)
        with wave.open(audio, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            stream.writeframes(raw)
        return audio.getvalue()

    @staticmethod
    def multipart(audio):
        return b'--test\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n' + audio + b"\r\n--test--\r\n"

    def test_overlap_alone_is_not_new_speech(self):
        body = self.multipart(self.speech_audio(0, 20, 180))
        with patch("groq_bridge.webrtcvad.Vad") as detector:
            detector.return_value.is_speech.return_value = True
            self.assertTrue(has_speech(body, "multipart/form-data; boundary=test"))
            self.assertFalse(has_speech(body, "multipart/form-data; boundary=test", 0.5))

    def test_new_speech_after_overlap_is_kept(self):
        body = self.multipart(self.speech_audio(25, 25, 150))
        with patch("groq_bridge.webrtcvad.Vad") as detector:
            detector.return_value.is_speech.return_value = True
            self.assertTrue(has_speech(body, "multipart/form-data; boundary=test", 0.5))

    def test_long_silent_ends_are_trimmed_with_padding(self):
        audio = self.speech_audio(50, 25, 125)
        with patch("groq_bridge.webrtcvad.Vad") as detector:
            detector.return_value.is_speech.return_value = True
            trimmed = trim_silence(audio)
        with wave.open(io.BytesIO(trimmed), "rb") as stream:
            duration = stream.getnframes() / stream.getframerate()
        self.assertAlmostEqual(duration, 0.18 + 0.5 + 0.24, places=3)

    def test_background_noise_does_not_count_as_speech(self):
        self.assertFalse(has_speech(EndpointTests.audio_body(600), "multipart/form-data; boundary=test"))

    def test_confidence_check_alone_accepts_thanks(self):
        value = {"text": "Thank you.", "segments": [{"text": "Thank you.", "no_speech_prob": 0.01, "avg_logprob": -0.1}]}
        self.assertEqual(transcription_text(value), "Thank you.")

    def test_silent_thank_you_is_rejected(self):
        value = {"text": "Thank you.", "segments": [{"text": "Thank you.", "no_speech_prob": 0.95, "avg_logprob": -1.2}]}
        self.assertEqual(transcription_text(value), "")

    def test_silent_tail_does_not_remove_the_spoken_sentence(self):
        value = {"text": "Keep this sentence. Thank you.", "segments": [
            {"text": "Keep this sentence.", "no_speech_prob": 0.01, "avg_logprob": -0.1},
            {"text": "Thank you.", "no_speech_prob": 0.7, "avg_logprob": -0.8},
        ]}
        self.assertEqual(transcription_text(value), "Keep this sentence.")


if __name__ == "__main__":
    unittest.main()
