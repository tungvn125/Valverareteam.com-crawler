import json
import os
import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
from loguru import logger

class VideoMetadata(BaseModel):
    title: str = Field(description="Catchy YouTube title")
    description: str = Field(description="Detailed SEO description")
    tags: List[str] = Field(description="Relevants SEO tags", default_factory=list)

class AIHelper:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None

    async def generate_metadata(self, chapter_text: str, story_info: Dict[str, Any]) -> VideoMetadata:
        """Generates viral metadata for a novel chapter using an LLM."""
        if not self.client:
            logger.warning("OpenAI client not configured. Using fallback metadata.")
            return self._get_fallback_metadata(story_info)

        story_title = story_info.get("title", "Unknown Novel")
        prompt = f"""
        You are a YouTube SEO expert specializing in web novel audiobooks for the Vietnamese audience.
        Analyze the following chapter content from the novel "{story_title}" and generate catchy, viral metadata.

        Instructions:
        1. Title: Create a clickbait, viral title in Vietnamese (e.g., "SỐC! Hành Động Cực Gắt Của [Nhân Vật]...").
        2. Description: Detailed SEO-friendly description in Vietnamese, including:
           - A compelling "hook" in the first 2 lines.
           - A brief, intriguing summary of the chapter.
           - Relevant keywords for "Truyện audio", "Tiên hiệp", "Huyền huyễn", or similar genres.
        3. Tags: 10-15 relevant SEO tags in Vietnamese.

        The tone should be dramatic and engaging, suitable for the Vietnamese "truyện audio" community.

        Return ONLY a JSON object matching this schema:
        {{
            "title": "...",
            "description": "...",
            "tags": ["tag1", "tag2", ...]
        }}

        Chapter Content (first 2000 chars):
        {chapter_text[:2000]}
        """

        try:
            response = await self.client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-3.5-turbo"),
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            data = self._parse_json(content)
            return VideoMetadata(**data)
        except Exception as e:
            logger.error(f"Error generating AI metadata: {e}")
            return self._get_fallback_metadata(story_info)

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Robustly parses JSON from LLM response, handling Markdown blocks."""
        # Try direct parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown blocks
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            
            # Last resort: try to find anything that looks like a JSON object
            match = re.search(r"(\{.*?\})", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            
            raise

    def _get_fallback_metadata(self, story_info: Dict[str, Any]) -> VideoMetadata:
        title = story_info.get("title", "Novel")
        return VideoMetadata(
            title=f"{title} - Audiobook Chapter",
            description=f"Audiobook for {title}. Chapter content from Valvrare Team.",
            tags=[title, "audiobook", "web novel", "valvrareteam"]
        )
