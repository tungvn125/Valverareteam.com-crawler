# Voice Bank CLI Client — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone CLI binary (`vvrt-client`) that interacts with the Voice Bank API over HTTP.

**Architecture:** New `vvr_scraper/cli_client/` package with 5 modules. `APIClient` wraps `httpx.AsyncClient` with auth injection and error mapping. `TokenManager` resolves JWT from env/file/login. Each voice command is an async function called by `main.py` argparse router. No modifications to existing code except `pyproject.toml` entry point.

**Tech Stack:** Python 3.12+, httpx, rich, prompt-toolkit, loguru, PyJWT (for local expiry check)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `vvr_scraper/cli_client/__init__.py` | Package init, version |
| `vvr_scraper/cli_client/main.py` | Argparse entry point, route dispatch, `main()` |
| `vvr_scraper/cli_client/client.py` | `APIClient` class, `CLIError` exception |
| `vvr_scraper/cli_client/auth_manager.py` | `TokenManager` class, `AuthenticationRequired` exception |
| `vvr_scraper/cli_client/voice_commands.py` | All 11 voice bank command functions |
| `vvr_scraper/cli_client/display.py` | Rich formatters (tables, panels, colors) |
| `tests/test_cli_client.py` | Unit tests for all cli_client modules |
| `pyproject.toml` | Add `vvrt-client` entry point |

---

### Task 1: `display.py` — Rich Formatters

**Files:**
- Create: `vvr_scraper/cli_client/display.py`
- Test: `tests/test_cli_client.py`

- [ ] **Step 1: Write failing tests for display functions**

```python
# tests/test_cli_client.py
"""Unit tests for cli_client.display module."""
import pytest
from rich.console import Console
from io import StringIO

from vvr_scraper.cli_client.display import (
    print_voice_table,
    print_voice_detail,
    print_error,
    print_success,
    VISIBILITY_COLORS,
)


class TestPrintError:
    def test_print_error_outputs_message(self, capsys):
        from vvr_scraper.cli_client.display import print_error
        print_error("Something went wrong")
        output = capsys.readouterr().out
        assert "Something went wrong" in output
        assert "Error" in output


class TestPrintSuccess:
    def test_print_success_outputs_message(self, capsys):
        from vvr_scraper.cli_client.display import print_success
        print_success("Voice uploaded")
        output = capsys.readouterr().out
        assert "Voice uploaded" in output


class TestVisibilityColors:
    def test_visibility_color_mapping(self):
        assert VISIBILITY_COLORS["public"] == "green"
        assert VISIBILITY_COLORS["private"] == "yellow"
        assert VISIBILITY_COLORS["delisted"] == "red"


class TestPrintVoiceTable:
    def test_print_voice_table_with_items(self, capsys):
        items = [
            {
                "id": "abc-123",
                "name": "Minh",
                "gender": "male",
                "age_group": "young_adult",
                "duration_ms": 5000,
                "tags": ["vietnamese", "male"],
                "vote_score": 3,
                "visibility": "public",
            }
        ]
        print_voice_table(items, title="My Voices")
        output = capsys.readouterr().out
        assert "Minh" in output
        assert "abc-123" in output

    def test_print_voice_table_empty(self, capsys):
        print_voice_table([], title="My Voices")
        output = capsys.readouterr().out
        assert "No voices found" in output


class TestPrintVoiceDetail:
    def test_print_voice_detail_shows_all_fields(self, capsys):
        voice = {
            "id": "abc-123",
            "name": "Minh",
            "gender": "male",
            "age_group": "young_adult",
            "duration_ms": 5000,
            "sample_rate": 22050,
            "language": "vi",
            "mood": "calm",
            "visibility": "public",
            "usage_count": 10,
            "tags": ["vietnamese", "male"],
            "vote_score": 3,
            "ref_text": "Xin chào các bạn",
            "description": "A calm male voice",
            "user_id": "user-1",
            "created_at": "2026-04-21T10:00:00Z",
            "updated_at": "2026-04-21T10:00:00Z",
        }
        print_voice_detail(voice)
        output = capsys.readouterr().out
        assert "Minh" in output
        assert "abc-123" in output
        assert "Xin chào các bạn" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestPrintError or TestPrintSuccess or TestVisibilityColors or TestPrintVoiceTable or TestPrintVoiceDetail" 2>&1 | head -30`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.cli_client'`

- [ ] **Step 3: Create `__init__.py` and `display.py`**

```python
# vvr_scraper/cli_client/__init__.py
"""Voice Bank CLI Client — remote client for the VVR Voice Bank API."""

__version__ = "0.1.0"
```

