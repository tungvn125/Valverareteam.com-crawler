import pytest

from vvr_scraper.models import ContentItem, StoryInfo
from vvr_scraper.sources import BaseSource, ChapterTreeItem, VolumeTreeItem


class MinimalSource(BaseSource):
    """Concrete minimal source — chỉ implement abstract methods."""

    base_urls = ["minimal.test"]
    priority = 50
    name = "minimal"
    requires_browser = False

    async def get_info(self, url: str) -> StoryInfo:
        return StoryInfo(title="Unknown", author="", description="", slug="test")

    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        return []

    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        raise RuntimeError("not implemented")

    async def aclose(self) -> None:
        pass


def test_basesource_has_classvar_declarations():
    assert hasattr(MinimalSource, "base_urls")
    assert hasattr(MinimalSource, "priority")
    assert hasattr(MinimalSource, "name")
    assert hasattr(MinimalSource, "requires_browser")


def test_basesource_priority_default_is_100():
    class NoPrioritySource(BaseSource):
        base_urls = ["nopriority.test"]
        name = "no-priority"
        requires_browser = False

        async def get_info(self, url):
            ...

        async def get_chapter_list(self, url):
            ...

        async def get_content(self, url):
            ...

        async def aclose(self):
            ...

    assert NoPrioritySource.priority == 100


@pytest.mark.asyncio
async def test_basesource_search_returns_empty_list_by_default():
    source = MinimalSource()
    result = await source.search("query")
    assert result == []


@pytest.mark.asyncio
async def test_basesource_fetch_cover_returns_none_without_client():
    source = MinimalSource()
    result = await source.fetch_cover("https://example.com/cover.jpg")
    assert result is None


def test_basesource_slug_to_url_returns_none_by_default():
    assert MinimalSource.slug_to_url("some-slug") is None


def test_basesource_matches_url():
    source = MinimalSource()
    assert source.matches("https://minimal.test/truyen/abc")
    assert not source.matches("https://other.test/truyen/abc")


import os
import inspect
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import httpx

from vvr_scraper.sources import PluginRegistry, BaseSource, REGISTRY


class HighPrioritySource(BaseSource):
    base_urls = ["high.test"]
    priority = 10
    name = "high"
    requires_browser = False
    async def get_info(self, url): return StoryInfo(title="High", author="", description="", slug="high")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class LowPrioritySource(BaseSource):
    base_urls = ["low.test"]
    priority = 90
    name = "low"
    requires_browser = False
    async def get_info(self, url): return StoryInfo(title="Low", author="", description="", slug="low")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class ConflictHighSource(BaseSource):
    base_urls = ["conflict.test"]
    priority = 10
    name = "conflict-high"
    requires_browser = False
    async def get_info(self, url): return StoryInfo(title="ConflictHigh", author="", description="", slug="ch")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class ConflictLowSource(BaseSource):
    base_urls = ["conflict.test"]
    priority = 90
    name = "conflict-low"
    requires_browser = False
    async def get_info(self, url): return StoryInfo(title="ConflictLow", author="", description="", slug="cl")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class ClientInjectSource(BaseSource):
    base_urls = ["clientinject.test"]
    priority = 50
    name = "client-inject"
    requires_browser = False
    def __init__(self, client=None):
        self.client = client
    async def get_info(self, url): return StoryInfo(title="CI", author="", description="", slug="ci")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class BrowserInjectSource(BaseSource):
    base_urls = ["browserinject.test"]
    priority = 50
    name = "browser-inject"
    requires_browser = True
    def __init__(self, client=None, browser=None):
        self.client = client
        self.browser = browser
    async def get_info(self, url): return StoryInfo(title="BI", author="", description="", slug="bi")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


class SlugSource(BaseSource):
    base_urls = ["slugsite.test"]
    priority = 50
    name = "slug-site"
    requires_browser = False
    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        return f"https://slugsite.test/truyen/{slug}"
    async def get_info(self, url): return StoryInfo(title="Slug", author="", description="", slug="slug")
    async def get_chapter_list(self, url): return []
    async def get_content(self, url): raise RuntimeError("not implemented")
    async def aclose(self): pass


