#!/usr/bin/env /home/tung/Data/dev/backup/Valvrareteam.net-crawler/.venv/bin/python
"""
Demo script to extract chapter content from ln.hako.vn using Playwright.
Content is protected with xor_shuffle encoding and requires JavaScript execution.

Usage:
    .venv/bin/python scripts/demo_lnhako_chapter.py [chapter_url]

Example:
    .venv/bin/python scripts/demo_lnhako_chapter.py "https://ln.hako.vn/truyen/25956-ban-gai-doi-xu-voi-toi-qua-tot/c365957-chuong-1-doi-toi-von-di-mau-hong-cho-den-khi"
"""

import asyncio
import sys


async def extract_chapter_content(url: str) -> str:
    """
    Extract chapter content from ln.hako.vn using Playwright.
    The content is loaded via JavaScript with xor_shuffle encoding.
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            extra_http_headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        page = await context.new_page()

        # Navigate to chapter page
        await page.goto(url, wait_until="networkidle")

        # Wait for chapter content to load (JavaScript renders it)
        await page.wait_for_selector("#chapter-content", timeout=30000)

        # Get the decoded content
        content = await page.inner_text("#chapter-content")

        await context.close()
        await browser.close()
        return content


async def main():
    if len(sys.argv) < 2:
        url = "https://ln.hako.vn/truyen/25956-ban-gai-doi-xu-voi-toi-qua-tot/c365957-chuong-1-doi-toi-von-di-mau-hong-cho-den-khi"
        print(f"No URL provided, using default: {url}")
    else:
        url = sys.argv[1]

    print(f"Extracting content from:\n{url}\n")
    print("=" * 60)

    try:
        content = await extract_chapter_content(url)
        print(f"Extracted {len(content)} characters:")
        print("-" * 60)
        print(content[:2000])
        if len(content) > 2000:
            print("\n... (truncated) ...\n")
            print(content[-500:])
        print("-" * 60)
    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
