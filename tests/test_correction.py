"""
Tests for the correction API routes.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from vvr_scraper.web.routes.correction import (
    ApplySimilarRequest,
    CharacterUpdateRequest,
    CorrectionRequest,
    _find_script_files,
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
        import asyncio

        from fastapi.testclient import TestClient

        from vvr_scraper.db import DatabaseManager
        from vvr_scraper.social.auth import get_auth_user
        from vvr_scraper.utils import get_config_path
        from vvr_scraper.web import app

        # Mock auth for testing
        def _fake_auth_user():
            from vvr_scraper.social.auth import AuthUser

            return AuthUser(id="test-user-id", username="testuser", role="admin")

        app.dependency_overrides[get_auth_user] = _fake_auth_user

        loop = asyncio.new_event_loop()
        db = DatabaseManager(db_path=get_config_path("test_vvr_library.db"))
        loop.run_until_complete(db.init_db())
        app.state.db = db
        client = TestClient(app)
        yield client
        loop.run_until_complete(db.close())
        loop.close()
        os.remove(get_config_path("test_vvr_library.db"))
        # Clean up dependency overrides
        app.dependency_overrides.pop(get_auth_user, None)

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

    def test_apply_similar_returns_500_when_all_matching_scripts_are_invalid(self, client, tmp_path):
        novel_dir = tmp_path / "novel"
        chapter_dir = novel_dir / "chapters" / "1"
        chapter_dir.mkdir(parents=True)
        script_path = chapter_dir / "Novel.1.ad.mp3.script.json"
        script_path.write_text("{not valid json", encoding="utf-8")

        with patch("vvr_scraper.web.routes.correction._async_get_output_dir", return_value=novel_dir):
            response = client.post(
                "/api/correction/test-slug/apply-similar",
                json={"segment_idx": 0, "new_role": "Mahiru", "chapter_idx": 1},
            )

        assert response.status_code == 500
        assert response.json()["detail"] == "No readable script found for chapter 1"

    def test_apply_similar_returns_500_when_saving_script_fails(self, client, tmp_path):
        novel_dir = tmp_path / "novel"
        chapter_dir = novel_dir / "chapters" / "1"
        chapter_dir.mkdir(parents=True)
        script_path = chapter_dir / "Novel.1.ad.mp3.script.json"
        script_path.write_text(
            json.dumps(
                [
                    {"type": "segment", "role": "Narrator", "text": "first"},
                    {"type": "segment", "role": "Narrator", "text": "second"},
                ]
            ),
            encoding="utf-8",
        )

        original_replace = os.replace
        failed_once = False

        def failing_replace(src, dst, *args, **kwargs):
            nonlocal failed_once
            if Path(dst) == script_path and not failed_once:
                failed_once = True
                raise OSError("disk full")
            return original_replace(src, dst, *args, **kwargs)

        with (
            patch("vvr_scraper.web.routes.correction._async_get_output_dir", return_value=novel_dir),
            patch("os.replace", side_effect=failing_replace),
        ):
            response = client.post(
                "/api/correction/test-slug/apply-similar",
                json={"segment_idx": 0, "new_role": "Mahiru", "chapter_idx": 1},
            )

        assert response.status_code == 500
        assert response.json()["detail"] == f"Error saving script: disk full ({script_path.name})"

    def test_apply_similar_rolls_back_earlier_files_when_later_save_fails(self, client, tmp_path):
        novel_dir = tmp_path / "novel"
        chapter1_dir = novel_dir / "chapters" / "1"
        chapter2_dir = novel_dir / "chapters" / "2"
        chapter1_dir.mkdir(parents=True)
        chapter2_dir.mkdir(parents=True)

        script1_path = chapter1_dir / "Novel.1.ad.mp3.script.json"
        script2_path = chapter2_dir / "Novel.2.ad.mp3.script.json"

        original_script1 = [
            {"type": "segment", "role": "Narrator", "text": "chapter1-source"},
            {"type": "segment", "role": "Narrator", "text": "chapter1-target"},
        ]
        original_script2 = [
            {"type": "segment", "role": "Narrator", "text": "chapter2-target"},
        ]

        script1_path.write_text(json.dumps(original_script1), encoding="utf-8")
        script2_path.write_text(json.dumps(original_script2), encoding="utf-8")

        original_replace = os.replace
        failed_once = False

        def failing_replace(src, dst, *args, **kwargs):
            nonlocal failed_once
            if Path(dst) == script2_path and not failed_once:
                failed_once = True
                raise OSError("disk full")
            return original_replace(src, dst, *args, **kwargs)

        with (
            patch("vvr_scraper.web.routes.correction._async_get_output_dir", return_value=novel_dir),
            patch("os.replace", side_effect=failing_replace),
        ):
            response = client.post(
                "/api/correction/test-slug/apply-similar",
                json={"segment_idx": 0, "new_role": "Mahiru"},
            )

        assert response.status_code == 500
        assert response.json()["detail"] == f"Error saving script: disk full ({script2_path.name})"
        assert json.loads(script1_path.read_text(encoding="utf-8")) == original_script1
        assert json.loads(script2_path.read_text(encoding="utf-8")) == original_script2
