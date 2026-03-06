"""Tests for ConfigService — typed get/set wrapper around config.py."""

from __future__ import annotations

import pytest

from liscribe.services.config_service import ConfigService


@pytest.fixture()
def svc(tmp_path, monkeypatch):
    """ConfigService pointed at a temp directory, isolated from real config."""
    config_dir = tmp_path / ".config" / "liscribe"
    config_path = config_dir / "config.json"
    monkeypatch.setattr("liscribe.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("liscribe.config.CONFIG_PATH", config_path)
    return ConfigService()


# ---------------------------------------------------------------------------
# get / set
# ---------------------------------------------------------------------------

class TestGet:
    def test_known_key_returns_default(self, svc):
        assert svc.get("whisper_model") == "base"

    def test_unknown_key_returns_none(self, svc):
        assert svc.get("nonexistent_key") is None

    def test_unknown_key_returns_supplied_default(self, svc):
        assert svc.get("nonexistent_key", "fallback") == "fallback"


class TestSet:
    def test_updates_in_memory(self, svc):
        svc.set("whisper_model", "small")
        assert svc.get("whisper_model") == "small"

    def test_persists_to_disk(self, svc, tmp_path, monkeypatch):
        config_dir = tmp_path / ".config" / "liscribe"
        config_path = config_dir / "config.json"
        monkeypatch.setattr("liscribe.config.CONFIG_DIR", config_dir)
        monkeypatch.setattr("liscribe.config.CONFIG_PATH", config_path)

        svc.set("whisper_model", "medium")
        fresh = ConfigService()
        assert fresh.get("whisper_model") == "medium"

    def test_reload_picks_up_external_change(self, svc):
        from liscribe import config as _config
        values = _config.load_config()
        values["whisper_model"] = "large"
        _config.save_config(values)
        svc.reload()
        assert svc.get("whisper_model") == "large"


# ---------------------------------------------------------------------------
# Typed properties — every one present in config.py DEFAULTS
# ---------------------------------------------------------------------------

class TestTypedProperties:
    def test_save_folder_default(self, svc):
        assert svc.save_folder == "~/transcripts"

    def test_save_folder_setter(self, svc):
        svc.save_folder = "/tmp/recs"
        assert svc.save_folder == "/tmp/recs"

    def test_default_mic_none_by_default(self, svc):
        assert svc.default_mic is None

    def test_default_mic_setter(self, svc):
        svc.default_mic = "MacBook Pro Microphone"
        assert svc.default_mic == "MacBook Pro Microphone"

    def test_whisper_model_default(self, svc):
        assert svc.whisper_model == "base"

    def test_whisper_model_setter(self, svc):
        svc.whisper_model = "small"
        assert svc.whisper_model == "small"

    def test_dictation_model_default(self, svc):
        assert svc.dictation_model == "base"

    def test_dictation_hotkey_default(self, svc):
        assert svc.dictation_hotkey == "right_option"

    def test_dictation_auto_enter_default(self, svc):
        assert svc.dictation_auto_enter is True

    def test_dictation_auto_enter_setter(self, svc):
        svc.dictation_auto_enter = False
        assert svc.dictation_auto_enter is False

    def test_open_transcript_app_default(self, svc):
        assert svc.open_transcript_app == "cursor"

    def test_launch_hotkey_none_by_default(self, svc):
        assert svc.launch_hotkey is None

    def test_launch_hotkey_setter(self, svc):
        svc.launch_hotkey = "<ctrl>+<alt>+l"
        assert svc.launch_hotkey == "<ctrl>+<alt>+l"

    def test_auto_clipboard_default(self, svc):
        assert svc.auto_clipboard is True

    def test_auto_clipboard_setter(self, svc):
        svc.auto_clipboard = False
        assert svc.auto_clipboard is False

    def test_sample_rate_default(self, svc):
        assert svc.sample_rate == 16000

    def test_channels_default(self, svc):
        assert svc.channels == 1

    def test_speaker_device_default(self, svc):
        assert svc.speaker_device == "Multi-Output Device"

    def test_blackhole_device_default(self, svc):
        assert svc.blackhole_device == "BlackHole 2ch"

    def test_language_default(self, svc):
        assert svc.language == "en"

    def test_language_setter(self, svc):
        svc.language = "fr"
        assert svc.language == "fr"

    def test_group_consecutive_speaker_lines_default(self, svc):
        assert svc.group_consecutive_speaker_lines is True

    def test_source_include_timestamps_default(self, svc):
        assert svc.source_include_timestamps is False

    def test_suppress_mic_bleed_duplicates_default(self, svc):
        assert svc.suppress_mic_bleed_duplicates is True

    def test_mic_bleed_similarity_threshold_default(self, svc):
        assert abs(svc.mic_bleed_similarity_threshold - 0.62) < 1e-9

    def test_command_alias_default(self, svc):
        assert svc.command_alias == "rec"

    def test_record_here_by_default_default(self, svc):
        assert svc.record_here_by_default is False

    def test_dictation_sounds_default(self, svc):
        assert svc.dictation_sounds is True

    def test_rec_binary_path_none_by_default(self, svc):
        assert svc.rec_binary_path is None

    def test_rec_binary_path_setter(self, svc):
        svc.rec_binary_path = "/usr/local/bin/rec"
        assert svc.rec_binary_path == "/usr/local/bin/rec"
