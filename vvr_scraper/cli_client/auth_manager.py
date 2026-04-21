"""Authentication manager for Voice Bank CLI Client."""

import json
import os
from pathlib import Path


class AuthenticationRequired(Exception):
    """Raised when no valid authentication token is available."""

    pass


class TokenManager:
    """Manages JWT tokens for API authentication."""

    def __init__(self, token: str | None = None, token_path: str | None = None):
        self._token = token
        self._token_path = token_path or self._default_token_path()

    @staticmethod
    def _default_token_path() -> str:
        """Returns ~/.config/vvr-scraper/token.json, creating dir if needed."""
        config_dir = Path.home() / ".config" / "vvr-scraper"
        config_dir.mkdir(parents=True, exist_ok=True)
        return str(config_dir / "token.json")

    def get_token(self) -> str:
        """Return token from: constructor -> env var -> file.

        Raises:
            AuthenticationRequired: If no token is found.
        """
        # 1. Check constructor-provided token (highest priority)
        if self._token is not None:
            return self._token

        # 2. Check environment variable
        env_token = os.environ.get("VVR_TOKEN")
        if env_token is not None:
            return env_token

        # 3. Check token file
        if os.path.exists(self._token_path):
            try:
                with open(self._token_path) as f:
                    data = json.load(f)
                token = data.get("token")
                if token is not None:
                    return token
            except (OSError, json.JSONDecodeError):
                pass

        # No token found
        raise AuthenticationRequired("No valid authentication token available")

    def is_authenticated(self) -> bool:
        """Return True if token available, False otherwise (no exception)."""
        try:
            self.get_token()
            return True
        except AuthenticationRequired:
            return False

    def save_token(self, token_data: dict) -> None:
        """Save token dict as JSON to token file."""
        # Ensure directory exists
        token_dir = os.path.dirname(self._token_path)
        if token_dir:
            os.makedirs(token_dir, exist_ok=True)

        with open(self._token_path, "w") as f:
            json.dump(token_data, f, indent=2)

    def logout(self) -> None:
        """Delete token file if it exists."""
        if os.path.exists(self._token_path):
            os.remove(self._token_path)
