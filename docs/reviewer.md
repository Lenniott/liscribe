
A phase of Liscribe v2 has been declared done. Review it now.
Be direct. Do not soften findings. Every unflagged issue becomes
technical debt that costs more to fix later.

---

## 1. Test count — run this first

```bash
.venv/bin/pytest
```

State the previous phase count and the current count.

**If the count did not increase:** the phase is not done. Stop here.
List every piece of new behaviour that has no test. Do not proceed
until tests are written and passing.

**If any test was deleted or marked skip:** flag it. Explain why.
Deleted tests require explicit sign-off from the project owner.

---

## 2. Done condition — line by line

Copy the done condition checklist from `docs/plan-v2.md` for this phase.
Go through every checkbox. For each one state:

- ✅ Met — show the evidence (test output, file content, or exact manual steps to verify)
- ❌ Not met — state what is missing
- ⚠️ Unverifiable — describe exactly what a human needs to do to check it

"It should work" and "I believe it passes" are not evidence.
If you cannot demonstrate it, it is not met.

---

## 3. Rubric alignment

Open `docs/v2-rubric.md`. For every success criterion this phase was
supposed to address, quote the criterion and state pass or fail with evidence.

If anything in the rubric was interpreted differently from how it is written,
flag the interpretation. The rubric wins over the implementation.

---

## 4. Architecture check

Verify the C4 structure from `docs/plan-v2.md` is intact:

- Does the call chain hold: panel → bridge → controller → service → engine?
- Is anything importing across layers it shouldn't?
- Are services instantiated in `app.py` and passed down — not created inside controllers?
- Do all new files sit in the correct layer folders?
- Do file names match the Phase 2 scaffold exactly?

Flag every deviation. "It works anyway" is not a defence.
Structure drift in Phase 3 is a footnote. Structure drift in Phase 7 is a rewrite.

---

## 5. Code audit — every file changed in this phase

For each file, check:

**Does it do one thing?**
If a file handles business logic AND state AND formatting AND config,
name each concern and say which file should own it.

**Code smells — flag without softening:**
- Functions over 40 lines
- Nesting deeper than 3 levels
- `except: pass` or any swallowed exception
- Commented-out code
- Magic strings or numbers with no named constant
- Mutable default arguments
- Logic duplicated in two or more places
- Any engine file imported outside the services layer

**Test quality:**
- Are tests asserting behaviour or just that methods were called?
- Do tests cover: empty input, missing files, wrong types, permission denied?
- Are mocks hiding real bugs rather than isolating units?
- Would these tests catch a regression if the implementation changed?

**Naming:**
- Any vague names: `data`, `result`, `thing`, `temp`, `info`
- Any boolean not phrased as a question
- Any function named after implementation rather than intent

---

## 6. What will this break later?

Look at the code added in this phase and identify:

- Which decisions will cause friction in a specific future phase?
- What is currently flexible that will become rigid once Phase N builds on it?
- Is there anything that should be refactored now before it becomes load-bearing?

Name the file, the function, and the future phase it will affect.
"This is fine for now" is not an acceptable answer.

---

## 7. Verdict

**PASS**
All done conditions met with evidence. Tests increased. No structural violations.
No blocking code quality issues. Ready for next phase.

**PASS WITH DEBT**
Done conditions met. Tests increased. Issues found that are not blocking
but will compound if not addressed. List each item as a named debt entry.
Project owner decides: fix now or log and move on.

**FAIL**
One or more of the following is true:
- Done condition not demonstrably met
- Test count did not increase
- Structural violation found (layer skipped, engine file modified, service instantiated in wrong place)
- Silent failure left in code

State exactly what must be fixed before this phase can be signed off.
Do not suggest the next phase. Do not summarise what went well.
State what is broken and what fixing it looks like.