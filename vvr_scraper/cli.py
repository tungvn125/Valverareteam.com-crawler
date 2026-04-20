"""
CLI interface and main logic for the web novel scraper.
"""

import argparse
import asyncio
import glob
import json
import os
import sys
from typing import Any

import httpx
from loguru import logger
from playwright.async_api import async_playwright
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table
from simple_term_menu import TerminalMenu

from . import tao_so_do_cay
from .db import DatabaseManager
from .exporter import (
    tao_file_audiodrama,
    tao_file_epub,
    tao_file_html,
    tao_file_md,
    tao_file_mp3,
    tao_file_mp4,
    tao_file_pdf,
    tao_file_txt,
)
from .models import StoryInfo
from .scraper_core import lay_thong_tin_truyen, scrape_chapters
from .session_manager import capture_session, load_session, save_session
from .utils import (
    BASE_URL,
    HEADERS,
    configure_logger,
    get_config_path,
    get_token_from_state,
    normalize_vietnamese_url,
    resolve_playwright_headless,
    resolve_story_url,
    sanitize_filename,
)

SESSION_FILE = ".vvr_session.json"
console = Console()


class NovelCompleter(Completer):
    """Completer for live novel search using the Valvrare Team API."""

    def __init__(self, token: str | None = None):
        self.token = token
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=3.0)
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def get_completions(self, document, complete_event):
        text = document.text.strip()
        if len(text) < 3:
            return

        try:
            headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/",
                "Accept": "application/json, text/plain, */*",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

            response = self.client.get(
                "https://val-ssr-2kzit.ondigitalocean.app/api/novels/search", params={"title": text}, headers=headers
            )

            if response.status_code == 200:
                results = response.json()
                for item in results:
                    title = item.get("title", "").strip()
                    author = item.get("author", "Unknown")
                    _id = item.get("_id", "")
                    status = item.get("status", "Unknown")
                    total = item.get("totalChapters", 0)

                    if title and _id:
                        slug = normalize_vietnamese_url(title) + "-" + _id[-8:]
                        meta = f"{author} | {status} | {total} ch"
                        yield Completion(slug, start_position=-len(document.text), display=title, display_meta=meta)
        except Exception:  # noqa: S110  — autocomplete failure is non-critical
            pass


class InteractiveUI:
    """Handles all interactive terminal elements."""

    @staticmethod
    def show_menu(items: list[str], title: str, multi_select: bool = False) -> Any:
        menu = TerminalMenu(
            items,
            title=f" {title} ",
            menu_cursor_style=("fg_cyan", "bold"),
            menu_highlight_style=("bg_cyan", "fg_black"),
            multi_select=multi_select,
            show_multi_select_hint=multi_select,
        )
        return menu.show()

    @staticmethod
    async def get_novel_name_interactive(token: str | None = None) -> str:
        console.print("[yellow]Nhập tên truyện hoặc tìm kiếm (tối thiểu 3 ký tự để hiện gợi ý)...[/yellow]")
        completer = NovelCompleter(token=token)
        try:
            session = PromptSession()
            name = await session.prompt_async(
                "Tên truyện: ", completer=ThreadedCompleter(completer), complete_while_typing=True
            )
            return name.strip()
        except (KeyboardInterrupt, Exception) as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            return ""
        finally:
            completer.close()

    @staticmethod
    def display_story_summary(info: StoryInfo):
        table = Table(
            title="[bold cyan]Thông tin truyện[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
            border_style="bright_blue",
        )
        table.add_column("Trường", style="cyan", width=15)
        table.add_column("Giá trị", style="white")

        table.add_row("Tiêu đề", info.title)
        table.add_row("Tác giả", info.author)
        table.add_row("Thể loại", ", ".join(info.genres) if info.genres else "N/A")
        desc = info.description
        if len(desc) > 200:
            desc = desc[:197] + "..."
        table.add_row("Mô tả", desc)

        console.print(table)


