# Liscribe Architecture

## C4 Context Diagram

```mermaid
graph TD
    User["White-collar Worker"]
    Liscribe["Liscribe CLI"]
    Mic["Microphone / Audio Input"]
    Speaker["System Audio via BlackHole"]
    FS["Local Filesystem"]
    Clip["System Clipboard"]

    User -->|"rec -f ./notes"| Liscribe
    Mic -->|"Audio stream"| Liscribe
    Speaker -->|"Loopback via BlackHole"| Liscribe
    Liscribe -->|"Save .md transcript"| FS
    Liscribe -->|"Copy text"| Clip
```

## C4 Container Diagram

```mermaid
graph TD
    subgraph cli_layer [CLI Layer]
        CLI["cli.py - Click commands"]
        Dictation["dictation.py - Hotkey daemon + paste"]
    end

    subgraph core [Core]
        Recorder["recorder.py - Audio capture"]
        Transcriber["transcriber.py - faster-whisper"]
        Notes["notes.py - Note linking"]
        Output["output.py - Markdown + clipboard"]
    end

    subgraph ui [TUI Layer]
        App["app.py - Textual recording screen"]
        Waveform["waveform.py - Live audio levels"]
    end

    subgraph infra [Infrastructure]
        Config["config.py - JSON config"]
        Platform["platform_setup.py - macOS checks"]
    end

    CLI --> App
    CLI --> Dictation
    CLI --> Config
    App --> Recorder
    App --> Waveform
    App --> Notes
    Recorder --> Transcriber
    Transcriber --> Output
    Notes --> Output
    Recorder --> Platform
    Dictation --> Recorder
    Dictation --> Transcriber
    Dictation --> Clip
```

## Recording Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as cli.py
    participant Rec as recorder.py
    participant Platform as platform_setup.py
    participant FS as Filesystem

    User->>CLI: rec -f /path [-s]
    CLI->>Platform: Check PortAudio, BlackHole
    Platform-->>CLI: OK / error with instructions

    alt -s flag set
        CLI->>Platform: Switch output to Multi-Output Device
    end

    CLI->>Rec: Start recording (mic [+ BlackHole])
    loop During recording
        Rec->>Rec: Buffer audio chunks
        User->>Rec: (optional) Switch mic
        Rec->>Rec: Swap InputStream, continue writing
    end
    User->>CLI: Stop (Ctrl+S)
    alt mic only
        Rec->>FS: Save timestamp.wav
    else mic + speaker
        Rec->>FS: Save session/mic.wav + session/speaker.wav + session.json
    end

    alt -s flag was set
        CLI->>Platform: Restore original output device
    end
```

## Dictation Flow

```mermaid
sequenceDiagram
    participant User
    participant Daemon as dictation.py
    participant Listener as pynput listener
    participant Rec as _DictationRecorder
    participant Trans as transcriber.py
    participant App as Active application

    User->>Daemon: rec dictate
    Daemon->>Listener: Start global key listener (Right Option)
    loop Idle — waiting for double-tap
        Listener->>Daemon: key press event
    end
    Note over Daemon: Double-tap detected within 0.35s window
    Daemon->>Rec: start() — open mic stream
    Note over Rec: Live waveform + timer in terminal
    loop Recording
        Rec->>Rec: Buffer audio chunks
    end
    User->>Daemon: Single tap (stop)
    Daemon->>Rec: stop_and_save() → dictation.wav
    Daemon->>Trans: transcribe(wav, model=dictation_model)
    Trans-->>Daemon: TranscriptionResult.text
    Daemon->>App: Copy text → Cmd+V → paste at cursor
    Daemon->>App: Restore original clipboard
    Note over Daemon: Ready for next double-tap
```

## Transcription and Cleanup Flow

```mermaid
sequenceDiagram
    participant Rec as recorder.py
    participant Trans as transcriber.py
    participant Out as output.py
    participant FS as Filesystem

    Rec->>Trans: Transcribe mic and speaker WAVs independently
    Trans-->>Out: Source-labeled segments + merged chronological timeline
    Out->>FS: Write .md transcript
    FS-->>Out: Write confirmed
    Out->>FS: Delete source WAV(s) (only after MD saved)
```
