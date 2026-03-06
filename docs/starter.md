
You are implementing a phase of Liscribe v2. The following constraints are
non-negotiable. They are not guidelines. Violating them means the phase is
not done, regardless of whether the feature works.

Read `docs/v2-rubric.md` and `docs/plan-v2.md` now. Do not write a single line of
code until you have done this.

---

## Before you write any code — answer these five questions explicitly

1. What is the exact done condition for this phase? Copy it from `docs/plan-v2.md`.
2. What new tests must exist before implementation starts? Name the files and describe what each test covers.
3. Which layer does each new file belong to: engine / service / controller / bridge / panel? If you cannot answer this, you do not understand the architecture yet.
4. Which services does this phase use? Are they already instantiated and passed down from `app.py`? If not, that is the first thing to fix.
5. Does anything in this phase touch an engine file? If yes, stop. Engine files are frozen.

Do not proceed until you have answered all five out loud.

---

## Hard rules

**TDD is not optional.**
Write the test. Run it. Watch it fail. Write the code. Watch it pass.
In that order. Every time. No exceptions.
The pytest count must increase. If you complete a phase and the count
is the same as when you started, you have not done TDD — you have
written code and called it done. That is not acceptable.

**Separation of concerns is structural, not cosmetic.**
- Panels contain HTML/CSS/JS only. No business logic.
- Bridges translate JS calls to Python. No business logic.
- Controllers orchestrate services. No direct engine imports.
- Services wrap engine files. One job each.
- Engine files are never imported outside the services layer.

If a function is doing two things, it should be two functions.
If a file is doing two things, it should be two files.

**No silent failures.**
Every `except` block must either re-raise, log, or surface a message to the user.
`except: pass` is a bug, not error handling.
`except Exception as e: print(e)` is not acceptable in production code.
Errors must reach the user in a form they can act on.

**No magic values.**
No raw strings for config keys, model names, file extensions, or permission types.
Name your constants. Put them at the top of the file or in a constants module.

**Services are singletons passed from app.py.**
Controllers receive services as constructor arguments.
Controllers do not import services directly.
Controllers do not instantiate services.
If you find yourself writing `self.audio = AudioService()` inside a controller,
you are doing it wrong.

**One phase at a time.**
If you notice something that belongs in a future phase, write a `# TODO Phase N:` comment.
Do not implement it. Do not refactor things outside this phase's scope.
Scope creep is how phases never end.

---

## Code quality — flag these before submitting

Before saying a phase is done, review every file you touched and check for:

**Structural issues**
- Any file handling more than one concern
- Any controller importing directly from engine files
- Any service instantiated outside `app.py`
- Any panel containing Python logic

**Code smells**
- Functions over 40 lines — split them
- Nesting deeper than 3 levels — extract functions
- Repeated logic in two or more places — extract it
- Commented-out code — delete it or explain it
- Mutable default arguments (`def f(x=[])`)
- Boolean parameters that flip behaviour (`def f(mode=True)`) — use two functions

**Test smells**
- Tests that test method names rather than behaviour
- Tests with no assertion
- Tests that only pass because of overly broad mocking
- Missing edge cases: empty input, missing file, wrong type, permission denied, concurrent calls

**Naming**
- Vague names: `data`, `result`, `info`, `temp`, `thing`
- Unexplained abbreviations
- Booleans not phrased as questions: `recording` should be `is_recording`
- Functions named after implementation not intent: `run_whisper` vs `transcribe`

---

## Diagram alignment check

Before marking done, verify the code matches `docs/plan-v2.md` C4 diagrams:

- Does every new file sit in the correct layer folder?
- Does the call chain match: panel → bridge → controller → service → engine?
- Are the file names exactly as specified in the Phase 2 scaffold?
- If you deviated from the scaffold, document why in a comment at the top of the file.

Structural drift in early phases becomes load-bearing by Phase 7.
Flag deviations now, not later.