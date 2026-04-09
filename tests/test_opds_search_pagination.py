import os

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from vvr_scraper.db import DatabaseManager
from vvr_scraper.web import app, get_current_user


# Mock authentication
def skip_auth():
    return "admin"


@pytest.fixture
async def test_client():
    app.dependency_overrides[get_current_user] = skip_auth
    db_path = "test_opds_pagination.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    db = DatabaseManager(db_path=db_path)
    await db.init_db()

    # Insert some fake data for testing pagination (25 novels)
    for i in range(1, 26):
        await db.upsert_novel(
            {
                "title": f"Novel {i:02d}",
                "slug": f"novel-{i:02d}",
                "author": f"Author {i % 5}",
                "last_chapter_count": 10,
                "genres": "Action, Fantasy",
                "description": f"Description for novel {i}",
            }
        )

    app.state.db = db

    with TestClient(app) as client:
        yield client

    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_opds_pagination_all(test_client):
    # Test page 1
    response = test_client.get("/opds/v1/all?page=1&size=10")
    assert response.status_code == 200

    root = etree.fromstring(response.content)
    entries = root.xpath("//atom:entry", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(entries) == 10

    # Check for next link
    next_links = root.xpath("//atom:link[@rel='next']", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(next_links) == 1
    assert "page=2" in next_links[0].get("href")

    # Test page 3 (last page with 5 items)
    response = test_client.get("/opds/v1/all?page=3&size=10")
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    entries = root.xpath("//atom:entry", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(entries) == 5

    # No next link on last page
    next_links = root.xpath("//atom:link[@rel='next']", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(next_links) == 0


@pytest.mark.asyncio
async def test_opds_search(test_client):
    # Search for "Novel 0" (should match 01 to 09)
    response = test_client.get("/opds/v1/search?q=Novel 0")
    assert response.status_code == 200

    root = etree.fromstring(response.content)
    entries = root.xpath("//atom:entry", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(entries) == 9

    # Search by author
    response = test_client.get("/opds/v1/search?q=Author 1")
    assert response.status_code == 200
    root = etree.fromstring(response.content)
    entries = root.xpath("//atom:entry", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    # Author 1 matches 1, 6, 11, 16, 21 (5 items)
    assert len(entries) == 5


@pytest.mark.asyncio
async def test_opds_root_search_link(test_client):
    response = test_client.get("/opds/v1/root")
    assert response.status_code == 200

    root = etree.fromstring(response.content)
    search_links = root.xpath("//atom:link[@rel='search']", namespaces={"atom": "http://www.w3.org/2005/Atom"})
    assert len(search_links) == 1
    assert "{searchTerms}" in search_links[0].get("href")
