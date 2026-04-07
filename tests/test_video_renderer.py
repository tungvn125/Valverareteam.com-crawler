import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
from vvr_scraper.video_renderer import VideoRenderer
from vvr_scraper.exporter import tao_file_mp4
from vvr_scraper.models import ContentItem

@pytest.fixture
def mock_manifest(tmp_path):
    manifest_data = {
        "title": "Test Chapter",
        "audio": "test.mp3",
        "base_path": "",
        "events": [
            {
                "type": "background",
                "src": "bg1.webp",
                "start": 0,
                "end": 5000
            },
            {
                "type": "dialogue",
                "text": "Hello world",
                "start": 1000,
                "end": 3000,
                "alignment": [{"word": "Hello", "start": 1000, "end": 1500}]
            }
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)
    return str(manifest_path)

class TestVideoRenderer:
    def test_initialization(self, mock_manifest):
        renderer = VideoRenderer(mock_manifest, "output.mp4", fps=60, render_format='portrait')
        assert renderer.fps == 60
        assert renderer.width == 1080
        assert renderer.height == 1920
        assert renderer.output_path == "output.mp4"

    @pytest.mark.asyncio
    async def test_render_logic_flow(self, mock_manifest, tmp_path):
        output_path = str(tmp_path / "test_video.mp4")
        renderer = VideoRenderer(mock_manifest, output_path, fps=30)
        
        # Mocking subprocess and playwright
        with patch("subprocess.Popen") as mock_popen, \
             patch("vvr_scraper.video_renderer.async_playwright") as mock_playwright:
            
            # Setup Playwright mocks
            mock_pw_instance = mock_playwright.return_value.__aenter__.return_value
            mock_browser = await mock_pw_instance.chromium.launch()
            mock_context = await mock_browser.new_context()
            mock_page = await mock_context.new_page()
            
            # Setup FFmpeg mock
            mock_process = mock_popen.return_value
            mock_process.stdin = MagicMock()
            
            await renderer.render()
            
            # Verify FFmpeg was called with correct arguments
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert "ffmpeg" in args
            assert "-r" in args
            assert "30" in args
            
            # Verify Playwright navigation
            mock_page.goto.assert_called()
            # Verify seekTo was called (at least once)
            mock_page.evaluate.assert_any_call("window.player.prepareForRendering();")

    @pytest.mark.asyncio
    async def test_mux_audio(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        audio_path = str(tmp_path / "audio.mp3")
        final_path = str(tmp_path / "final.mp4")
        
        with patch("subprocess.run") as mock_run:
            await VideoRenderer.mux_audio(video_path, audio_path, final_path)
            
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "-i" in args
            assert video_path in args
            assert audio_path in args
            assert final_path in args

@pytest.mark.asyncio
async def test_tao_file_mp4_integration(tmp_path):
    output_mp4 = str(tmp_path / "final.mp4")
    content_list = [ContentItem(type="text", data="Test")]
    
    # Mocking dependencies to avoid real AI/rendering
    with patch("vvr_scraper.exporter.tao_file_audiodrama", new_callable=AsyncMock) as mock_ad, \
         patch("vvr_scraper.exporter.VideoRenderer") as MockRenderer, \
         patch("os.path.exists", return_value=True):
        
        # Mock instance and its methods
        renderer_instance = MagicMock()
        renderer_instance.render = AsyncMock()
        renderer_instance.mux_audio = AsyncMock() # Static method called via instance
        MockRenderer.return_value = renderer_instance
        
        # Also mock static method on class just in case
        MockRenderer.mux_audio = AsyncMock()
        
        await tao_file_mp4(
            content_list=content_list,
            filename=output_mp4,
            story_id="test_story",
            db_manager=MagicMock(),
            title="Test Title",
            fps=30,
            render_format="landscape"
        )
        
        # Verify flow
        mock_ad.assert_called_once()
        MockRenderer.assert_called_once()
        renderer_instance.render.assert_called_once()
        renderer_instance.mux_audio.assert_called_once()

def test_cli_args_parsing():
    from vvr_scraper.cli import ValvrareScraperCLI
    import sys
    
    # Mock sys.argv
    test_args = ["vvrt", "test-slug", "-f", "MP4", "--fps", "60", "--render-format", "portrait"]
    with patch.object(sys, 'argv', test_args):
        cli = ValvrareScraperCLI()
        assert "MP4" in cli.args.format
        assert cli.args.fps == 60
        assert cli.args.render_format == "portrait"
