"""
Tests for the correction API routes.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from vvr_scraper.web.routes.correction import (
    ApplySimilarRequest,
    CorrectionRequest,
    CharacterUpdateRequest,
    _find_script_files,
    _async_get_output_dir,
)


class TestFindScriptFiles:
    def test_finds_script_json_files(self, tmp_path):
        novel_dir = tmp_path / "My Novel"
        novel_dir.mkdir()
        (novel_dir / "My Novel.ad.mp3.script.json").write_text(
            json.dumps([{"type": "segment", "role": "Narrator", "text": "Hello"}])
        )

        scripts = _find_script_files(novel_dir, "my-novel")
        assert len(scripts) == 1
        assert scripts[0]["chapter_idx"] == 0

    def test_finds_chapter_scripts(self, tmp_path):
        novel_dir = tmp_path / "My Novel"
        chapters_dir = novel_dir / "chapters" / "1"
        chapters_dir.mkdir(parents=True)
        (chapters_dir / "My Novel.1.ad.mp3.script.json").write_text(
            json.dumps([{"type": "segment", "role": "Narrator", "text": "Hello"}])
        )

        scripts = _find_script_files(novel_dir, "my-novel")
        assert len(scripts) == 1
        assert scripts[0]["chapter_idx"] == 1

    def test_empty_dir(self, tmp_path):
        novel_dir = tmp_path / "Empty"
        novel_dir.mkdir()
        scripts = _find_script_files(novel_dir, "empty")
        assert scripts == []

    def test_nonexistent_dir(self, tmp_path):
        novel_dir = tmp_path / "DoesNotExist"
        scripts = _find_script_files(novel_dir, "doesnotexist")
        assert scripts == []

    def test_multiple_chapters(self, tmp_path):
        novel_dir = tmp_path / "My Novel"
        novel_dir.mkdir()
        # Whole novel script
        (novel_dir / "My Novel.ad.mp3.script.json").write_text(
            json.dumps([{"type": "segment", "role": "Narrator", "text": "Intro"}])
        )
        # Per-chapter scripts
        for i in [1, 2, 3]:
            ch_dir = novel_dir / "chapters" / str(i)
            ch_dir.mkdir(parents=True)
            (ch_dir / f"My Novel.{i}.ad.mp3.script.json").write_text(
                json.dumps([{"type": "segment", "role": "Narrator", "text": f"Chapter {i}"}])
            )

        scripts = _find_script_files(novel_dir, "my-novel")
        assert len(scripts) == 4

    def test_extracts_chapter_idx(self, tmp_path):
        novel_dir = tmp_path / "Novel"
        ch5_dir = novel_dir / "chapters" / "5"
        ch5_dir.mkdir(parents=True)
        ch5_dir = Path(ch5_dir)
        (ch5_dir / "Novel.5.ad.mp3.script.json").write_text(
            json.dumps([{"type": "segment", "role": "Narrator", "text": "Ch5"}])
        )

        scripts = _find_script_files(novel_dir, "novel")
        assert scripts[0]["chapter_idx"] == 5


class TestPydanticModels:
    def test_correction_request(self):
        req = CorrectionRequest(corrections=[{"segment_idx": 5, "new_role": "Mahiru"}])
        assert len(req.corrections) == 1
        assert req.corrections[0].segment_idx == 5
        assert req.corrections[0].new_role == "Mahiru"

    def test_apply_similar_request(self):
        req = ApplySimilarRequest(segment_idx=3, new_role="Yudai")
        assert req.chapter_idx is None

        req_with_chapter = ApplySimilarRequest(segment_idx=3, new_role="Yudai", chapter_idx=5)
        assert req_with_chapter.chapter_idx == 5

    def test_character_update_request(self):
        req = CharacterUpdateRequest(voice_id="abc123", color="#4ade80")
        assert req.voice_id == "abc123"
        assert req.color == "#4ade80"
        assert req.aliases is None


class TestCorrectionAPI:
    """Integration tests for correction API endpoints using FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from vvr_scraper.web import app
        from vvr_scraper.db import DatabaseManager
        from vvr_scraper.utils import get_config_path
        from fastapi.testclient import TestClient
        import asyncio

        loop = asyncio.new_event_loop()
        db = DatabaseManager(db_path=get_config_path("test_vvr_library.db"))
        loop.run_until_complete(db.init_db())
        app.state.db = db
        client = TestClient(app)
        yield client
        loop.run_until_complete(db.close())
        loop.close()
        os.remove(get_config_path("test_vvr_library.db"))

    def test_list_chapters_not_found(self, client):
        response = client.get("/api/correction/nonexistent-novel/chapters")
        assert response.status_code == 404

    def test_get_script_not_found(self, client):
        response = client.get("/api/correction/nonexistent-novel/chapter/0/script")
        assert response.status_code == 404

    def test_get_characters_empty(self, client):
        response = client.get("/api/correction/nonexistent-novel/characters")
        assert response.status_code == 200
        data = response.json()
        assert "characters" in data
