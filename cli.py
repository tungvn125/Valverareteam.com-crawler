"""
CLI interface and main logic for the web novel scraper.
"""
import argparse
import asyncio
import json
import os
import sys
from typing import List, Dict, Any, Optional

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from simple_term_menu import TerminalMenu

import tao_so_do_cay
from scraper_core import lay_thong_tin_truyen, scrape_chapters
from exporter import (
    tao_file_epub, tao_file_pdf, tao_file_html, tao_file_md, tao_file_txt,
    ContentList, ChaptersData
)
from utils import sanitize_filename, create_folders_from_tree, normalize_vietnamese_url, HEADERS
from models import StoryInfo, ContentItem


skipped_urls: List[str] = []


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tải truyện từ Valvrare Team dưới dạng PDF, EPUB, và các định dạng khác.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    # If there are command line arguments, use CLI mode, otherwise, use interactive mode
    is_cli_mode = len(sys.argv) > 1

    # --- Define arguments for CLI ---
    parser.add_argument(
        'ten_truyen',
        nargs='?' if not is_cli_mode else None,
        help="Tên truyện cần tải (bắt buộc ở chế độ CLI)."
    )
    parser.add_argument(
        '-o', '--output',
        dest='output_folder',
        help="Thư mục đầu ra để lưu file. Mặc định là tên truyện."
    )
    parser.add_argument(
        '-f', '--format',
        nargs='+',
        default=['EPUB'],
        choices=['PDF', 'EPUB', 'HTML', 'MD', 'TXT'],
        help="Định dạng file đầu ra. Có thể chọn nhiều. Mặc định: EPUB."
    )
    parser.add_argument(
        '-g', '--gop',
        default='rieng',
        choices=['rieng', 'volume', 'tatca'],
        help="Cách gộp file:\n"
             "rieng: Mỗi chương một file (mặc định).\n"
             "volume: Gộp các chương theo từng tập.\n"
             "tatca: Gộp tất cả thành một file duy nhất."
    )
    parser.add_argument(
        '--khong-minh-hoa',
        action='store_true',
        help="Bỏ qua các chương/tập minh họa."
    )
    parser.add_argument(
        '--font',
        default='DejaVuSans',
        choices=['NotoSerif', 'DejaVuSans'],
        help="Font chữ cho file PDF. Mặc định: DejaVuSans."
    )
    parser.add_argument(
        '-t', '--tasks',
        type=int,
        default=5,
        help="Số lượng tác vụ tải song song. Mặc định: 5."
    )

    selection_group = parser.add_mutually_exclusive_group()
    selection_group.add_argument(
        '--all',
        action='store_true',
        help="Tải tất cả các chương (mặc định)."
    )
    selection_group.add_argument(
        '--volumes',
        nargs='+',
        type=int,
        help="Tải các tập cụ thể theo số thứ tự (ví dụ: --volumes 1 3 5)."
    )
    selection_group.add_argument(
        '--chapters',
        nargs='+',
        type=int,
        help="Tải các chương cụ thể theo số thứ tự tuyệt đối (ví dụ: --chapters 1 10 15)."
    )

    args = parser.parse_args()

    # --- Main Logic ---
    if is_cli_mode:
        ten_truyen_raw = args.ten_truyen
        if not ten_truyen_raw:
            parser.error("Tên truyện là bắt buộc ở chế độ CLI.")
    else:
        ten_truyen_raw = input("Nhập tên truyện bạn muốn tải: ")

    sitemap_url = "https://valvrareteam.net/sitemap.xml"

    # Use httpx for sitemap request
    async with httpx.AsyncClient(headers=HEADERS) as client:
        response = await client.get(sitemap_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml-xml")

    ten_truyen_normalized = normalize_vietnamese_url(ten_truyen_raw)
    output_folder = args.output_folder if is_cli_mode and args.output_folder else sanitize_filename(ten_truyen_raw.strip())
    os.makedirs(output_folder, exist_ok=True)

    trang_chinh = None
    for loc in soup.find_all("loc"):
        url = loc.text
        if ten_truyen_normalized in url and "/chuong" not in url:
            trang_chinh = url
            break

    if not trang_chinh:
        print(f"Không tìm thấy truyện '{ten_truyen_raw}'. Vui lòng kiểm tra lại tên truyện.")
        return

    # Get story info
    async with httpx.AsyncClient(headers=HEADERS) as client:
        story_info = await lay_thong_tin_truyen(client, trang_chinh.split("https://valvrareteam.net/")[-1])

    print("Đang lấy danh sách chương từ trang chính của truyện...")
    await tao_so_do_cay.get_chapter_tree_list(trang_chinh, output_file="chapter_list.json")
    await asyncio.sleep(1)

    try:
        with open("chapter_list.json", "r", encoding="utf-8") as f:
            chapter_data = json.load(f)
    except Exception as e:
        print(f"Đã xảy ra lỗi khi đọc file chapter_list.json: {e}")
        return

    # --- Xử lý lựa chọn của người dùng (CLI hoặc tương tác) ---

    # Lọc chương minh họa
    if is_cli_mode:
        minh_hoa_choice = 'y' if args.khong_minh_hoa else 'n'
    else:
        minh_hoa_choice = input("Bạn có muốn bỏ qua các chương minh họa và các chương lỗi không? (Y/n): ").strip().lower()

    if not minh_hoa_choice or minh_hoa_choice in ["y", "yes"]:
        print("Bạn đã chọn bỏ qua các chương minh họa và các tập rỗng.")
        chapter_data = [vol for vol in chapter_data if vol['chapters']]

    if not chapter_data:
        print("Không có chương nào để tải sau khi đã lọc.")
        return

    # Chọn chương/tập để tải
    selected_chapters_relative: List[str] = []
    if is_cli_mode:
        if args.volumes:
            selected_indices = [int(i) - 1 for i in args.volumes]
            for index in selected_indices:
                if 0 <= index < len(chapter_data):
                    selected_chapters_relative.extend(chapter_data[index]['chapters'])
                else:
                    print(f"[Cảnh báo] Bỏ qua chỉ số tập không hợp lệ: {index + 1}")
        elif args.chapters:
            all_chapters_flat = [chap_url for vol in chapter_data for chap_url in vol['chapters']]
            selected_indices = [int(i) - 1 for i in args.chapters]
            for index in selected_indices:
                if 0 <= index < len(all_chapters_flat):
                    selected_chapters_relative.append(all_chapters_flat[index])
                else:
                    print(f"[Cảnh báo] Bỏ qua chỉ số chương không hợp lệ: {index + 1}")
        else:  # Mặc định là tải tất cả
            selected_chapters_relative.extend(chap for vol in chapter_data for chap in vol['chapters'])
    else:
        # Menu chọn chương/tập (chế độ tương tác)
        main_menu_items = ["Tải xuống tất cả", "Chọn tập để tải", "Chọn chương để tải"]
        main_menu = TerminalMenu(main_menu_items, title=" Tùy chọn tải xuống ", menu_cursor_style=("fg_cyan", "bold"), menu_highlight_style=("bg_cyan", "fg_black"))
        main_menu_selection_index = main_menu.show()

        if main_menu_selection_index == 0:  # Tải tất cả
            for volume in chapter_data:
                selected_chapters_relative.extend(volume['chapters'])
        elif main_menu_selection_index == 1:  # Chọn tập
            volume_titles = [volume['volume'] for volume in chapter_data]
            volume_menu = TerminalMenu(volume_titles, title=" Chọn tập (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
            selected_volume_indices = volume_menu.show()
            if selected_volume_indices:
                for index in selected_volume_indices:
                    selected_chapters_relative.extend(chapter_data[index]['chapters'])
        elif main_menu_selection_index == 2:  # Chọn chương
            all_chapters_for_menu = [(f"{vol['volume']}: {ch.split('/')[-1]}", ch) for vol in chapter_data for ch in vol['chapters']]
            chapter_menu_items = [item[0] for item in all_chapters_for_menu]
            chapter_menu = TerminalMenu(chapter_menu_items, title=" Chọn chương (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
            selected_chapter_indices = chapter_menu.show()
            if selected_chapter_indices:
                for index in selected_chapter_indices:
                    selected_chapters_relative.append(all_chapters_for_menu[index][1])

    if not selected_chapters_relative:
        print("Không có chương nào được chọn. Đang thoát.")
        return

    base_url = "https://valvrareteam.net"
    chapter_urls = [base_url + rel_url for rel_url in selected_chapters_relative]

    # Chọn cách gộp và định dạng file
    if is_cli_mode:
        gop_map = {'rieng': 0, 'volume': 1, 'tatca': 2}
        gop_choice_index = gop_map[args.gop]
        formats_to_export = [f.upper() for f in args.format]
        font_name = args.font
        CONCURRENT_TASKS = args.tasks
    else:
        gop_menu_items = ["Xuất riêng từng chương (mặc định)", "Gộp các chương theo từng Volume", "Gộp tất cả chương đã chọn thành 1 file"]
        gop_menu = TerminalMenu(gop_menu_items, title=" Chọn cách thức xuất file ", menu_cursor_style=("fg_green", "bold"), menu_highlight_style=("bg_green", "fg_black"))
        gop_choice_index = gop_menu.show()
        if gop_choice_index == 0:  # xuat rieng tung chuong
            # Tạo cấu trúc thư mục trước
            tree_path = os.path.join(output_folder, "tree_map.txt")
            await tao_so_do_cay.get_chapter_tree_folder(url=trang_chinh, output_file=tree_path)
            create_folders_from_tree(tree_path, output_folder)
        elif gop_choice_index == 1:  # Gop theo volume
            # Tạo cấu trúc thư mục trước
            tree_path = os.path.join(output_folder, "tree_map.txt")
            await tao_so_do_cay.get_chapter_tree_folder(url=trang_chinh, output_file=tree_path)
            create_folders_from_tree(tree_path, output_folder)
        elif gop_choice_index == 3:
            os.mkdir(output_folder)
        format_items = ["PDF", "EPUB", "HTML", "Markdown (.md)", "Text (.txt)"]
        format_menu = TerminalMenu(format_items, title=" Chọn định dạng file (Space để chọn, Enter để xác nhận) ", multi_select=True, show_multi_select_hint=True, multi_select_cursor_style=("fg_yellow", "bold"))
        selected_format_indices = format_menu.show()
        if not selected_format_indices:
            print("Không có định dạng nào được chọn. Đang thoát.")
            return
        formats_to_export = [format_items[i] for i in selected_format_indices]

        font_name = 'DejaVuSans'
        if "PDF" in formats_to_export:
            font_choice = input("Chọn font cho PDF:\n1. Noto Serif\n2. DejaVu Sans (mặc định)\nLựa chọn của bạn (1/2, Enter để dùng mặc định): ").strip()
            if font_choice == '1':
                font_name = 'NotoSerif'

        CONCURRENT_TASKS_str = input("Nhập số lượng tác vụ song song tối đa (mặc định là 5): ")
        CONCURRENT_TASKS = int(CONCURRENT_TASKS_str) if CONCURRENT_TASKS_str.isdigit() and int(CONCURRENT_TASKS_str) > 0 else 5

    # Scrape chapters
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        scraped_content = await scrape_chapters(browser, chapter_urls, CONCURRENT_TASKS, skipped_urls=skipped_urls)
        await browser.close()

    print("Đã tải xong nội dung. Bắt đầu tạo file...")

    # --- Xử lý tạo file sau khi đã scrape ---

    # Build a map from relative url to volume name
    url_to_volume_map: Dict[str, str] = {}
    for vol_info in chapter_data:
        for chap_url in vol_info['chapters']:
            url_to_volume_map[chap_url] = vol_info['volume']

    # 1. Xuất riêng từng chương
    if gop_choice_index == 0:
        for url in chapter_urls:
            if url in scraped_content:
                relative_url = url.replace(base_url, "")
                volume_name = url_to_volume_map.get(relative_url, "Unknown Volume")
                current_folder = os.path.join(output_folder, sanitize_filename(volume_name))
                os.makedirs(current_folder, exist_ok=True)

                ten_chuong = url.split("/")[-1]
                content_list: ContentList = scraped_content[url]  # Already List[ContentItem]
                author = story_info.author
                description = story_info.description
                cover_path = story_info.cover_path

                for fmt in formats_to_export:
                    file_path = os.path.join(current_folder, f"{ten_chuong}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
                    if fmt == "PDF":
                        tao_file_pdf(content_list, file_path, ten_chuong, font_name)
                    elif fmt == "EPUB":
                        chapters_data: ChaptersData = [{'title': ten_chuong, 'content': content_list}]
                        tao_file_epub(file_path, ten_chuong, author, chapters_data, description, cover_path)
                    elif fmt == "HTML":
                        tao_file_html(content_list, file_path, ten_chuong)
                    elif fmt == "Markdown (.md)":
                        tao_file_md(content_list, file_path, ten_chuong)
                    elif fmt == "Text (.txt)":
                        tao_file_txt(content_list, file_path, ten_chuong)

    # 2. Gộp theo Volume
    elif gop_choice_index == 1:
        volume_contents: Dict[str, List[Dict[str, Any]]] = {}
        for url in chapter_urls:
            if url in scraped_content:
                relative_url = url.replace(base_url, "")
                volume_name = url_to_volume_map.get(relative_url, "Unknown Volume")
                if volume_name not in volume_contents:
                    volume_contents[volume_name] = []

                ten_chuong = url.split("/")[-1]
                volume_contents[volume_name].append({
                    'title': ten_chuong,
                    'content': scraped_content[url]
                })

        author = story_info.author
        description = story_info.description
        cover_path = story_info.cover_path

        for volume_name, chapters_list in volume_contents.items():
            sanitized_vol_name = sanitize_filename(volume_name)
            # Volume folder is not strictly needed when merging, but let's keep it clean
            current_folder = os.path.join(output_folder, sanitized_vol_name)
            os.makedirs(current_folder, exist_ok=True)

            # Use the full content of the volume for PDF and other simple formats
            full_volume_content: ContentList = []
            for chap in chapters_list:
                full_volume_content.extend(chap['content'])

            for fmt in formats_to_export:
                file_path = os.path.join(current_folder, f"{sanitized_vol_name}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
                if fmt == "PDF":
                    tao_file_pdf(full_volume_content, file_path, volume_name, font_name)
                elif fmt == "EPUB":
                    tao_file_epub(file_path, volume_name, author, chapters_list, description, cover_path)
                elif fmt == "HTML":
                    tao_file_html(full_volume_content, file_path, volume_name)
                elif fmt == "Markdown (.md)":
                    tao_file_md(full_volume_content, file_path, volume_name)
                elif fmt == "Text (.txt)":
                    tao_file_txt(full_volume_content, file_path, volume_name)

    # 3. Gộp tất cả
    elif gop_choice_index == 2:
        full_story_structure: ChaptersData = []
        full_content_list_simple: ContentList = []

        # Preserve the original volume and chapter order from chapter_data
        for volume_info in chapter_data:
            volume_title = volume_info['volume']
            chapters_in_volume: List[Dict[str, Any]] = []

            # Filter for selected chapters only
            for relative_url in volume_info['chapters']:
                full_url = base_url + relative_url
                if full_url in scraped_content:
                    chapter_title = relative_url.split('/')[-1]
                    content = scraped_content[full_url]
                    chapters_in_volume.append({'title': chapter_title, 'content': content})
                    full_content_list_simple.extend(content)

            if chapters_in_volume:
                full_story_structure.append({'volume': volume_title, 'chapters': chapters_in_volume})

        sanitized_story_name = sanitize_filename(ten_truyen_raw)
        author = story_info.author
        description = story_info.description
        cover_path = story_info.cover_path

        for fmt in formats_to_export:
            file_path = os.path.join(output_folder, f"{sanitized_story_name}.{fmt.lower().split(' ')[0].replace('(.md)', '.md').replace('(.txt)', '.txt')}")
            if fmt == "PDF":
                tao_file_pdf(full_content_list_simple, file_path, ten_truyen_raw, font_name)
            elif fmt == "EPUB":
                tao_file_epub(file_path, ten_truyen_raw, author, full_story_structure, description, cover_path)
            elif fmt == "HTML":
                tao_file_html(full_content_list_simple, file_path, ten_truyen_raw)
            elif fmt == "Markdown (.md)":
                tao_file_md(full_content_list_simple, file_path, ten_truyen_raw)
            elif fmt == "Text (.txt)":
                tao_file_txt(full_content_list_simple, file_path, ten_truyen_raw)

    print("\n--- HOÀN TẤT ---")
    if skipped_urls:
        log_file_path = os.path.join(output_folder, "cac_chuong_da_bo_qua.txt")
        print(f"(!) Cảnh báo: {len(skipped_urls)} chương đã bị bỏ qua do lỗi.")
        print(f"Đang ghi danh sách các chương bị lỗi vào file: {log_file_path}")
        with open(log_file_path, "w", encoding="utf-8") as f:
            for url in skipped_urls:
                f.write(f"{url}\n")