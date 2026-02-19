# Transcription Progress Bar — Implementation Plan

## Current State

When a recording is saved, `TranscribingScreen` launches `transcribe_worker.py` in a subprocess. The screen currently shows:

```
Transcribing…
Model: base
[empty space where progress should be]
[ Back to Home — disabled ]
```

The progress widget exists (`Static("", id="transcribing-progress")`) but is **never updated**. The transcription subprocess runs completely silently from the TUI's perspective — the TUI only learns it's done when the subprocess exits.

### Why a subprocess?

Textual keeps file descriptors open. `faster-whisper` uses `multiprocessing` internally, and Python's multiprocessing has issues with inheriting open fds. Running transcription in a clean subprocess avoids this entirely.

### Why progress is hard

Progress callbacks in `transcriber.py` run **inside** the subprocess. The TUI's `TranscribingScreen` is in the **parent** process. Getting data from child → parent in real-time requires IPC (inter-process communication).

---

## How Progress Works in `transcriber.py`

The callback already exists and provides:

```python
def on_progress(progress_float: float, info: dict) -> None:
    # progress_float: 0.0 → 1.0
    # info = {
    #     "segment_index": int,      # segments processed so far
    #     "total_estimated": int,    # estimated total segments
    #     "elapsed_sec": float,      # wall time so far
    #     "eta_remaining_sec": float | None,  # estimated time left
    # }
```

Progress is estimated because faster-whisper doesn't know total segments upfront. The estimate uses:
- `total_estimated = max(1, int(audio_duration_seconds / 6.0))`
- `eta = elapsed * (total - current) / current`

This gives reasonable (not perfect) progress for typical recordings.

---

## Recommended Implementation: Line-buffered stdout IPC

The cleanest approach: the worker prints JSON progress lines to stdout; the TUI reads them from the subprocess's stdout pipe in a background thread.

**Advantages:**
- No temp files needed for progress
- Works on all platforms
- Low latency (line-buffered)
- Already supported by `subprocess.Popen` with `stdout=PIPE`

**Disadvantages:**
- The result (OK:/ERROR: line) currently goes to a file; stdout IPC means we keep that pattern but add progress lines before the result line.

### Protocol

The worker emits one JSON object per line to stdout:

```json
{"type": "progress", "value": 0.25, "eta_sec": 12.4, "elapsed_sec": 4.1}
{"type": "progress", "value": 0.50, "eta_sec": 8.2, "elapsed_sec": 8.2}
{"type": "progress", "value": 1.0, "eta_sec": 0.0, "elapsed_sec": 16.4}
```

The final result continues to go to the `result_path` temp file (unchanged). Stdout only carries progress.

---

## Implementation Steps

### Step 1: Update `transcribe_worker.py`

Add a progress callback that emits JSON to stdout:

```python
import json, sys

def main() -> None:
    # ... existing arg parsing ...

    # Progress reporter: write one JSON line per segment
    def on_progress(progress: float, info: dict | None = None) -> None:
        eta = info.get("eta_remaining_sec") if info else None
        elapsed = info.get("elapsed_sec", 0.0) if info else 0.0
        line = json.dumps({
            "type": "progress",
            "value": round(progress, 4),
            "eta_sec": round(eta, 1) if eta is not None else None,
            "elapsed_sec": round(elapsed, 1),
        })
        print(line, flush=True)

    try:
        model = load_model(model_size)
        result = transcribe(
            str(wav_path),
            model=model,
            model_size=model_size,
            on_progress=on_progress,   # ← ADD THIS
        )
    except Exception as e:
        write_error(str(e))
        sys.exit(1)

    # ... rest unchanged ...
```

### Step 2: Update `TranscribingScreen._run_pipeline`

Switch from `subprocess.run` to `subprocess.Popen` so we can read stdout line by line while the process runs:

```python
import json, subprocess, sys, threading
from pathlib import Path

def _run_pipeline(self) -> None:
    # ... existing model check and notes serialisation ...

    cmd = [sys.executable, "-m", "liscribe.transcribe_worker",
           result_path, self._wav_path, model_size, out_dir,
           notes_path, "true" if self._speaker_mode else "false"]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,       # line-buffered
        )

        # Read progress from stdout in this thread
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                if msg.get("type") == "progress":
                    value = float(msg.get("value", 0.0))
                    eta = msg.get("eta_sec")
                    self.app.call_from_thread(self._update_progress, value, eta)
            except (json.JSONDecodeError, ValueError):
                pass  # ignore malformed lines

        proc.wait(timeout=3600)

        raw = Path(result_path).read_text(encoding="utf-8").strip()
        if raw.startswith("OK:"):
            self._saved_md = raw[3:].strip()
        else:
            self._error = raw[6:].strip() if raw.startswith("ERROR:") else raw

    except subprocess.TimeoutExpired:
        proc.kill()
        self._error = "Transcription timed out."
    except Exception as e:
        self._error = str(e)
    finally:
        Path(notes_path).unlink(missing_ok=True)
        Path(result_path).unlink(missing_ok=True)

    self.app.call_from_thread(self._update_done)
```

