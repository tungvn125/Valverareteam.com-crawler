import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from vvr_scraper.sources import get_source, _SOURCE_CACHE
from vvr_scraper.sources.truyenfull import TruyenFullSource
from vvr_scraper.sources.lnhako import LnHakoSource
from vvr_scraper.models import StoryInfo, ContentItem


@pytest.mark.asyncio
async def test_truyenfull_search():
    mock_resp = MagicMock()
    mock_resp.text = '<a href="http://test.com/1" class="list-group-item" title="Title 1">Title 1</a>'
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    results = await source.search("query")

    assert len(results) == 1
    assert results[0].title == "Title 1"
    assert results[0].url == "http://test.com/1"
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_truyenfull_get_info():
    html = """
    <h3 class="title">Test Story</h3>
    <a itemprop="author">Test Author</a>
    <div class="desc-text">Test Description</div>
    <div class="book-thumb"><img src="http://test.com/cover.jpg"></div>
    <div class="info">
        <a itemprop="genre">Action</a>
        <div>Trạng thái: Chương 100</div>
    </div>
    <input id="truyen-id" value="123">
    <input id="total-page" value="2">
    """
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    info = await source.get_info("http://truyenfull.vision/test-story/")

    assert info.title == "Test Story"
    assert info.author == "Test Author"
    assert info.total_chapters == "100"
    assert info.cover_url == "http://test.com/cover.jpg"
    assert "Action" in info.genres


@pytest.mark.asyncio
async def test_lnhako_search():
    html = '<div class="thumb_attr series-title"><a href="/truyen/1-slug">Hako Story</a></div>'
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = LnHakoSource(client=mock_client)
    results = await source.search("query")

    assert len(results) == 1
    assert results[0].title == "Hako Story"
    assert results[0].url == "https://ln.hako.vn/truyen/1-slug"


@pytest.mark.asyncio
async def test_lnhako_get_info():
    html = """
    <h1 class="series-name"><a href="#">Hako Title</a></h1>
    <a href="/tac-gia/1">Hako Author</a>
    <div class="summary-content">Hako Desc</div>
    <div class="series-cover" style="background-image: url('http://test.com/hako.jpg')"></div>
    <div class="series-gernes"><a>Fantasy</a></div>
    <a href="/truyen/1-slug/c12345-chuong-1">Chương 1</a>
    """
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = LnHakoSource(client=mock_client)
    info = await source.get_info("https://ln.hako.vn/truyen/1-slug")

    assert info.title == "Hako Title"
    assert info.author == "Hako Author"
    assert info.cover_url == "http://test.com/hako.jpg"
    assert info.total_chapters == "1"


@pytest.mark.asyncio
async def test_lnhako_get_content():
    # Mocking Playwright is complex, so we'll mock the high-level calls
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    # Use MagicMock for page because locator() is sync
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    # page.goto and page.close ARE async
    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()

    # Define a Mock for Locator
    class MockLocator:
        def __init__(self, data):
            self.all_inner_texts = AsyncMock(return_value=data)
            self.all = AsyncMock(return_value=[])

    # page.locator() is a synchronous call returning a Locator object
    def locator_side_effect(selector):
        if "p" in selector:
            return MockLocator(["Para 1", "Para 2"])
        return MockLocator([])

    mock_page.locator.side_effect = locator_side_effect

    source = LnHakoSource(browser=mock_browser)
    content = await source.get_content("https://ln.hako.vn/chapter/1")

    assert len(content) == 2
    assert content[0].type == "text"
    assert content[0].data == "Para 1"
    mock_page.goto.assert_called_once_with("https://ln.hako.vn/chapter/1", wait_until="networkidle", timeout=60000)
    mock_page.close.assert_called_once()


@pytest.mark.asyncio
async def test_source_aclose_only_closes_owned_client():
    owned = TruyenFullSource()
    assert owned.client.is_closed is False
    await owned.aclose()
    assert owned.client.is_closed is True

    external_client = AsyncMock(spec=httpx.AsyncClient)
    borrowed = TruyenFullSource(client=external_client)
    await borrowed.aclose()
    external_client.aclose.assert_not_called()


@pytest.mark.asyncio
async def test_lnhako_aclose_only_closes_owned_client():
    owned = LnHakoSource()
    assert owned.client.is_closed is False
    await owned.aclose()
    assert owned.client.is_closed is True

    external_client = AsyncMock(spec=httpx.AsyncClient)
    borrowed = LnHakoSource(client=external_client)
    await borrowed.aclose()
    external_client.aclose.assert_not_called()


def test_get_source_caches_by_domain():
    _SOURCE_CACHE.clear()
    source1 = get_source("https://truyenfull.vision/story-1")
    source2 = get_source("https://truyenfull.vision/story-2")
    assert source1 is source2


def test_get_source_with_external_client_not_cached():
    _SOURCE_CACHE.clear()
    external_client = object()
    source1 = get_source("https://truyenfull.vision/story-1", client=external_client)
    source2 = get_source("https://truyenfull.vision/story-2", client=external_client)
    assert source1 is not source2
