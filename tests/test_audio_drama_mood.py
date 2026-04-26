import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import OpenAIParser


@pytest.mark.asyncio
async def test_openai_parser_mood_shift():
    # Setup
    parser = OpenAIParser(api_key="test_key", base_url="https://api.test.com")
    parser.model = "gpt-4-turbo"

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "reasoning": {
                            "speaker_map": "Narrator and Hero.",
                            "ambiguous_lines": "",
                            "mood_analysis": "Action then peaceful.",
                            "confidence": "high",
                            "needs_escalation": False,
                        },
                        "script": [
                            {"type": "mood_shift", "mood": "action"},
                            {"type": "segment", "role": "narrator", "text": "The battle begins.", "gender": "unknown"},
                            {"type": "mood_shift", "mood": "peaceful"},
                            {"type": "segment", "role": "Hero", "text": "It's over.", "gender": "male"},
                        ],
                    }
                )
            )
        )
    ]

    with patch.object(parser.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        # Execute
        result = await parser.parse_chapter("Some text")

        # Assert
        assert len(result) == 4
        assert result[0]["type"] == "mood_shift"
        assert result[0]["mood"] == "action"
        assert result[1]["type"] == "segment"
        assert result[1]["role"] == "narrator"
        assert result[2]["type"] == "mood_shift"
        assert result[2]["mood"] == "peaceful"
        assert result[3]["type"] == "segment"
        assert result[3]["role"] == "Hero"


@pytest.mark.asyncio
async def test_openai_parser_mood_shift_prompt():
    # Setup
    parser = OpenAIParser(api_key="test_key", base_url="https://api.test.com")
    parser.model = "gpt-4-turbo"

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "reasoning": {
                            "speaker_map": "No characters.",
                            "ambiguous_lines": "",
                            "mood_analysis": "Neutral.",
                            "confidence": "high",
                            "needs_escalation": False,
                        },
                        "script": [],
                    }
                )
            )
        )
    ]

    with patch.object(parser.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        # Execute
        await parser.parse_chapter("Some text")

        # Assert — check the Step 1 (scratchpad) prompt was used
        args, kwargs = mock_create.call_args
        system_instruction = kwargs["messages"][0]["content"]

        assert "mood_shift" in system_instruction
        assert "action" in system_instruction
        assert "type" in system_instruction
        assert "peaceful" in system_instruction
        assert "mysterious" in system_instruction
        assert "romantic" in system_instruction
        assert "sad" in system_instruction
        assert "suspense" in system_instruction


@pytest.mark.asyncio
async def test_openai_parser_injects_available_bgm_moods_into_scratchpad_prompt():
    parser = OpenAIParser(api_key="test_key", base_url="https://api.test.com")
    parser.model = "gpt-4-turbo"

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "reasoning": {
                            "speaker_map": "No characters.",
                            "ambiguous_lines": "",
                            "mood_analysis": "Calm.",
                            "confidence": "high",
                            "needs_escalation": False,
                        },
                        "script": [],
                    }
                )
            )
        )
    ]

    with patch.object(parser.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        await parser.parse_chapter("Some text", bgm_moods=["calm", "sad", "tense"])

    _, kwargs = mock_create.call_args
    system_instruction = kwargs["messages"][0]["content"]
    assert "## Available BGM Moods" in system_instruction
    assert 'Choose mood_shift.tags strictly from: ["calm", "sad", "tense"]' in system_instruction


@pytest.mark.asyncio
async def test_openai_parser_defaults_missing_overlap_with_previous_to_false():
    parser = OpenAIParser(api_key="test_key", base_url="https://api.test.com")
    parser.model = "gpt-4-turbo"

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content=json.dumps(
                    {
                        "reasoning": {
                            "speaker_map": "Narrator and Hero.",
                            "ambiguous_lines": "",
                            "mood_analysis": "Neutral.",
                            "confidence": "high",
                            "needs_escalation": False,
                        },
                        "script": [
                            {"type": "segment", "role": "narrator", "text": "Line one.", "gender": "unknown"},
                            {
                                "type": "segment",
                                "role": "Hero",
                                "text": "Line two.",
                                "gender": "male",
                                "overlap_with_previous": True,
                            },
                        ],
                    }
                )
            )
        )
    ]

    with patch.object(parser.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        result = await parser.parse_chapter("Some text")

    assert result[0]["overlap_with_previous"] is False
    assert result[1]["overlap_with_previous"] is True