### Step 3: Add `_update_progress` to `TranscribingScreen`

```python
def _update_progress(self, value: float, eta_sec: float | None) -> None:
    """Update progress bar and ETA text (called from thread)."""
    try:
        # Progress bar
        bar = self.query_one("#transcribing-progress-bar", ProgressBar)
        bar.update(progress=value * 100)

        # ETA text
        if eta_sec is not None and eta_sec > 0:
            mins, secs = divmod(int(eta_sec), 60)
            eta_str = f"{mins}m {secs}s remaining" if mins else f"{secs}s remaining"
        elif value >= 1.0:
            eta_str = "Finishing…"
        else:
            eta_str = "Estimating…"

        self.query_one("#transcribing-eta", Static).update(eta_str)
    except Exception:
        pass
```

### Step 4: Update `TranscribingScreen.compose`

Replace the empty `#transcribing-progress` Static with actual progress widgets:

```python
from textual.widgets import Button, Static, ProgressBar

def compose(self):
    with Vertical(id="home-frame"):
        yield Static("Transcribing…", id="transcribing-title")
        yield Static("Model: —", id="transcribing-status")
        yield ProgressBar(total=100, show_eta=False, id="transcribing-progress-bar")
        yield Static("Estimating…", id="transcribing-eta")
        yield Button("Back to Home", id="btn-back", disabled=True)
```

### Step 5: Auto-focus `btn-back` when done

In `_update_done`, after enabling the button, focus it:

```python
def _update_done(self) -> None:
    self._done = True
    try:
        title = self.query_one("#transcribing-title", Static)
        status = self.query_one("#transcribing-status", Static)
        if self._error:
            title.update("Transcription failed")
            status.update(self._error)
        else:
            title.update("Done")
            status.update(f"Saved: {Path(self._saved_md or '').name}" if self._saved_md else "Saved")
        btn = self.query_one("#btn-back", Button)
        btn.disabled = False
        btn.focus()    # ← ADD THIS
    except Exception:
        pass
```

### Step 6: Add CSS for progress widgets

In `rec.css`, add styling that matches the recording screen's visual language:

```css
#transcribing-title {
    width: 100%;
    content-align: center middle;
    text-style: bold;
    margin-bottom: 0;
}

#transcribing-status {
    width: 100%;
    content-align: center middle;
    color: $text-muted;
    margin-bottom: 1;
}

#transcribing-progress-bar {
    width: 100%;
    margin-bottom: 0;
}

#transcribing-eta {
    width: 100%;
    content-align: center middle;
    color: $text-muted;
    margin-bottom: 1;
}
```

---

## What the Progress Bar Will Look Like

```
┌────────────────────────────────────────────────────────────────────────┐
│                          liscribe                                      │
│                       Transcribing…                                    │
│  Model: base                                                           │
│  ████████████████████████░░░░░░░░░░░░░░░░░░░░░░░░   48%              │
│  8s remaining                                                          │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Back to Home   (disabled)                                       │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

And when done:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          liscribe                                      │
│                            Done                                        │
│  Saved: 2024-01-15_10-30-00.md                                        │
│  ████████████████████████████████████████████████  100%              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Back to Home   ← FOCUSED                                        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Progress Accuracy Notes

- faster-whisper processes audio in VAD-filtered segments. It does not know the total segment count before processing starts.
- The ETA estimate assumes ~6 seconds of audio per segment (`AVG_SEGMENT_SEC = 6.0` in `transcriber.py`). For speech-heavy recordings this is accurate. For recordings with lots of silence (filtered by VAD), it will underestimate segment count and show > 100% then snap to done.
- If this looks jarring, we can cap displayed progress at 99% until the process exits, then snap to 100%.

---

## Files to Change

| File | Change |
|------|--------|
| `src/liscribe/transcribe_worker.py` | Add `on_progress` callback printing JSON to stdout |
| `src/liscribe/screens/transcribing.py` | Switch to `Popen`, read stdout, add `_update_progress`, add `ProgressBar` widget, focus btn-back on done |
| `src/liscribe/rec.css` | Add CSS for `#transcribing-title`, `#transcribing-status`, `#transcribing-eta`, `#transcribing-progress-bar` |

---

## Testing the Progress Bar

### Unit test (no hardware needed)

```python
# tests/test_transcription_progress_ipc.py
import json

def test_progress_line_format():
    """Progress lines must be valid JSON with required keys."""
    line = json.dumps({
        "type": "progress",
        "value": 0.5,
        "eta_sec": 10.0,
        "elapsed_sec": 10.0,
    })
    msg = json.loads(line)
    assert msg["type"] == "progress"
    assert 0.0 <= msg["value"] <= 1.0
```

### Manual test

1. Record a ~30 second clip
2. Save it
3. Watch the Transcribing screen:
   - Progress bar should fill from 0% to ~100%
   - ETA should count down
   - "Done" should appear when finished
   - `Back to Home` should become active and focused automatically
4. Press Enter → back to Home
