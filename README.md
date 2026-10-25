# Dictate

A macOS menu bar app for dictating into any text field. Hold a key, talk, release, and clean text appears at your cursor.

I built it for my own daily use. It runs on my MacBook and I use it every day.

## How it works

```
hold Fn -> record mic -> whisper.cpp (local) -> Claude Haiku cleanup -> paste at cursor
```

1. **Record.** Audio is captured in memory at 16 kHz mono with `sounddevice`.
2. **Transcribe.** `whisper.cpp` (through `pywhispercpp`) turns the audio into text on the device. The audio never leaves the Mac.
3. **Clean up.** The transcript is sent to Claude Haiku, which removes filler words and false starts and fixes punctuation without answering or rewording what you said. If the API call fails, the raw transcript is used, so a dictation is never lost.
4. **Insert.** The text is placed on the clipboard, pasted with a simulated Cmd+V, and the previous clipboard contents are restored.

## Controls

| Action | Result |
|---|---|
| Hold **Fn**, talk, release | Hold-to-talk dictation |
| Double-tap **Fn** | Hands-free recording, tap again to stop |
| **Cmd + Shift + H** | Open the history window (raw and cleaned text) |

The menu bar icon shows the state: idle, recording, or hands-free.

## Design notes

- The Fn key is a modifier, so it never produces key down or key up events. The app listens for `flagsChanged` events instead.
- Hold, tap, and double-tap handling is an explicit finite state machine in `fsm.py`, driven only by key transitions, which makes it testable without hardware.
- Hotkey monitors are re-armed after the Mac wakes from sleep and on a timer, because macOS can silently drop them.
- Every dictation is logged to a local SQLite database (`history.db`) with the raw and cleaned text.

## Setup

Requires macOS and Python 3.13.

```bash
git clone https://github.com/Mariokoubayati/Dictate.git
cd Dictate
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Whisper model (about 142 MB)
mkdir -p models
curl -L -o models/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin

export ANTHROPIC_API_KEY="sk-ant-..."   # add to ~/.zshrc to persist
python app.py
```

macOS will ask for Microphone and Accessibility permission the first time. Both are needed, one to record and one to paste into other apps.

## Tests

```bash
python test_fsm.py        # state machine, no hardware needed
python test_pipeline.py   # end to end, needs a short 16 kHz mono test.wav and an API key
```

## Privacy

Speech recognition is fully local. Only the transcribed text is sent to the Anthropic API for cleanup. `history.db` and `dictate.log` stay on your machine and are git-ignored.

## Stack

Python, PyObjC (AppKit, Quartz, AVFoundation), whisper.cpp, Anthropic API (Claude Haiku), SQLite, rumps.
