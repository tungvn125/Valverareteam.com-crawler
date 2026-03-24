"""
CLI interface and main logic for the web novel scraper.
"""
import argparse
import asyncio
import json
import os
import sys
from typing import List, Dict, Any, Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from simple_term_menu import TerminalMenu
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, ThreadedCompleter
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

from . import tao_so_do_cay
from .scraper_core import lay_thong_tin_truyen, scrape_chapters
from .exporter import (
    tao_file_epub, tao_file_pdf, tao_file_html, tao_file_md, tao_file_txt,
    ContentList, ChaptersData
)
from .utils import (
    sanitize_filename, create_folders_from_tree, normalize_vietnamese_url, 
    get_token_from_state, HEADERS, configure_logger
)
from .models import StoryInfo, ContentItem
from .session_manager import load_session, save_session, capture_session

SESSION_FILE = ".vvr_session.json"
BASE_URL = "https://valvrareteam.net"
console = Console()


class NovelCompleter(Completer):
    """Completer for live novel search using the Valvrare Team API."""
    def __init__(self, token: Optional[str] = None):
        self.token = token

    def get_completions(self, document, complete_event):
        text = document.text.strip()
        if len(text) < 3:
            return

        try:
            with httpx.Client(timeout=3.0) as client:
                headers = {
                    "User-Agent": HEADERS["User-Agent"],
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}/",
                    "Accept": "application/json, text/plain, */*"
                }
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"
                
                url = f"https://val-ssr-2kzit.ondigitalocean.app/api/novels/search?title={text}"
                response = client.get(url, headers=headers)
                
                if response.status_code == 200:
                    results = response.json()
                    for item in results:
                        title = item.get('title', '').strip()
                        author = item.get('author', 'Unknown')
                        _id = item.get('_id', '')
                        status = item.get('status', 'Unknown')
                        total = item.get('totalChapters', 0)
                        
                        if title and _id:
                            slug = normalize_vietnamese_url(title) + "-" + _id[-8:]
                            meta = f"{author} | {status} | {total} ch"
                            yield Completion(
                                slug, 
                                start_position=-len(document.text), 
                                display=title, 
                                display_meta=meta
                            )
        except Exception:
            pass


