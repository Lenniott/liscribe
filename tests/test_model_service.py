"""Tests for ModelService — model discovery, download, and removal."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from liscribe.services.config_service import ConfigService
from liscribe.services.model_service import ModelService


@pytest.fixture()
def mock_config():
    cfg = MagicMock(spec=ConfigService)
    cfg.whisper_model = "base"
    return cfg


@pytest.fixture()
def svc(mock_config):
    return ModelService(mock_config)


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

class TestListModels:
    def test_returns_exactly_five_entries(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=False):
            result = svc.list_models()
        assert len(result) == 5

    def test_entry_keys_are_correct(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=False):
            for entry in svc.list_models():
                assert "name" in entry
                assert "is_downloaded" in entry
                assert "size_label" in entry

    def test_model_names_in_quality_order(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=False):
            names = [m["name"] for m in svc.list_models()]
        assert names == ["tiny", "base", "small", "medium", "large"]

    def test_is_downloaded_flag_reflects_availability(self, svc):
        def fake_available(name):
            return name == "base"
        with patch("liscribe.services.model_service._transcriber.is_model_available", side_effect=fake_available):
            entries = {m["name"]: m["is_downloaded"] for m in svc.list_models()}
        assert entries["base"] is True
        assert entries["tiny"] is False

    def test_size_labels_are_non_empty(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=False):
            for entry in svc.list_models():
                assert entry["size_label"] != ""


# ---------------------------------------------------------------------------
# is_downloaded
# ---------------------------------------------------------------------------

class TestIsDownloaded:
    def test_returns_true_when_available(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=True):
            assert svc.is_downloaded("base") is True

    def test_returns_false_when_not_available(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=False):
            assert svc.is_downloaded("large") is False

    def test_delegates_to_transcriber(self, svc):
        with patch("liscribe.services.model_service._transcriber.is_model_available", return_value=True) as m:
            svc.is_downloaded("small")
        m.assert_called_once_with("small")


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------

class TestDownload:
    def test_calls_load_model(self, svc):
        with patch("liscribe.services.model_service._transcriber.load_model") as m:
            svc.download("base")
        m.assert_called_once_with("base")

    def test_calls_on_progress_with_1_on_completion(self, svc):
        cb = MagicMock()
        with patch("liscribe.services.model_service._transcriber.load_model"):
            svc.download("base", on_progress=cb)
        cb.assert_called_once_with(1.0)

    def test_no_progress_callback_is_safe(self, svc):
        with patch("liscribe.services.model_service._transcriber.load_model"):
            svc.download("base", on_progress=None)  # must not raise


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

class TestRemove:
    def test_delegates_to_transcriber(self, svc):
        with patch("liscribe.services.model_service._transcriber.remove_model", return_value=(True, "ok")) as m:
            ok, msg = svc.remove("base")
        m.assert_called_once_with("base")
        assert ok is True
        assert msg == "ok"

    def test_evicts_loaded_model_from_cache(self, svc):
        svc._loaded_models["base"] = MagicMock()
        with patch("liscribe.services.model_service._transcriber.remove_model", return_value=(True, "ok")):
            svc.remove("base")
        assert "base" not in svc._loaded_models

    def test_remove_non_existent_returns_false(self, svc):
        with patch(
            "liscribe.services.model_service._transcriber.remove_model",
            return_value=(False, "Model not installed: tiny"),
        ):
            ok, msg = svc.remove("tiny")
        assert ok is False
        assert "not installed" in msg