class ValvrareScraperCLI:
    """Main Orchestrator for the Valvrare Team Scraper CLI."""

    def __init__(self):
        self.args = self._parse_arguments()
        self.is_cli_mode = len(sys.argv) > 1
        self.session_state = None
        self.cookies = {}
        self.token = None
        self.skipped_urls = []
        self.output_folder = ""
        self.db_manager = DatabaseManager(db_path=get_config_path("vvr_library.db"))

        # Configure logging
        configure_logger(self.args.verbose)

    def _parse_arguments(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Tải truyện từ Valvrare Team dưới dạng PDF, EPUB, và các định dạng khác.",
            formatter_class=argparse.RawTextHelpFormatter,
        )
        parser.add_argument(
            "ten_truyen",
            nargs="*",
            help="Tên truyện cần tải (slug). Hoặc dùng 'web' để mở giao diện, 'run <file>' để chạy manifest.",
        )
        parser.add_argument("-o", "--output", dest="output_folder", help="Thư mục đầu ra.")
        parser.add_argument(
            "-f",
            "--format",
            nargs="+",
            default=["EPUB"],
            choices=["PDF", "EPUB", "HTML", "MD", "TXT", "MP3", "AD-MP3", "MP4"],
            help="Định dạng file.",
        )
        parser.add_argument(
            "-g",
            "--gop",
            default="rieng",
            choices=["rieng", "volume", "tatca"],
            help="Cách gộp file (rieng/volume/tatca).",
        )
        parser.add_argument("--khong-minh-hoa", action="store_true", help="Bỏ qua minh họa.")
        parser.add_argument("--font", default="DejaVuSans", choices=["NotoSerif", "DejaVuSans"], help="Font cho PDF.")
        parser.add_argument("-t", "--tasks", type=int, default=5, help="Số lượng tác vụ song song.")
        parser.add_argument(
            "--fps", type=int, default=30, choices=[30, 60], help="Số khung hình trên giây cho video (30/60)."
        )
        parser.add_argument(
            "--render-format",
            default="landscape",
            choices=["landscape", "portrait"],
            help="Định dạng render video (landscape/portrait).",
        )
        parser.add_argument(
            "--tts-provider",
            default=None,
            help="TTS backend. Built-in: elevenlabs, omnivoice, openai_tts. Custom providers also supported. Default: auto-detect.",
        )
        parser.add_argument("--login", action="store_true", help="Đăng nhập thủ công.")
        parser.add_argument("--refresh-session", action="store_true", help="Xóa session cũ.")
        parser.add_argument("--verbose", action="store_true", help="Hiển thị log chi tiết.")

        # Web-specific arguments (moved to top-level)
        parser.add_argument("--host", default="127.0.0.1", help="Host cho web server.")
        parser.add_argument("--port", type=int, default=8000, help="Port cho web server.")
        parser.add_argument("--workers", type=int, default=1, help="Số lượng novel tải song song (chế độ web).")
        parser.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt.")

        parser.add_argument("--username", help="Username for social admin bootstrap.")
        parser.add_argument("--password", help="Password for social admin bootstrap.")
        parser.add_argument("--display-name", help="Display name for social admin bootstrap.")

        playwright_group = parser.add_mutually_exclusive_group()
        playwright_group.add_argument(
            "--head-playwright", action="store_true", help="Chạy Playwright ở chế độ có giao diện."
        )
        playwright_group.add_argument(
            "--headless-playwright", action="store_true", help="Buộc Playwright chạy headless."
        )

        selection_group = parser.add_mutually_exclusive_group()
        selection_group.add_argument("--all", action="store_true", help="Tải tất cả.")
        selection_group.add_argument("--volumes", nargs="+", type=int, help="Tải các tập cụ thể.")
        selection_group.add_argument("--chapters", nargs="+", type=int, help="Tải các chương cụ thể.")

        return parser.parse_args()

    async def setup_session(self):
        """Handles session loading, login, and token extraction."""
        # Initialize DB
        await self.db_manager.init_db()

        # Check API Key for Audio Drama
        formats = self.args.format
        if "AD-MP3" in formats:
            if not os.getenv("VVR_API_KEY") or not os.getenv("VVR_BASE_URL"):
                logger.warning(
                    "VVR_API_KEY or VVR_BASE_URL not found. Audio Drama generation might fail or fallback to simple MP3."
                )

        session_path = get_config_path(SESSION_FILE)
        self.session_state = load_session(session_path)

        if self.args.refresh_session and os.path.exists(session_path):
            os.remove(session_path)
            self.session_state = None

        if self.args.login or not self.session_state:
            do_login = self.args.login
            if not do_login and not self.is_cli_mode:
                choice = input("\nKhông tìm thấy session. Bạn có muốn đăng nhập không? (Y/n): ").strip().lower()
                do_login = not choice or choice in ["y", "yes"]

            if do_login:
                logger.info("Đang khởi tạo trình duyệt để lấy session...")
                self.session_state = await capture_session(f"{BASE_URL}/")
                save_session(self.session_state, session_path)
                logger.success("Session đã được lưu.")

        self.token = get_token_from_state(self.session_state)
        if self.session_state and "cookies" in self.session_state:
            for c in self.session_state["cookies"]:
                self.cookies[c["name"]] = c["value"]

        if self.args.verbose:
            self._print_debug_info()

    def _print_debug_info(self):
        logger.debug(f"Số lượng cookies: {len(self.session_state.get('cookies', [])) if self.session_state else 0}")
        if self.token:
            logger.debug(f"Token (JWT): {self.token[:20]}...")
        logger.debug(f"Headers: {HEADERS['User-Agent']}")

    def filter_chapters(self, chapter_data: list[dict]) -> list[dict]:
        """Applies filters like excluding illustrations/empty volumes."""
        if self.is_cli_mode:
            skip_minh_hoa = self.args.khong_minh_hoa
        else:
            choice = input("Bạn có muốn bỏ qua minh họa và chương lỗi? (Y/n): ").strip().lower()
            skip_minh_hoa = not choice or choice in ["y", "yes"]

        if skip_minh_hoa:
            for vol in chapter_data:
                vol["chapters"] = [c for c in vol["chapters"] if "Minh họa" not in c["title"]]
            return [vol for vol in chapter_data if vol["chapters"]]
        return chapter_data

    def select_chapters_to_download(self, chapter_data: list[dict]) -> list[dict]:
        """Handles chapter selection logic for both CLI and Interactive modes."""
        selected = []
        if self.is_cli_mode:
            if self.args.volumes:
                for idx in self.args.volumes:
                    if 0 < idx <= len(chapter_data):
                        selected.extend(chapter_data[idx - 1]["chapters"])
            elif self.args.chapters:
                flat = [c for v in chapter_data for c in v["chapters"]]
                for idx in self.args.chapters:
                    if 0 < idx <= len(flat):
                        selected.append(flat[idx - 1])
            else:  # All
                selected = [c for v in chapter_data for c in v["chapters"]]
        else:
            menu_idx = InteractiveUI.show_menu(
                ["Tải xuống tất cả", "Chọn tập để tải", "Chọn chương để tải"], "Tùy chọn tải xuống"
            )
            if menu_idx == 0:
                selected = [c for v in chapter_data for c in v["chapters"]]
            elif menu_idx == 1:
                vols = [v["volume"] for v in chapter_data]
                v_idxs = InteractiveUI.show_menu(vols, "Chọn tập", multi_select=True)
                if v_idxs:
                    for i in v_idxs:
                        selected.extend(chapter_data[i]["chapters"])
            elif menu_idx == 2:
                all_chaps = [(f"{v['volume']}: {c['title']}", c) for v in chapter_data for c in v["chapters"]]
                c_idxs = InteractiveUI.show_menu([i[0] for i in all_chaps], "Chọn chương", multi_select=True)
                if c_idxs:
                    for i in c_idxs:
                        selected.append(all_chaps[i][1])
        return selected

    def _cli_playwright_mode(self) -> str | None:
        if self.args.head_playwright:
            return "head"
        if self.args.headless_playwright:
            return "headless"
        return None

    async def run(self):
        """Main execution flow."""
        # Handle 'social create-admin' command
        if self.args.ten_truyen and len(self.args.ten_truyen) >= 2 and self.args.ten_truyen[:2] == ["social", "create-admin"]:
            from .social.auth import hash_password
            from .social.db import SocialDatabaseManager

            social_db = SocialDatabaseManager(db_path=get_config_path("social.db"))
            await social_db.init_db()
            user = await social_db.create_admin_user(
                username=self.args.username,
                hashed_password=hash_password(self.args.password),
                display_name=self.args.display_name or self.args.username,
            )
            console.print(f"Created admin user: {user['username']}")
            await social_db.close()
            return

        # Handle 'run' command
        if self.args.ten_truyen and self.args.ten_truyen[0] == "run":
            if len(self.args.ten_truyen) < 2:
                logger.error("Vui lòng cung cấp đường dẫn đến file manifest JSON.")
                return
            from .job_runner import run_manifest

            await run_manifest(self.args.ten_truyen[1], playwright_mode=self._cli_playwright_mode())
            return

        # Handle 'freesound-login' command
        if self.args.ten_truyen and self.args.ten_truyen[0] == "freesound-login":
            from .freesound_manager import FreesoundManager

            try:
                fs = FreesoundManager()
                auth_url = fs.get_auth_url()
                console.print(f"[bold cyan]Mở trình duyệt và đăng nhập tại:[/bold cyan]\n{auth_url}")

                code = input("\nDán mã xác thực (code) tại đây: ").strip()

                if code:
                    with console.status("[bold green]Đang xác thực với Freesound...[/bold green]"):
                        await fs.exchange_code(code)
                    console.print("[bold green]Đăng nhập Freesound thành công![/bold green]")
                else:
                    console.print("[bold yellow]Hủy đăng nhập do không có mã xác thực.[/bold yellow]")
            except ValueError as ve:
                logger.error(f"Lỗi cấu hình Freesound: {ve}")
                logger.info("Hãy đảm bảo FREESOUND_CLIENT_ID và FREESOUND_CLIENT_SECRET đã được thiết lập.")
            except Exception as e:
                logger.error(f"Lỗi khi đăng nhập Freesound: {e}")
            return

        # Handle 'web' command as a positional argument
        if self.args.ten_truyen and self.args.ten_truyen[0] == "web":
            import webbrowser

            from .web import run_web_server

            url = f"http://{self.args.host}:{self.args.port}"
            if not self.args.no_browser:
                webbrowser.open(url)

            await run_web_server(
                host=self.args.host,
                port=self.args.port,
                num_workers=self.args.workers,
                playwright_mode=self._cli_playwright_mode(),
            )
            return

        await self.setup_session()

        # 1. Get Novel Names
        if self.is_cli_mode:
            names_raw = self.args.ten_truyen
            if not names_raw:
                # Should not happen if is_cli_mode is correctly handled
                # but if user passed other flags but no slug?
                logger.error("Tên truyện là bắt buộc ở chế độ CLI.")
                return

            total = len(names_raw)
            for i, name in enumerate(names_raw):
                if total > 1:
                    console.print(Panel(f"[bold cyan]Đang xử lý truyện {i + 1}/{total}: {name}[/bold cyan]"))
                try:
                    await self.process_novel(name)
                except Exception as e:
                    logger.error(f"Lỗi khi xử lý '{name}': {e}")
                    if self.args.verbose:
                        import traceback

                        logger.error(traceback.format_exc())
        else:
            name_raw = await InteractiveUI.get_novel_name_interactive(self.token)
            if name_raw:
                await self.process_novel(name_raw)

        # Ensure DB is closed
        await self.db_manager.close()

    async def process_novel(self, name_raw: str):
        """Process a single novel download."""
        self.skipped_urls = []
        # 2. Resolve URL and Info
        story_url = await resolve_story_url(name_raw, cookies=self.cookies)
        if not story_url:
            logger.error(f"Không tìm thấy truyện '{name_raw}'.")
            return

        # Folder name is based on the slug from the URL
        relative_path = story_url.rstrip("/").split(f"{BASE_URL}/")[-1]
        self.output_folder = self.args.output_folder or sanitize_filename(relative_path.split("/")[-1])
        os.makedirs(self.output_folder, exist_ok=True)

        async with httpx.AsyncClient(headers=HEADERS, cookies=self.cookies) as client:
            story_info = await lay_thong_tin_truyen(client, relative_path, verbose=self.args.verbose)
            if not self.is_cli_mode or self.args.verbose:
                InteractiveUI.display_story_summary(story_info)

        # Open browser early to share between chapter tree and scraping
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=resolve_playwright_headless(cli_mode=self._cli_playwright_mode())
            )
            try:
                # 3. Load Chapter List (using shared browser)
                logger.info(f"Đang lấy danh sách chương cho '{story_info.title}'...")
                chapter_data = await tao_so_do_cay.get_chapter_tree_list(
                    story_url, output_file="chapter_list.json", session_state=self.session_state, browser=browser
                )
                if not chapter_data:
                    if os.path.exists("chapter_list.json"):
                        with open("chapter_list.json", encoding="utf-8") as f:
                            chapter_data = json.load(f)
                    else:
                        logger.error("Không thể lấy danh sách chương.")
                        return

                # 4. Filter and Select
                chapter_data = self.filter_chapters(chapter_data)
                if not chapter_data:
                    return

                selected_chaps = self.select_chapters_to_download(chapter_data)
                if not selected_chaps:
                    return

                # 5. Export Config
                export_config = await self._get_export_config(story_url)

                # 6. Scrape with live progress
                urls = [c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}" for c in selected_chaps]

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                    transient=True,
                ) as progress:
                    scrape_task = progress.add_task(f"[green]Đang tải {len(urls)} chương...", total=len(urls))

                    async def on_chapter_done(url, content, idx, total):
                        progress.update(scrape_task, advance=1)

                    scraped = await scrape_chapters(
                        browser,
                        urls,
                        export_config["tasks"],
                        skipped_urls=self.skipped_urls,
                        session_state=self.session_state,
                        verbose=self.args.verbose,
                        token=self.token,
                        on_chapter_done=on_chapter_done,
                    )
            finally:
                await browser.close()

        # Check failure rate — abort if too many chapters failed
        failed_count = len(urls) - len(scraped)
        failure_rate = failed_count / len(urls) if urls else 0
        if failure_rate > 0.3:
            logger.error(
                f"Quá nhiều chương tải thất bại: {failed_count}/{len(urls)} ({failure_rate:.0%}). Hủy xuất file."
            )
            return

        # 7. Generate Files
        logger.info(f"Bắt đầu tạo file cho '{story_info.title}'...")
        await self._generate_files(chapter_data, selected_chaps, scraped, story_info, export_config)

        # Clean up temp cover file
        if story_info.cover_path and os.path.exists(story_info.cover_path):
            try:
                os.remove(story_info.cover_path)
            except OSError:
                pass
        self._cleanup()

    async def _get_export_config(self, story_url: str) -> dict:
        if self.is_cli_mode:
            gop_map = {"rieng": 1, "volume": 2, "tatca": 0}
            return {
                "mode_idx": gop_map[self.args.gop],
                "formats": [f.upper() for f in self.args.format],
                "font": self.args.font,
                "tasks": self.args.tasks,
                "fps": self.args.fps,
                "render_format": self.args.render_format,
            }

        mode_idx = InteractiveUI.show_menu(
            ["Gộp tất cả (mặc định)", "Xuất riêng từng chương", "Gộp theo Volume"], "Chọn cách thức xuất file"
        )
        if mode_idx is None:
            mode_idx = 0

        format_items = [
            "PDF",
            "EPUB",
            "HTML",
            "Markdown (.md)",
            "Text (.txt)",
            "MP3 (Audiobook)",
            "MP3 (Audio Drama - AI Script)",
            "MP4 (Cinematic Video)",
        ]
        f_idxs = InteractiveUI.show_menu(format_items, "Chọn định dạng file", multi_select=True)
        if not f_idxs:
            return {}

        mapping = {
            "PDF": "PDF",
            "EPUB": "EPUB",
            "HTML": "HTML",
            "Markdown (.md)": "MD",
            "Text (.txt)": "TXT",
            "MP3 (Audiobook)": "MP3",
            "MP3 (Audio Drama - AI Script)": "AD-MP3",
            "MP4 (Cinematic Video)": "MP4",
        }
        formats = [mapping[format_items[i]] for i in f_idxs]

        font = "DejaVuSans"
        if "PDF" in formats:
            f_choice = input("Chọn font PDF (1. Noto Serif, 2. DejaVu Sans): ").strip()
            if f_choice == "1":
                font = "NotoSerif"

        tasks_in = input("Số lượng tác vụ song song (mặc định 5): ")
        tasks = int(tasks_in) if tasks_in.isdigit() and int(tasks_in) > 0 else 5

        fps = self.args.fps
        render_format = self.args.render_format

        if "MP4" in formats:
            # Chọn tỷ lệ khung hình
            ratio_idx = InteractiveUI.show_menu(["16:9 (Landscape)", "9:16 (Portrait)"], "Chọn tỷ lệ khung hình video")
            render_format = "landscape" if ratio_idx == 0 else "portrait"

            # Chọn FPS
            fps_idx = InteractiveUI.show_menu(["30 FPS", "60 FPS"], "Chọn số khung hình trên giây (FPS)")
            fps = 30 if fps_idx == 0 else 60

        return {
            "mode_idx": mode_idx,
            "formats": formats,
            "font": font,
            "tasks": tasks,
            "fps": fps,
            "render_format": render_format,
        }

    async def _generate_files(self, chapter_data, selected_chaps, scraped, story_info, config):
        # Map URL to metadata
        url_to_vol = {c["url"]: v["volume"] for v in chapter_data for c in v["chapters"]}
        url_to_title = {
            (c["url"] if c["url"].startswith("http") else f"{BASE_URL}{c['url']}"): c["title"] for c in selected_chaps
        }

        mode = config["mode_idx"]

        if mode == 1:  # Rieng
            for url, content in scraped.items():
                lookup_url = url.replace(BASE_URL, "") if url.startswith(BASE_URL) else url
                vol_name = url_to_vol.get(lookup_url, "Unknown")
                folder = os.path.join(self.output_folder, sanitize_filename(vol_name))
                os.makedirs(folder, exist_ok=True)
                title = url_to_title.get(url, "Chapter")
                await self._write_to_formats(
                    folder, title, content, story_info, config, [{"title": title, "content": content}]
                )

        elif mode == 2:  # Volume
            vol_map = {}
            for url, content in scraped.items():
                lookup_url = url.replace(BASE_URL, "") if url.startswith(BASE_URL) else url
                v = url_to_vol.get(lookup_url, "Unknown")
                if v not in vol_map:
                    vol_map[v] = []
                vol_map[v].append({"title": url_to_title[url], "content": content})

            for vol_name, chapters in vol_map.items():
                folder = os.path.join(self.output_folder, sanitize_filename(vol_name))
                os.makedirs(folder, exist_ok=True)
                full_content = [item for c in chapters for item in c["content"]]
                await self._write_to_formats(folder, vol_name, full_content, story_info, config, chapters)

        else:  # Tat ca
            full_structure = []
            full_flat = []
            for v_info in chapter_data:
                v_chaps = []
                for c_entry in v_info["chapters"]:
                    f_url = c_entry["url"] if c_entry["url"].startswith("http") else f"{BASE_URL}{c_entry['url']}"
                    if f_url in scraped:
                        v_chaps.append({"title": c_entry["title"], "content": scraped[f_url]})
                        full_flat.extend(scraped[f_url])
                if v_chaps:
                    full_structure.append({"volume": v_info["volume"], "chapters": v_chaps})

            # Use real title for the filename
            await self._write_to_formats(
                self.output_folder, story_info.title, full_flat, story_info, config, full_structure
            )

    async def _write_to_formats(self, folder, title, content, info, config, structure):
        for fmt in config["formats"]:
            ext = fmt.lower()
            if ext == "ad-mp3":
                ext = "ad.mp3"
            fname = sanitize_filename(title)
            fpath = os.path.join(folder, f"{fname}.{ext}")
            if fmt == "PDF":
                await tao_file_pdf(content, fpath, title, config["font"])
            elif fmt == "EPUB":
                await tao_file_epub(
                    fpath, title, info.author, structure, info.description, info.cover_path, info.genres
                )
            elif fmt == "HTML":
                await tao_file_html(content, fpath, title)
            elif fmt == "MD":
                await tao_file_md(content, fpath, title)
            elif fmt == "TXT":
                await tao_file_txt(content, fpath, title)
            elif fmt == "MP3":
                await tao_file_mp3(content, fpath, title)
            elif fmt == "AD-MP3":
                if not os.getenv("VVR_API_KEY") or not os.getenv("VVR_BASE_URL"):
                    logger.warning(
                        "VVR_API_KEY or VVR_BASE_URL not found. Audio Drama generation might fail or fallback."
                    )

                await tao_file_audiodrama(
                    content_list=content,
                    filename=fpath,
                    story_id=info.slug,
                    db_manager=self.db_manager,
                    title=title,
                    tts_provider_name=self.args.tts_provider,
                )
            elif fmt == "MP4":
                # Check for API Key as video needs Audio Drama
                if not os.getenv("VVR_API_KEY") or not os.getenv("VVR_BASE_URL"):
                    logger.warning("VVR_API_KEY or VVR_BASE_URL not found. Video render might fail.")

                await tao_file_mp4(
                    content_list=content,
                    filename=fpath,
                    story_id=info.slug,
                    db_manager=self.db_manager,
                    title=title,
                    fps=config.get("fps", 30),
                    render_format=config.get("render_format", "landscape"),
                )

    def _cleanup(self):
        logger.success("--- HOÀN TẤT ---")
        if self.skipped_urls:
            log_path = os.path.join(self.output_folder, "cac_chuong_da_bo_qua.txt")
            logger.warning(f"{len(self.skipped_urls)} chương bị lỗi. Xem tại: {log_path}")
            with open(log_path, "w", encoding="utf-8") as f:
                for url in self.skipped_urls:
                    f.write(f"{url}\n")


def main():
    """Entry point for the CLI."""
    cli = ValvrareScraperCLI()
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        console.print("\n[bold red]Chương trình bị dừng bởi người dùng.[/bold red]")
    finally:
        # Cleanup temporary files
        for temp_file in glob.glob("chapters_*.json") + ["chapter_list.json"]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass  # noqa: S110  — best-effort cleanup of temp files

        # Close DB connection
        try:
            # We need an event loop to call async close()
            # but main() is calling asyncio.run(cli.run())
            # Let's add a close method to the CLI and call it within run() or at the end of run()
            pass
        except Exception:  # noqa: S110  — final cleanup, nothing to do
            pass
        logger.info("Đã dọn dẹp file tạm. Hẹn gặp lại!")


if __name__ == "__main__":
    main()
