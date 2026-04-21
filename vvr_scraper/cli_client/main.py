"""Argparse entry point and route dispatcher for Voice Bank CLI Client."""

import argparse
import asyncio
import sys
from typing import Any

from . import voice_commands
from .client import APIClient, CLIError
from .display import print_error


def build_parser() -> argparse.ArgumentParser:
    """Build and return the ArgumentParser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="vvrt-client",
        description="Voice Bank CLI Client — remote client for the VVR Voice Bank API",
    )

    # Global flags
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="JWT token for authentication (overrides token file)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # login
    login_parser = subparsers.add_parser("login", help="Authenticate with the server")
    login_parser.add_argument("--username", "-u", help="Username (will prompt if omitted)")
    login_parser.add_argument("--password", "-p", help="Password (will prompt if omitted)")

    # logout
    subparsers.add_parser("logout", help="Remove stored authentication token")

    # upload
    upload_parser = subparsers.add_parser("upload", help="Upload a new voice sample")
    upload_parser.add_argument("--audio", "-a", help="Path to audio file (will prompt if omitted)")
    upload_parser.add_argument("--name", "-n", help="Voice name (will prompt if omitted)")
    upload_parser.add_argument("--ref-text", "-t", help="Reference text (will prompt if omitted)")
    upload_parser.add_argument(
        "--gender",
        "-g",
        choices=["male", "female", "other"],
        help="Speaker gender (will prompt if omitted)",
    )
    upload_parser.add_argument(
        "--age-group",
        choices=["child", "teen", "young_adult", "adult", "elder"],
        help="Speaker age group (will prompt if omitted)",
    )
    upload_parser.add_argument("--description", default="", help="Voice description")
    upload_parser.add_argument("--language", default="vi", help="Language code (default: vi)")
    upload_parser.add_argument("--mood", "-m", help="Voice mood/tag")
    upload_parser.add_argument("--tags", help="Comma-separated tags")

    # list
    list_parser = subparsers.add_parser("list", help="List your voices")
    list_parser.add_argument("--limit", type=int, default=20, help="Max items (default: 20)")
    list_parser.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")

    # community
    community_parser = subparsers.add_parser("community", help="Browse public voice gallery")
    community_parser.add_argument("--tag", help="Filter by tag")
    community_parser.add_argument(
        "--gender",
        choices=["male", "female", "other"],
        help="Filter by gender",
    )
    community_parser.add_argument(
        "--age-group",
        choices=["child", "teen", "young_adult", "adult", "elder"],
        help="Filter by age group",
    )
    community_parser.add_argument(
        "--sort",
        choices=["votes", "newest"],
        default="votes",
        help="Sort order (default: votes)",
    )
    community_parser.add_argument("--limit", type=int, default=20, help="Max items (default: 20)")
    community_parser.add_argument("--offset", type=int, default=0, help="Offset (default: 0)")

    # show
    show_parser = subparsers.add_parser("show", help="Show voice details")
    show_parser.add_argument("voice_id", help="Voice ID")

    # update
    update_parser = subparsers.add_parser("update", help="Update voice metadata")
    update_parser.add_argument("voice_id", help="Voice ID")
    update_parser.add_argument("--name", help="New name")
    update_parser.add_argument("--description", help="New description")
    update_parser.add_argument("--mood", help="New mood")
    update_parser.add_argument("--tags", help="New comma-separated tags")

    # delete
    delete_parser = subparsers.add_parser("delete", help="Delete a voice")
    delete_parser.add_argument("voice_id", help="Voice ID")

    # publish
    publish_parser = subparsers.add_parser("publish", help="Make voice public")
    publish_parser.add_argument("voice_id", help="Voice ID")

    # delist
    delist_parser = subparsers.add_parser("delist", help="Make voice private")
    delist_parser.add_argument("voice_id", help="Voice ID")

    # vote
    vote_parser = subparsers.add_parser("vote", help="Upvote or downvote a voice")
    vote_parser.add_argument("voice_id", help="Voice ID")
    vote_direction = vote_parser.add_mutually_exclusive_group(required=True)
    vote_direction.add_argument("--up", dest="direction", action="store_const", const="up", help="Upvote the voice")
    vote_direction.add_argument(
        "--down", dest="direction", action="store_const", const="down", help="Downvote the voice"
    )

    # download
    download_parser = subparsers.add_parser("download", help="Download voice audio")
    download_parser.add_argument("voice_id", help="Voice ID")
    download_parser.add_argument("--output", "-o", required=True, help="Output file path")

    # preview
    preview_parser = subparsers.add_parser("preview", help="Generate preview audio")
    preview_parser.add_argument("voice_id", help="Voice ID")
    preview_parser.add_argument("--text", "-t", help="Text to synthesize (will prompt if omitted)")

    return parser


# Command map: subcommand name -> handler function
COMMAND_MAP: dict[str, Any] = {
    "login": voice_commands.login,
    "logout": voice_commands.logout,
    "upload": voice_commands.upload,
    "list": voice_commands.list_voices,
    "community": voice_commands.community,
    "show": voice_commands.show,
    "update": voice_commands.update,
    "delete": voice_commands.delete,
    "publish": voice_commands.publish,
    "delist": voice_commands.delist,
    "vote": voice_commands.vote,
    "download": voice_commands.download,
    "preview": voice_commands.preview,
}


async def async_main(args: argparse.Namespace) -> int:
    """Create APIClient and dispatch to the appropriate handler.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    if args.command is None:
        print_error("No command specified. Use --help for usage.")
        return 1

    # Create APIClient with global settings
    client = APIClient(
        host=args.host,
        port=args.port,
        token=args.token,
    )

    # Get the handler for the command
    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        print_error(f"Unknown command: {args.command}")
        return 1

    # Dispatch to handler
    await handler(client, args)
    return 0


def main() -> int:
    """Entry point: parse args, run async_main, handle errors.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = build_parser()
    args = parser.parse_args()

    try:
        return asyncio.run(async_main(args))
    except CLIError as e:
        print_error(str(e))
        return e.exit_code
    except KeyboardInterrupt:
        print_error("Operation cancelled by user")
        return 130  # Standard exit code for Ctrl+C


if __name__ == "__main__":
    sys.exit(main())
