# LnHako Cover Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `LnHakoSource.get_info()` return a valid `cover_url` for LnHako story pages.

**Architecture:** Prefer the canonical `og:image` metadata exposed by the story page, then fall back to parsing the visible cover block's `background-image` style. Keep the change confined to `vvr_scraper/sources/lnhako.py` and cover both code paths with unit tests in `tests/test_sources.py`.

**Tech Stack:** Python, httpx, BeautifulSoup, pytest

---

### Task 1: Add Failing Tests For LnHako Cover Extraction

**Files:**
- Modify: `tests/test_sources.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Write the failing `og:image` test**

```python
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
```

- [ ] **Step 2: Write the failing inner-style fallback test**

```python
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_sources.py -k "og_image_cover or inner_cover_style_fallback" --no-cov`
Expected: FAIL because `info.cover_url` is `None` or still uses the wrong node.

- [ ] **Step 4: Commit the failing tests**

```bash
git add tests/test_sources.py
git commit -m "test: cover lnhako cover extraction"
```

### Task 2: Implement Minimal LnHako Cover Extraction Fix

**Files:**
- Modify: `vvr_scraper/sources/lnhako.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Update `get_info()` to prefer `og:image`**

```python
        cover_url = None

        og_image = soup.select_one("meta[property='og:image']")
        if og_image and og_image.get("content"):
            cover_url = og_image.get("content")
```

- [ ] **Step 2: Add the DOM fallback for the inner cover node**

```python
        if not cover_url:
            cover_node = soup.select_one(".series-cover .content.img-in-ratio") or soup.find("div", class_="series-cover")
            if cover_node and cover_node.get("style"):
                url_match = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", cover_node["style"])
                cover_url = url_match.group(1) if url_match else None
```

- [ ] **Step 3: Run the focused tests to verify they pass**

Run: `pytest tests/test_sources.py -k "og_image_cover or inner_cover_style_fallback" --no-cov`
Expected: PASS

- [ ] **Step 4: Run the full LnHako source test file**

Run: `pytest tests/test_sources.py --no-cov`
Expected: PASS

- [ ] **Step 5: Lint the modified files**

Run: `ruff check vvr_scraper/sources/lnhako.py tests/test_sources.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit the implementation**

```bash
git add vvr_scraper/sources/lnhako.py tests/test_sources.py
git commit -m "fix: support lnhako cover extraction"
```
