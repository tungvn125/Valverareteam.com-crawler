#!/usr/bin/env python3
"""
Main entry point for the web novel scraper.
This is a thin wrapper that delegates to the CLI module.
"""
import os

from vvr_scraper.cli import main as cli_main


if __name__ == "__main__":
    try:
        cli_main()
    finally:
        # Cleanup temporary files
        if os.path.exists("chapter_list.json"):
            os.remove("chapter_list.json")
        if os.path.exists("cover.jpg"):
            os.remove("cover.jpg")
        print("Đã dọn dẹp file tạm. Hẹn gặp lại!")
