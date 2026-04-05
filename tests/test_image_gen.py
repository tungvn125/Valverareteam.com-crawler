import pytest
import os
import hashlib
from unittest.mock import AsyncMock, patch, MagicMock
from vvr_scraper.image_gen import ImageGenerator
import io

@pytest.fixture
def image_gen(tmp_path):
    # Use a temporary directory for backgrounds
    # Set a fake API key so it initializes the client
    return ImageGenerator(cache_dir=str(tmp_path / "backgrounds"), api_key="fake-key")

@pytest.mark.asyncio
async def test_image_generator_deduplication(image_gen, tmp_path):
    prompt = "A beautiful sunset over the mountains"
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    expected_path = os.path.join(image_gen.cache_dir, f"{prompt_hash}.webp")
    
    # Ensure cache dir exists
    os.makedirs(image_gen.cache_dir, exist_ok=True)
    
    # Create a dummy file to simulate existing image
    with open(expected_path, "wb") as f:
        f.write(b"fake image data")
        
    # Mock _generate_new to ensure it's not called if file exists
    with patch.object(image_gen, '_generate_new', AsyncMock()) as mock_gen:
        path = await image_gen.generate(prompt)
        assert path == expected_path
        mock_gen.assert_not_called()

@pytest.mark.asyncio
async def test_image_generator_calls_openai(image_gen, tmp_path):
    prompt = "A futuristic city at night"
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    expected_path = os.path.join(image_gen.cache_dir, f"{prompt_hash}.webp")
    
    # Mocking OpenAI response
    mock_response = MagicMock()
    mock_data = MagicMock()
    mock_data.url = "http://fakeurl.com/image.png"
    mock_response.data = [mock_data]
    
    # We need to mock the client already attached to image_gen
    image_gen.client.images.generate = AsyncMock(return_value=mock_response)
    
    # Mock httpx to download the fake image
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake png content"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        
        # Mock Pillow to save as webp
        # Image.open returns an object with a save method
        with patch("PIL.Image.open") as mock_img_open:
            mock_img = MagicMock()
            mock_img_open.return_value = mock_img
            
            # The save method is called in asyncio.to_thread, but we can still mock it
            # mock_img.save = MagicMock()
            
            path = await image_gen.generate(prompt)
            
            assert path == expected_path
            image_gen.client.images.generate.assert_called_once()
            mock_get.assert_called_once_with("http://fakeurl.com/image.png")
            mock_img.save.assert_called_once()
            # Verify it was saved as WEBP
            args, kwargs = mock_img.save.call_args
            assert kwargs['format'] == "WEBP"

@pytest.mark.asyncio
async def test_image_generator_no_api_key(tmp_path):
    # Temporarily remove API key from env
    with patch.dict(os.environ, {}, clear=True):
        gen = ImageGenerator(cache_dir=str(tmp_path / "backgrounds"), api_key=None)
        with pytest.raises(ValueError, match="OpenAI client not initialized"):
            await gen.generate("some prompt")
