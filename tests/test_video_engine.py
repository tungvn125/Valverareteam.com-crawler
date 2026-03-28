import pytest
import os
import asyncio
from unittest.mock import patch, MagicMock
from vvr_scraper.video_engine import VideoEngine

def test_duration_per_image_calculation():
    engine = VideoEngine()
    # 60 seconds audio, 5 images -> 12 seconds per image
    duration = engine.calculate_duration_per_image(60.0, 5)
    assert duration == 12.0
    
    # 60 seconds audio, 0 images -> 0 (should use stock background)
    duration = engine.calculate_duration_per_image(60.0, 0)
    assert duration == 0

def test_build_slideshow_ffmpeg_args():
    engine = VideoEngine()
    images = ["img1.jpg", "img2.jpg"]
    audio = "audio.mp3"
    output = "out.mp4"
    title = "Chương 1: Khởi đầu"
    
    # Test without title
    args = engine._build_slideshow_ffmpeg_args(images, audio, output, 10.0)
    assert isinstance(args, list)
    assert "ffmpeg" in args
    assert "img1.jpg" in args
    assert "zoompan" in args[args.index("-filter_complex") + 1]
    assert "drawtext" not in args[args.index("-filter_complex") + 1]
    assert "out.mp4" in args

    # Test with title
    args = engine._build_slideshow_ffmpeg_args(images, audio, output, 10.0, title=title)
    filter_complex = args[args.index("-filter_complex") + 1]
    assert "drawtext" in filter_complex
    # The title is escaped, so we check for a part of it or the escaped version
    assert "Chương 1" in filter_complex
    assert "Khởi đầu" in filter_complex
    assert "DejaVuSans" in filter_complex

def test_build_loop_background_ffmpeg_args():
    engine = VideoEngine()
    bg_video = "bg.mp4"
    audio = "audio.mp3"
    output = "out.mp4"
    title = "Chương 1: Khởi đầu"
    
    # Test without title
    args = engine._build_loop_background_ffmpeg_args(bg_video, audio, output, 60.0)
    assert isinstance(args, list)
    assert "ffmpeg" in args
    assert "bg.mp4" in args
    assert "-stream_loop" in args
    assert "-c:v" in args
    assert "copy" in args
    assert "out.mp4" in args

    # Test with title
    args = engine._build_loop_background_ffmpeg_args(bg_video, audio, output, 60.0, title=title)
    vf = args[args.index("-vf") + 1]
    assert "drawtext" in vf
    assert "Chương 1" in vf
    assert "Khởi đầu" in vf
    # When drawing text, we can't use -c:v copy
    assert "libx264" in args

def test_complex_title_escaping():
    engine = VideoEngine()
    title = "Title with 'single quotes', :colons: and %percent%"
    args = engine._build_loop_background_ffmpeg_args("bg.mp4", "audio.mp3", "out.mp4", 60.0, title=title)
    vf = args[args.index("-vf") + 1]
    
    # Check for proper escaping
    assert "'\\''single quotes'\\''" in vf
    assert "\\:colons\\:" in vf
    assert "%%percent%%" in vf
    assert "drawtext" in vf

@pytest.mark.asyncio
async def test_generate_video_black_bg_with_title():
    # Mock subprocess to avoid running real FFmpeg
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_process = MagicMock()
        # Use an AsyncMock for communicate if available, otherwise mock the future return value
        async def mock_communicate():
            return b"stdout", b"stderr"
        
        mock_process.communicate = mock_communicate
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        # Ensure stock background doesn't exist
        engine = VideoEngine(stock_bg_path="nonexistent.mp4")
        
        await engine.generate_video(image_paths=[], audio_path="audio.mp3", output_path="out.mp4", total_duration=10.0, title="Black BG Title")
        
        # Check if create_subprocess_exec was called with correct args
        call_args = mock_exec.call_args[0]
        assert "ffmpeg" == call_args[0]
        assert any("color=c=black" in arg for arg in call_args)
        assert any("drawtext" in arg for arg in call_args)
        assert any("Black BG Title" in arg for arg in call_args)
