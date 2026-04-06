import pytest
from fastapi.testclient import TestClient
from vvr_scraper.web import app
import os
import base64

# Mock environment variables for testing
os.environ["VVR_OPDS_USER"] = "admin"
os.environ["VVR_OPDS_PASS"] = "password"

client = TestClient(app)

def get_auth_headers(user="admin", password="password"):
    auth_str = f"{user}:{password}"
    auth_bytes = auth_str.encode("ascii")
    auth_base64 = base64.b64encode(auth_bytes).decode("ascii")
    return {"Authorization": f"Basic {auth_base64}"}

def test_opds_auth_required():
    """Test that OPDS routes require authentication."""
    with TestClient(app) as client:
        response = client.get("/opds/v1/root")
        assert response.status_code == 401

def test_opds_auth_invalid():
    """Test that OPDS routes reject invalid credentials."""
    with TestClient(app) as client:
        headers = get_auth_headers("wrong", "user")
        response = client.get("/opds/v1/root", headers=headers)
        assert response.status_code == 401

def test_opds_root_feed():
    """Test the root OPDS feed."""
    with TestClient(app) as client:
        headers = get_auth_headers()
        response = client.get("/opds/v1/root", headers=headers)
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]
        assert b"M\xe1\xbb\x9bi t\xe1\xba\xa3i" in response.content # "Mới tải" in UTF-8
        assert b"Theo Th\xe1\xbb\x83 lo\xe1\xba\xa1i" in response.content # "Theo Thể loại"

def test_opds_newest_feed():
    """Test the newest novels feed."""
    with TestClient(app) as client:
        headers = get_auth_headers()
        response = client.get("/opds/v1/newest", headers=headers)
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]

def test_opds_all_feed():
    """Test the all novels feed."""
    with TestClient(app) as client:
        headers = get_auth_headers()
        response = client.get("/opds/v1/all", headers=headers)
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]

def test_opds_genres_list():
    """Test the genres list feed."""
    with TestClient(app) as client:
        headers = get_auth_headers()
        response = client.get("/opds/v1/genres", headers=headers)
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]

def test_opds_authors_list():
    """Test the authors list feed."""
    with TestClient(app) as client:
        headers = get_auth_headers()
        response = client.get("/opds/v1/authors", headers=headers)
        assert response.status_code == 200
        assert "application/atom+xml" in response.headers["content-type"]

def test_opds_data_integration():
    """Test that data from DB is correctly reflected in the OPDS feed."""
    with TestClient(app) as client:
        # Add a sample novel to the DB via the app state
        db = app.state.db
        import asyncio
        
        async def setup_data():
            await db.upsert_novel({
                "title": "Test Novel OPDS",
                "slug": "truyen/test-novel-opds",
                "author": "OPDS Author",
                "genres": "Action, Adventure",
                "description": "This is a test novel for OPDS integration.",
                "last_chapter_count": 10,
                "formats": "epub,pdf"
            })
            
        # Run the async setup in the current loop (which should be running due to TestClient)
        # However, TestClient with context manager runs lifespan which might be in a different thread/loop.
        # Let's try to run it directly.
        asyncio.run(setup_data())
        
        headers = get_auth_headers()
        response = client.get("/opds/v1/all", headers=headers)
        assert response.status_code == 200
        assert b"Test Novel OPDS" in response.content
        assert b"OPDS Author" in response.content
        assert b"Action" in response.content
        assert b"Adventure" in response.content

def test_opds_download_endpoint():
    """Test the OPDS download endpoint."""
    slug = "truyen/test-novel-download"
    title = "Test Novel Download"
    output_folder = "test_novels_opds/test_novel"
    os.makedirs(output_folder, exist_ok=True)
    # sanitize_filename("Test Novel Download") -> "Test Novel Download"
    from vvr_scraper.utils import sanitize_filename
    filename = sanitize_filename(title)
    file_path = os.path.join(output_folder, f"{filename}.epub")
    with open(file_path, "wb") as f:
        f.write(b"fake epub content")
        
    import asyncio
    async def setup_data():
        db = app.state.db
        await db.upsert_novel({
            "slug": slug,
            "title": title,
            "output_folder": os.path.abspath(output_folder),
            "formats": "epub"
        })
    
    with TestClient(app) as client:
        # lifespan has run here, so app.state.db is initialized
        asyncio.run(setup_data())
        
        headers = get_auth_headers()
        # Use URL-encoded slug for the path if needed, but path params handle slashes if defined as :path
        response = client.get(f"/api/opds/download/{slug}?fmt=epub", headers=headers)
        assert response.status_code == 200
        assert response.content == b"fake epub content"
        # Starlette/FastAPI might use filename*=utf-8'' encoding for filenames with spaces
        cd = response.headers["content-disposition"]
        assert "attachment" in cd
        assert "Test" in cd and "Novel" in cd and "Download.epub" in cd
    
    import shutil
    # Cleanup
    if os.path.exists("test_novels_opds"):
        shutil.rmtree("test_novels_opds")
