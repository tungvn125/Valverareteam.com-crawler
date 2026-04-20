# Formatting Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve source paragraph boundaries so EPUB, HTML, MD, and TXT exports stay closer to the web reading layout.

**Architecture:** Fix paragraph preservation at the source extraction layer instead of adding exporter heuristics. Keep exporters mapping one text `ContentItem` to one paragraph/block, and make TruyenFull/LnHako extraction less destructive so downstream formats inherit the improved spacing automatically.

**Tech Stack:** Python, BeautifulSoup, Playwright async API, pytest, ebooklib

---

### Task 1: Add Failing Paragraph-Preservation Tests

**Files:**
- Modify: `tests/test_sources.py`
- Modify: `tests/test_scraper.py`
- Test: `tests/test_sources.py`
- Test: `tests/test_scraper.py`

- [ ] **Step 1: Add the failing TruyenFull paragraph-preservation test**

```python
@pytest.mark.asyncio
async def test_truyenfull_get_content_preserves_paragraph_boundaries():
    html = """
    <div id="chapter-c">
        <p>Doan 1</p>
        <p>"Loi thoai rieng"</p>
        <p>Doan 3</p>
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
```

- [ ] **Step 2: Add the failing LnHako paragraph-preservation test**

```python
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
```

- [ ] **Step 3: Add the exporter regression test that proves separate text items stay separate in EPUB output**

```python
async def test_epub_keeps_separate_paragraph_blocks(tmp_path):
    chapters_data = [
        {
            "title": "Chapter 1",
            "content": [
                {"type": "text", "data": "Doan 1"},
                {"type": "text", "data": '"Loi thoai rieng"'},
                {"type": "text", "data": "Doan 3"},
            ],
        }
    ]
    filepath = str(tmp_path / "test.epub")

    await tao_file_epub(filepath, "Test Book", "Test Author", chapters_data)

    with zipfile.ZipFile(filepath, "r") as zip_ref:
        chapter_files = [name for name in zip_ref.namelist() if name.endswith("chap_1.xhtml")]
        chapter_html = zip_ref.read(chapter_files[0]).decode("utf-8")

    assert "<p>Doan 1</p>" in chapter_html
    assert '<p>&quot;Loi thoai rieng&quot;</p>' in chapter_html
    assert "<p>Doan 3</p>" in chapter_html
```

- [ ] **Step 4: Run the new tests to verify the current behavior gap**

Run: `pytest tests/test_sources.py -k "paragraph_boundaries or browser_paragraphs" tests/test_scraper.py -k separate_paragraph_blocks --no-cov`
Expected: If the source extraction currently collapses or over-normalizes paragraph content, at least one new test fails for the expected formatting-preservation reason.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/test_sources.py tests/test_scraper.py
git commit -m "test: cover paragraph preservation regressions"
```

### Task 2: Make TruyenFull Extraction Preserve Paragraph Content More Faithfully

**Files:**
- Modify: `vvr_scraper/sources/truyenfull.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Replace the destructive paragraph text read in `TruyenFullSource.get_content()`**

```python
            elif element.name == "p":
                text = element.get_text(separator=" ", strip=False)
                clean_text = text.strip()
                if clean_text:
                    extracted_content.append(ContentItem(type="text", data=clean_text))
```

- [ ] **Step 2: Run the focused TruyenFull test**

Run: `pytest tests/test_sources.py -k truyenfull_get_content_preserves_paragraph_boundaries --no-cov`
Expected: PASS

- [ ] **Step 3: Commit the TruyenFull change**

```bash
git add vvr_scraper/sources/truyenfull.py tests/test_sources.py
git commit -m "fix: preserve truyenfull paragraph extraction"
```

### Task 3: Keep LnHako Browser Paragraph Extraction Minimal And Stable

**Files:**
- Modify: `vvr_scraper/sources/lnhako.py`
- Test: `tests/test_sources.py`

- [ ] **Step 1: Keep one browser paragraph per item while trimming only surrounding whitespace**

```python
            for p in paragraphs:
                clean_text = p.strip()
                if clean_text:
                    extracted_content.append(ContentItem(type="text", data=clean_text))
```

- [ ] **Step 2: Run the focused LnHako test**

Run: `pytest tests/test_sources.py -k lnhako_get_content_preserves_browser_paragraphs_without_collapsing_items --no-cov`
Expected: PASS

- [ ] **Step 3: Commit the LnHako confirmation change if a code edit was needed**

```bash
git add vvr_scraper/sources/lnhako.py tests/test_sources.py
git commit -m "test: lock lnhako paragraph extraction behavior"
```

### Task 4: Verify Downstream Export Behavior

**Files:**
- Test: `tests/test_scraper.py`
- Test: `tests/test_sources.py`
- Modify if needed: `vvr_scraper/exporter.py`

- [ ] **Step 1: Run the EPUB regression test**

Run: `pytest tests/test_scraper.py -k separate_paragraph_blocks --no-cov`
Expected: PASS

- [ ] **Step 2: Run the full touched test files**

Run: `pytest tests/test_sources.py tests/test_scraper.py --no-cov`
Expected: PASS

- [ ] **Step 3: Lint the touched files**

Run: `ruff check vvr_scraper/sources/truyenfull.py vvr_scraper/sources/lnhako.py vvr_scraper/exporter.py tests/test_sources.py tests/test_scraper.py`
Expected: `All checks passed!`

- [ ] **Step 4: Commit the final verified state**

```bash
git add vvr_scraper/sources/truyenfull.py vvr_scraper/sources/lnhako.py vvr_scraper/exporter.py tests/test_sources.py tests/test_scraper.py
git commit -m "fix: preserve exported paragraph spacing"
```
