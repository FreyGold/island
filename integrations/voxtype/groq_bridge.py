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
import tempfile
import threading
import time
import urllib.error
import urllib.request
import wave
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


PORT = 26741
GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
MAX_UPLOAD = 25 * 1024 * 1024


def runtime_dir():
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "voxtype"


def merge_text(left, right):
    """Remove words repeated by VoxType's overlapping audio chunks."""
    old, new = left.split(), right.split()
    normalize = lambda word: re.sub(r"[^\w]", "", word.casefold())
    overlap = 0
    for count in range(1, min(8, len(old), len(new)) + 1):
        if [normalize(w) for w in old[-count:]] == [normalize(w) for w in new[:count]]:
            overlap = count
    return " ".join(old + new[overlap:])


def has_speech(body, content_type):
    """Skip near-silent WAV chunks before they use an API request."""
    try:
        message = BytesParser(policy=email.policy.default).parsebytes(
            ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + body
        )
        for part in message.iter_parts():
            if part.get_param("name", header="content-disposition") != "file":
                continue
            with wave.open(io.BytesIO(part.get_payload(decode=True)), "rb") as audio:
                if audio.getsampwidth() != 2:
                    return True
                samples = array.array("h", audio.readframes(audio.getnframes()))
                if os.sys.byteorder != "little":
                    samples.byteswap()
                frame = max(1, int(audio.getframerate() * audio.getnchannels() * 0.02))
                loud = 0
                for start in range(0, len(samples), frame):
                    block = samples[start:start + frame]
                    rms = (sum(s * s for s in block) / max(1, len(block))) ** 0.5 / 32768
                    loud += rms >= 0.001
                return loud >= 3
    except (ValueError, TypeError, AttributeError, wave.Error, EOFError):
        pass
    return True


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
                elif current in ("done", "error") and time.time() * 1000 - self.value["updatedAt"] > 6000:
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
        if self.path == "/session/finish":
            try:
                text = json.loads(body).get("text", "")
                if not isinstance(text, str):
                    raise ValueError()
            except (ValueError, AttributeError):
                self.reply(400, {"error": "Invalid transcript"})
                return
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
        if not has_speech(body, content_type):
            transcript.complete(ticket)
            self.reply(200, {"text": ""})
            return
        request = urllib.request.Request(GROQ_URL, data=body, headers={
            "Authorization": expected, "Content-Type": content_type,
            "User-Agent": "Island-Voxtype/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                value = json.load(response)
            text = value.get("text")
            if not isinstance(text, str):
                raise ValueError("Invalid Groq response")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("serve", "begin", "finish"))
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        parser.exit(1, "The Groq API key is not configured.\n")
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
