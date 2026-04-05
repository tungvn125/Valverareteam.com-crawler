import os
import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from vvr_scraper.exporter import tao_file_audiodrama
from vvr_scraper.models import ContentItem

@pytest.mark.asyncio
async def test_cinematic_manifest_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake_key")
    # Setup paths
    output_folder = tmp_path / "output"
    output_folder.mkdir()
    mp3_filename = str(output_folder / "test_chapter.ad.mp3")
    
    # Mock content
    content_list = [
        ContentItem(type="text", data="Hắn rút kiếm ra, bầu trời bỗng chớp sáng. 'Ngươi phải chết!', hắn hét lên.")
    ]
    
    # Mock script with visual cues and dialogue
    mock_script = [
        {
            "type": "mood_shift",
            "mood": "suspense",
            "tags": ["suspense", "dark"],
            "visual_prompt": "A dark warrior drawing a glowing sword under a stormy sky.",
            "vfx": ["flash", "rain"],
            "transition": "fade",
            "intensity": 0.8,
            "duration": 2000
        },
        {
            "type": "segment",
            "role": "narrator",
            "text": "Hắn rút kiếm ra, bầu trời bỗng chớp sáng.",
            "gender": "female"
        },
        {
            "type": "segment",
            "role": "Warrior",
            "text": "Ngươi phải chết!",
            "gender": "male"
        }
    ]
    
    # Mock alignment data
    mock_alignment = [
        {"word": "Hắn", "start": 0, "end": 100},
        {"word": "rút", "start": 150, "end": 300}
    ]

    # Mock DatabaseManager
    mock_db = AsyncMock()
    mock_db.get_all_story_voices.return_value = {}
    mock_db.save_character_voice = AsyncMock()

    # Patches
    with patch("vvr_scraper.exporter.OpenAIParser") as MockParser, \
         patch("vvr_scraper.exporter.VoiceManager") as MockVoiceManager, \
         patch("vvr_scraper.exporter.BGMManager") as MockBGMManager, \
         patch("vvr_scraper.exporter.MixingEngine") as MockMixingEngine, \
         patch("vvr_scraper.exporter.ImageGenerator") as MockImageGenerator, \
         patch("vvr_scraper.exporter.FreesoundManager") as MockFreesoundManager, \
         patch("pydub.AudioSegment.from_file") as MockAudioFromFile, \
         patch("pydub.AudioSegment.silent") as MockAudioSilent:

        # Configure Mock Parser
        parser_instance = MockParser.return_value
        parser_instance.parse_chapter = AsyncMock(return_value=mock_script)

        # Configure Mock VoiceManager
        vm_instance = MockVoiceManager.return_value
        vm_instance.get_voice = AsyncMock(side_effect=["narrator_id", "warrior_id"])
        vm_instance.synthesize = AsyncMock(return_value=(b"fake_audio", mock_alignment))

        # Configure Mock ImageGenerator
        ig_instance = MockImageGenerator.return_value
        ig_instance.generate = AsyncMock(return_value="backgrounds/fake_hash.webp")

        # Configure BGM and Mixing
        MockBGMManager.return_value.get_random_track.return_value = "fake_bgm.mp3"
        MockAudioFromFile.return_value = MagicMock()
        MockAudioFromFile.return_value.__len__.return_value = 5000 # 5 seconds
        MockAudioSilent.return_value = MagicMock()
        MockAudioSilent.return_value.__len__.return_value = 5000
        MockAudioSilent.return_value.__add__.return_value = MockAudioSilent.return_value
        MockMixingEngine.return_value.create_looped_background.return_value = MockAudioSilent.return_value
        MockMixingEngine.return_value.overlay_voice_on_background.return_value = MockAudioSilent.return_value

        # Run implementation
        await tao_file_audiodrama(
            content_list=content_list,
            filename=mp3_filename,
            story_id="test_story",
            db_manager=mock_db,
            title="Test Chapter"
        )

        # 1. Verify manifest existence
        manifest_path = str(output_folder / "test_chapter.manifest.json")
        assert os.path.exists(manifest_path)

        # 2. Verify manifest content
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        assert manifest["title"] == "Test Chapter"
        assert "audio" in manifest
        assert "base_path" in manifest
        assert "events" in manifest
        
        # Check background event
        bg_events = [e for e in manifest["events"] if e["type"] == "background"]
        assert len(bg_events) > 0
        assert bg_events[0]["src"] == "backgrounds/fake_hash.webp"
        
        # Check vfx event
        vfx_events = [e for e in manifest["events"] if e["type"] == "vfx"]
        assert len(vfx_events) > 0
        assert vfx_events[0]["effect"] == "flash"
        
        # Check dialogue event
        dialogue_events = [e for e in manifest["events"] if e["type"] == "dialogue"]
        assert len(dialogue_events) >= 2
        assert dialogue_events[0]["role"] == "narrator"
        assert "alignment" in dialogue_events[0]
        assert "word" in dialogue_events[0]["alignment"][0]
        
        # Check image generation call
        ig_instance.generate.assert_called()
        
        # Verify backgrounds folder exists
        assert os.path.exists(output_folder / "backgrounds")
