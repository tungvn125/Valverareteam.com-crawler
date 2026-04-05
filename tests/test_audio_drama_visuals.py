import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from vvr_scraper.audio_drama import OpenAIParser

@pytest.mark.asyncio
async def test_parse_visual_cues():
    with patch("vvr_scraper.audio_drama.AsyncOpenAI") as MockOpenAI:
        mock_client = MockOpenAI.return_value
        mock_response = MagicMock()
        mock_message = MagicMock()
        
        # Mocking the NEW format (mood_shift with visual info)
        mock_message.content = json.dumps({
            "script": [
                {
                    "type": "mood_shift", 
                    "tags": ["mysterious"], 
                    "visual_prompt": "A man draws a sword under a lightning sky.",
                    "vfx": ["flash"],
                    "transition": "cut"
                },
                {"type": "segment", "role": "narrator", "text": "He entered.", "gender": "unknown"}
            ]
        })
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        parser = OpenAIParser(api_key="fake", base_url="fake")
        text = "Hắn rút kiếm ra, bầu trời bỗng chớp sáng."
        script = await parser.parse_chapter(text)
        
        # Check if a block has visual_prompt in English and vfx
        # Based on the plan, script should have a 'blocks' key
        assert any('visual_prompt' in b['mood_info'] for b in script['blocks'])
        assert any('vfx' in b['mood_info'] for b in script['blocks'])
