# Security Audit Report — Liscribe

**Date:** 2026-02-19
**Auditor:** Senior Developer Review
**Scope:** Full codebase — primary focus on information leakage and data breach risk
**Branch:** `claude/security-audit-report-GyLGz`

---

## Executive Summary

Liscribe is an offline audio recorder and transcriber. Its offline-first architecture is its strongest security property — there is no server, no API, no cloud sync, and no network calls at runtime. This eliminates entire categories of attack surface.

That said, this audit identified **one high-priority issue**, **three medium-priority issues**, and **several low-priority items** that a security-conscious developer should address. The most sensitive dimension of this application is that it handles audio recordings and transcripts of potentially private speech — any path that leaks, exposes, or improperly retains that content deserves scrutiny.

---

## Findings

### HIGH — Unbounded Log File Grows Forever and Contains Sensitive Metadata

**File:** `src/liscribe/logging_setup.py:25`
**File:** `src/liscribe/transcriber.py:131`, `src/liscribe/recorder.py:124`

The log file at `~/.config/liscribe/liscribe.log` uses `logging.FileHandler` with no rotation policy. The file grows without limit.

More importantly, the DEBUG-level file handler logs:
- Full absolute file paths of every audio recording and transcript
- Microphone device names
- The language being transcribed
- Transcription segment counts and word counts (indirect content fingerprint)
- Timestamps of every recording session

```python
# transcriber.py:131 — leaks file path, language, and activity timestamps
logger.info("Transcribing: %s (language=%s)", audio_path, lang or "auto")

# transcriber.py:185-188 — leaks word count and segment count
logger.info(
    "Transcription complete: %d segments, %d words, language=%s",
    len(segments), len(full_text.split()), info.language,
)

# recorder.py:124 — leaks audio callback status flags
logger.warning("Mic callback status: %s", status)
```

**Risk:** The log file is a metadata trail of all recording activity — what was recorded, when, from which device, in which language, how long. On a shared machine, or if an attacker achieves local file read access (malware, physical access), this log is a complete diary. The file will also eventually fill the disk on long-running installations.

**Recommendation:**
1. Replace `FileHandler` with `RotatingFileHandler` — cap at ~5 MB with 2–3 backups.
2. Reduce log verbosity for file paths at INFO level; log only the filename, not the full absolute path.
3. Consider whether word count and segment count need to be logged at all — they are indirect content fingerprints.

```python
# Suggested change in logging_setup.py
from logging.handlers import RotatingFileHandler

fh = RotatingFileHandler(
    str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
)
```

---

### MEDIUM — Transcript YAML Front Matter Embeds Hardware and Behavioural Metadata

**File:** `src/liscribe/output.py:86-96`

Every generated Markdown transcript includes a YAML front matter block:

```yaml
---
title: Transcript 2026-02-19 14:32
date: 2026-02-19T14:32:11.456789
duration_seconds: 183.4
word_count: 412
language: en
mic: MacBook Pro Microphone
speaker_capture: false
source_audio: 2026-02-19_14-32-11.wav
model: base
---
```

This front matter is written to disk unconditionally and copied to clipboard (when `auto_clipboard` is true). It reveals:

- The **exact microphone hardware** used — identifiable hardware fingerprint
- The **exact recording duration and word count** — content fingerprint
- The **source WAV filename** — links back to the audio file if it still exists
- The **model size** — reveals capabilities/configuration of the user's setup

**Risk:** If transcripts are shared (email, Git, cloud sync of the transcripts folder), this metadata leaves the machine. Users may not realise they are sharing hardware details and usage patterns alongside their text. The `source_audio` field in particular creates a linkage between transcript and audio file that users may not intend.

**Recommendation:**
1. Make `source_audio` opt-in via config rather than always-on. Most users sharing a transcript don't want to expose the audio filename.
2. Document clearly in `config.example.json` what metadata ends up in every file.
3. If `mic_name` is `"unknown"`, omit it from the front matter rather than writing `mic: unknown`.

---

### MEDIUM — Auto-Clipboard Copies Full Transcript Without Warning

**File:** `src/liscribe/output.py:160-168`
**File:** `src/liscribe/config.py:29-33` (default: `true`)

`auto_clipboard` is **enabled by default**. After every transcription, the full transcript text is written to the system clipboard:

```python
def copy_to_clipboard(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
```