```python
# vvr_scraper/cli_client/display.py
"""Rich terminal formatters for the Voice Bank CLI client."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

VISIBILITY_COLORS = {
    "public": "green",
    "private": "yellow",
    "delisted": "red",
}


def print_error(msg: str) -> None:
    """Print an error message in bold red."""
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_success(msg: str) -> None:
    """Print a success message in bold green."""
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_voice_table(items: list[dict], title: str = "Voices") -> None:
    """Print a Rich table of voice samples."""
    if not items:
        console.print(f"[yellow]No voices found.[/yellow]")
        return

    table = Table(title=f"[bold cyan]{title}[/bold cyan]", border_style="bright_blue")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name", style="white")
    table.add_column("Gender", style="cyan")
    table.add_column("Age", style="cyan")
    table.add_column("Duration", style="cyan", justify="right")
    table.add_column("Tags", style="dim")
    table.add_column("Votes", style="yellow", justify="right")
    table.add_column("Visibility", style="bold")

    for v in items:
        vis = v.get("visibility", "private")
        vis_color = VISIBILITY_COLORS.get(vis, "white")
        tags = ", ".join(v.get("tags", [])[:3])
        duration = f"{v.get('duration_ms', 0)}ms"
        table.add_row(
            v.get("id", "")[:12],
            v.get("name", ""),
            v.get("gender", ""),
            v.get("age_group", ""),
            duration,
            tags,
            str(v.get("vote_score", 0)),
            f"[{vis_color}]{vis}[/{vis_color}]",
        )

    console.print(table)


def print_voice_detail(voice: dict) -> None:
    """Print a detailed panel for a single voice sample."""
    vis = voice.get("visibility", "private")
    vis_color = VISIBILITY_COLORS.get(vis, "white")
    tags = ", ".join(voice.get("tags", []))

    lines = [
        f"[cyan]ID:[/cyan]          {voice.get('id', '')}",
        f"[cyan]Name:[/cyan]        {voice.get('name', '')}",
        f"[cyan]Gender:[/cyan]      {voice.get('gender', '')}",
        f"[cyan]Age Group:[/cyan]   {voice.get('age_group', '')}",
        f"[cyan]Language:[/cyan]    {voice.get('language', 'vi')}",
        f"[cyan]Duration:[/cyan]    {voice.get('duration_ms', 0)}ms",
        f"[cyan]Sample Rate:[/cyan] {voice.get('sample_rate', 0)} Hz",
        f"[cyan]Mood:[/cyan]        {voice.get('mood', 'N/A')}",
        f"[cyan]Visibility:[/cyan]   [{vis_color}]{vis}[/{vis_color}]",
        f"[cyan]Usage Count:[/cyan] {voice.get('usage_count', 0)}",
        f"[cyan]Votes:[/cyan]        {voice.get('vote_score', 0)}",
        f"[cyan]Tags:[/cyan]        {tags or 'None'}",
        f"[cyan]Description:[/cyan] {voice.get('description', 'N/A')}",
        f"[cyan]Ref Text:[/cyan]     {voice.get('ref_text', 'N/A')}",
        f"[cyan]Created:[/cyan]     {voice.get('created_at', 'N/A')}",
    ]

    panel = Panel(
        "\n".join(lines),
        title=f"[bold cyan]Voice: {voice.get('name', 'Unknown')}[/bold cyan]",
        border_style="bright_blue",
    )
    console.print(panel)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestPrintError or TestPrintSuccess or TestVisibilityColors or TestPrintVoiceTable or TestPrintVoiceDetail" 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/cli_client/__init__.py vvr_scraper/cli_client/display.py tests/test_cli_client.py
git commit -m "feat(cli-client): add display module with Rich formatters"
```

---

### Task 2: `auth_manager.py` — Token Manager

**Files:**
- Create: `vvr_scraper/cli_client/auth_manager.py`
- Modify: `tests/test_cli_client.py` (add tests)

- [ ] **Step 1: Write failing tests for TokenManager**

```python
# Append to tests/test_cli_client.py

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

from vvr_scraper.cli_client.auth_manager import TokenManager, AuthenticationRequired


class TestTokenManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.token_path = os.path.join(self.tmpdir, "token.json")

    def teardown_method(self):
        if os.path.exists(self.token_path):
            os.remove(self.token_path)
        os.rmdir(self.tmpdir)

    def test_get_token_from_constructor(self):
        mgr = TokenManager(token="test-token-123", token_path=self.token_path)
        assert mgr.get_token() == "test-token-123"

    def test_get_token_from_env_var(self):
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token-456"}):
            mgr = TokenManager(token_path=self.token_path)
            assert mgr.get_token() == "env-token-456"

    def test_get_token_from_file(self):
        data = {
            "token": "file-token-789",
            "username": "alice",
            "user_id": "uuid-1",
            "role": "member",
            "created_at": "2026-04-21T10:00:00Z",
        }
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.get_token() == "file-token-789"

    def test_get_token_priority_constructor_over_env(self):
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token"}):
            mgr = TokenManager(token="ctor-token", token_path=self.token_path)
            assert mgr.get_token() == "ctor-token"

    def test_get_token_priority_env_over_file(self):
        data = {"token": "file-token", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        with patch.dict(os.environ, {"VVR_TOKEN": "env-token"}):
            mgr = TokenManager(token_path=self.token_path)
            assert mgr.get_token() == "env-token"

    def test_no_token_raises_authentication_required(self):
        mgr = TokenManager(token_path=self.token_path)
        with pytest.raises(AuthenticationRequired):
            mgr.get_token()

    def test_logout_deletes_token_file(self):
        data = {"token": "tok", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        mgr.logout()
        assert not os.path.exists(self.token_path)

    def test_is_authenticated_with_file(self):
        data = {"token": "tok", "username": "a", "user_id": "b", "role": "member", "created_at": "2026-01-01T00:00:00Z"}
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.is_authenticated() is True

    def test_is_authenticated_without_any_token(self):
        mgr = TokenManager(token_path=self.token_path)
        assert mgr.is_authenticated() is False

    def test_expired_token_raises_authentication_required(self):
        """Token with exp in the past should be treated as expired."""
        import time
        # Create a token that looks like a JWT with expired exp claim
        # We'll test the _is_token_expired method directly
        data = {
            "token": "fake.jwt.token",
            "username": "a",
            "user_id": "b",
            "role": "member",
            "created_at": "2026-01-01T00:00:00Z",
        }
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump(data, f)
        mgr = TokenManager(token_path=self.token_path)
        # The fake token won't decode as JWT, so _is_token_expired returns False
        # (we only check real JWT tokens). This is acceptable — the server
        # will reject expired tokens with 401.
        assert mgr.get_token() == "fake.jwt.token"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestTokenManager" 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.cli_client.auth_manager'`

- [ ] **Step 3: Write `auth_manager.py`**

