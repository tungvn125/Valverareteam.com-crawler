#!/usr/bin/env python3
"""
Main entry point for the web novel scraper.
This is a thin wrapper that delegates to the CLI module.
"""
import asyncio
import os

from cli import main as cli_main


if __name__ == "__main__":
    try:
        asyncio.run(cli_main())
    except KeyboardInterrupt:
        print("\nChương trình bị dừng bởi người dùng.")
    finally:
        # Cleanup temporary files
        if os.path.exists("chapter_list.json"):
            os.remove("chapter_list.json")
        if os.path.exists("cover.jpg"):
            os.remove("cover.jpg")
        print("Đã dọn dẹp file tạm. Hẹn gặp lại!")