**Risk:** The system clipboard is readable by any application running on the machine with clipboard access — which on macOS includes every foreground application automatically. If the transcript contains sensitive speech (medical consultations, legal calls, financial discussions, credentials spoken aloud), that content sits in a globally readable buffer until overwritten.

This is also relevant for clipboard manager applications, which typically log clipboard history to disk — meaning the transcript could be persisted indefinitely in a third-party store without the user's awareness.

**Recommendation:**
1. Change the default for `auto_clipboard` to `false`. Make it opt-in. Users who want convenience should enable it consciously.
2. At minimum, add a note in the README and setup wizard explaining that clipboard managers may retain transcript content.

---

### MEDIUM — `requests` Dependency Included But Never Used

**File:** `requirements.txt:10`

```
requests>=2.32.0
```

The `requests` library is declared as a dependency but is not imported anywhere in the source code. This was verified by searching all Python source files.

**Risk:** This is a ghost dependency. It:
1. Installs an HTTP client library into the environment with no stated purpose — raising questions about whether undocumented network calls were planned or are present in future versions.
2. Increases supply chain exposure for no benefit — any CVE in `requests` (or its transitive dependencies like `urllib3`, `certifi`, `charset-normalizer`) affects this application for no functional gain.
3. May mislead future contributors or security reviewers into assuming network functionality exists or is intentionally available.

**Recommendation:** Remove `requests>=2.32.0` from `requirements.txt` and `pyproject.toml` immediately. If network functionality is planned for a future feature (e.g., model downloads managed by the app), add it back at that time with a clear comment.

---

### LOW — Transcript Files Created With Default umask (No Explicit Permissions)

**File:** `src/liscribe/output.py:155`

```python
md_path.write_text(content, encoding="utf-8")
```

Transcript files are created using `Path.write_text()` with no explicit file mode. The resulting permissions depend entirely on the process umask — typically `0644` (world-readable) on most systems.

**Risk:** On a shared machine (e.g., a university computer, a family Mac, a corporate laptop with multiple users), transcripts are readable by any user who can navigate to the save folder. The default save folder is `~/transcripts` which is under the home directory (typically protected), but the config allows arbitrary paths. If a user sets `save_folder` to something under `/tmp` or a world-accessible location, transcripts are immediately exposed.

**Recommendation:** Explicitly set permissions when creating transcript files:

```python
md_path.write_text(content, encoding="utf-8")
md_path.chmod(0o600)  # owner read/write only
```

Same applies to the WAV file created in `recorder.py:331`.

---

### LOW — No Validation on `save_folder` Path in Config

**File:** `src/liscribe/config.py:69-76`
**File:** `src/liscribe/recorder.py:105-106`

The `save_folder` config value is consumed directly without validating that it is a reasonable path:

```python
self.save_dir = Path(folder).expanduser().resolve()
self.save_dir.mkdir(parents=True, exist_ok=True)
```

`mkdir(parents=True, exist_ok=True)` will silently create an arbitrary deep directory tree anywhere the user has write access.

**Risk:** Low in practice since this is the user's own machine and their own config. However, if config is ever sourced from an external location (e.g., a shared config in a future team feature), this could create directories in unexpected places. Also, a typo in config (e.g., `/transcripts` instead of `~/transcripts`) would silently create a root-level directory attempt and fail with a confusing permission error rather than a helpful validation message.

**Recommendation:** Validate that the resolved path is within the user's home directory or an explicitly allowed prefix before creating it. Emit a clear error if it points outside expected bounds.

---

### LOW — Whisper Model Downloads Have No Integrity Check

**File:** `src/liscribe/transcriber.py:82-87`

```python
model = WhisperModel(
    model_size,
    device="cpu",
    compute_type="int8",
    download_root=str(get_model_path()),
)
```

On first use, `faster-whisper` downloads models from Hugging Face. There is no SHA256 or other hash verification performed after download.

**Risk:** This is a supply chain trust issue. The app trusts whatever Hugging Face serves without verifying it matches known-good checksums. In a network-interception scenario (hostile Wi-Fi, compromised DNS), a poisoned model could be delivered. A compromised model could theoretically behave maliciously during inference (e.g., exfiltrating audio data through side channels). This is a low-probability scenario but non-zero.

**Recommendation:** Document expected model checksums in the repo (e.g., a `model_checksums.json` file). After a model is downloaded for the first time, verify its SHA256. `faster-whisper` uses Hugging Face's standard cache format, making the model files locatable at known paths under `~/.cache/liscribe/models/`.