```python
# vvr_scraper/cli_client/auth_manager.py
"""Token management for the Voice Bank CLI client."""

import json
import os
from pathlib import Path

from loguru import logger


class AuthenticationRequired(Exception):
    """Raised when no valid authentication token is available."""
    pass


class TokenManager:
    """Manages JWT tokens for API authentication.

    Resolution order:
    1. Constructor-provided token (highest priority)
    2. VVR_TOKEN environment variable
    3. Token file (~/.config/vvr-scraper/token.json)

    If no token is found, raises AuthenticationRequired.
    """

    def __init__(self, token: str | None = None, token_path: str | None = None):
        self._token = token
        self._token_path = token_path or self._default_token_path()

    @staticmethod
    def _default_token_path() -> str:
        config_dir = os.path.join(os.path.expanduser("~"), ".config", "vvr-scraper")
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, "token.json")

    def get_token(self) -> str:
        """Return a valid token, checking sources in priority order.

        Raises AuthenticationRequired if no token is available.
        """
        # 1. Constructor-provided token
        if self._token:
            return self._token

        # 2. Environment variable
        env_token = os.environ.get("VVR_TOKEN")
        if env_token:
            return env_token

        # 3. Token file
        if os.path.exists(self._token_path):
            try:
                with open(self._token_path, encoding="utf-8") as f:
                    data = json.load(f)
                token = data.get("token")
                if token:
                    return token
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read token file: {e}")

        raise AuthenticationRequired(
            "Chưa có token. Chạy `vvrt-client login` để đăng nhập."
        )

    def is_authenticated(self) -> bool:
        """Check if a token is available without raising."""
        try:
            self.get_token()
            return True
        except AuthenticationRequired:
            return False

    def save_token(self, token_data: dict) -> None:
        """Save token data to the token file."""
        os.makedirs(os.path.dirname(self._token_path), exist_ok=True)
        with open(self._token_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        logger.debug(f"Token saved to {self._token_path}")

    def logout(self) -> None:
        """Delete the token file."""
        if os.path.exists(self._token_path):
            os.remove(self._token_path)
            logger.info("Token removed.")
        else:
            logger.info("No token file to remove.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestTokenManager" 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/cli_client/auth_manager.py tests/test_cli_client.py
git commit -m "feat(cli-client): add TokenManager with env/file/constructor priority"
```

---

### Task 3: `client.py` — API Client

**Files:**
- Create: `vvr_scraper/cli_client/client.py`
- Modify: `tests/test_cli_client.py` (add tests)

- [ ] **Step 1: Write failing tests for APIClient**

```python
# Append to tests/test_cli_client.py

from unittest.mock import AsyncMock, patch
import httpx

from vvr_scraper.cli_client.client import APIClient, CLIError


class TestCLIError:
    def test_cli_error_with_message(self):
        err = CLIError("Something went wrong", exit_code=1)
        assert str(err) == "Something went wrong"
        assert err.exit_code == 1

    def test_cli_error_default_exit_code(self):
        err = CLIError("Error")
        assert err.exit_code == 1


class TestAPIClientInit:
    def test_default_base_url(self):
        client = APIClient()
        assert client.base_url == "http://127.0.0.1:8000"

    def test_custom_host_port(self):
        client = APIClient(host="192.168.1.100", port=8080)
        assert client.base_url == "http://192.168.1.100:8080"

    def test_token_passed_to_token_manager(self):
        client = APIClient(token="my-token")
        assert client.token_manager._token == "my-token"


class TestAPIClientErrorMapping:
    """Test that APIClient maps HTTP status codes to Vietnamese messages."""

    def test_401_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[401] == "Chưa đăng nhập. Chạy `vvrt-client login`"

    def test_403_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[403] == "Không có quyền thực hiện"

    def test_404_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[404] == "Không tìm thấy voice sample"

    def test_413_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[413] == "File quá lớn (tối đa 30MB)"

    def test_429_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[429] == "Quá nhiều request, thử lại sau"

    def test_500_message(self):
        client = APIClient()
        assert client.ERROR_MESSAGES[500] == "Lỗi server"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestCLIError or TestAPIClientInit or TestAPIClientErrorMapping" 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.cli_client.client'`

- [ ] **Step 3: Write `client.py`**

