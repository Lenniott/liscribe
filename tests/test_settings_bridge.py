"""Tests for SettingsBridge — JS-to-Python call translation for Settings panel.

Bridge methods delegate to config/model/permissions; no business logic.
Return JSON-serialisable values; surface errors to the caller.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from liscribe.bridge.settings_bridge import SettingsBridge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_svc():
    svc = MagicMock()
    svc.get.side_effect = lambda k, default=None: {
        "save_folder": "~/transcripts",
        "default_mic": None,
        "keep_wav": False,
        "dictation_auto_enter": True,
        "open_transcript_app": "Cursor",
        "launch_hotkey": "<ctrl>+<alt>+l",
        "dictation_hotkey": "left_ctrl",
        "scribe_models": ["base"],
        "whisper_model": "base",
        "dictation_model": "base",
    }.get(k, default)
    svc.save_folder = "~/transcripts"
    svc.default_mic = None
    svc.keep_wav = False
    svc.dictation_auto_enter = True
    svc.open_transcript_app = "Cursor"
    svc.launch_hotkey = "<ctrl>+<alt>+l"
    svc.dictation_hotkey = "left_ctrl"
    svc.scribe_models = ["base"]
    svc.whisper_model = "base"
    svc.dictation_model = "base"
    svc.replacement_rules = []
    return svc


@pytest.fixture()
def model_svc():
    svc = MagicMock()
    svc.list_models.return_value = [
        {"name": "tiny", "is_downloaded": True, "size_label": "~75 MB"},
        {"name": "base", "is_downloaded": True, "size_label": "~145 MB"},
        {"name": "small", "is_downloaded": False, "size_label": "~465 MB"},
    ]
    return svc


@pytest.fixture()
def audio_svc():
    svc = MagicMock()
    svc.list_mics.return_value = [{"name": "MacBook Pro Microphone", "index": 0}]
    return svc


@pytest.fixture()
def bridge(config_svc, model_svc, audio_svc):
    return SettingsBridge(config=config_svc, model=model_svc, audio=audio_svc)


# ---------------------------------------------------------------------------
# get_config()
# ---------------------------------------------------------------------------


class TestGetConfig:
    def test_returns_dict_with_general_keys(self, bridge, config_svc):
        result = bridge.get_config()
        assert "save_folder" in result
        assert result["save_folder"] == "~/transcripts"
        assert "default_mic" in result
        assert "keep_wav" in result
        assert "dictation_auto_enter" in result
        assert "open_transcript_app" in result

    def test_returns_hotkey_keys(self, bridge):
        result = bridge.get_config()
        assert "launch_hotkey" in result
        assert "dictation_hotkey" in result

    def test_returns_model_keys(self, bridge):
        result = bridge.get_config()
        assert "scribe_models" in result
        assert "dictation_model" in result


# ---------------------------------------------------------------------------
# set_config()
# ---------------------------------------------------------------------------


class TestSetConfig:
    def test_delegates_to_config_set(self, bridge, config_svc):
        bridge.set_config("save_folder", "/new/path")
        config_svc.set.assert_called_once_with("save_folder", "/new/path")

    def test_delegates_keep_wav(self, bridge, config_svc):
        bridge.set_config("keep_wav", True)
        config_svc.set.assert_called_once_with("keep_wav", True)


# ---------------------------------------------------------------------------
# list_models()
# ---------------------------------------------------------------------------


class TestListModels:
    def test_delegates_to_model_list_models(self, bridge, model_svc):
        bridge.list_models()
        model_svc.list_models.assert_called_once()

    def test_returns_same_list_as_model_service(self, bridge, model_svc):
        result = bridge.list_models()
        assert result == model_svc.list_models.return_value


# ---------------------------------------------------------------------------
# download_model() / get_download_progress()
# ---------------------------------------------------------------------------


class TestDownloadModel:
    def test_starts_download_and_returns_immediately(self, bridge, model_svc):
        model_svc.download.side_effect = lambda name, on_progress=None: (
            on_progress(1.0) if on_progress else None
        )
        result = bridge.download_model("small")
        assert "started" in result or "ok" in result or result is None

    def test_get_download_progress_returns_dict(self, bridge):
        progress = bridge.get_download_progress()
        assert isinstance(progress, dict)


# ---------------------------------------------------------------------------
# remove_model()
# ---------------------------------------------------------------------------


class TestRemoveModel:
    def test_delegates_to_model_remove_when_not_default(self, bridge, model_svc):
        model_svc.remove.return_value = (True, "Removed")
        result = bridge.remove_model("small")
        model_svc.remove.assert_called_once_with("small")
        assert result.get("ok") is True

    def test_returns_reason_when_remove_is_default_scribe(self, bridge, config_svc):
        config_svc.scribe_models = ["base", "small"]
        result = bridge.remove_model("base")
        assert result.get("ok") is False
        assert result.get("reason") == "default_scribe"

    def test_returns_reason_when_remove_is_default_dictate(self, bridge, config_svc):
        config_svc.scribe_models = ["small"]
        config_svc.dictation_model = "base"
        result = bridge.remove_model("base")
        assert result.get("ok") is False
        assert result.get("reason") == "default_dictate"


# ---------------------------------------------------------------------------
# get_permissions()
# ---------------------------------------------------------------------------


class TestGetPermissions:
    def test_returns_dict_with_permission_keys(self, bridge):
        result = bridge.get_permissions()
        assert isinstance(result, dict)
        assert "microphone" in result
        assert "accessibility" in result
        assert "input_monitoring" in result


# ---------------------------------------------------------------------------
# open_system_settings()
# ---------------------------------------------------------------------------


class TestOpenSystemSettings:
    def test_accepts_pane_name(self, bridge):
        # Should not raise; may call service
        bridge.open_system_settings("accessibility")
        bridge.open_system_settings("microphone")


# ---------------------------------------------------------------------------
# pick_app() / get_app_version()
# ---------------------------------------------------------------------------


class TestPickApp:
    def test_returns_none_or_dict_when_cancelled(self, bridge):
        # Without a real window, pick_app may return None or {}
        result = bridge.pick_app()
        assert result is None or isinstance(result, dict)


class TestGetAppVersion:
    def test_returns_string(self, bridge):
        result = bridge.get_app_version()
        assert isinstance(result, str)
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# get_replacements() / add_replacement() / update_replacement() / delete_replacement() (Phase 10)
# ---------------------------------------------------------------------------


class TestGetReplacements:
    def test_returns_list_with_is_default_flag(self, bridge, config_svc):
        config_svc.replacement_rules = [
            {"trigger": "hashtag", "type": "wrap", "prefix": "#", "suffix": "", "scope": "both", "transform": "lower"},
        ]
        result = bridge.get_replacements()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["trigger"] == "hashtag"
        assert "is_default" in result[0]
        assert result[0]["is_default"] is True

    def test_user_rule_has_is_default_false(self, bridge, config_svc):
        config_svc.replacement_rules = [
            {"trigger": "custom", "type": "simple", "output": "x", "scope": "both"},
        ]
        result = bridge.get_replacements()
        assert result[0]["is_default"] is False


class TestAddReplacement:
    def test_empty_trigger_returns_error(self, bridge):
        result = bridge.add_replacement("", "simple", "#", scope="both")
        assert result.get("ok") is False
        assert "error" in result
        assert "trigger" in result["error"].lower()

    def test_empty_output_for_simple_returns_error(self, bridge):
        result = bridge.add_replacement("x", "simple", "", scope="both")
        assert result.get("ok") is False
        assert "error" in result

    def test_success_appends_rule_and_persists(self, bridge, config_svc):
        config_svc.replacement_rules = []
        result = bridge.add_replacement("hashtag", "simple", "#", scope="both")
        assert result.get("ok") is True
        assert "rule" in result
        assert result["rule"]["trigger"] == "hashtag"
        assert config_svc.replacement_rules == [result["rule"]]


class TestUpdateReplacement:
    def test_empty_trigger_returns_error(self, bridge, config_svc):
        config_svc.replacement_rules = [{"trigger": "x", "type": "simple", "output": "y", "scope": "both"}]
        result = bridge.update_replacement(0, "", "simple", "y", scope="both")
        assert result.get("ok") is False
        assert "error" in result

    def test_invalid_index_returns_error(self, bridge, config_svc):
        config_svc.replacement_rules = []
        result = bridge.update_replacement(0, "x", "simple", "y", scope="both")
        assert result.get("ok") is False
        assert "error" in result

    def test_success_updates_rule(self, bridge, config_svc):
        config_svc.replacement_rules = [
            {"trigger": "old", "type": "simple", "output": "o", "scope": "both"},
        ]
        result = bridge.update_replacement(0, "new", "simple", "n", scope="both")
        assert result.get("ok") is True
        assert config_svc.replacement_rules[0]["trigger"] == "new"
        assert config_svc.replacement_rules[0]["output"] == "n"


class TestDeleteReplacement:
    def test_invalid_index_returns_error(self, bridge, config_svc):
        config_svc.replacement_rules = []
        result = bridge.delete_replacement(0)
        assert result.get("ok") is False

    def test_success_removes_rule(self, bridge, config_svc):
        config_svc.replacement_rules = [
            {"trigger": "a", "type": "simple", "output": "x", "scope": "both"},
        ]
        result = bridge.delete_replacement(0)
        assert result.get("ok") is True
        assert len(config_svc.replacement_rules) == 0
