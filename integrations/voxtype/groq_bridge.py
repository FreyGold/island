#!/usr/bin/env python3
"""Forward VoxType audio chunks to Groq and publish a live Island transcript."""

import argparse
import array
import email.policy
import hmac
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import urllib.error
import urllib.request
import uuid
import wave
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import webrtcvad
except ImportError:
    webrtcvad = None


PORT = 26741
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_UPLOAD = 25 * 1024 * 1024


def runtime_dir():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "voxtype"


def merge_text(left, right):
    """Use the newer chunk to correct words at the shared audio boundary."""
    old, new = left.split(), right.split()
    normalize = lambda word: re.sub(r"[^\w]", "", word.casefold())
    overlap = 0
    for count in range(1, min(64, len(old), len(new)) + 1):
        if [normalize(w) for w in old[-count:]] == [normalize(w) for w in new[:count]]:
            overlap = count
    if not overlap:
        return " ".join(old + new)
    for index in range(overlap):
        # Keep established letter case and use the newer punctuation.
        previous = re.fullmatch(r"(\W*)(.*?\w)(\W*)", old[-overlap + index])
        current = re.fullmatch(r"(\W*)(.*?\w)(\W*)", new[index])
        if previous and current and previous[2].casefold() == current[2].casefold():
            new[index] = current[1] + previous[2] + current[3]
    return " ".join(old[:-overlap] + new)


def voice_activity(data):
    """Return the WAV format, samples, and speech flags for 20 ms frames."""
    with wave.open(io.BytesIO(data), "rb") as audio:
        if audio.getsampwidth() != 2:
            return None
        rate, channels = audio.getframerate(), audio.getnchannels()
        raw = audio.readframes(audio.getnframes())
    samples = array.array("h", raw)
    if os.sys.byteorder != "little":
        samples.byteswap()
    frame = max(1, int(rate * channels * 0.02))
    detector = webrtcvad.Vad(2) if webrtcvad and channels == 1 and rate in (8000, 16000, 32000, 48000) else None
    flags = []
    for start in range(0, len(samples) - frame + 1, frame):
        block = samples[start:start + frame]
        rms = (sum(s * s for s in block) / frame) ** 0.5 / 32768
        flags.append(rms >= 0.001 and (detector is None or detector.is_speech(raw[start * 2:(start + frame) * 2], rate)))
    return rate, channels, raw, flags


def has_speech(body, content_type, skip_seconds=0):
    """Require new speech after any overlap with the previous audio chunk."""
    try:
        message = BytesParser(policy=email.policy.default).parsebytes(
            ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
        )
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") != "file":
                continue
            activity = voice_activity(part.get_payload(decode=True))
            if activity is None:
                return True
            flags = activity[3][int(skip_seconds / 0.02):]
            return sum(flags) >= max(6, int(len(flags) * 0.06))
    except (ValueError, TypeError, AttributeError, wave.Error, EOFError):
        pass
    return True


