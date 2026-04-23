from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import importlib.util
import inspect
import logging
import os
from typing import Any, ClassVar

from ..models import ContentItem, StoryInfo


logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    author: str | None = None
    cover: str | None = None


@dataclass
class ChapterTreeItem:
    title: str
    url: str
    locked: bool = False


@dataclass
class VolumeTreeItem:
    volume: str
    chapters: list[ChapterTreeItem] = field(default_factory=list)


class BaseSource(ABC):
    # --- Class-level declarations ---
    base_urls: ClassVar[list[str]] = []
    priority: ClassVar[int] = 100
    name: ClassVar[str] = ""
    requires_browser: ClassVar[bool] = False

    @abstractmethod
    async def get_info(self, url: str) -> StoryInfo:
        """Get novel info (title, author, cover, etc)."""
        ...

    @abstractmethod
    async def get_chapter_list(self, url: str) -> list[VolumeTreeItem]:
        """Get chapter list with volume structure.

        Returns list of VolumeTreeItem, each containing a volume name
        and list of ChapterTreeItem. For flat sources without volumes,
        return a single VolumeTreeItem with volume="Volume 1".
        """
        ...

    @abstractmethod
    async def get_content(self, chapter_url: str) -> list[ContentItem]:
        """Get chapter content."""
        ...

    @abstractmethod
    async def aclose(self) -> None:
        """Close owned resources (e.g. HTTP clients)."""
        ...

    # --- Optional hooks: có default implementation ---
    async def search(self, query: str) -> list[SearchResult]:
        """Search for novels by query. Optional — default returns empty list."""
        return []

    async def fetch_cover(self, cover_url: str) -> bytes | None:
        """Download cover image bytes. Default: GET via self.client if available."""
        if not cover_url or not getattr(self, "client", None):
            return None
        try:
            r = await self.client.get(cover_url, timeout=30.0)
            r.raise_for_status()
            return r.content
        except Exception:
            return None

    @classmethod
    def slug_to_url(cls, slug: str) -> str | None:
        """Build candidate URL from slug. Default: None."""
        return None

    def matches(self, url: str) -> bool:
        """Check if this source can handle the given URL."""
        return any(base in url for base in self.base_urls)


class PluginRegistry:
    """Central registry for all BaseSource subclasses.

    - register(cls): đăng ký một source class
    - get(url, client=None, browser=None): tìm + instantiate source phù hợp nhất
    - slug_candidates(slug): lấy list (cls, candidate_url) từ các source có slug_to_url()
    - discover(path): load plugin .py files từ thư mục ngoài
    - clear_cache(): xóa instance cache
    """

    def __init__(self) -> None:
        self._classes: list[type[BaseSource]] = []
        self._cache: dict[str, BaseSource] = {}

    def register(self, cls: type[BaseSource]) -> None:
        """Đăng ký một source class (idempotent)."""
        if cls not in self._classes:
            self._classes.append(cls)
            # Sort by priority ascending (lower number = higher priority)
            self._classes.sort(key=lambda c: c.priority)

    def get(
        self,
        url: str,
        client=None,
        browser=None,
    ) -> BaseSource | None:
        """Tìm source phù hợp với URL và instantiate.

        - Nếu không có client/browser inject: cache instance theo class name
        - Nếu có inject: tạo instance mới mỗi lần (không cache)
        """
        for cls in self._classes:
            # Dùng base_urls trực tiếp để tránh tạo instance thừa
            if any(base in url for base in cls.base_urls):
                has_inject = client is not None or browser is not None

                if not has_inject:
                    # Cache by class name
                    cache_key = cls.name or cls.__name__
                    if cache_key not in self._cache:
                        self._cache[cache_key] = self._instantiate(cls)
                    return self._cache[cache_key]

                return self._instantiate(cls, client=client, browser=browser)

        return None

    def _instantiate(self, cls: type[BaseSource], client=None, browser=None) -> BaseSource:
        """Instantiate source với dependency injection qua inspect.signature()."""
        sig = inspect.signature(cls.__init__)
        params = sig.parameters

        kwargs: dict[str, Any] = {}
        if "client" in params and client is not None:
            kwargs["client"] = client
        if "browser" in params and browser is not None:
            kwargs["browser"] = browser

        return cls(**kwargs)

    def slug_candidates(self, slug: str) -> list[tuple[type[BaseSource], str]]:
        """Gọi slug_to_url() trên mỗi registered source.

        Returns list of (cls, candidate_url) cho những source có slug_to_url() != None.
        """
        result: list[tuple[type[BaseSource], str]] = []
        for cls in self._classes:
            url = cls.slug_to_url(slug)
            if url is not None:
                result.append((cls, url))
        return result

    def clear_cache(self) -> None:
        """Xóa instance cache."""
        self._cache.clear()

    def discover(self, path) -> None:
        """Load và register source classes từ .py files trong thư mục path.

        Rules:
        - Bỏ qua files bắt đầu bằng _
        - Soft-fail (log WARNING) nếu import error
        - Chỉ register classes là subclass của BaseSource (không phải BaseSource chính)
        - Skip nếu file không thuộc sở hữu current user (security)
        """
        from pathlib import Path

        plugin_dir = Path(path)
        if not plugin_dir.exists():
            return

        current_uid = os.getuid()

        for plugin_file in sorted(plugin_dir.glob("*.py")):
            if plugin_file.name.startswith("_"):
                continue

            # Security: skip files not owned by current user
            try:
                file_stat = plugin_file.stat()
                if file_stat.st_uid != current_uid:
                    logger.warning(f"Plugin skipped (not owned by current user): {plugin_file}")
                    continue
            except OSError:
                continue

            try:
                spec = importlib.util.spec_from_file_location(
                    f"vvr_plugin_{plugin_file.stem}", plugin_file
                )
                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseSource)
                        and attr is not BaseSource
                    ):
                        self.register(attr)
                        logger.info(f"Loaded plugin source: {attr.__name__} from {plugin_file}")
            except Exception as e:
                logger.warning(f"Plugin load failed for {plugin_file}: {e}")


# Global singleton registry
REGISTRY = PluginRegistry()


# Backward-compatible cache alias used by existing tests/callers
_SOURCE_CACHE = REGISTRY._cache


def _bootstrap() -> None:
    """Register built-in sources và discover external plugins."""
    from pathlib import Path

    # 1. Built-in sources
    from .lnhako import LnHakoSource
    from .truyenfull import TruyenFullSource

    REGISTRY.register(TruyenFullSource)  # priority=50
    REGISTRY.register(LnHakoSource)  # priority=50

    # 2. External plugins từ ~/.config/vvr-scraper/plugins/
    default_plugin_dir = Path.home() / ".config" / "vvr-scraper" / "plugins"
    REGISTRY.discover(default_plugin_dir)

    # 3. Extra paths từ VVR_PLUGIN_PATHS env (colon-separated)
    extra_paths = os.environ.get("VVR_PLUGIN_PATHS", "")
    for p in extra_paths.split(":"):
        p = p.strip()
        if p:
            REGISTRY.discover(Path(p))


def get_source(url: str, client: Any | None = None, browser: Any | None = None) -> BaseSource | None:
    """Factory function to get the correct source instance for a URL."""
    return REGISTRY.get(url, client=client, browser=browser)


_bootstrap()