---

### LOW — `python-dotenv` Dependency Has No Active Use

**File:** `requirements.txt:7`

```
python-dotenv>=1.0.1
```

`python-dotenv` is listed as a dependency but is not called in any source file. It is not loaded in `__main__.py` or `cli.py`.

**Risk:** Similar to the `requests` issue — this is dead weight in the dependency tree. It also signals to readers that `.env` files may be in use (they are not), and that secrets may be loaded from the environment (they are not). This creates confusion during security review.

**Recommendation:** Remove it. If environment variable support is added in future, re-introduce it with an explicit comment.

---

### LOW — Exception Details Logged Directly May Expose Filesystem Paths

**File:** `src/liscribe/config.py:77-78`

```python
except (json.JSONDecodeError, OSError) as exc:
    logger.warning("Could not read config at %s: %s", CONFIG_PATH, exc)
```

OSError messages on most platforms include the full filesystem path and system-level error description. These are logged to both the log file and to stderr (at WARNING level, which is shown to users). For example:

```
WARNING: Could not read config at /Users/alice/.config/liscribe/config.json:
[Errno 13] Permission denied: '/Users/alice/.config/liscribe/config.json'
```

**Risk:** Low individually, but full absolute paths in error output are a minor information leakage vector — they reveal the username and home directory structure in any terminal session that might be shared (screen sharing, pair programming, screenshots).

**Recommendation:** Log `CONFIG_PATH.name` (just the filename) or a relative representation rather than the full absolute path in user-facing warning messages. The full path is fine in the log file for debugging, but not on stderr.

---

## What is Done Well

It's worth being explicit about what the codebase gets right, because these decisions meaningfully limit the threat surface:

- **No network calls at runtime.** After the initial model download, the application makes zero outbound network connections. There is no telemetry, no analytics, no cloud sync. This single architectural decision prevents an entire class of data exfiltration risks.
- **No credentials anywhere.** No API keys, no tokens, no passwords in code, config, or environment variables.
- **`eval()` and `exec()` are absent.** All data parsing uses `json.loads()` and `yaml.dump()` — both safe for the operations performed.
- **Subprocess calls use list form, not `shell=True`.** `platform_setup.py` calls `SwitchAudioSource` via a list argument to `subprocess.run`, which prevents shell injection even if a device name contains shell metacharacters.
- **File paths use `pathlib` throughout.** No string concatenation for paths. `expanduser()` and `resolve()` are called consistently.
- **Audio deletion only happens after transcript is verified.** `cleanup_audio()` checks both existence and non-zero size of all transcript files before deleting the source WAV — protecting against data loss.
- **Thread safety in audio capture.** `threading.Lock` protects the audio chunk lists from concurrent access between the recording callback and the main thread.

---

## Priority Summary

| # | Severity | Issue | File |
|---|----------|-------|------|
| 1 | **High** | Unbounded log file; metadata trail of all recording activity | `logging_setup.py` |
| 2 | **Medium** | YAML front matter leaks hardware and content metadata | `output.py:86` |
| 3 | **Medium** | Auto-clipboard on by default; transcript exposed to all apps | `output.py:160`, config default |
| 4 | **Medium** | `requests` ghost dependency — dead supply chain exposure | `requirements.txt:10` |
| 5 | Low | Transcript/WAV files created world-readable (umask default) | `output.py:155`, `recorder.py:331` |
| 6 | Low | No path validation on `save_folder` config value | `config.py`, `recorder.py:105` |
| 7 | Low | No model integrity verification after download | `transcriber.py:82` |
| 8 | Low | `python-dotenv` ghost dependency | `requirements.txt:7` |
| 9 | Low | Exception messages in stderr include full absolute paths | `config.py:77` |

---

## Recommended Immediate Actions

1. **Fix log rotation** — one-line change to use `RotatingFileHandler`.
2. **Remove `requests` and `python-dotenv`** from requirements — these should not be in a production dependency list if unused.
3. **Flip `auto_clipboard` default to `false`** — transcripts may contain sensitive speech. Convenience should be opt-in, not opt-out.
4. **Add `chmod(0o600)` after writing transcripts and WAV files** — protects content on shared machines.

The remaining items are worth tracking but are not urgent for typical single-user macOS deployments.