def trim_silence(data):
    """Keep speech with short padding and remove long silent ends."""
    try:
        activity = voice_activity(data)
        if activity is None:
            return data
        rate, channels, raw, flags = activity
        voiced = [index for index, flag in enumerate(flags) if flag]
        if not voiced:
            return data
        start = max(0, int((voiced[0] * 0.02 - 0.18) * rate))
        end = min(len(raw) // (channels * 2), int(((voiced[-1] + 1) * 0.02 + 0.24) * rate))
        output = io.BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setnchannels(channels)
            audio.setsampwidth(2)
            audio.setframerate(rate)
            audio.writeframes(raw[start * channels * 2:end * channels * 2])
        return output.getvalue()
    except (ValueError, TypeError, wave.Error, EOFError):
        return data


def configured_overlap():
    try:
        path = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "voxtype/config.toml"
        settings = tomllib.loads(path.read_text()).get("whisper", {})
        return max(0.0, float(settings.get("eager_overlap_secs", 0.5))) if settings.get("eager_processing") else 0.0
    except (OSError, ValueError, TypeError):
        return 0.0


def groq_form(body, content_type, context=""):
    """Add recent text and request confidence data for the uploaded audio."""
    message = BytesParser(policy=email.policy.default).parsebytes(
        ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
    )
    boundary = "IslandGroq" + uuid.uuid4().hex
    parts = []
    prompt = ""
    allowed = {"file", "model", "language", "prompt"}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name not in allowed:
            continue
        disposition = f'Content-Disposition: form-data; name="{name}"'
        if name == "file":
            disposition += '; filename="audio.wav"\r\nContent-Type: audio/wav'
        payload = part.get_payload(decode=True) or b""
        if name == "prompt":
            prompt = payload.decode("utf-8", "replace")
            continue
        if name == "file":
            payload = trim_silence(payload)
        parts.append(f"--{boundary}\r\n{disposition}\r\n\r\n".encode() + payload + b"\r\n")
    prompt = "\n".join(value for value in (prompt, context) if value)
    if prompt:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="prompt"\r\n\r\n'.encode() + prompt.encode() + b"\r\n")
    for name, value in (("response_format", "verbose_json"), ("temperature", "0")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def transcription_text(value):
    """Keep spoken segments and reject uncertain text from silent audio."""
    text = value.get("text")
    if not isinstance(text, str):
        raise ValueError("Invalid Groq response")
    segments = value.get("segments")
    if not isinstance(segments, list) or not segments:
        return text
    kept = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
            return text
        no_speech = float(segment.get("no_speech_prob") or 0)
        logprob = float(segment.get("avg_logprob") or 0)
        compression = float(segment.get("compression_ratio") or 0)
        if no_speech >= 0.85 or (no_speech >= 0.6 and logprob < -0.5):
            continue
        if logprob < -1.4 and compression > 2.4:
            continue
        kept.append(segment["text"].strip())
    return " ".join(kept)


def filter_standalone_thanks(text, allow=False):
    """Block the standalone outro that can pass Whisper's confidence checks."""
    if not allow and re.findall(r"\w+", text.casefold()) == ["thank", "you"]:
        return ""
    return text


def error_message(code):
    if code in (401, 403):
        return "Groq rejected the API key."
    if code == 429:
        return "Groq rate limit reached. Try again shortly."
    return "Groq could not transcribe this audio."


class Transcript:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / "island-dictation.json"
        self.lock = threading.RLock()
        self.generation = 0
        self.sequence = 0
        self.results = {}
        self.overlap_seconds = 0.0
        self.value = {"phase": "idle", "text": "", "startedAt": 0, "error": "", "pending": 0}

    def publish(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.value["updatedAt"] = int(time.time() * 1000)
        descriptor, name = tempfile.mkstemp(prefix=".island-dictation-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(self.value, stream, ensure_ascii=False)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def begin(self):
        with self.lock:
            self.generation += 1
            self.sequence = 0
            self.results = {}
            self.overlap_seconds = configured_overlap()
            self.value = {"phase": "recording", "text": "", "startedAt": int(time.time() * 1000), "error": "", "pending": 0}
            self.publish()

    def reserve(self):
        with self.lock:
            ticket = (self.generation, self.sequence)
            self.sequence += 1
            if self.value["phase"] in ("recording", "transcribing"):
                self.value["pending"] += 1
                self.publish()
            return ticket

    def overlap_for(self, ticket):
        with self.lock:
            active = self.value["phase"] in ("recording", "transcribing")
            return self.overlap_seconds if active and ticket[0] == self.generation and ticket[1] > 0 else 0.0

    def context_for(self, ticket):
        with self.lock:
            if ticket[0] != self.generation or self.value["phase"] not in ("recording", "transcribing"):
                return ""
            combined = ""
            for number in range(ticket[1]):
                if number not in self.results:
                    break
                combined = merge_text(combined, self.results[number])
            return combined.encode("utf-8")[-480:].decode("utf-8", "ignore")

    def finalize(self, fallback):
        with self.lock:
            ready = (self.value["phase"] in ("recording", "transcribing")
                     and self.sequence > 0 and len(self.results) == self.sequence
                     and self.value["pending"] == 0 and not self.value["error"])
            return self.value["text"] if ready and self.value["text"] else fallback

    def complete(self, ticket, text="", error=""):
        with self.lock:
            generation, index = ticket
            if generation != self.generation or self.value["phase"] not in ("recording", "transcribing"):
                return
            self.results[index] = text
            combined = ""
            for number in range(self.sequence):
                if number not in self.results:
                    break
                combined = merge_text(combined, self.results[number])
            self.value["text"] = combined
            self.value["pending"] = max(0, self.value["pending"] - 1)
            if error:
                self.value["error"] = error
            self.publish()

    def finish(self, text):
        with self.lock:
            self.value.update(phase="done", text=text, pending=0)
            self.publish()

    def watch(self):
        while True:
            time.sleep(0.2)
            try:
                phase = (self.directory / "state").read_text().strip()
                pid = int((self.directory / "pid").read_text())
                os.kill(pid, 0)
            except (OSError, ValueError):
                phase = "idle"
            with self.lock:
                current = self.value["phase"]
                if current in ("recording", "transcribing"):
                    if phase == "idle":
                        # A cancelled session must not leave text in the next one.
                        self.generation += 1
                        self.value.update(phase="error" if self.value["error"] else "idle", text="", pending=0)
                        self.publish()
                    elif phase == "transcribing" and current != "transcribing":
                        self.value["phase"] = "transcribing"
                        self.publish()
                elif current in ("done", "error") and time.time() * 1000 - self.value["updatedAt"] > (1500 if current == "done" else 6000):
                    self.value.update(phase="idle", text="", error="", pending=0)
                    self.publish()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        # Audio, API keys, and dictated text must not enter the journal.
        pass

    def reply(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        expected = "Bearer " + self.server.api_key
        if not hmac.compare_digest(self.headers.get("Authorization", ""), expected):
            self.reply(401, {"error": "Authorization required"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_UPLOAD:
            self.reply(413, {"error": "Audio size is not supported"})
            return
        self.connection.settimeout(30)
        try:
            body = self.rfile.read(length)
        except (OSError, socket.timeout):
            self.reply(408, {"error": "Audio upload timed out"})
            return
        transcript = self.server.transcript
        if self.path == "/session/begin":
            transcript.begin()
            self.reply(200, {"ok": True})
            return
        if self.path in ("/session/finish", "/session/finalize"):
            try:
                text = json.loads(body).get("text", "")
                if not isinstance(text, str):
                    raise ValueError()
            except (ValueError, AttributeError):
                self.reply(400, {"error": "Invalid transcript"})
                return
            if self.path == "/session/finalize":
                self.reply(200, {"text": transcript.finalize(text)})
            else:
                transcript.finish(text)
                self.reply(200, {"ok": True})
            return
        if self.path != "/v1/audio/transcriptions":
            self.reply(404, {"error": "Unknown endpoint"})
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data;"):
            self.reply(400, {"error": "Audio must use multipart form data"})
            return
        ticket = transcript.reserve()
        if not has_speech(body, content_type, transcript.overlap_for(ticket)):
            transcript.complete(ticket)
            self.reply(200, {"text": ""})
            return
        body, content_type = groq_form(body, content_type, transcript.context_for(ticket))
        request = urllib.request.Request(GROQ_URL, data=body, headers={
            "Authorization": expected, "Content-Type": content_type,
            "User-Agent": "Island-Voxtype/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                value = json.load(response)
            text = filter_standalone_thanks(
                transcription_text(value),
                allow=os.environ.get("ISLAND_ALLOW_STANDALONE_THANK_YOU") == "1",
            )
        except urllib.error.HTTPError as error:
            message = error_message(error.code)
            transcript.complete(ticket, error=message)
            self.reply(error.code, {"error": message})
            return
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            message = "Groq did not respond. Check your connection."
            transcript.complete(ticket, error=message)
            self.reply(502, {"error": message})
            return
        transcript.complete(ticket, text.strip())
        self.reply(200, {"text": text})


def hook(action, api_key, port):
    value = {}
    if action == "finish":
        result = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
        if result.returncode:
            return 1
        value["text"] = result.stdout.decode("utf-8", "replace")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/session/{action}", data=json.dumps(value).encode(),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=3):
            pass
    except (urllib.error.URLError, OSError):
        return 1
    return 0


def finalize(text, api_key, port):
    """Use the joined preview for output, or keep the input on failure."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/session/finalize", data=json.dumps({"text": text}).encode(),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            value = json.load(response).get("text")
        return value if isinstance(value, str) and value else text
    except (urllib.error.URLError, OSError, ValueError, AttributeError):
        return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve", "begin", "finish", "finalize"))
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        parser.exit(1, "The Groq API key is not configured.\n")
    if args.action == "finalize":
        sys.stdout.write(finalize(sys.stdin.read(), api_key, args.port))
        return 0
    if args.action != "serve":
        return hook(args.action, api_key, args.port)
    transcript = Transcript(runtime_dir())
    transcript.publish()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.api_key = api_key
    server.transcript = transcript
    threading.Thread(target=transcript.watch, daemon=True).start()
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
