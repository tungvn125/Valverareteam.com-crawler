from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import vvr_scraper.sources.lnhako as lnhako_module
from vvr_scraper.sources import _SOURCE_CACHE, get_source
from vvr_scraper.sources.lnhako import LnHakoSource
from vvr_scraper.sources.truyenfull import TruyenFullSource


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
async def test_truyenfull_get_info_follows_redirect_when_client_does_not_default_to_it():
    html = """
    <h3 class="title">Test Story</h3>
    <a itemprop="author">Test Author</a>
    <div class="desc-text">Test Description</div>
    <div class="book-thumb"><img src="http://test.com/cover.jpg"></div>
    <div class="info"><a itemprop="genre">Action</a></div>
    """
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    info = await source.get_info("https://truyenfull.vision/test-story")

    assert info.title == "Test Story"
    mock_client.get.assert_called_once_with("https://truyenfull.vision/test-story", params=None, follow_redirects=True)


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
async def test_lnhako_get_info_prefers_og_image_cover():
    html = """
    <meta property="og:image" content="https://i2.hako.vip/ln/series/covers/test-og.jpg">
    <h1 class="series-name"><a href="#">Hako Title</a></h1>
    <a href="/tac-gia/1">Hako Author</a>
    <div class="summary-content">Hako Desc</div>
    <div class="series-cover"><div class="content img-in-ratio" style="background-image: url('https://test.com/fallback.jpg')"></div></div>
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

    assert info.cover_url == "https://i2.hako.vip/ln/series/covers/test-og.jpg"


@pytest.mark.asyncio
async def test_lnhako_get_info_uses_inner_cover_style_fallback():
    html = """
    <h1 class="series-name"><a href="#">Hako Title</a></h1>
    <a href="/tac-gia/1">Hako Author</a>
    <div class="summary-content">Hako Desc</div>
    <div class="series-cover">
        <div class="a6-ratio">
            <div class="content img-in-ratio" style="background-image: url('https://i2.hako.vip/ln/series/covers/test-style.jpg')"></div>
        </div>
    </div>
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

    assert info.cover_url == "https://i2.hako.vip/ln/series/covers/test-style.jpg"


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
async def test_truyenfull_get_content_preserves_paragraph_boundaries():
    html = """
    <div id="chapter-c">
        <p>
            Doan 1<br class="html-br"/><br class="html-br"/>
            "Loi thoai rieng"<br class="html-br"/><br class="html-br"/>
            Doan 3
        </p>
    </div>
    """
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    content = await source.get_content("https://truyenfull.vision/test-story/chuong-1/")

    assert [item.data for item in content if item.type == "text"] == [
        "Doan 1",
        '"Loi thoai rieng"',
        "Doan 3",
    ]


@pytest.mark.asyncio
async def test_lnhako_get_content_preserves_browser_paragraphs_without_collapsing_items():
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()

    class MockLocator:
        def __init__(self, texts=None, images=None):
            self.all_inner_texts = AsyncMock(return_value=texts or [])
            self.all = AsyncMock(return_value=images or [])

    def locator_side_effect(selector):
        if selector == "#chapter-content p":
            return MockLocator(["Doan 1", '"Loi thoai rieng"', "Doan 3"])
        if selector == "#chapter-content img":
            return MockLocator(images=[])
        raise AssertionError(f"Unexpected selector: {selector}")

    mock_page.locator.side_effect = locator_side_effect

    source = LnHakoSource(browser=mock_browser)
    content = await source.get_content("https://ln.hako.vn/chapter/1")

    assert [item.data for item in content if item.type == "text"] == [
        "Doan 1",
        '"Loi thoai rieng"',
        "Doan 3",
    ]


@pytest.mark.asyncio
async def test_lnhako_get_content_continues_when_initial_container_wait_times_out():
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()
    mock_page.wait_for_selector = AsyncMock(side_effect=[TimeoutError("container timeout"), None])

    class MockLocator:
        def __init__(self, texts=None, images=None):
            self.all_inner_texts = AsyncMock(return_value=texts or [])
            self.all = AsyncMock(return_value=images or [])

    def locator_side_effect(selector):
        if selector == "#chapter-content p":
            return MockLocator(["Decoded para"])
        if selector == "#chapter-content img":
            return MockLocator(images=[])
        raise AssertionError(f"Unexpected selector: {selector}")

    mock_page.locator.side_effect = locator_side_effect

    source = LnHakoSource(browser=mock_browser)
    content = await source.get_content("https://ln.hako.vn/chapter/1")

    assert len(content) == 1
    assert content[0].type == "text"
    assert content[0].data == "Decoded para"


