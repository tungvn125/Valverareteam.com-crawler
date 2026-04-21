"""HTTP API client for the Voice Bank CLI."""

from pathlib import Path
from typing import Any

import httpx

from .auth_manager import AuthenticationRequired, TokenManager


class CLIError(Exception):
    """Custom exception for CLI errors with exit code."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


class APIClient:
    """HTTP client for Voice Bank API with authentication and error handling."""

    ERROR_MESSAGES: dict[int, str] = {
        401: "Chưa đăng nhập. Chạy `vvrt-client login`",
        403: "Không có quyền thực hiện",
        404: "Không tìm thấy voice sample",
        413: "File quá lớn (tối đa 30MB)",
        429: "Quá nhiều request, thử lại sau",
        500: "Lỗi server",
    }

    def __init__(self, host: str = "127.0.0.1", port: int = 8000, token: str | None = None):
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
        auth: bool = True,
    ) -> Any:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (without base URL)
            params: Query parameters
            json_data: JSON body data
            files: Files to upload (for multipart)
            data: Form data (for multipart)
            timeout: Request timeout in seconds
            auth: Whether to require authentication (default True).
                Set to False for login/register endpoints.

        Returns:
            Parsed JSON response, or None for 204 responses

        Raises:
            CLIError: On connection errors or HTTP error responses
        """
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}

        if auth:
            try:
                token = self.token_manager.get_token()
            except AuthenticationRequired as e:
                raise CLIError(str(e), exit_code=1) from None
            headers["Authorization"] = f"Bearer {token}"

        # Don't set Content-Type for multipart uploads (httpx sets it with boundary)
        if files is None:
            headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_data,
                    files=files,
                    data=data,
                    timeout=timeout,
                )
            except httpx.ConnectError as e:
                raise CLIError(
                    f"Không thể kết nối đến server tại {self.base_url}. Vui lòng kiểm tra server đã chạy chưa.",
                    exit_code=1,
                ) from e

        # Handle 204 No Content
        if response.status_code == 204:
            return None

        # Handle error responses
        if response.status_code >= 400:
            message = self.ERROR_MESSAGES.get(response.status_code, f"HTTP {response.status_code}: {response.text}")
            raise CLIError(message, exit_code=1)

        # Return parsed JSON
        return response.json()

    async def upload_file(
        self,
        path: str,
        file_path: str,
        file_field: str = "audio",
        fields: dict | None = None,
    ) -> Any:
        """Upload a file via multipart/form-data.

        Args:
            path: API endpoint path
            file_path: Path to the file to upload
            file_field: Name of the file field in the form
            fields: Additional form fields

        Returns:
            Parsed JSON response

        Raises:
            CLIError: On file not found, connection errors, or HTTP errors
        """
        # Get token from TokenManager
        try:
            token = self.token_manager.get_token()
        except AuthenticationRequired as e:
            raise CLIError(str(e), exit_code=1) from None

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise CLIError(f"File không tồn tại: {file_path}", exit_code=1)

        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        # Prepare additional fields
        data = fields or {}

        with file_path_obj.open("rb") as f:
            files = {
                file_field: (
                    file_path_obj.name,
                    f,
                    self._guess_mime_type(file_path_obj.suffix),
                )
            }

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        url=url,
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=60.0,  # Longer timeout for uploads
                    )
                except httpx.ConnectError as e:
                    raise CLIError(
                        f"Không thể kết nối đến server tại {self.base_url}. Vui lòng kiểm tra server đã chạy chưa.",
                        exit_code=1,
                    ) from e

        # Handle error responses
        if response.status_code >= 400:
            message = self.ERROR_MESSAGES.get(response.status_code, f"HTTP {response.status_code}: {response.text}")
            raise CLIError(message, exit_code=1)

        # Return parsed JSON
        return response.json()

    async def download_file(self, path: str, output_path: str) -> str:
        """Download a file from the server.

        Args:
            path: API endpoint path
            output_path: Path where the file should be saved

        Returns:
            The output path where the file was saved

        Raises:
            CLIError: On connection errors, HTTP errors, or IO errors
        """
        # Get token from TokenManager
        try:
            token = self.token_manager.get_token()
        except AuthenticationRequired as e:
            raise CLIError(str(e), exit_code=1) from None

        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url=url,
                    headers=headers,
                    timeout=60.0,  # Longer timeout for downloads
                )
            except httpx.ConnectError as e:
                raise CLIError(
                    f"Không thể kết nối đến server tại {self.base_url}. Vui lòng kiểm tra server đã chạy chưa.",
                    exit_code=1,
                ) from e

        # Handle error responses
        if response.status_code >= 400:
            message = self.ERROR_MESSAGES.get(response.status_code, f"HTTP {response.status_code}: {response.text}")
            raise CLIError(message, exit_code=1)

        # Save the file
        try:
            output_path_obj.write_bytes(response.content)
        except OSError as e:
            raise CLIError(
                f"Không thể ghi file: {output_path}",
                exit_code=1,
            ) from e

        return str(output_path_obj)

    def _guess_mime_type(self, extension: str) -> str:
        """Guess MIME type from file extension."""
        mime_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".json": "application/json",
            ".txt": "text/plain",
        }
        return mime_types.get(extension.lower(), "application/octet-stream")
