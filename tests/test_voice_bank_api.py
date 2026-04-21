"""
Integration tests for voice bank API endpoints using FastAPI TestClient.
"""

import io
import os
import struct
import tempfile
import wave
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from vvr_scraper.social.auth import AuthUser, get_auth_user
from vvr_scraper.voice_bank.db import VoiceBankDatabaseManager
from vvr_scraper.web import app


def _create_wav_bytes(duration_s=5, sample_rate=22050, channels=1, bit_depth=16):
    """Create a valid WAV file as bytes for upload."""
    n_samples = int(duration_s * sample_rate)
    data = struct.pack(f"<{n_samples * channels}h", *([0] * n_samples * channels))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bit_depth // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return buffer.getvalue()


def _make_wav_file(temp_dir, duration_s=5, filename="voice.wav"):
    """Create a valid WAV file on disk and return the path."""
    path = os.path.join(temp_dir, filename)
    n_samples = int(5 * 22050)
    data = struct.pack(f"<{n_samples}h", *([0] * n_samples))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(data)
    return path


# --- Fake user for auth mocking ---


def _fake_auth_user():
    return AuthUser(id="test-user", username="testuser", role="member")


class TestVoiceBankAPI:
    """Tests for voice bank API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Set up TestClient with mocked auth and real voice bank DB."""
        # Set up temp dir for voice bank storage and DB
        self._temp_dir = tempfile.TemporaryDirectory()
        voice_bank_dir = self._temp_dir.name
        db_path = os.path.join(self._temp_dir.name, "voice_bank.db")

        # Set env var so storage module uses our temp dir
        original_env = os.environ.get("VVR_VOICE_BANK_DIR")
        os.environ["VVR_VOICE_BANK_DIR"] = voice_bank_dir

        # Create and init the voice bank DB synchronously via aiosqlite
        voice_bank_db = VoiceBankDatabaseManager(db_path)
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(voice_bank_db.init_db())

        # Override lifespan to inject our DB
        @asynccontextmanager
        async def test_lifespan(a):
            a.state.voice_bank_db = voice_bank_db
            a.state.social_db = type("obj", (object,), {"init_db": None, "close": None})()
            try:
                yield
            finally:
                await voice_bank_db.close()

        original_lifespan = app.router.lifespan_context
        app.router.lifespan_context = test_lifespan

        # Override auth dependency
        app.dependency_overrides[get_auth_user] = _fake_auth_user

        with TestClient(app, raise_server_exceptions=True) as client:
            self._client = client
            yield

        # Cleanup
        app.router.lifespan_context = original_lifespan
        if get_auth_user in app.dependency_overrides:
            del app.dependency_overrides[get_auth_user]
        if original_env is not None:
            os.environ["VVR_VOICE_BANK_DIR"] = original_env
        elif "VVR_VOICE_BANK_DIR" in os.environ:
            del os.environ["VVR_VOICE_BANK_DIR"]
        loop.close()
        self._temp_dir.cleanup()

    @property
    def client(self):
        return self._client

    def test_upload_voice(self):
        """POST /api/voices/upload with valid WAV -> 200 OK."""
        wav_bytes = _create_wav_bytes(duration_s=5)
        response = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Xin chào, đây là giọng nói mẫu của tôi",
                "name": "My Test Voice",
                "description": "A test voice",
                "gender": "male",
                "age_group": "adult",
                "language": "vi",
            },
            files={"audio": ("test.wav", wav_bytes, "audio/wav")},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["name"] == "My Test Voice"
        assert data["visibility"] == "private"

    def test_upload_voice_missing_fields(self):
        """Missing ref_text -> 422."""
        wav_bytes = _create_wav_bytes(duration_s=5)
        response = self.client.post(
            "/api/voices/upload",
            data={
                "name": "Incomplete Upload",
                "gender": "male",
                "age_group": "adult",
                # ref_text is missing
            },
            files={"audio": ("test.wav", wav_bytes, "audio/wav")},
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}"

    def test_list_my_voices(self):
        """Upload 2 voices with different audio, GET /api/voices/me -> returns 2 items."""
        wav_bytes_1 = _create_wav_bytes(duration_s=5)
        wav_bytes_2 = _create_wav_bytes(duration_s=6)  # Different duration = different hash

        # Upload first voice
        self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng nói thứ nhất của tôi",
                "name": "Voice One",
                "gender": "male",
                "age_group": "adult",
            },
            files={"audio": ("v1.wav", wav_bytes_1, "audio/wav")},
        )

        # Upload second voice
        self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng nói thứ hai của tôi",
                "name": "Voice Two",
                "gender": "female",
                "age_group": "young_adult",
            },
            files={"audio": ("v2.wav", wav_bytes_2, "audio/wav")},
        )

        response = self.client.get("/api/voices/me")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_community_voices(self):
        """Publish 1, keep 1 private. GET /api/voices/community -> returns 1 public."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        # Upload and publish first voice
        r1 = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng công khai của tôi",
                "name": "Public Voice",
                "gender": "male",
                "age_group": "adult",
            },
            files={"audio": ("pub.wav", wav_bytes, "audio/wav")},
        )
        voice1_id = r1.json()["id"]

        # Publish it
        self.client.patch(f"/api/voices/{voice1_id}/publish")

        # Upload second voice (private by default)
        self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng riêng tư của tôi",
                "name": "Private Voice",
                "gender": "female",
                "age_group": "adult",
            },
            files={"audio": ("priv.wav", wav_bytes, "audio/wav")},
        )

        response = self.client.get("/api/voices/community")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Public Voice"

    def test_get_voice(self):
        """Upload, GET /api/voices/{id} -> returns voice details."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Chi tiết giọng nói của tôi",
                "name": "Detail Voice",
                "gender": "female",
                "age_group": "young_adult",
            },
            files={"audio": ("detail.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]

        response = self.client.get(f"/api/voices/{voice_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Detail Voice"
        assert data["id"] == voice_id

    def test_publish_voice(self):
        """PATCH /api/voices/{id}/publish -> visibility='public'."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng để publish của tôi",
                "name": "To Publish",
                "gender": "male",
                "age_group": "adult",
            },
            files={"audio": ("pub.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]

        response = self.client.patch(f"/api/voices/{voice_id}/publish")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["visibility"] == "public"

    def test_delist_voice(self):
        """Publish then delist -> visibility='delisted'."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        # Upload and publish
        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng để delist của tôi",
                "name": "To Delist",
                "gender": "female",
                "age_group": "adult",
            },
            files={"audio": ("delist.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]
        self.client.patch(f"/api/voices/{voice_id}/publish")

        # Delist
        response = self.client.patch(f"/api/voices/{voice_id}/delist")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["visibility"] == "delisted"

    def test_delete_voice(self):
        """DELETE /api/voices/{id} -> 204, then GET -> 404."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng để xóa của tôi",
                "name": "To Delete",
                "gender": "male",
                "age_group": "adult",
            },
            files={"audio": ("del.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]

        response = self.client.delete(f"/api/voices/{voice_id}")
        assert response.status_code == 204, f"Expected 204, got {response.status_code}"

        # Verify it's gone
        get_response = self.client.get(f"/api/voices/{voice_id}")
        assert get_response.status_code == 404

    def test_vote_voice(self):
        """POST /api/voices/{id}/vote with {vote: 1} -> score increases."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        # Upload and publish
        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng để vote của tôi",
                "name": "Voteable Voice",
                "gender": "male",
                "age_group": "adult",
            },
            files={"audio": ("vote.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]
        self.client.patch(f"/api/voices/{voice_id}/publish")

        # Vote
        response = self.client.post(f"/api/voices/{voice_id}/vote", json={"vote": 1})
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
        data = response.json()
        assert data["vote_score"] == 1

    def test_get_voice_audio(self):
        """Upload, GET /api/voices/{id}/audio -> returns audio/wav bytes."""
        wav_bytes = _create_wav_bytes(duration_s=5)

        r = self.client.post(
            "/api/voices/upload",
            data={
                "ref_text": "Giọng để nghe của tôi",
                "name": "Audio Voice",
                "gender": "female",
                "age_group": "adult",
            },
            files={"audio": ("audio.wav", wav_bytes, "audio/wav")},
        )
        voice_id = r.json()["id"]

        response = self.client.get(f"/api/voices/{voice_id}/audio")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.headers["content-type"] == "audio/wav"
        assert len(response.content) > 0