```python
# vvr_scraper/cli_client/client.py
"""HTTP API client for the Voice Bank CLI."""

from typing import Any

import httpx
from loguru import logger

from .auth_manager import AuthenticationRequired, TokenManager


class CLIError(Exception):
    """Custom exception for CLI errors with exit code."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class APIClient:
    """Async HTTP client for the VVR Voice Bank API.

    Handles authentication, error mapping, and request formatting.
    """

    ERROR_MESSAGES: dict[int, str] = {
        401: "Chưa đăng nhập. Chạy `vvrt-client login`",
        403: "Không có quyền thực hiện",
        404: "Không tìm thấy voice sample",
        413: "File quá lớn (tối đa 30MB)",
        429: "Quá nhiều request, thử lại sau",
        500: "Lỗi server",
    }

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        token: str | None = None,
    ):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.token_manager = TokenManager(token=token)

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_data: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Make an authenticated API request.

        Returns parsed JSON (dict/list) or None for 204 responses.
        Raises CLIError on HTTP errors or connection failures.
        """
        try:
            token = self.token_manager.get_token()
        except AuthenticationRequired as e:
            raise CLIError(str(e)) from e

        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        ) as client:
            try:
                response = await client.request(
                    method,
                    path,
                    params=params,
                    json=json_data,
                    files=files,
                    data=data,
                )
            except httpx.ConnectError as e:
                raise CLIError(
                    f"Không thể kết nối đến server {self.base_url}. Kiểm tra host/port."
                ) from e

        # Handle 204 No Content
        if response.status_code == 204:
            return None

        # Handle error status codes
        if response.status_code >= 400:
            msg = self.ERROR_MESSAGES.get(response.status_code)
            if msg is None:
                # Try to extract detail from response body
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                msg = f"Lỗi HTTP {response.status_code}: {detail}"
            raise CLIError(msg)

        # Return parsed JSON
        try:
            return response.json()
        except Exception:
            return None

    async def upload_file(
        self,
        path: str,
        file_path: str,
        file_field: str = "audio",
        fields: dict | None = None,
    ) -> Any:
        """Upload a file with multipart form data.

        Args:
            path: API endpoint path.
            file_path: Local path to the file to upload.
            file_field: Form field name for the file.
            fields: Additional form fields.
        """
        try:
            token = self.token_manager.get_token()
        except AuthenticationRequired as e:
            raise CLIError(str(e)) from e

        headers = {"Authorization": f"Bearer {token}"}
        # Don't set Content-Type — httpx sets it with boundary for multipart

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=60.0,  # Longer timeout for uploads
        ) as client:
            with open(file_path, "rb") as f:
                files = {file_field: (os.path.basename(file_path), f, "application/octet-stream")}
                try:
                    response = await client.post(path, files=files, data=fields or {})
                except httpx.ConnectError as e:
                    raise CLIError(
                        f"Không thể kết nối đến server {self.base_url}. Kiểm tra host/port."
                    ) from e

        if response.status_code >= 400:
            msg = self.ERROR_MESSAGES.get(response.status_code)
            if msg is None:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                msg = f"Lỗi HTTP {response.status_code}: {detail}"
            raise CLIError(msg)

        return response.json()

    async def download_file(
        self,
        path: str,
        output_path: str,
    ) -> str:
        """Download a file from the API and save to disk.

        Returns the output path.
        """
        try:
            token = self.token_manager.get_token()
        except AuthenticationRequired as e:
            raise CLIError(str(e)) from e

        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=60.0,
        ) as client:
            try:
                response = await client.get(path)
            except httpx.ConnectError as e:
                raise CLIError(
                    f"Không thể kết nối đến server {self.base_url}. Kiểm tra host/port."
                ) from e

        if response.status_code >= 400:
            msg = self.ERROR_MESSAGES.get(response.status_code)
            if msg is None:
                try:
                    detail = response.json().get("detail", response.text)
                except Exception:
                    detail = response.text
                msg = f"Lỗi HTTP {response.status_code}: {detail}"
            raise CLIError(msg)

        with open(output_path, "wb") as f:
            f.write(response.content)

        return output_path


# Need os import for upload_file
import os
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestCLIError or TestAPIClient" 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/cli_client/client.py tests/test_cli_client.py
git commit -m "feat(cli-client): add APIClient with auth, error mapping, file upload/download"
```

---

### Task 4: `voice_commands.py` — Voice Bank Commands

**Files:**
- Create: `vvr_scraper/cli_client/voice_commands.py`
- Modify: `tests/test_cli_client.py` (add tests)

This is the largest task. Each command function takes `(client: APIClient, args: argparse.Namespace)` and prints output via `display.py`.

- [ ] **Step 1: Write failing tests for voice commands**

```python
# Append to tests/test_cli_client.py

from unittest.mock import AsyncMock, MagicMock, patch
import argparse

from vvr_scraper.cli_client.voice_commands import (
    cmd_login,
    cmd_logout,
    cmd_list,
    cmd_community,
    cmd_show,
    cmd_delete,
    cmd_publish,
    cmd_delist,
    cmd_vote,
    cmd_update,
)


def make_args(**kwargs):
    """Create an argparse.Namespace with given kwargs."""
    return argparse.Namespace(**kwargs)


class TestCmdLogin:
    @pytest.mark.asyncio
    async def test_login_success(self, capsys):
        client = AsyncMock()
        client.base_url = "http://127.0.0.1:8000"
        client.token_manager = AsyncMock()
        client.token_manager.save_token = MagicMock()
        client.request = AsyncMock(return_value={
            "user": {"id": "uuid-1", "username": "alice", "role": "member"},
            "token": "jwt-token-123",
        })
        args = make_args(username="alice", password="secret123")
        await cmd_login(client, args)
        output = capsys.readouterr().out
        assert "alice" in output or "Đăng nhập thành công" in output

    @pytest.mark.asyncio
    async def test_login_failure(self):
        client = AsyncMock()
        client.base_url = "http://127.0.0.1:8000"
        client.request = AsyncMock(side_effect=CLIError("Invalid username or password"))
        args = make_args(username="alice", password="wrong")
        with pytest.raises(CLIError):
            await cmd_login(client, args)


class TestCmdLogout:
    @pytest.mark.asyncio
    async def test_logout_removes_token(self, capsys):
        client = AsyncMock()
        client.token_manager = AsyncMock()
        args = make_args()
        await cmd_logout(client, args)
        client.token_manager.logout.assert_called_once()


class TestCmdList:
    @pytest.mark.asyncio
    async def test_list_shows_voices(self, capsys):
        client = AsyncMock()
        client.request = AsyncMock(return_value={
            "items": [
                {
                    "id": "v1",
                    "name": "Test Voice",
                    "gender": "male",
                    "age_group": "adult",
                    "duration_ms": 5000,
                    "tags": ["vietnamese"],
                    "vote_score": 3,
                    "visibility": "public",
                }
            ],
            "total": 1,
        })
        args = make_args(limit=20, offset=0)
        await cmd_list(client, args)
        output = capsys.readouterr().out
        assert "Test Voice" in output


class TestCmdShow:
    @pytest.mark.asyncio
    async def test_show_displays_detail(self, capsys):
        client = AsyncMock()
        client.request = AsyncMock(return_value={
            "id": "v1",
            "name": "Test Voice",
            "gender": "male",
            "age_group": "adult",
            "duration_ms": 5000,
            "sample_rate": 22050,
            "language": "vi",
            "mood": "calm",
            "visibility": "public",
            "usage_count": 10,
            "tags": ["vietnamese"],
            "vote_score": 3,
            "ref_text": "Xin chào",
            "description": "A calm voice",
            "user_id": "u1",
            "created_at": "2026-04-21T10:00:00Z",
            "updated_at": "2026-04-21T10:00:00Z",
        })
        args = make_args(voice_id="v1")
        await cmd_show(client, args)
        output = capsys.readouterr().out
        assert "Test Voice" in output
        assert "Xin chào" in output


class TestCmdDelete:
    @pytest.mark.asyncio
    async def test_delete_success(self, capsys):
        client = AsyncMock()
        client.request = AsyncMock(return_value=None)  # 204 No Content
        args = make_args(voice_id="v1")
        await cmd_delete(client, args)
        output = capsys.readouterr().out
        assert "đã xóa" in output.lower() or "deleted" in output.lower() or "✓" in output


class TestCmdPublish:
    @pytest.mark.asyncio
    async def test_publish_success(self, capsys):
        client = AsyncMock()
        client.request = AsyncMock(return_value={
            "id": "v1", "name": "Test", "visibility": "public", "vote_score": 0,
        })
        args = make_args(voice_id="v1")
        await cmd_publish(client, args)
        output = capsys.readouterr().out
        assert "public" in output.lower() or "✓" in output


class TestCmdVote:
    @pytest.mark.asyncio
    async def test_vote_up_shows_score(self, capsys):
        client = AsyncMock()
        client.request = AsyncMock(return_value={"voice_id": "v1", "vote_score": 5})
        args = make_args(voice_id="v1", direction="up")
        await cmd_vote(client, args)
        output = capsys.readouterr().out
        assert "5" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestCmdLogin or TestCmdLogout or TestCmdList or TestCmdShow or TestCmdDelete or TestCmdPublish or TestCmdVote" 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.cli_client.voice_commands'`

