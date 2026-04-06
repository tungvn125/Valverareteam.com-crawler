import json
import os
import freesound
import tempfile
import httpx
import asyncio
from pathlib import Path
from typing import Dict, Optional, List
from pydub import AudioSegment
from loguru import logger
from .utils import get_config_path

class FreesoundManager:
    """
    Manages background music from Freesound.org using OAuth2 authentication.
    """

    def __init__(self, 
                 client_id: Optional[str] = None, 
                 client_secret: Optional[str] = None,
                 auth_file: Optional[str] = None):
        self.client_id = client_id or os.getenv("FREESOUND_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("FREESOUND_CLIENT_SECRET")
        
        # Use get_config_path for default auth file
        if auth_file:
            self.auth_file = Path(auth_file)
        else:
            self.auth_file = Path(get_config_path(".vvr_freesound_auth.json"))
            
        self.client = freesound.FreesoundClient()
        self.token: Optional[Dict[str, str]] = None
        
        self._load_token()

    def _load_token(self):
        """Loads OAuth2 token from file and sets it in the client."""
        if self.auth_file.exists():
            try:
                with open(self.auth_file, "r") as f:
                    self.token = json.load(f)
                
                if self.token and "access_token" in self.token:
                    self.client.set_token(self.token["access_token"], "oauth")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load Freesound token from {self.auth_file}: {e}")

    def save_token(self, token_data: Dict[str, str]):
        """Saves OAuth2 token to file."""
        self.token = token_data
        with open(self.auth_file, "w") as f:
            json.dump(token_data, f)
        
        if "access_token" in self.token:
            self.client.set_token(self.token["access_token"], "oauth")

    def get_auth_url(self) -> str:
        """Returns the Freesound OAuth2 authorization URL."""
        if not self.client_id:
            raise ValueError("FREESOUND_CLIENT_ID is not set.")
        return f"https://freesound.org/apiv2/oauth2/authorize/?client_id={self.client_id}&response_type=code"

    async def exchange_code(self, code: str) -> Dict[str, str]:
        """Exchanges an authorization code for an access token."""
        if not self.client_id or not self.client_secret:
            raise ValueError("FREESOUND_CLIENT_ID or FREESOUND_CLIENT_SECRET is not set.")

        url = "https://freesound.org/apiv2/oauth2/access_token/"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data)
            if response.status_code != 200:
                raise Exception(f"Failed to exchange code: {response.text}")
            
            token_data = response.json()
            self.save_token(token_data)
            return token_data

    async def search_bgm(self, tags: List[str], limit: int = 10) -> List[freesound.Sound]:
        """Async wrapper for searching BGM."""
        return await asyncio.to_thread(self._search_bgm_sync, tags, limit)

    def _search_bgm_sync(self, tags: List[str], limit: int = 10) -> List[freesound.Sound]:
        """
        Searches for BGM based on tags (Synchronous).
        Prioritizes loop, music, ambient tags and lossless formats (wav/flac).
        """
        query = " ".join(tags)
        # Filter for original high-quality files (wav/flac)
        filter_str = "type:(wav OR flac)"
        
        results = self.client.text_search(
            query=query,
            filter=filter_str,
            fields="id,name,tags,type,previews,url",
            page_size=limit
        )
        
        return list(results.results)

    async def download_and_convert(self, sound_id: int, output_path: str) -> str:
        """Async wrapper for downloading and converting."""
        return await asyncio.to_thread(self._download_and_convert_sync, sound_id, output_path)

    def _download_and_convert_sync(self, sound_id: int, output_path: str) -> str:
        """
        Downloads a sound from Freesound and converts it to a standard WAV format (44.1kHz).
        (Synchronous)
        """
        sound = self.client.get_sound(sound_id)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # retrieve(directory) downloads the original file (WAV/FLAC)
            sound.retrieve(temp_dir)
            
            # Find the downloaded file in the temp directory
            downloaded_files = os.listdir(temp_dir)
            if not downloaded_files:
                raise RuntimeError(f"Failed to download sound {sound_id}")
            
            temp_file_path = os.path.join(temp_dir, downloaded_files[0])
            
            # Load with pydub and export to standard WAV 44.1kHz
            audio = AudioSegment.from_file(temp_file_path)
            audio.export(output_path, format="wav", parameters=["-ar", "44100"])
            
        return output_path
