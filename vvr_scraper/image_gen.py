import os
import hashlib
import asyncio
import io
from typing import Optional
import httpx
from openai import AsyncOpenAI
from PIL import Image
from loguru import logger

class ImageGenerator:
    def __init__(self, cache_dir: str = "backgrounds", api_key: Optional[str] = None):
        self.cache_dir = cache_dir
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found in environment. Image generation will fail.")
        
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_hash(self, prompt: str) -> str:
        """Returns the SHA-256 hash of the prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    async def generate(self, prompt: str, output_path: Optional[str] = None) -> str:
        """
        Generates an image from a prompt using DALL-E 3.
        Uses deduplication based on prompt hash.
        Converts the image to WebP format.
        """
        prompt_hash = self._get_hash(prompt)
        
        # If output_path is not provided, use the hash-based name in cache_dir
        if not output_path:
            filename = f"{prompt_hash}.webp"
            final_path = os.path.join(self.cache_dir, filename)
        else:
            # If output_path is a directory, use hash-based filename within it
            if os.path.isdir(output_path):
                filename = f"{prompt_hash}.webp"
                final_path = os.path.join(output_path, filename)
            else:
                # If output_path is a file path, ensure it ends with .webp or change it?
                # The requirement says "convert to WebP".
                base, ext = os.path.splitext(output_path)
                final_path = base + ".webp"

        # Check for deduplication
        if os.path.exists(final_path):
            logger.info(f"Using cached image for prompt: {prompt[:30]}... -> {final_path}")
            return final_path

        if not self.client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY.")

        return await self._generate_new(prompt, final_path)

    async def _generate_new(self, prompt: str, final_path: str) -> str:
        """Actually calls DALL-E and saves the image."""
        logger.info(f"Generating new image for prompt: {prompt[:50]}...")
        
        try:
            response = await self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024", # or "1792x1024" for wide
                quality="standard",
                n=1,
            )
            
            image_url = response.data[0].url
            if not image_url:
                raise Exception("No image URL returned from OpenAI")

            # Download image
            async with httpx.AsyncClient() as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                image_data = resp.content

            # Convert to WebP and save
            await asyncio.to_thread(self._save_as_webp, image_data, final_path)
            
            logger.info(f"Image saved to {final_path}")
            return final_path

        except Exception as e:
            logger.error(f"Failed to generate image: {e}")
            raise

    def _save_as_webp(self, image_data: bytes, output_path: str):
        """Converts raw image data (PNG/JPG) to WebP using Pillow."""
        img = Image.open(io.BytesIO(image_data))
        # Ensure directory exists for final_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, format="WEBP", quality=80)