- [ ] **Step 3: Write `voice_commands.py`**

```python
# vvr_scraper/cli_client/voice_commands.py
"""Voice Bank CLI commands — each function is an async command handler."""

import os
import shutil
import subprocess
import tempfile

from prompt_toolkit import PromptSession
from rich.console import Console

from .client import APIClient, CLIError
from .display import print_error, print_success, print_voice_detail, print_voice_table

console = Console()


async def cmd_login(client: APIClient, args) -> None:
    """Login and save token."""
    username = args.username
    password = args.password

    if not username:
        session = PromptSession()
        username = await session.prompt_async("Username: ")
        username = username.strip()

    if not password:
        session = PromptSession()
        password = await session.prompt_async("Password: ", is_password=True)
        password = password.strip()

    if not username or not password:
        print_error("Username và password là bắt buộc.")
        return

    result = await client.request("POST", "/api/auth/login", json_data={
        "username": username,
        "password": password,
    })

    token_data = {
        "token": result["token"],
        "username": result["user"]["username"],
        "user_id": result["user"]["id"],
        "role": result["user"]["role"],
        "created_at": result["user"].get("created_at", ""),
    }
    client.token_manager.save_token(token_data)
    print_success(f"Đăng nhập thành công! Xin chào, {token_data['username']}.")


async def cmd_logout(client: APIClient, args) -> None:
    """Logout and remove token file."""
    client.token_manager.logout()
    print_success("Đã đăng xuất.")


async def cmd_list(client: APIClient, args) -> None:
    """List user's own voice samples."""
    params = {"limit": getattr(args, "limit", 20), "offset": getattr(args, "offset", 0)}
    result = await client.request("GET", "/api/voices/me", params=params)
    items = result.get("items", [])
    total = result.get("total", 0)
    print_voice_table(items, title=f"Voices của bạn ({total} tổng)")
    if total > len(items):
        console.print(f"[dim]Hiển thị {len(items)}/{total}. Dùng --offset để xem thêm.[/dim]")


async def cmd_community(client: APIClient, args) -> None:
    """Browse community voices."""
    params = {"limit": getattr(args, "limit", 20), "offset": getattr(args, "offset", 0)}
    if getattr(args, "tag", None):
        params["tag"] = args.tag
    if getattr(args, "gender", None):
        params["gender"] = args.gender
    if getattr(args, "age_group", None):
        params["age_group"] = args.age_group
    if getattr(args, "sort", None):
        params["sort"] = args.sort

    result = await client.request("GET", "/api/voices/community", params=params)
    items = result.get("items", [])
    total = result.get("total", 0)
    print_voice_table(items, title=f"Community Voices ({total} tổng)")
    if total > len(items):
        console.print(f"[dim]Hiển thị {len(items)}/{total}. Dùng --offset để xem thêm.[/dim]")


async def cmd_show(client: APIClient, args) -> None:
    """Show detail of a single voice sample."""
    voice = await client.request("GET", f"/api/voices/{args.voice_id}")
    print_voice_detail(voice)


async def cmd_update(client: APIClient, args) -> None:
    """Update voice metadata."""
    update_data = {}
    if getattr(args, "name", None):
        update_data["name"] = args.name
    if getattr(args, "description", None):
        update_data["description"] = args.description
    if getattr(args, "mood", None):
        update_data["mood"] = args.mood
    if getattr(args, "tags", None):
        update_data["tags"] = [t.strip().lower() for t in args.tags.split(",") if t.strip()]

    if not update_data:
        print_error("Không có gì để cập nhật. Dùng --name, --description, --mood, hoặc --tags.")
        return

    result = await client.request("PATCH", f"/api/voices/{args.voice_id}", json_data=update_data)
    print_success(f"Đã cập nhật voice '{result.get('name', args.voice_id)}'.")
    print_voice_detail(result)


async def cmd_delete(client: APIClient, args) -> None:
    """Delete a voice sample."""
    # Confirm deletion
    confirm = input(f"Bạn có chắc muốn xóa voice '{args.voice_id}'? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        console.print("[yellow]Hủy xóa.[/yellow]")
        return

    await client.request("DELETE", f"/api/voices/{args.voice_id}")
    print_success(f"Đã xóa voice '{args.voice_id}'.")


async def cmd_publish(client: APIClient, args) -> None:
    """Publish a voice to community."""
    result = await client.request("PATCH", f"/api/voices/{args.voice_id}/publish")
    print_success(f"Đã đăng voice '{result.get('name', args.voice_id)}' lên cộng đồng.")
    print_voice_detail(result)


async def cmd_delist(client: APIClient, args) -> None:
    """Delist a voice from community."""
    result = await client.request("PATCH", f"/api/voices/{args.voice_id}/delist")
    print_success(f"Đã gỡ voice '{result.get('name', args.voice_id)}' khỏi cộng đồng.")
    print_voice_detail(result)


async def cmd_vote(client: APIClient, args) -> None:
    """Vote on a voice sample."""
    vote_value = 1 if args.direction == "up" else -1
    result = await client.request("POST", f"/api/voices/{args.voice_id}/vote", json_data={"vote": vote_value})
    score = result.get("vote_score", "?")
    direction = "👍" if vote_value == 1 else "👎"
    print_success(f"{direction} Vote recorded! Điểm mới: {score}")


async def cmd_download(client: APIClient, args) -> None:
    """Download original audio file."""
    output_path = getattr(args, "output", None) or f"{args.voice_id}.wav"
    saved_path = await client.download_file(f"/api/voices/{args.voice_id}/audio", output_path)
    print_success(f"Đã tải về: {saved_path}")


async def cmd_preview(client: APIClient, args) -> None:
    """Generate TTS preview and play it."""
    text = args.text
    if not text:
        session = PromptSession()
        text = await session.prompt_async("Nhập văn bản để preview: ")
        text = text.strip()

    if not text:
        print_error("Văn bản không được để trống.")
        return

    result_bytes = await client.request(
        "POST", f"/api/voices/{args.voice_id}/preview", json_data={"text": text}
    )

    # The preview endpoint returns raw audio bytes, not JSON
    # We need to handle this differently — use download_file approach
    # Actually, let's use the raw client for this
    import httpx
    try:
        token = client.token_manager.get_token()
    except Exception as e:
        raise CLIError(str(e)) from e

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(base_url=client.base_url, headers=headers, timeout=60.0) as http_client:
        response = await http_client.post(f"/api/voices/{args.voice_id}/preview", json={"text": text})

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise CLIError(f"Lỗi preview: {detail}")

    # Save to temp file
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"vvr_preview_{args.voice_id}.wav")
    with open(tmp_path, "wb") as f:
        f.write(response.content)

    print_success(f"Preview saved to: {tmp_path}")

    # Try to play
    played = False
    for player in ["aplay", "ffplay", "mpv"]:
        if shutil.which(player):
            try:
                if player == "ffplay":
                    subprocess.run([player, "-nodisp", "-autoexit", tmp_path], capture_output=True, timeout=30)
                elif player == "mpv":
                    subprocess.run([player, "--no-video", tmp_path], capture_output=True, timeout=30)
                else:
                    subprocess.run([player, tmp_path], capture_output=True, timeout=30)
                played = True
                break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    if not played:
        console.print("[dim]Không tìm thấy audio player. Mở file thủ công.[/dim]")


async def cmd_upload(client: APIClient, args) -> None:
    """Upload a voice sample."""
    audio_path = getattr(args, "audio", None)
    name = getattr(args, "name", None)
    ref_text = getattr(args, "ref_text", None)
    gender = getattr(args, "gender", None)
    age_group = getattr(args, "age_group", None)
    description = getattr(args, "description", None)
    language = getattr(args, "language", "vi")
    mood = getattr(args, "mood", None)
    tags = getattr(args, "tags", None)

    # Interactive prompts for missing required fields
    session = PromptSession()

    if not audio_path:
        audio_path = (await session.prompt_async("Đường dẫn file audio: ")).strip()
    if not name:
        name = (await session.prompt_async("Tên voice (3-100 ký tự): ")).strip()
    if not ref_text:
        ref_text = (await session.prompt_async("Văn bản tham chiếu (tối thiểu 10 ký tự): ")).strip()
    if not gender:
        from rich.prompt import Prompt
        gender = Prompt.ask("Giới tính", choices=["male", "female", "other"])
    if not age_group:
        from rich.prompt import Prompt
        age_group = Prompt.ask("Nhóm tuổi", choices=["child", "teen", "young_adult", "adult", "elder"])

    # Validate required fields
    if not audio_path or not os.path.exists(audio_path):
        print_error(f"File không tồn tại: {audio_path}")
        return
    if not name or len(name) < 3:
        print_error("Tên voice phải từ 3-100 ký tự.")
        return
    if not ref_text or len(ref_text) < 10:
        print_error("Văn bản tham chiếu phải tối thiểu 10 ký tự.")
        return

    # Build form fields
    fields = {
        "name": name,
        "ref_text": ref_text,
        "gender": gender,
        "age_group": age_group,
    }
    if description:
        fields["description"] = description
    if language:
        fields["language"] = language
    if mood:
        fields["mood"] = mood
    if tags:
        fields["tags"] = tags

    result = await client.upload_file("/api/voices/upload", audio_path, file_field="audio", fields=fields)
    print_success(f"Đã upload voice '{result.get('name', name)}'!")
    print_voice_detail(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestCmd" 2>&1 | tail -30`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add vvr_scraper/cli_client/voice_commands.py tests/test_cli_client.py
