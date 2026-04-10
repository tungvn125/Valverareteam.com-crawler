import os
import pytest
import httpx
from bs4 import BeautifulSoup

from vvr_scraper.utils import BASE_URL, HEADERS

@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip real HTTP requests on GitHub CI due to Cloudflare blocks")
async def test_smoke_integration_homepage_reachable():
    """
    Smoke test to verify that the website is up, reachable, and our HEADERS
    aren't instantly blocked by a WAF returning 403 Forbidden.
    """
    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0) as client:
        response = await client.get(BASE_URL)
        
        # 200 means we passed basic WAF checks 
        # (A 403 usually means Cloudflare Captcha blocked us)
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}. The crawler might be blocked by WAF."
        
        # Verify it's actually the site by checking the DOM
        soup = BeautifulSoup(response.text, "lxml")
        
        # The homepage should have some identifiable structure
        title = soup.find("title")
        assert title is not None
        assert "valvrareteam" in title.text.lower() or "truyện" in title.text.lower()
        
        # Look for basic navigation or stories (just searching for chapter or truyen links)
        nav_links = soup.select("a[href*='/truyen']")
        assert len(nav_links) > 0, "Could not find expected DOM elements. Website structure might have changed."

@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("CI") == "true", reason="Skip real HTTP requests on GitHub CI")
async def test_smoke_integration_search():
    """
    Smoke test an actual simple parsing flow to ensure Valvrare's basic search logic works.
    """
    search_url = f"{BASE_URL}/truyen?q=a"
    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0) as client:
        response = await client.get(search_url)
        assert response.status_code == 200
        
        assert b"Valvrare" in response.content, "Response doesn't contain expected content. WAF might be blocking."
