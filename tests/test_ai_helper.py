import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from vvr_scraper.ai_helper import AIHelper, VideoMetadata

@pytest.mark.asyncio
async def test_generate_metadata_success():
    # Setup mock response
    mock_choice = MagicMock()
    mock_choice.message.content = '{"title": "Viral Title", "description": "Amazing description", "tags": ["novel", "audiobook"]}'
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    # We need to mock the AsyncOpenAI client's chat.completions.create method
    with patch('vvr_scraper.ai_helper.AsyncOpenAI') as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        
        helper = AIHelper(api_key="test-key")
        metadata = await helper.generate_metadata("Chapter text", {"title": "Novel Title"})
        
        assert isinstance(metadata, VideoMetadata)
        assert metadata.title == "Viral Title"
        assert metadata.description == "Amazing description"
        assert "novel" in metadata.tags

@pytest.mark.asyncio
async def test_generate_metadata_markdown_json():
    # Setup mock response with markdown blocks
    mock_choice = MagicMock()
    mock_choice.message.content = '```json\n{"title": "Markdown Title", "description": "Markdown description", "tags": ["markdown"]}\n```'
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    with patch('vvr_scraper.ai_helper.AsyncOpenAI') as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        
        helper = AIHelper(api_key="test-key")
        metadata = await helper.generate_metadata("Chapter text", {"title": "Novel Title"})
        
        assert metadata.title == "Markdown Title"
        assert "markdown" in metadata.tags

@pytest.mark.asyncio
async def test_generate_metadata_embedded_json():
    # Setup mock response with JSON embedded in text
    mock_choice = MagicMock()
    mock_choice.message.content = 'Here is the JSON: {"title": "Embedded Title", "description": "Embedded description", "tags": ["embedded"]} Hope this helps!'
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    with patch('vvr_scraper.ai_helper.AsyncOpenAI') as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create = AsyncMock(return_value=mock_response)
        
        helper = AIHelper(api_key="test-key")
        metadata = await helper.generate_metadata("Chapter text", {"title": "Novel Title"})
        
        assert metadata.title == "Embedded Title"
        assert "embedded" in metadata.tags

@pytest.mark.asyncio
async def test_generate_metadata_fallback():
    # Simulate an error or malformed response
    with patch('vvr_scraper.ai_helper.AsyncOpenAI') as mock_openai:
        mock_instance = mock_openai.return_value
        mock_instance.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
        
        helper = AIHelper(api_key="test-key")
        metadata = await helper.generate_metadata("Chapter text", {"title": "Novel Title"})
        
        assert isinstance(metadata, VideoMetadata)
        assert "Novel Title" in metadata.title
        assert "Audiobook" in metadata.description