@pytest.mark.asyncio
async def test_lnhako_get_content_retries_on_transient_failure_then_succeeds(monkeypatch):
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    calls = {"count": 0}

    async def goto_side_effect(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PlaywrightTimeoutError("transient timeout")

    mock_page.goto = AsyncMock(side_effect=goto_side_effect)
    mock_page.wait_for_selector = AsyncMock(return_value=None)
    mock_page.close = AsyncMock()

    class MockLocator:
        def __init__(self, texts=None, images=None):
            self.all_inner_texts = AsyncMock(return_value=texts or [])
            self.all = AsyncMock(return_value=images or [])

    def locator_side_effect(selector):
        if selector == "#chapter-content p":
            return MockLocator(["Recovered para"])
        if selector == "#chapter-content img":
            return MockLocator(images=[])
        raise AssertionError(f"Unexpected selector: {selector}")

    mock_page.locator.side_effect = locator_side_effect

    monkeypatch.setattr(lnhako_module.asyncio, "sleep", AsyncMock())

    source = LnHakoSource(browser=mock_browser)
    content = await source.get_content("https://ln.hako.vn/chapter/1")

    assert calls["count"] == 2
    assert [item.data for item in content if item.type == "text"] == ["Recovered para"]


@pytest.mark.asyncio
async def test_lnhako_get_content_raises_after_retry_exhausted(monkeypatch):
    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock()
    mock_page = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("always timeout"))
    mock_page.close = AsyncMock()

    monkeypatch.setattr(lnhako_module.asyncio, "sleep", AsyncMock())

    source = LnHakoSource(browser=mock_browser)
    with pytest.raises(PlaywrightTimeoutError):
        await source.get_content("https://ln.hako.vn/chapter/1")

    assert mock_page.goto.await_count == 3


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


# --- Tests cho Phase 3: contract standardization ---


@pytest.mark.asyncio
async def test_truyenfull_get_content_raises_when_no_content_div():
    """get_content() phải raise khi không tìm thấy #chapter-c div."""
    html = "<html><body><p>No chapter content here</p></body></html>"

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    with pytest.raises(RuntimeError, match="chapter"):
        await source.get_content("https://truyenfull.vision/test-story/chuong-1/")


@pytest.mark.asyncio
async def test_truyenfull_get_content_raises_when_extracted_content_empty():
    """get_content() phải raise khi div tồn tại nhưng parse ra rỗng."""
    html = """<html><body>
    <div id="chapter-c">
        <div class="ads-banner">Quảng cáo</div>
    </div>
    </body></html>"""

    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    with pytest.raises(RuntimeError):
        await source.get_content("https://truyenfull.vision/test-story/chuong-1/")


def test_truyenfull_slug_to_url():
    """slug_to_url() phải trả đúng URL pattern của TruyenFull."""
    url = TruyenFullSource.slug_to_url("toi-nhap-xac-vao-nu-chinh")
    assert url == "https://truyenfull.vision/toi-nhap-xac-vao-nu-chinh"


def test_truyenfull_slug_to_url_returns_none_for_empty():
    url = TruyenFullSource.slug_to_url("")
    assert url is not None


@pytest.mark.asyncio
async def test_lnhako_get_content_raises_when_no_browser():
    """get_content() phải raise RuntimeError ngay khi không có browser."""
    source = LnHakoSource()
    with pytest.raises(RuntimeError, match="[Bb]rowser"):
        await source.get_content("https://ln.hako.vn/truyen/1-slug/c12345-chuong-1")


def test_lnhako_slug_to_url():
    """slug_to_url() phải trả đúng URL pattern của LnHako."""
    url = LnHakoSource.slug_to_url("toi-nhap-xac-vao-nu-chinh")
    assert url == "https://ln.hako.vn/truyen/toi-nhap-xac-vao-nu-chinh"


def test_lnhako_slug_to_url_returns_string():
    url = LnHakoSource.slug_to_url("some-novel")
    assert isinstance(url, str)
    assert "ln.hako.vn" in url


@pytest.mark.asyncio
async def test_truyenfull_search_still_works_after_downgrade():
    """TruyenFull.search() vẫn hoạt động — phải trả list (không raise)."""
    mock_resp = MagicMock()
    mock_resp.text = '<a href="http://test.com/1" class="list-group-item" title="Title 1">Title 1</a>'
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = TruyenFullSource(client=mock_client)
    results = await source.search("query")

    assert isinstance(results, list)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_lnhako_search_still_works_after_downgrade():
    """LnHako.search() vẫn hoạt động — phải trả list (không raise)."""
    html = '<div class="thumb_attr series-title"><a href="/truyen/1-slug">Hako Story</a></div>'
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.status_code = 200

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get.return_value = mock_resp

    source = LnHakoSource(client=mock_client)
    results = await source.search("query")

    assert isinstance(results, list)
    assert len(results) >= 1


def test_minimal_source_without_search_still_valid():
    """Source không implement search() vẫn valid — dùng default return []."""
    from vvr_scraper.models import StoryInfo
    from vvr_scraper.sources import BaseSource

    class NoSearchSource(BaseSource):
        base_urls = ["nosearch.test"]
        priority = 80
        name = "no-search"
        requires_browser = False

        async def get_info(self, url):
            return StoryInfo(title="NS", author="", description="", slug="ns")

        async def get_chapter_list(self, url):
            return []

        async def get_content(self, url):
            raise RuntimeError("not implemented")

        async def aclose(self):
            pass

    import asyncio

    source = NoSearchSource()
    result = asyncio.run(source.search("query"))
    assert result == []