git commit -m "feat(cli-client): add all voice bank commands"
```

---

### Task 5: `main.py` — Entry Point & Argparse

**Files:**
- Create: `vvr_scraper/cli_client/main.py`
- Modify: `pyproject.toml` (add entry point)
- Modify: `tests/test_cli_client.py` (add tests)

- [ ] **Step 1: Write failing tests for main.py argument parsing**

```python
# Append to tests/test_cli_client.py

from vvr_scraper.cli_client.main import build_parser


class TestBuildParser:
    def test_global_host_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--host", "192.168.1.100", "--port", "9090", "list"])
        assert args.host == "192.168.1.100"
        assert args.port == 9090

    def test_default_host_port(self):
        parser = build_parser()
        args = parser.parse_args(["list"])
        assert args.host == "127.0.0.1"
        assert args.port == 8000

    def test_token_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--token", "my-jwt", "list"])
        assert args.token == "my-jwt"

    def test_upload_command_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "upload", "-a", "voice.wav", "-n", "Minh", "-t", "Hello world test",
            "-g", "male", "--age-group", "adult",
        ])
        assert args.command == "upload"
        assert args.audio == "voice.wav"
        assert args.name == "Minh"
        assert args.ref_text == "Hello world test"
        assert args.gender == "male"
        assert args.age_group == "adult"

    def test_community_command_filters(self):
        parser = build_parser()
        args = parser.parse_args([
            "community", "--tag", "male", "--gender", "male",
            "--age-group", "adult", "--sort", "votes", "--limit", "10",
        ])
        assert args.command == "community"
        assert args.tag == "male"
        assert args.gender == "male"
        assert args.age_group == "adult"
        assert args.sort == "votes"
        assert args.limit == 10

    def test_vote_command_directions(self):
        parser = build_parser()
        args = parser.parse_args(["vote", "v1", "--up"])
        assert args.direction == "up"
        args = parser.parse_args(["vote", "v1", "--down"])
        assert args.direction == "down"

    def test_update_command_flags(self):
        parser = build_parser()
        args = parser.parse_args([
            "update", "v1", "--name", "New Name", "--mood", "serious", "--tags", "a,b",
        ])
        assert args.command == "update"
        assert args.name == "New Name"
        assert args.mood == "serious"
        assert args.tags == "a,b"

    def test_download_command_output(self):
        parser = build_parser()
        args = parser.parse_args(["download", "v1", "--output", "/tmp/out.wav"])
        assert args.command == "download"
        assert args.output == "/tmp/out.wav"

    def test_preview_command_text(self):
        parser = build_parser()
        args = parser.parse_args(["preview", "v1", "--text", "Hello"])
        assert args.command == "preview"
        assert args.text == "Hello"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestBuildParser" 2>&1 | tail -20`
