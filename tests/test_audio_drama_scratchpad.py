"""
Tests for scratchpad + escalation pipeline in OpenAIParser.
Spec: docs/superpowers/specs/2026-04-23-scratchpad-escalation-design.md
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import OpenAIParser, ScriptResult


def _make_mock_response(content: str) -> MagicMock:
    """Helper: build a minimal OpenAI-style response mock."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


# ---------------------------------------------------------------------------
# Test 1: Happy path — high confidence, no escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_happy_path_no_escalation(tmp_path):
    """High-confidence scratchpad response → no escalation, reasoning sidecar written."""
    script_content = json.dumps({
        "reasoning": {
            "speaker_map": "Narrator describes scene. Nam says hello.",
            "ambiguous_lines": "",
            "mood_analysis": "Peaceful throughout.",
            "confidence": "high",
            "needs_escalation": False,
        },
        "script": [
            {"type": "segment", "role": "narrator", "gender": "unknown", "text": "Ngày hôm đó..."},
            {"type": "segment", "role": "Nam", "gender": "male", "text": "Xin chào!"},
        ],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_response(script_content))

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter("Một ngày...", output_prefix=output_prefix)

    # Script returned correctly
    assert len(result) == 2
    assert result[0]["role"] == "narrator"
    assert result[1]["role"] == "Nam"

    # Reasoning sidecar always written
    reasoning_file = output_prefix + ".script.reasoning.json"
    assert os.path.exists(reasoning_file), "reasoning sidecar must be written"
    with open(reasoning_file, encoding="utf-8") as f:
        reasoning_data = json.load(f)
    assert len(reasoning_data["chunks"]) == 1
    assert reasoning_data["chunks"][0]["escalated"] is False
    assert reasoning_data["chunks"][0]["reasoning"]["confidence"] == "high"

    # No raw.md when no escalation occurred
    raw_md_file = output_prefix + ".script.raw.md"
    assert not os.path.exists(raw_md_file), "raw.md must NOT be written when no escalation"


# ---------------------------------------------------------------------------
# Test 2: Escalation via confidence: "low"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_via_confidence_low(tmp_path):
    """confidence=low triggers _escalate_chunk; script.raw.md written."""
    step1_content = json.dumps({
        "reasoning": {
            "speaker_map": "Unclear who is speaking.",
            "ambiguous_lines": "Line 3 has no speaker.",
            "mood_analysis": "Tense.",
            "confidence": "low",
            "needs_escalation": False,
        },
        "script": [
            {"type": "segment", "role": "unknown", "gender": "unknown", "text": "Ai đó nói gì đó."},
        ],
    })

    step2a_prose = "## Analysis\nLine 3 is spoken by Nam based on context."
    step2b_content = json.dumps({
        "script": [
            {"type": "segment", "role": "Nam", "gender": "male", "text": "Ai đó nói gì đó."},
        ],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            _make_mock_response(step1_content),   # Step 1
            _make_mock_response(step2a_prose),     # Step 2a
            _make_mock_response(step2b_content),   # Step 2b
        ])

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter("Ai đó nói gì đó.", output_prefix=output_prefix)

    assert len(result) == 1
    assert result[0]["role"] == "Nam"

    raw_md_file = output_prefix + ".script.raw.md"
    assert os.path.exists(raw_md_file), "raw.md must be written when escalation occurred"
    with open(raw_md_file, encoding="utf-8") as f:
        raw_content = f.read()
    assert "## Chunk 1" in raw_content
    assert step2a_prose in raw_content

    reasoning_file = output_prefix + ".script.reasoning.json"
    with open(reasoning_file, encoding="utf-8") as f:
        reasoning_data = json.load(f)
    assert reasoning_data["chunks"][0]["escalated"] is True


# ---------------------------------------------------------------------------
# Test 3: Escalation via keyword fallback (missing confidence field)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_escalation_via_keyword_fallback(tmp_path):
    """Missing confidence field + 'unclear' in speaker_map → escalation triggered."""
    step1_content = json.dumps({
        "reasoning": {
            "speaker_map": "It is unclear who is speaking in line 2.",
            "ambiguous_lines": "",
            # Note: 'confidence' field deliberately missing
            "mood_analysis": "Neutral.",
            "needs_escalation": False,
        },
        "script": [
            {"type": "segment", "role": "unknown", "gender": "unknown", "text": "Chào."},
        ],
    })

    step2a_prose = "Nam says hello."
    step2b_content = json.dumps({
        "script": [
            {"type": "segment", "role": "Nam", "gender": "male", "text": "Chào."},
        ],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            _make_mock_response(step1_content),
            _make_mock_response(step2a_prose),
            _make_mock_response(step2b_content),
        ])

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter("Chào.", output_prefix=output_prefix)

    assert result[0]["role"] == "Nam"
    assert os.path.exists(output_prefix + ".script.raw.md")


# ---------------------------------------------------------------------------
# Test 4: Multi-chunk aggregation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_chunk_aggregation(tmp_path):
    """3 chunks: chunk 0 passes, chunk 1 escalates, chunk 2 passes → correct sidecar files."""
    chunk_pass = json.dumps({
        "reasoning": {
            "speaker_map": "Clear.",
            "ambiguous_lines": "",
            "mood_analysis": "Normal.",
            "confidence": "high",
            "needs_escalation": False,
        },
        "script": [{"type": "segment", "role": "narrator", "gender": "unknown", "text": "Pass."}],
    })

    chunk_escalate_step1 = json.dumps({
        "reasoning": {
            "speaker_map": "Không rõ ai nói.",
            "ambiguous_lines": "Dòng thứ 3 không rõ ai nói, có thể là Nam hoặc Nữ.",
            "mood_analysis": "Tense.",
            "confidence": "low",
            "needs_escalation": True,
        },
        "script": [{"type": "segment", "role": "unknown", "gender": "unknown", "text": "Escalated."}],
    })
    chunk_escalate_step2a = "## Chunk 2 analysis\nNam is clearly speaking here."
    chunk_escalate_step2b = json.dumps({
        "script": [{"type": "segment", "role": "Nam", "gender": "male", "text": "Escalated."}],
    })

    # 5 total calls: chunk0-step1, chunk1-step1, chunk1-step2a, chunk1-step2b, chunk2-step1
    call_responses = [
        _make_mock_response(chunk_pass),               # chunk 0 step 1
        _make_mock_response(chunk_escalate_step1),     # chunk 1 step 1
        _make_mock_response(chunk_escalate_step2a),    # chunk 1 step 2a
        _make_mock_response(chunk_escalate_step2b),    # chunk 1 step 2b
        _make_mock_response(chunk_pass),               # chunk 2 step 1
    ]

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=call_responses)

        parser = OpenAIParser(api_key="fake", base_url="fake")

        # Patch _chunk_text to return exactly 3 chunks
        with patch.object(parser, "_chunk_text", return_value=["chunk0", "chunk1", "chunk2"]):
            output_prefix = str(tmp_path / "chapter001.ad.mp3")
            result = await parser.parse_chapter("any text", output_prefix=output_prefix)

    reasoning_file = output_prefix + ".script.reasoning.json"
    with open(reasoning_file, encoding="utf-8") as f:
        reasoning_data = json.load(f)

    assert len(reasoning_data["chunks"]) == 3
    assert reasoning_data["chunks"][0]["escalated"] is False
    assert reasoning_data["chunks"][1]["escalated"] is True
    assert reasoning_data["chunks"][2]["escalated"] is False

    raw_md_file = output_prefix + ".script.raw.md"
    assert os.path.exists(raw_md_file)
    with open(raw_md_file, encoding="utf-8") as f:
        raw_content = f.read()

    # Only chunk 1 (1-based = Chunk 2) should appear in raw.md
    assert "## Chunk 2" in raw_content
    assert "## Chunk 1" not in raw_content
    assert "## Chunk 3" not in raw_content


