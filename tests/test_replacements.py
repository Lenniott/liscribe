"""Tests for replacements.apply() — Phase 10 word replacement engine.

All tests written before replacements.py implementation (TDD).
"""

from __future__ import annotations

import pytest

from liscribe.replacements import apply


# Rule dict keys and values used in tests
def _rule(
    trigger: str,
    type_: str,
    output: str = "",
    prefix: str = "",
    suffix: str = "",
    scope: str = "both",
    transform: str | None = None,
):
    r = {"trigger": trigger, "type": type_, "output": output, "scope": scope}
    if type_ == "wrap":
        r["prefix"] = prefix
        r["suffix"] = suffix
        if transform is not None:
            r["transform"] = transform
    return r


class TestSimpleReplacement:
    """Simple replacement: trigger word replaced by output string."""

    def test_replaces_trigger_with_output(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="both")]
        assert apply("say hashtag project", rules, "both") == "say # project"

    def test_case_insensitive(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="both")]
        assert apply("Hashtag project", rules, "both") == "# project"
        assert apply("HASHTAG project", rules, "both") == "# project"

    def test_whole_word_only_not_substring(self) -> None:
        rules = [_rule("hash", "simple", output="#", scope="both")]
        assert apply("hashtag project", rules, "both") == "hashtag project"
        assert apply("hash tag", rules, "both") == "# tag"

    def test_phrase_trigger_merges_space(self) -> None:
        rules = [_rule("hashtag ", "simple", output="#", scope="both")]
        assert apply("Hashtag Monday", rules, "both") == "#Monday"
        assert apply("say hashtag Monday", rules, "both") == "say #Monday"


class TestNewlineReplacement:
    """Newline replacement: trigger word replaced by \\n."""

    def test_newline_produces_line_break(self) -> None:
        rules = [_rule("newline", "newline", output="\n", scope="both")]
        assert apply("hello newline world", rules, "both") == "hello \n world"

    def test_new_line_phrase_produces_line_break(self) -> None:
        rules = [_rule("new line", "newline", output="\n", scope="both")]
        assert apply("hello new line world", rules, "both") == "hello \n world"


class TestWrapReplacement:
    """Wrap: trigger removed, next word wrapped in prefix + suffix."""

    def test_wrap_next_word_only(self) -> None:
        rules = [_rule("bold", "wrap", prefix="**", suffix="**", scope="both")]
        assert apply("bold hello", rules, "both") == "**hello**"

    def test_wrap_leaves_rest_unchanged(self) -> None:
        rules = [_rule("bold", "wrap", prefix="**", suffix="**", scope="both")]
        assert apply("bold hello world", rules, "both") == "**hello** world"

    def test_wrap_trigger_last_word_unchanged(self) -> None:
        rules = [_rule("bold", "wrap", prefix="**", suffix="**", scope="both")]
        assert apply("say bold", rules, "both") == "say bold"

    def test_wrap_with_lower_transform(self) -> None:
        rules = [_rule("hashtag", "wrap", prefix="#", suffix="", scope="both", transform="lower")]
        assert apply("Hashtag Monday", rules, "both") == "#monday"


class TestScopeFiltering:
    """Scope transcripts / dictate / both."""

    def test_transcripts_rule_not_applied_to_dictate_scope(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="transcripts")]
        assert apply("hashtag x", rules, "dictate") == "hashtag x"

    def test_dictate_rule_not_applied_to_transcripts_scope(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="dictate")]
        assert apply("hashtag x", rules, "transcripts") == "hashtag x"

    def test_both_rule_applied_regardless_of_scope_arg(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="both")]
        assert apply("hashtag x", rules, "transcripts") == "# x"
        assert apply("hashtag x", rules, "dictate") == "# x"


class TestMultipleRules:
    """Multiple rules applied in sequence."""

    def test_multiple_rules_in_order(self) -> None:
        rules = [
            _rule("hashtag", "simple", output="#", scope="both"),
            _rule("todo", "simple", output="[ ]", scope="both"),
        ]
        assert apply("hashtag project todo item", rules, "both") == "# project [ ] item"

    def test_phrase_dash_merges_numbers_and_words(self) -> None:
        rules = [_rule(" dash ", "simple", output="-", scope="both")]
        assert apply("11 dash may", rules, "both") == "11-may"

    def test_no_matching_triggers_unchanged(self) -> None:
        rules = [_rule("hashtag", "simple", output="#", scope="both")]
        assert apply("hello world", rules, "both") == "hello world"


class TestValidation:
    """Invalid rules raise ValueError."""

    def test_empty_trigger_raises(self) -> None:
        rules = [_rule("", "simple", output="#", scope="both")]
        with pytest.raises(ValueError, match="trigger"):
            apply("text", rules, "both")

    def test_unknown_type_raises(self) -> None:
        rules = [{"trigger": "x", "type": "unknown", "output": "y", "scope": "both"}]
        with pytest.raises(ValueError, match="type"):
            apply("x", rules, "both")
