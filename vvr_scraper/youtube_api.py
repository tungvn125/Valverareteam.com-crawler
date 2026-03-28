import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from loguru import logger

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

class YouTubeClient:
    def __init__(self, client_secrets_path: str = "client_secrets.json", token_path: str = ".youtube_token.json", dry_run: bool = False):
        self.client_secrets_path = client_secrets_path
        self.token_path = token_path
        self.dry_run = dry_run
        self.service = self._authenticate()
        self.quota_path = ".youtube_quota.json"

    def _authenticate(self):
        """Handles YouTube OAuth 2.0 authentication."""
        creds = None
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secrets_path):
                    logger.warning(f"YouTube credentials not found at {self.client_secrets_path}. Skipping auth.")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secrets_path, SCOPES)
                creds = flow.run_local_server(port=0)
            
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        return build('youtube', 'v3', credentials=creds)

    def get_remaining_quota(self) -> int:
        """Returns the remaining daily quota (estimated)."""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Daily limit is usually 10,000 units. 
        # For simplicity, we track locally in a file.
        if not os.path.exists(self.quota_path):
            self._write_quota(10000, today)
            return 10000
        
        try:
            with open(self.quota_path, 'r') as f:
                data = json.load(f)
                last_reset = data.get("last_reset")
                if last_reset != today:
                    self._write_quota(10000, today)
                    return 10000
                return data.get("remaining", 10000)
        except Exception as e:
            logger.error(f"Error reading quota file: {e}")
            return 10000

    def _update_quota(self, cost: int):
        """Updates the local quota tracker."""
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        current = self.get_remaining_quota()
        self._write_quota(max(0, current - cost), today)

    def _write_quota(self, remaining: int, last_reset: str):
        """Writes the quota state to a file."""
        with open(self.quota_path, 'w') as f:
            json.dump({"remaining": remaining, "last_reset": last_reset}, f)

    async def upload_video(self, file_path: str, metadata: Dict[str, Any]) -> str:
        """Uploads a video to YouTube with the provided metadata."""
        if self.dry_run:
            import uuid
            video_id = f"dry_run_{uuid.uuid4().hex[:8]}"
            logger.info(f"[DRY RUN] Simulating upload of {file_path}. Generated ID: {video_id}")
            return video_id

        if not self.service:
            raise Exception("YouTube service not authenticated")

        # Each upload costs 1600 quota units
        if self.get_remaining_quota() < 1600:
            raise Exception("Insufficient YouTube API quota")

        body = {
            'snippet': {
                'title': metadata.get('title', 'Novel Audiobook'),
                'description': metadata.get('description', ''),
                'tags': metadata.get('tags', []),
                'categoryId': '24' # Entertainment
            },
            'status': {
                'privacyStatus': metadata.get('privacy', 'public'),
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(
            file_path,
            mimetype='video/mp4',
            resumable=True
        )

        logger.info(f"Uploading {file_path} to YouTube...")
        
        # Wrapping synchronous call in to_thread
        def _execute_upload():
            request = self.service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            return request.execute()

        response = await asyncio.to_thread(_execute_upload)
        self._update_quota(1600)
        
        video_id = response.get('id')
        logger.success(f"Successfully uploaded video to YouTube. ID: {video_id}")
        return video_id