class InteractiveUI:
    """Handles all interactive terminal elements."""
    
    @staticmethod
    def show_menu(items: List[str], title: str, multi_select: bool = False) -> Any:
        menu = TerminalMenu(
            items, 
            title=f" {title} ", 
            menu_cursor_style=("fg_cyan", "bold"), 
            menu_highlight_style=("bg_cyan", "fg_black"),
            multi_select=multi_select,
            show_multi_select_hint=multi_select
        )
        return menu.show()

    @staticmethod
    async def get_novel_name_interactive(token: Optional[str] = None) -> str:
        console.print("[yellow]Nhập tên truyện hoặc tìm kiếm (tối thiểu 3 ký tự để hiện gợi ý)...[/yellow]")
        try:
            session = PromptSession()
            name = await session.prompt_async(
                "Tên truyện: ",
                completer=ThreadedCompleter(NovelCompleter(token=token)),
                complete_while_typing=True
            )
            return name.strip()
        except (KeyboardInterrupt, Exception) as e:
            if isinstance(e, KeyboardInterrupt): raise
            return input("Nhập tên truyện bạn muốn tải: ").strip()

    @staticmethod
    def display_story_summary(info: StoryInfo):
        table = Table(title="[bold cyan]Thông tin truyện[/bold cyan]", show_header=True, header_style="bold magenta", border_style="bright_blue")
        table.add_column("Trường", style="cyan", width=15)
        table.add_column("Giá trị", style="white")
        
        table.add_row("Tiêu đề", info.title)
        table.add_row("Tác giả", info.author)
        table.add_row("Thể loại", ", ".join(info.genres) if info.genres else "N/A")
        desc = info.description
        if len(desc) > 200: desc = desc[:197] + "..."
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
        
        # Configure logging
        configure_logger(self.args.verbose)

    def _parse_arguments(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Tải truyện từ Valvrare Team dưới dạng PDF, EPUB, và các định dạng khác.",
            formatter_class=argparse.RawTextHelpFormatter
        )
        parser.add_argument('ten_truyen', nargs='*', help="Tên truyện cần tải (slug). Hoặc dùng 'web' để mở giao diện.")
        parser.add_argument('-o', '--output', dest='output_folder', help="Thư mục đầu ra.")
        parser.add_argument('-f', '--format', nargs='+', default=['EPUB'], 
                           choices=['PDF', 'EPUB', 'HTML', 'MD', 'TXT'], help="Định dạng file.")
        parser.add_argument('-g', '--gop', default='rieng', choices=['rieng', 'volume', 'tatca'], 
                           help="Cách gộp file (rieng/volume/tatca).")
        parser.add_argument('--khong-minh-hoa', action='store_true', help="Bỏ qua minh họa.")
        parser.add_argument('--font', default='DejaVuSans', choices=['NotoSerif', 'DejaVuSans'], 
                           help="Font cho PDF.")
        parser.add_argument('-t', '--tasks', type=int, default=5, help="Số lượng tác vụ song song.")
        parser.add_argument('--login', action='store_true', help="Đăng nhập thủ công.")
        parser.add_argument('--refresh-session', action='store_true', help="Xóa session cũ.")
        parser.add_argument('--verbose', action='store_true', help="Hiển thị log chi tiết.")
        
        # Web-specific arguments (moved to top-level)
        parser.add_argument('--host', default='127.0.0.1', help='Host cho web server.')
        parser.add_argument('--port', type=int, default=8000, help='Port cho web server.')
        parser.add_argument('--workers', type=int, default=1, help='Số lượng novel tải song song (chế độ web).')
        parser.add_argument('--no-browser', action='store_true', help='Không tự động mở trình duyệt.')

        selection_group = parser.add_mutually_exclusive_group()
        selection_group.add_argument('--all', action='store_true', help="Tải tất cả.")
        selection_group.add_argument('--volumes', nargs='+', type=int, help="Tải các tập cụ thể.")
        selection_group.add_argument('--chapters', nargs='+', type=int, help="Tải các chương cụ thể.")
        
        return parser.parse_args()

    async def setup_session(self):
        """Handles session loading, login, and token extraction."""
        self.session_state = load_session(SESSION_FILE)
        
        if self.args.refresh_session and os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
            self.session_state = None

        if self.args.login or not self.session_state:
            do_login = self.args.login
            if not do_login and not self.is_cli_mode:
                choice = input("\nKhông tìm thấy session. Bạn có muốn đăng nhập không? (Y/n): ").strip().lower()
                do_login = not choice or choice in ['y', 'yes']
            
            if do_login:
                logger.info("Đang khởi tạo trình duyệt để lấy session...")
                self.session_state = await capture_session(f"{BASE_URL}/")
                save_session(self.session_state, SESSION_FILE)
                logger.success("Session đã được lưu.")

        self.token = get_token_from_state(self.session_state)
        if self.session_state and 'cookies' in self.session_state:
            for c in self.session_state['cookies']:
                self.cookies[c['name']] = c['value']

        if self.args.verbose:
            self._print_debug_info()

    def _print_debug_info(self):
        logger.debug(f"Số lượng cookies: {len(self.session_state.get('cookies', [])) if self.session_state else 0}")
        if self.token: logger.debug(f"Token (JWT): {self.token[:20]}...")
        logger.debug(f"Headers: {HEADERS['User-Agent']}")

    async def resolve_story_url(self, name_raw: str) -> Optional[str]:
        """Finds the story URL from sitemap."""
        normalized = normalize_vietnamese_url(name_raw)
        sitemap_url = f"{BASE_URL}/sitemap.xml"
        
        async with httpx.AsyncClient(headers=HEADERS, cookies=self.cookies) as client:
            try:
                response = await client.get(sitemap_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, "lxml-xml")
                for loc in soup.find_all("loc"):
                    url = loc.text
                    if normalized in url and "/chuong" not in url:
                        return url
            except Exception as e:
                logger.error(f"Lỗi khi truy cập sitemap: {e}")
        return None

    def filter_chapters(self, chapter_data: List[Dict]) -> List[Dict]:
        """Applies filters like excluding illustrations/empty volumes."""
        if self.is_cli_mode:
            skip_minh_hoa = self.args.khong_minh_hoa
        else:
            choice = input("Bạn có muốn bỏ qua minh họa và chương lỗi? (Y/n): ").strip().lower()
            skip_minh_hoa = not choice or choice in ["y", "yes"]

        if skip_minh_hoa:
            return [vol for vol in chapter_data if vol['chapters']]
        return chapter_data

    def select_chapters_to_download(self, chapter_data: List[Dict]) -> List[Dict]:
        """Handles chapter selection logic for both CLI and Interactive modes."""
        selected = []
        if self.is_cli_mode:
            if self.args.volumes:
                for idx in self.args.volumes:
                    if 0 < idx <= len(chapter_data):
                        selected.extend(chapter_data[idx-1]['chapters'])
            elif self.args.chapters:
                flat = [c for v in chapter_data for c in v['chapters']]
                for idx in self.args.chapters:
                    if 0 < idx <= len(flat):
                        selected.append(flat[idx-1])
            else: # All
                selected = [c for v in chapter_data for c in v['chapters']]
        else:
            menu_idx = InteractiveUI.show_menu(
                ["Tải xuống tất cả", "Chọn tập để tải", "Chọn chương để tải"],
                "Tùy chọn tải xuống"
            )
            if menu_idx == 0:
                selected = [c for v in chapter_data for c in v['chapters']]
            elif menu_idx == 1:
                vols = [v['volume'] for v in chapter_data]
                v_idxs = InteractiveUI.show_menu(vols, "Chọn tập", multi_select=True)
                if v_idxs:
                    for i in v_idxs: selected.extend(chapter_data[i]['chapters'])
            elif menu_idx == 2:
                all_chaps = [(f"{v['volume']}: {c['title']}", c) for v in chapter_data for c in v['chapters']]
                c_idxs = InteractiveUI.show_menu([i[0] for i in all_chaps], "Chọn chương", multi_select=True)
                if c_idxs:
                    for i in c_idxs: selected.append(all_chaps[i][1])
        return selected

    async def run(self):
        """Main execution flow."""
        # Handle 'web' command as a positional argument
        if self.args.ten_truyen and self.args.ten_truyen[0] == 'web':
            from .web import run_web_server
            import webbrowser
            
            url = f"http://{self.args.host}:{self.args.port}"
            if not self.args.no_browser:
                webbrowser.open(url)
            
            await run_web_server(host=self.args.host, port=self.args.port, num_workers=self.args.workers)
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
                    console.print(Panel(f"[bold cyan]Đang xử lý truyện {i+1}/{total}: {name}[/bold cyan]"))
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

    async def process_novel(self, name_raw: str):
        """Process a single novel download."""
        self.skipped_urls = []
        # 2. Resolve URL and Info
        story_url = await self.resolve_story_url(name_raw)
        if not story_url:
            logger.error(f"Không tìm thấy truyện '{name_raw}'.")
            return

        # Folder name is based on the slug from the URL
        relative_path = story_url.split(f"{BASE_URL}/")[-1]
        self.output_folder = self.args.output_folder or sanitize_filename(relative_path.split("/")[-1])
        os.makedirs(self.output_folder, exist_ok=True)

        async with httpx.AsyncClient(headers=HEADERS, cookies=self.cookies) as client:
            story_info = await lay_thong_tin_truyen(client, relative_path, verbose=self.args.verbose)
            if not self.is_cli_mode or self.args.verbose:
                InteractiveUI.display_story_summary(story_info)

        # 3. Load Chapter List
        logger.info(f"Đang lấy danh sách chương cho '{story_info.title}'...")
        await tao_so_do_cay.get_chapter_tree_list(story_url, output_file="chapter_list.json", session_state=self.session_state)
        with open("chapter_list.json", "r", encoding="utf-8") as f:
            chapter_data = json.load(f)

        # 4. Filter and Select
        chapter_data = self.filter_chapters(chapter_data)
        if not chapter_data: return
        
        selected_chaps = self.select_chapters_to_download(chapter_data)
        if not selected_chaps: return

        # 5. Export Config
        export_config = await self._get_export_config(story_url)
        
        # 6. Scrape
        urls = [f"{BASE_URL}{c['url']}" for c in selected_chaps]
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True
            ) as progress:
                scrape_task = progress.add_task(f"[green]Đang tải {len(urls)} chương...", total=len(urls))
                
                scraped = await scrape_chapters(
                    browser, urls, export_config['tasks'], 
                    skipped_urls=self.skipped_urls, 
                    session_state=self.session_state, 
                    verbose=self.args.verbose,
                    token=self.token
                )
                progress.update(scrape_task, completed=len(urls))
                
            await browser.close()

        # 7. Generate Files
        logger.info(f"Bắt đầu tạo file cho '{story_info.title}'...")
        await self._generate_files(chapter_data, selected_chaps, scraped, story_info, export_config)
        self._cleanup()

    async def _get_export_config(self, story_url: str) -> Dict:
        if self.is_cli_mode:
            gop_map = {'rieng': 1, 'volume': 2, 'tatca': 0}
            return {
                'mode_idx': gop_map[self.args.gop],
                'formats': [f.upper() for f in self.args.format],
                'font': self.args.font,
                'tasks': self.args.tasks
            }
        
        mode_idx = InteractiveUI.show_menu(
            ["Gộp tất cả (mặc định)", "Xuất riêng từng chương", "Gộp theo Volume"],
            "Chọn cách thức xuất file"
        )
        if mode_idx in [1, 2]:
            tree_path = os.path.join(self.output_folder, "tree_map.txt")
            await tao_so_do_cay.get_chapter_tree_folder(url=story_url, output_file=tree_path, cookies=self.cookies)
            create_folders_from_tree(tree_path, self.output_folder)

        format_items = ["PDF", "EPUB", "HTML", "Markdown (.md)", "Text (.txt)"]
        f_idxs = InteractiveUI.show_menu(format_items, "Chọn định dạng file", multi_select=True)
        if not f_idxs: return {}
        
        mapping = {"PDF": "PDF", "EPUB": "EPUB", "HTML": "HTML", "Markdown (.md)": "MD", "Text (.txt)": "TXT"}
        formats = [mapping[format_items[i]] for i in f_idxs]
        
        font = 'DejaVuSans'
        if "PDF" in formats:
            f_choice = input("Chọn font PDF (1. Noto Serif, 2. DejaVu Sans): ").strip()
            if f_choice == '1': font = 'NotoSerif'

        tasks_in = input("Số lượng tác vụ song song (mặc định 5): ")
        tasks = int(tasks_in) if tasks_in.isdigit() and int(tasks_in) > 0 else 5
        
        return {'mode_idx': mode_idx, 'formats': formats, 'font': font, 'tasks': tasks}

    async def _generate_files(self, chapter_data, selected_chaps, scraped, story_info, config):
        # Map URL to metadata
        url_to_vol = {c['url']: v['volume'] for v in chapter_data for c in v['chapters']}
        url_to_title = {f"{BASE_URL}{c['url']}": c['title'] for c in selected_chaps}
        
        mode = config['mode_idx']
        
        if mode == 1: # Rieng
            for url, content in scraped.items():
                rel_url = url.replace(BASE_URL, "")
                vol_name = url_to_vol.get(rel_url, "Unknown")
                folder = os.path.join(self.output_folder, sanitize_filename(vol_name))
                os.makedirs(folder, exist_ok=True)
                title = url_to_title.get(url, "Chapter")
                await self._write_to_formats(folder, title, content, story_info, config, [{'title': title, 'content': content}])

        elif mode == 2: # Volume
            vol_map = {}
            for url, content in scraped.items():
                v = url_to_vol.get(url.replace(BASE_URL, ""), "Unknown")
                if v not in vol_map: vol_map[v] = []
                vol_map[v].append({'title': url_to_title[url], 'content': content})
            
            for vol_name, chapters in vol_map.items():
                folder = os.path.join(self.output_folder, sanitize_filename(vol_name))
                os.makedirs(folder, exist_ok=True)
                full_content = [item for c in chapters for item in c['content']]
                await self._write_to_formats(folder, vol_name, full_content, story_info, config, chapters)

        else: # Tat ca
            full_structure = []
            full_flat = []
            for v_info in chapter_data:
                v_chaps = []
                for c_entry in v_info['chapters']:
                    f_url = f"{BASE_URL}{c_entry['url']}"
                    if f_url in scraped:
                        v_chaps.append({'title': c_entry['title'], 'content': scraped[f_url]})
                        full_flat.extend(scraped[f_url])
                if v_chaps:
                    full_structure.append({'volume': v_info['volume'], 'chapters': v_chaps})
            
            # Use real title for the filename
            await self._write_to_formats(self.output_folder, story_info.title, full_flat, story_info, config, full_structure)

    async def _write_to_formats(self, folder, title, content, info, config, structure):
        for fmt in config['formats']:
            fname = sanitize_filename(title)
            fpath = os.path.join(folder, f"{fname}.{fmt.lower()}")
            if fmt == "PDF": await tao_file_pdf(content, fpath, title, config['font'])
            elif fmt == "EPUB": await tao_file_epub(fpath, title, info.author, structure, info.description, info.cover_path, info.genres)
            elif fmt == "HTML": await tao_file_html(content, fpath, title)
            elif fmt == "MD": await tao_file_md(content, fpath, title)
            elif fmt == "TXT": await tao_file_txt(content, fpath, title)

    def _cleanup(self):
        logger.success("--- HOÀN TẤT ---")
        if self.skipped_urls:
            log_path = os.path.join(self.output_folder, "cac_chuong_da_bo_qua.txt")
            logger.warning(f"{len(self.skipped_urls)} chương bị lỗi. Xem tại: {log_path}")
            with open(log_path, "w", encoding="utf-8") as f:
                for url in self.skipped_urls: f.write(f"{url}\n")


def main():
    """Entry point for the CLI."""
    cli = ValvrareScraperCLI()
    try:
        asyncio.run(cli.run())
    except KeyboardInterrupt:
        console.print("\n[bold red]Chương trình bị dừng bởi người dùng.[/bold red]")
    finally:
        # Cleanup temporary files
        for temp_file in ["chapter_list.json", "cover.jpg"]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
        logger.info("Đã dọn dẹp file tạm. Hẹn gặp lại!")


if __name__ == "__main__":
    main()
