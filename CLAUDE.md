# CLAUDE.md — Liscribe v2

This file is your orientation. Read it first, then read the docs it points to before touching anything.

---

## What this project is

Liscribe is a macOS menu bar app for offline audio recording and transcription. No cloud, no accounts, no network calls after the one-time model download. It runs on Python (rumps, pywebview, faster-whisper) and is distributed via `git clone` + `./install.sh`.

Three workflows: **Scribe** (record a conversation → transcript), **Dictate** (double-tap or hold Right Control → speak → text pasted at cursor), **Transcribe** (drop in an existing audio file → transcript).

---

## Current state

**The app is feature-complete and in live testing.** All workflows are built, all rubric criteria are met, 438 tests are passing. Work coming in is bug reports and fixes from real use — not new features.

---

## Before you write a single line of code

Run the tests:

```bash
.venv/bin/pytest
```

Note the count. It must not decrease. Then read:

1. `docs/v2-rubric.md` — defines what correct behaviour looks like for every workflow. If your fix changes something the rubric describes, that is a regression, not a fix.
2. `docs/starter.md` — hard rules: TDD, layering, no silent failures, no magic values.
3. `docs/architecture.md` — C4 diagrams and the call chain. Know which layer you are working in before you touch anything.

---

## Your mode is bug fixing

Find the specific thing that is wrong. Understand it fully. Fix it minimally. Leave everything else alone.

1. **Reproduce before fixing.** State what is actually broken and under what conditions before proposing anything.
2. **Write the failing test first.** If a bug has no test that catches it, write one that fails, then fix until it passes.
3. **Minimal change.** Do not refactor adjacent code unless it is directly causing the bug.
4. **No silent failures.** Every `except` block must re-raise, log, or surface a message to the user. `except: pass` is a bug.
5. **No scope creep.** If you notice something unrelated, add a `# TODO:` comment and move on.

---

## Architecture — the one thing you must not get wrong

The call chain is:

```
panel (HTML/JS)
  → bridge (JS↔Python translation only)
    → controller (orchestration)
      → service (wraps engine)
        → engine (frozen)
```

**Engine files are frozen.** Do not modify them:

```
recorder.py  transcriber.py  output.py  notes.py
transcribe_worker.py  waveform.py  config.py  platform_setup.py
```

If you find a bug in an engine file, note it with a `# BUG:` comment. Do not fix it in place.

**Services are singletons instantiated in `app.py` and passed down.** Controllers receive services as constructor arguments. If you find yourself writing `self.x = SomeService()` inside a controller, stop.

---

## What good looks like when you are done

- Test count has not decreased — ideally increased by one test that covers the bug
- The rubric still accurately describes the app's behaviour
- The thing that was broken is demonstrably fixed
- No new `except: pass`, no new magic strings, no new cross-layer imports

---

## Key file locations

```
src/liscribe/
├── app.py                        # entry point, service instantiation
├── app_instance.py               # single-instance lock
├── replacements.py               # word replacement engine (pure, stdlib only)
├── bridge/                       # JS↔Python translation
├── controllers/                  # orchestration
├── services/                     # audio, model, config, hotkey, permissions
└── ui/
    ├── panels/                   # scribe, transcribe, dictate, settings, onboarding
    └── assets/style.css

docs/
├── v2-rubric.md                  # source of truth for correct behaviour
├── starter.md                    # hard rules for all work
├── architecture.md               # C4 diagrams and call chain
└── reviewer.md                   # sign-off checklist

tests/                            # 438 tests — must not decrease
```

Config: `~/.config/liscribe/config.json`
Transcripts: `~/transcripts` (default)
Model cache: `~/.cache/liscribe`