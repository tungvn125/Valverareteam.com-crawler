import json
import os
from typing import Any

from playwright.async_api import async_playwright


def save_session(state: dict[str, Any], file_path: str):
    """Saves the browser storage state (cookies and local storage) to a file."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.chmod(file_path, 0o600)


def load_session(file_path: str) -> dict[str, Any] | None:
    """Loads the browser storage state from a file."""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def capture_session(url: str) -> dict[str, Any]:
    """
    Launches a non-headless browser for the user to login or bypass Cloudflare.
    Returns the storage state upon user confirmation.
    """
    async with async_playwright() as p:
        # Launch non-headless browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(url)

        print("\n" + "=" * 60)
        print("VUI LÒNG ĐĂNG NHẬP HOẶC GIẢI CLOUDFLARE TRONG TRÌNH DUYỆT.")
        print("Sau khi hoàn tất và thấy nội dung truyện ĐÃ MỞ KHÓA, hãy quay lại đây.")
        print("Nhấn phím ENTER trong terminal này để tiếp tục...")
        print("=" * 60 + "\n")

        # Use input() which is more standard for this
        input()

        state = await context.storage_state()
        print(f"Đã bắt được session với {len(state.get('cookies', []))} cookies.")
        await browser.close()
        return state