def test_registry_register_and_get_by_url():
    reg = PluginRegistry()
    reg.register(HighPrioritySource)
    source = reg.get("https://high.test/truyen/abc")
    assert source is not None
    assert isinstance(source, HighPrioritySource)


def test_registry_get_returns_none_for_unknown_url():
    reg = PluginRegistry()
    reg.register(HighPrioritySource)
    assert reg.get("https://unknown.test/truyen/abc") is None


def test_registry_priority_sort():
    reg = PluginRegistry()
    reg.register(ConflictLowSource)
    reg.register(ConflictHighSource)
    source = reg.get("https://conflict.test/truyen/abc")
    assert isinstance(source, ConflictHighSource)


def test_registry_cache_when_no_deps():
    reg = PluginRegistry()
    reg.register(MinimalSource)
    src1 = reg.get("https://minimal.test/truyen/a")
    src2 = reg.get("https://minimal.test/truyen/b")
    assert src1 is src2


def test_registry_no_cache_with_external_client():
    reg = PluginRegistry()
    reg.register(ClientInjectSource)
    client = MagicMock(spec=httpx.AsyncClient)
    src1 = reg.get("https://clientinject.test/truyen/a", client=client)
    src2 = reg.get("https://clientinject.test/truyen/b", client=client)
    assert src1 is not src2


def test_registry_injects_client_via_inspect():
    reg = PluginRegistry()
    reg.register(ClientInjectSource)
    mock_client = MagicMock(spec=httpx.AsyncClient)
    source = reg.get("https://clientinject.test/truyen/abc", client=mock_client)
    assert source.client is mock_client


def test_registry_injects_browser_via_inspect():
    reg = PluginRegistry()
    reg.register(BrowserInjectSource)
    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_browser = MagicMock()
    source = reg.get("https://browserinject.test/truyen/abc", client=mock_client, browser=mock_browser)
    assert source.browser is mock_browser


def test_registry_slug_candidates():
    reg = PluginRegistry()
    reg.register(SlugSource)
    reg.register(MinimalSource)
    candidates = reg.slug_candidates("my-novel")
    assert len(candidates) == 1
    cls, url = candidates[0]
    assert cls is SlugSource
    assert url == "https://slugsite.test/truyen/my-novel"


def test_registry_clear_cache():
    reg = PluginRegistry()
    reg.register(MinimalSource)
    src1 = reg.get("https://minimal.test/truyen/a")
    reg.clear_cache()
    src2 = reg.get("https://minimal.test/truyen/a")
    assert src1 is not src2


def test_registry_discover_loads_valid_plugin(tmp_path):
    plugin_content = textwrap.dedent("""
        from vvr_scraper.sources import BaseSource, VolumeTreeItem
        from vvr_scraper.models import ContentItem, StoryInfo

        class DynamicSource(BaseSource):
            base_urls = ["dynamic.test"]
            priority = 80
            name = "dynamic"
            requires_browser = False
            async def get_info(self, url): return StoryInfo(title="Dynamic", author="", description="", slug="d")
            async def get_chapter_list(self, url): return []
            async def get_content(self, url): raise RuntimeError("not implemented")
            async def aclose(self): pass
    """).strip()
    plugin_file = tmp_path / "dynamic_source.py"
    plugin_file.write_text(plugin_content, encoding="utf-8")

    reg = PluginRegistry()
    reg.discover(tmp_path)
    source = reg.get("https://dynamic.test/truyen/abc")
    assert source is not None
    assert type(source).__name__ == "DynamicSource"


def test_registry_discover_skips_underscore_files(tmp_path):
    plugin_file = tmp_path / "_private.py"
    plugin_file.write_text("raise ImportError('should not be imported')", encoding="utf-8")
    reg = PluginRegistry()
    reg.discover(tmp_path)  # phải không raise


def test_registry_discover_soft_fails_on_import_error(tmp_path):
    plugin_file = tmp_path / "broken_plugin.py"
    plugin_file.write_text("import nonexistent_module_xyz_12345", encoding="utf-8")
    reg = PluginRegistry()
    reg.discover(tmp_path)  # phải không raise, chỉ log warning
