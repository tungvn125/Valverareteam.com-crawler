import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vvr_scraper.audio_drama import OpenAIParser


@pytest.mark.asyncio
async def test_parse_visual_cues():
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_message = MagicMock()

        # Mocking the NEW format (mood_shift with visual info)
        mock_message.content = json.dumps(
            {
                "script": [
                    {
                        "type": "mood_shift",
                        "tags": ["mysterious"],
                        "visual_prompt": "A man draws a sword under a lightning sky.",
                        "vfx": ["flash"],
                        "intensity": 0.8,
                        "duration": 2000,
                        "transition": "cut",
                    },
                    {"type": "segment", "role": "narrator", "text": "He entered.", "gender": "unknown"},
                ]
            }
        )
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_choice.message.content = mock_message.content
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = OpenAIParser(api_key="fake", base_url="fake")
        text = "Hắn rút kiếm ra, bầu trời bỗng chớp sáng."
        script = await parser.parse_chapter(text)

        # Check if a block has visual_prompt, vfx, intensity, and duration
        blocks = script.blocks
        assert any(b["mood_info"].get("visual_prompt") == "A man draws a sword under a lightning sky." for b in blocks)
        assert any("flash" in b["mood_info"].get("vfx", []) for b in blocks)
        assert any(b["mood_info"].get("intensity") == 0.8 for b in blocks)
        assert any(b["mood_info"].get("duration") == 2000 for b in blocks)
