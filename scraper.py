#!/usr/bin/env python3
"""
Main entry point for the web novel scraper.
This is a thin wrapper that delegates to the CLI module.
"""
from vvr_scraper.cli import main as cli_main


if __name__ == "__main__":
    cli_main()
