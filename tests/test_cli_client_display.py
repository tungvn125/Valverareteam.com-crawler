"""Tests for the CLI client display module."""

import io
import pytest
from rich.console import Console

from vvr_scraper.cli_client.display import (
    print_error,
    print_success,
    print_voice_table,
    print_voice_detail,
    VISIBILITY_COLORS,
)


class TestPrintError:
    """Tests for print_error function."""

    def test_print_error_output(self, capsys):
        """Test that print_error outputs the message and 'Error'."""
        from vvr_scraper.cli_client import display

        original_console = display.console
        buffer = io.StringIO()
        display.console = Console(file=buffer, force_terminal=True)

        try:
            print_error("Something went wrong")
            output = buffer.getvalue()

            assert "Something went wrong" in output
            assert "Error" in output
        finally:
            display.console = original_console


class TestPrintSuccess:
    """Tests for print_success function."""

    def test_print_success_output(self, capsys):
        """Test that print_success outputs the message."""
        from vvr_scraper.cli_client import display

        original_console = display.console
        buffer = io.StringIO()
        display.console = Console(file=buffer, force_terminal=True)

        try:
            print_success("Voice uploaded")
            output = buffer.getvalue()

            assert "Voice uploaded" in output
        finally:
            display.console = original_console


class TestVisibilityColors:
    """Tests for VISIBILITY_COLORS dict."""

    def test_visibility_colors_mappings(self):
        """Test that VISIBILITY_COLORS has correct mappings."""
        assert VISIBILITY_COLORS["public"] == "green"
        assert VISIBILITY_COLORS["private"] == "yellow"
        assert VISIBILITY_COLORS["delisted"] == "red"


class TestPrintVoiceTable:
    """Tests for print_voice_table function."""

    def test_print_voice_table_with_one_item(self):
        """Test print_voice_table with a single item matching API response keys."""
        from vvr_scraper.cli_client import display

        original_console = display.console
        buffer = io.StringIO()
        display.console = Console(file=buffer, force_terminal=True, width=200)

        try:
            items = [
                {
                    "id": "voice_001",
                    "name": "Test Voice",
                    "gender": "female",
                    "age_group": "young_adult",
                    "duration_ms": 10500,
                    "sample_rate": 22050,
                    "tags": ["test", "demo"],
                    "vote_score": 42,
                    "visibility": "public",
                }
            ]

            print_voice_table(items, title="Test Voices")
            output = buffer.getvalue()

            assert "Test Voices" in output
            assert "voice_001" in output
            assert "Test Voice" in output
            assert "female" in output
            assert "young_adult" in output
            assert "10500ms" in output
            assert "42" in output
            assert "public" in output
        finally:
            display.console = original_console

    def test_print_voice_table_empty(self):
        """Test print_voice_table with empty list."""
        from vvr_scraper.cli_client import display

        original_console = display.console
        buffer = io.StringIO()
        display.console = Console(file=buffer, force_terminal=True)

        try:
            print_voice_table([], title="Test Voices")
            output = buffer.getvalue()

            assert "No voices found" in output
        finally:
            display.console = original_console


class TestPrintVoiceDetail:
    """Tests for print_voice_detail function."""

    def test_print_voice_detail_with_full_voice(self):
        """Test print_voice_detail with a full voice dict matching API response keys."""
        from vvr_scraper.cli_client import display

        original_console = display.console
        buffer = io.StringIO()
        display.console = Console(file=buffer, force_terminal=True, width=200)

        try:
            voice = {
                "id": "voice_001",
                "name": "Test Voice",
                "gender": "female",
                "age_group": "young_adult",
                "language": "vi",
                "duration_ms": 10500,
                "sample_rate": 44100,
                "mood": "happy",
                "visibility": "public",
                "usage_count": 100,
                "vote_score": 42,
                "tags": ["test", "demo", "female"],
                "description": "A test voice for demo purposes",
                "ref_text": "Hello world, this is a test.",
                "created_at": "2024-01-01T00:00:00Z",
            }

            print_voice_detail(voice)
            output = buffer.getvalue()

            assert "voice_001" in output
            assert "Test Voice" in output
            assert "female" in output
            assert "young_adult" in output
            assert "vi" in output
            assert "10500ms" in output
            assert "44100" in output
            assert "happy" in output
            assert "public" in output
            assert "100" in output
            assert "42" in output
            assert "test, demo, female" in output
            assert "A test voice for demo purposes" in output
            assert "Hello world, this is a test." in output
            assert "2024-01-01" in output
        finally:
            display.console = original_console