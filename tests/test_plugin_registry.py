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