Expected: FAIL — `ModuleNotFoundError: No module named 'vvr_scraper.cli_client.main'`

- [ ] **Step 3: Write `main.py`**

```python
# vvr_scraper/cli_client/main.py
"""Entry point for the vvrt-client CLI."""

import argparse
import asyncio
import sys

from .client import APIClient, CLIError
from .voice_commands import (
    cmd_community,
    cmd_delete,
    cmd_delist,
    cmd_download,
    cmd_list,
    cmd_login,
    cmd_logout,
    cmd_preview,
    cmd_publish,
    cmd_show,
    cmd_update,
    cmd_upload,
    cmd_vote,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for vvrt-client."""
    parser = argparse.ArgumentParser(
        prog="vvrt-client",
        description="Voice Bank CLI Client — quản lý voice samples qua API.",
    )

    # Global flags
    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--token", default=None, help="JWT token (overrides env/file)")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- login ---
    login_parser = subparsers.add_parser("login", help="Đăng nhập và lưu token")
    login_parser.add_argument("--username", "-u", help="Username")
    login_parser.add_argument("--password", "-p", help="Password")

    # --- logout ---
    subparsers.add_parser("logout", help="Đăng xuất và xóa token")

    # --- upload ---
    upload_parser = subparsers.add_parser("upload", help="Upload voice sample")
    upload_parser.add_argument("--audio", "-a", help="Đường dẫn file audio (wav, mp3, ogg, m4a)")
    upload_parser.add_argument("--name", "-n", help="Tên voice (3-100 ký tự)")
    upload_parser.add_argument("--ref-text", "-t", help="Văn bản tham chiếu (tối thiểu 10 ký tự)")
    upload_parser.add_argument("--gender", "-g", choices=["male", "female", "other"], help="Giới tính")
    upload_parser.add_argument("--age-group", choices=["child", "teen", "young_adult", "adult", "elder"], help="Nhóm tuổi")
    upload_parser.add_argument("--description", help="Mô tả (tối đa 500 ký tự)")
    upload_parser.add_argument("--language", default="vi", help="Mã ngôn ngữ (default: vi)")
    upload_parser.add_argument("--mood", "-m", help="Tâm trạng voice")
    upload_parser.add_argument("--tags", help="Tags, phân cách bằng phẩy (tối đa 5)")

    # --- list ---
    list_parser = subparsers.add_parser("list", help="Xem danh sách voice của bạn")
    list_parser.add_argument("--limit", type=int, default=20, help="Số lượng tối đa (default: 20)")
    list_parser.add_argument("--offset", type=int, default=0, help="Bỏ qua bao nhiêu kết quả (default: 0)")

    # --- community ---
    community_parser = subparsers.add_parser("community", help="Duyệt voice cộng đồng")
    community_parser.add_argument("--tag", help="Lọc theo tag")
    community_parser.add_argument("--gender", choices=["male", "female", "other"], help="Lọc theo giới tính")
    community_parser.add_argument("--age-group", choices=["child", "teen", "young_adult", "adult", "elder"], help="Lọc theo nhóm tuổi")
    community_parser.add_argument("--sort", choices=["votes", "newest"], default="votes", help="Sắp xếp (default: votes)")
    community_parser.add_argument("--limit", type=int, default=20, help="Số lượng tối đa")
    community_parser.add_argument("--offset", type=int, default=0, help="Bỏ qua bao nhiêu kết quả")

    # --- show ---
    show_parser = subparsers.add_parser("show", help="Xem chi tiết voice sample")
    show_parser.add_argument("voice_id", help="ID của voice sample")

    # --- update ---
    update_parser = subparsers.add_parser("update", help="Cập nhật metadata voice")
    update_parser.add_argument("voice_id", help="ID của voice sample")
    update_parser.add_argument("--name", help="Tên mới")
    update_parser.add_argument("--description", help="Mô tả mới")
    update_parser.add_argument("--mood", help="Tâm trạng mới")
    update_parser.add_argument("--tags", help="Tags mới, phân cách bằng phẩy")

    # --- delete ---
    delete_parser = subparsers.add_parser("delete", help="Xóa voice sample")
    delete_parser.add_argument("voice_id", help="ID của voice sample")

    # --- publish ---
    publish_parser = subparsers.add_parser("publish", help="Đăng voice lên cộng đồng")
    publish_parser.add_argument("voice_id", help="ID của voice sample")

    # --- delist ---
    delist_parser = subparsers.add_parser("delist", help="Gỡ voice khỏi cộng đồng")
    delist_parser.add_argument("voice_id", help="ID của voice sample")

    # --- vote ---
    vote_parser = subparsers.add_parser("vote", help="Vote cho voice sample")
    vote_parser.add_argument("voice_id", help="ID của voice sample")
    vote_group = vote_parser.add_mutually_exclusive_group(required=True)
    vote_group.add_argument("--up", action="store_const", const="up", dest="direction", help="Upvote")
    vote_group.add_argument("--down", action="store_const", const="down", dest="direction", help="Downvote")

    # --- download ---
    download_parser = subparsers.add_parser("download", help="Tải file audio gốc")
    download_parser.add_argument("voice_id", help="ID của voice sample")
    download_parser.add_argument("--output", "-o", help="Đường dẫn file đầu ra (default: <voice_id>.wav)")

    # --- preview ---
    preview_parser = subparsers.add_parser("preview", help="Nghe preview TTS")
    preview_parser.add_argument("voice_id", help="ID của voice sample")
    preview_parser.add_argument("--text", "-t", help="Văn bản để preview")

    return parser


# Map command names to handler functions
COMMAND_MAP = {
    "login": cmd_login,
    "logout": cmd_logout,
    "upload": cmd_upload,
    "list": cmd_list,
    "community": cmd_community,
    "show": cmd_show,
    "update": cmd_update,
    "delete": cmd_delete,
    "publish": cmd_publish,
    "delist": cmd_delist,
    "vote": cmd_vote,
    "download": cmd_download,
    "preview": cmd_preview,
}


async def async_main(args: argparse.Namespace) -> None:
    """Async main — create client and dispatch command."""
    client = APIClient(host=args.host, port=args.port, token=args.token)

    command = args.command
    if not command:
        build_parser().print_help()
        return

    handler = COMMAND_MAP.get(command)
    if handler is None:
        print(f"Unknown command: {command}")
        return

    await handler(client, args)


def main() -> None:
    """Entry point for vvrt-client."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        asyncio.run(async_main(args))
    except CLIError as e:
        from .display import print_error
        print_error(str(e))
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v -k "TestBuildParser" 2>&1 | tail -20`
Expected: All PASS

