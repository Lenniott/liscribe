"""Word replacement engine — pure function, stdlib only.

Phase 10: substitute spoken trigger words with defined output at text production.
No imports outside stdlib. Single entry point: apply().
"""

from __future__ import annotations

import re
from typing import Any

# Rule dict keys (for validation and clarity)
RULE_TRIGGER = "trigger"
RULE_TYPE = "type"
RULE_OUTPUT = "output"
RULE_PREFIX = "prefix"
RULE_SUFFIX = "suffix"
RULE_SCOPE = "scope"
RULE_TRANSFORM = "transform"

TYPE_SIMPLE = "simple"
TYPE_NEWLINE = "newline"
TYPE_WRAP = "wrap"

SCOPE_TRANSCRIPTS = "transcripts"
SCOPE_DICTATE = "dictate"
SCOPE_BOTH = "both"

TRANSFORM_NONE = "none"
TRANSFORM_LOWER = "lower"
TRANSFORM_UPPER = "upper"
TRANSFORM_SENTENCE = "sentence"


def apply(text: str, rules: list[dict[str, Any]], scope: str) -> str:
    """Apply replacement rules to text.

    Args:
        text: Input string (e.g. transcript or dictate output).
        rules: List of rule dicts with keys: trigger, type, output, scope;
            for type "wrap" also prefix and suffix.
        scope: Either "transcripts" or "dictate". Only rules whose scope
            is "both" or matches this value are applied.

    Returns:
        Text with replacements applied in rule order. Matching is
        case-insensitive and whole-word only.

    Raises:
        ValueError: If any rule has empty trigger or unknown type.
    """
    if not text:
        return text

    result = text
    for rule in rules:
        rule_scope = rule.get(RULE_SCOPE, SCOPE_BOTH)
        if rule_scope != SCOPE_BOTH and rule_scope != scope:
            continue

        trigger = rule.get(RULE_TRIGGER, "")
        if not trigger or not str(trigger).strip():
            raise ValueError("Replacement rule must have a non-empty trigger")

        rule_type = rule.get(RULE_TYPE, TYPE_SIMPLE)
        if rule_type not in (TYPE_SIMPLE, TYPE_NEWLINE, TYPE_WRAP):
            raise ValueError(f"Replacement rule has unknown type: {rule_type!r}")

        if rule_type == TYPE_SIMPLE:
            out = rule.get(RULE_OUTPUT, "")
            if " " in trigger:
                result = _replace_phrase(result, trigger, out)
            else:
                result = _replace_whole_word(result, trigger, out)
        elif rule_type == TYPE_NEWLINE:
            repl = "\n"
            if " " in trigger:
                result = _replace_phrase(result, trigger, repl)
            else:
                result = _replace_whole_word(result, trigger, repl)
        else:  # wrap
            prefix = rule.get(RULE_PREFIX, "")
            suffix = rule.get(RULE_SUFFIX, "")
            transform = str(rule.get(RULE_TRANSFORM, TRANSFORM_NONE)).lower()
            result = _wrap_next_word(result, trigger, prefix, suffix, transform)

    return result


def _replace_whole_word(text: str, trigger: str, replacement: str) -> str:
    """Replace whole-word occurrences of trigger (case-insensitive) with replacement."""
    pattern = r"\b" + re.escape(trigger) + r"\b"
    return re.sub(pattern, lambda m: replacement, text, flags=re.IGNORECASE)


def _replace_phrase(text: str, trigger: str, replacement: str) -> str:
    """Case-insensitive literal replacement for triggers that contain spaces."""
    pattern = re.escape(trigger)
    return re.sub(pattern, replacement, text, flags=re.IGNORECASE)


def _wrap_next_word(text: str, trigger: str, prefix: str, suffix: str, transform: str) -> str:
    """Replace whole-word trigger plus the immediately following word with prefix+word+suffix.

    If trigger is the last word, no change.
    """
    escaped = re.escape(trigger)
    # Match: trigger (whole word) + whitespace + next word
    pattern = r"\b(" + escaped + r")\s+(\S+)"

    def repl(m: re.Match[str]) -> str:
        word = m.group(2)
        word = _apply_transform(word, transform)
        return prefix + word + suffix

    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def _apply_transform(word: str, transform: str) -> str:
    t = transform or TRANSFORM_NONE
    if t == TRANSFORM_LOWER:
        return word.lower()
    if t == TRANSFORM_UPPER:
        return word.upper()
    if t == TRANSFORM_SENTENCE:
        lower = word.lower()
        return lower[:1].upper() + lower[1:] if lower else lower
    return word