# ---------------------------------------------------------------------------
# Test 5: VVR_DISABLE_SCRATCHPAD=1 kill switch
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kill_switch_disable_scratchpad(tmp_path, monkeypatch):
    """VVR_DISABLE_SCRATCHPAD=1 → legacy path, no reasoning extracted, no sidecar."""
    monkeypatch.setenv("VVR_DISABLE_SCRATCHPAD", "1")

    # Legacy response has NO reasoning field
    legacy_content = json.dumps({
        "script": [
            {"type": "segment", "role": "narrator", "gender": "unknown", "text": "Legacy mode."},
        ],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_response(legacy_content))

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter("Legacy text.", output_prefix=output_prefix)

    assert len(result) == 1
    assert result[0]["role"] == "narrator"

    # No sidecar files should exist
    assert not os.path.exists(output_prefix + ".script.reasoning.json")
    assert not os.path.exists(output_prefix + ".script.raw.md")


# ---------------------------------------------------------------------------
# Test 6: Empty script chunk (pure narration / narration-only)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_script_chunk_no_escalation(tmp_path):
    """script:[] is valid (pure narration), no escalation triggered."""
    content = json.dumps({
        "reasoning": {
            "speaker_map": "No characters, pure narration only.",
            "ambiguous_lines": "",
            "mood_analysis": "Peaceful.",
            "confidence": "high",
            "needs_escalation": False,
        },
        "script": [],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(return_value=_make_mock_response(content))

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter("Pure narration only.", output_prefix=output_prefix)

    assert len(result) == 0
    # No raw.md (no escalation)
    assert not os.path.exists(output_prefix + ".script.raw.md")
    # Reasoning sidecar still written
    reasoning_file = output_prefix + ".script.reasoning.json"
    assert os.path.exists(reasoning_file)


@pytest.mark.asyncio
async def test_bgm_moods_are_injected_into_escalation_format_prompt(tmp_path):
    step1_content = json.dumps({
        "reasoning": {
            "speaker_map": "Unclear speaker.",
            "ambiguous_lines": "This line is intentionally long enough to trigger escalation because the speaker is unclear.",
            "mood_analysis": "Tense.",
            "confidence": "low",
            "needs_escalation": True,
        },
        "script": [{"type": "segment", "role": "unknown", "gender": "unknown", "text": "Ai đó nói."}],
    })
    step2a_prose = "Nam says the line. The mood should use known local BGM vocabulary."
    step2b_content = json.dumps({
        "script": [{"type": "segment", "role": "Nam", "gender": "male", "text": "Ai đó nói."}],
    })

    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            _make_mock_response(step1_content),
            _make_mock_response(step2a_prose),
            _make_mock_response(step2b_content),
        ])

        parser = OpenAIParser(api_key="fake", base_url="fake")
        output_prefix = str(tmp_path / "chapter001.ad.mp3")
        result = await parser.parse_chapter(
            "Ai đó nói.",
            output_prefix=output_prefix,
            bgm_moods=["calm", "sad", "tense"],
        )

    assert result[0]["role"] == "Nam"
    calls = mock_client.chat.completions.create.call_args_list
    format_prompt = calls[2].kwargs["messages"][0]["content"]
    assert "## Available BGM Moods" in format_prompt
    assert 'Choose mood_shift.tags strictly from: ["calm", "sad", "tense"]' in format_prompt