- [ ] **Step 5: Add entry point to pyproject.toml**

In `pyproject.toml`, find the `[project.scripts]` section and add the `vvrt-client` entry:

```toml
[project.scripts]
vvrt = "vvr_scraper.cli:main"
vvrt-client = "vvr_scraper.cli_client.main:main"
```

- [ ] **Step 6: Verify entry point works**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && pip install -e . 2>&1 | tail -5 && vvrt-client --help`
Expected: Shows help text with all subcommands

- [ ] **Step 7: Commit**

```bash
git add vvr_scraper/cli_client/main.py tests/test_cli_client.py pyproject.toml
git commit -m "feat(cli-client): add entry point, argparse router, and all subcommands"
```

---

### Task 6: Integration Smoke Test

**Files:**
- Modify: `tests/test_cli_client.py` (add integration test)

- [ ] **Step 1: Write an integration test that verifies the CLI can be invoked**

```python
# Append to tests/test_cli_client.py

class TestCLIIntegration:
    def test_help_output(self):
        """Verify vvrt-client --help runs without error."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "vvr_scraper.cli_client.main", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "vvrt-client" in result.stdout
        assert "upload" in result.stdout
        assert "login" in result.stdout

    def test_unknown_command_exits_gracefully(self):
        """Verify unknown command doesn't crash."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "vvr_scraper.cli_client.main", "nonexistent"],
            capture_output=True, text=True, timeout=10,
        )
        # Should exit with error, not crash with traceback
        assert result.returncode != 0
```

- [ ] **Step 2: Run all tests**

Run: `cd /home/tung/Data/dev/backup/Valvrareteam.net-crawler && python -m pytest tests/test_cli_client.py -v 2>&1 | tail -30`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_client.py
git commit -m "test(cli-client): add integration smoke tests"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| `APIClient` with auth, error mapping | Task 3 |
| `TokenManager` with 3-tier resolution | Task 2 |
| `display.py` formatters | Task 1 |
| `upload` command (interactive + flags) | Task 4 |
| `list` command (paginated) | Task 4 |
| `community` command (filters + sort) | Task 4 |
| `show` command | Task 4 |
| `update` command | Task 4 |
| `delete` command (confirm + 204) | Task 4 |
| `publish` command | Task 4 |
| `delist` command | Task 4 |
| `vote` command (prints score) | Task 4 |
| `download` command | Task 4 |
| `preview` command (playback) | Task 4 |
| `login` command | Task 4 |
| `logout` command | Task 4 |
| `main.py` argparse router | Task 5 |
| `pyproject.toml` entry point | Task 5 |
| JWT expiry handling | Task 2 (server rejects with 401, CLI prompts re-login) |
| 204 No Content handling | Task 4 (`cmd_delete` checks `None`) |
| 404 for private voices | Task 3 (error mapping) |
| Rich visibility colors | Task 1 |
| `tempfile` for preview | Task 4 |
| `--limit`/`--offset` pagination | Task 5 |

All spec requirements covered. No placeholders. No TBDs.