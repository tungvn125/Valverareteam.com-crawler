import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from vvr_scraper.web import Settings, app


def test_web_assets(tmp_path):
    """Verifies that novel assets can be served and manifest API works."""
    # 1. Setup mock asset directory
    novels_base = tmp_path / "novels"
    novels_base.mkdir()

    chapter_path = novels_base / "test-novel" / "chapter-1"
    chapter_path.mkdir(parents=True)

    # Create a manifest.json
    manifest_data = {"title": "Test Chapter", "story_id": "test-novel", "events": []}
    with open(chapter_path / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    # Create a dummy image
    image_data = b"fake-png-data"
    with open(chapter_path / "cover.png", "wb") as f:
        f.write(image_data)

    # 2. Mock settings to use this tmp_path as base
    mock_settings = Settings(default_output_folder=str(novels_base))

    with patch("vvr_scraper.web.routes.api.load_vvr_settings", return_value=mock_settings):
        # We need to manually update the static mount's directory for testing
        # because it was mounted during module import.
        from fastapi.staticfiles import StaticFiles

        # Remove any existing "/novels" mount to avoid conflicts
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/novels"]
        app.mount("/novels", StaticFiles(directory=str(novels_base)), name="novels")

        # Re-create client to ensure it picks up route changes
        client = TestClient(app)

        # 3. Test Static File Access
        response = client.get("/novels/test-novel/chapter-1/cover.png")
        assert response.status_code == 200
        assert response.content == image_data

        # 4. Test Manifest API
        response = client.get("/api/novels/manifest", params={"path": "test-novel/chapter-1"})
        assert response.status_code == 200
        assert response.json() == manifest_data

        # 5. Test Path Traversal Security
        # Try to access something outside base_dir using '..'
        response = client.get("/api/novels/manifest", params={"path": "../../"})
        assert response.status_code == 403

        # 6. Test Missing Manifest
        response = client.get("/api/novels/manifest", params={"path": "non-existent"})
        assert response.status_code == 404
