# VoxType live dictation

The Groq bridge works with VoxType's eager processing mode. VoxType sends short,
overlapping audio chunks while the microphone is active. The bridge forwards
them to Groq and writes the growing transcript for Island. The bridge joins
shared words and lets later audio correct their punctuation. VoxType uses this
same text for the final paste when recording stops.

Ctrl + Super + X keeps its normal toggle action. Right Alt and the Dictate
control also work. The Dictation switch is under Settings → Live Activities.

The first preview arrives after six seconds, plus the API response time. Later
updates arrive about every four seconds. Each six-second window repeats two
seconds from the previous window: 0–6, 4–10, 8–14, and so on. The bridge also
sends recent text as context. This reduces false sentence breaks at a boundary.
Whisper can still make punctuation errors.

Groq uses file uploads for speech recognition. This is chunked transcription, so it
does not show each word immediately. Groq bills each request for at least ten
seconds of audio, including requests with shorter chunks.

## Local setup

`~/.config/voxtype/groq.env` holds `GROQ_API_KEY` and
`VOXTYPE_WHISPER_API_KEY`. Keep its permissions at `600`. The API key and local
configuration are outside this repository.

The `island-voxtype.service` user service runs `groq_bridge.py serve` with a
Python environment that contains `requirements.txt`. WebRTC voice detection
rejects silence and background noise. The bridge trims long silent ends before
upload. Later chunks must contain speech beyond the overlap with the previous
chunk. A repeated tail with no new speech does not make another API request.
Groq segment confidence checks also reject uncertain text from silent audio.

The bridge also blocks a chunk that contains only “Thank you.”. Whisper can
produce that phrase with high confidence over noise. This rule also removes a
genuine “thank you” when it occupies a whole chunk. Longer phrases such as
“tell him thank you” stay unchanged. Set
`ISLAND_ALLOW_STANDALONE_THANK_YOU=1` in the service environment to allow it.

The VoxType service loads the same environment file and starts after the bridge.
VoxType uses these settings:

```toml
[whisper]
mode = "remote"
remote_endpoint = "http://127.0.0.1:26741"
remote_model = "whisper-large-v3-turbo"
remote_timeout_secs = 30
eager_processing = true
eager_chunk_secs = 6.0
eager_overlap_secs = 2.0

[output]
mode = "paste"
paste_keys = "shift+insert"
restore_clipboard = false
wait_for_modifier_release = true
pre_type_delay_ms = 150
pre_recording_command = "python3 '/absolute/path/to/groq_bridge.py' begin"
post_output_command = "python3 '/absolute/path/to/groq_bridge.py' finish"

[output.post_process]
command = "python3 '/absolute/path/to/groq_bridge.py' finalize"
timeout_ms = 3000

[osd]
enabled = false
```

Set `mode = "clipboard"` for copy only. Paste mode sends text through the
terminal or browser paste action. Ctrl + V can
invoke image paste in a terminal application. Keep `restore_clipboard = false`
to retain the dictated text for manual paste.

The VoxType service adds `integrations/voxtype/bin` to its command path. Its
`wl-copy` wrapper labels dictation as UTF-8 text. Explicit clipboard types,
such as an image restored by the caller, retain their original type.

Create the speech filter environment from the plugin folder:

```sh
python3 -m venv ~/.local/share/omarchy/island-voxtype-venv
~/.local/share/omarchy/island-voxtype-venv/bin/python -m pip install -r integrations/voxtype/requirements.txt
```

Use that environment's Python for the bridge service. The start, finish, and
finalize commands can use the system Python. Finalize uses the joined preview
for the final paste. It keeps VoxType's output if the bridge is unavailable or
the session has an error.

Use the plugin's installed path for all three commands. Restart the bridge and
VoxType after a configuration change.

The bridge listens on localhost and requires the key for each request. It
stores the preview in `$XDG_RUNTIME_DIR/voxtype/island-dictation.json` with
permissions `600`. It clears the text about 1.5 seconds after completion. Error
notices stay for six seconds. It does not write audio, transcripts, or keys to
the journal.

Run the bridge checks with the environment's Python:
`python -m unittest discover -s integrations/voxtype`.
