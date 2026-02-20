"""Tests for transcriber merge utilities."""

from liscribe.transcriber import (
    TranscriptionResult,
    merge_source_segments,
    build_merged_transcription_result,
)


def _result(segments: list[dict], duration: float = 5.0, language: str = "en") -> TranscriptionResult:
    text = " ".join(seg["text"] for seg in segments)
    return TranscriptionResult(
        text=text,
        segments=segments,
        language=language,
        duration=duration,
        model_name="base",
    )


class TestMergeSourceSegments:
    def test_source_labels_and_sorting(self):
        mic = [{"start": 0.5, "end": 1.2, "text": "hello"}]
        speaker = [{"start": 0.1, "end": 0.4, "text": "hi"}]
        merged = merge_source_segments(mic, speaker, speaker_offset_seconds=0.0)
        assert [m["speaker"] for m in merged] == ["THEM", "YOU"]
        assert [m["source"] for m in merged] == ["speaker", "mic"]

    def test_applies_speaker_offset(self):
        mic = [{"start": 2.0, "end": 3.0, "text": "mic line"}]
        speaker = [{"start": 0.0, "end": 1.0, "text": "speaker line"}]
        merged = merge_source_segments(mic, speaker, speaker_offset_seconds=2.1)
        assert merged[0]["speaker"] == "YOU"
        assert merged[1]["speaker"] == "THEM"
        assert merged[1]["start"] == 2.1

    def test_group_consecutive(self):
        mic = [
            {"start": 0.0, "end": 0.7, "text": "one"},
            {"start": 0.8, "end": 1.2, "text": "two"},
        ]
        merged = merge_source_segments(mic, [], group_consecutive=True)
        assert len(merged) == 1
        assert merged[0]["text"] == "one two"

    def test_suppresses_mic_bleed_duplicate(self):
        mic = [{"start": 1.0, "end": 2.0, "text": "the bottom edge of our headline right"}]
        speaker = [{"start": 0.9, "end": 1.9, "text": "the bottom edge of our headline right"}]
        merged = merge_source_segments(
            mic,
            speaker,
            suppress_mic_bleed_duplicates=True,
        )
        assert len(merged) == 1
        assert merged[0]["source"] == "speaker"

    def test_keeps_distinct_overlap_content(self):
        mic = [{"start": 1.0, "end": 2.0, "text": "I am speaking on mic"}]
        speaker = [{"start": 1.1, "end": 2.1, "text": "this is the video playback"}]
        merged = merge_source_segments(
            mic,
            speaker,
            suppress_mic_bleed_duplicates=True,
        )
        assert len(merged) == 2

    def test_suppresses_duplicate_even_when_far_apart(self):
        mic = [{"start": 30.0, "end": 31.0, "text": "this exact sentence repeats"}]
        speaker = [{"start": 1.0, "end": 2.0, "text": "this exact sentence repeats"}]
        merged = merge_source_segments(
            mic,
            speaker,
            suppress_mic_bleed_duplicates=True,
        )
        assert len(merged) == 1
        assert merged[0]["source"] == "speaker"

    def test_suppresses_asr_variant_duplicate(self):
        mic = [{"start": 10.0, "end": 11.5, "text": "we want our image to stretch from volume 2 to volume 12"}]
        speaker = [{"start": 2.0, "end": 3.5, "text": "we want our image to stretch from column 2 to column 12"}]
        merged = merge_source_segments(
            mic,
            speaker,
            suppress_mic_bleed_duplicates=True,
        )
        assert len(merged) == 1
        assert merged[0]["source"] == "speaker"


class TestBuildMergedTranscriptionResult:
    def test_builds_metadata_and_text(self):
        mic_result = _result([{"start": 0.0, "end": 1.0, "text": "hello"}], duration=2.0)
        speaker_result = _result([{"start": 0.5, "end": 1.5, "text": "there"}], duration=2.5)

        merged = build_merged_transcription_result(mic_result, speaker_result, speaker_offset_seconds=0.2)

        assert merged.metadata["diarization"] == "source-based"
        assert merged.metadata["sources"]["mic"] == "YOU"
        assert merged.metadata["sources"]["speaker"] == "THEM"
        assert "YOU: hello" in merged.text
        assert "THEM: there" in merged.text
