# VoxType live dictation

The Groq bridge works with VoxType's eager processing mode. VoxType sends short,
overlapping audio chunks while the microphone is active. The bridge forwards
them to Groq and writes the growing transcript for Island. VoxType combines the
chunks and copies the full text when recording stops.

Ctrl + Super + X keeps its normal toggle action. Right Alt and the Dictate
control also work. The Dictation switch is under Settings → Live Activities.

The preview updates about every four seconds, plus the API response time. Groq
uses file uploads for speech recognition. This is chunked transcription, so it
does not show each word immediately. Groq bills each request for at least ten
seconds of audio, including requests with shorter chunks.

## Local setup

`~/.config/voxtype/groq.env` holds `GROQ_API_KEY` and
`VOXTYPE_WHISPER_API_KEY`. Keep its permissions at `600`. The API key and local
configuration are outside this repository.

The `island-voxtype.service` user service runs `groq_bridge.py serve`. The
VoxType service loads the same environment file and starts after the bridge.
VoxType uses these settings:

```toml
[whisper]
mode = "remote"
remote_endpoint = "http://127.0.0.1:26741"
remote_model = "whisper-large-v3-turbo"
remote_timeout_secs = 30
eager_processing = true
eager_chunk_secs = 4.0
eager_overlap_secs = 0.5

[output]
mode = "clipboard"
pre_recording_command = "python3 '/absolute/path/to/groq_bridge.py' begin"
post_output_command = "python3 '/absolute/path/to/groq_bridge.py' finish"

[osd]
enabled = false
```

Use the plugin's installed path for both commands. Restart the bridge and
VoxType after a configuration change.

The bridge listens on localhost and requires the key for each request. It
stores the preview in `$XDG_RUNTIME_DIR/voxtype/island-dictation.json` with
permissions `600`. It clears the text about 1.5 seconds after completion. Error
notices stay for six seconds. It does not write audio, transcripts, or keys to
the journal.

Run the bridge checks with `python3 -m unittest discover -s integrations/voxtype`.
