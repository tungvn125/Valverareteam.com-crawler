import asyncio
import hashlib
import io
import os

import httpx
import openai
from loguru import logger
from openai import AsyncOpenAI
from PIL import Image


class ImageGenerator:
    def __init__(self, cache_dir: str = "backgrounds", api_key: str | None = None):
        self.cache_dir = cache_dir
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found in environment. Image generation will fail.")

        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        # Add shared httpx client and semaphore
        self.httpx_client = httpx.AsyncClient(timeout=60.0)
        self._semaphore = asyncio.Semaphore(2)

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

    async def close(self):
        """Closes the shared httpx client."""
        await self.httpx_client.aclose()

    def _get_hash(self, prompt: str) -> str:
        """Returns the SHA-256 hash of the prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    async def generate(self, prompt: str, output_path: str | None = None) -> str:
        """
        Generates an image from a prompt using DALL-E 3.
        Uses deduplication based on prompt hash.
        Converts the image to WebP format.
        """
        prompt_hash = self._get_hash(prompt)
        filename = f"{prompt_hash}.webp"

        # Determine final_path
        if not output_path:
            final_path = os.path.join(self.cache_dir, filename)
        else:
            if os.path.isdir(output_path):
                final_path = os.path.join(output_path, filename)
            else:
                # Use provided path but ensure .webp extension
                base, _ = os.path.splitext(output_path)
                final_path = base + ".webp"

        # Check for deduplication
        if os.path.exists(final_path):
            logger.info(f"Using cached image for prompt: {prompt[:30]}... -> {final_path}")
            return final_path

        if not self.client:
            raise ValueError("OpenAI client not initialized. Check OPENAI_API_KEY.")

        return await self._generate_new(prompt, final_path)

    async def _generate_new(self, prompt: str, final_path: str) -> str:
        """Actually calls DALL-E and saves the image with concurrency limit and robust error handling."""
        async with self._semaphore:
            logger.info(f"Generating new image for prompt: {prompt[:50]}...")

            try:
                response = await self.client.images.generate(
                    model="dall-e-3",
                    prompt=prompt,
                    size="1024x1024",  # or "1792x1024" for wide
                    quality="standard",
                    n=1,
                )

                if not response.data:
                    raise Exception("No image data in OpenAI response")

                image_url = response.data[0].url
                if not image_url:
                    raise Exception("No image URL returned from OpenAI")

                # Download image using shared client
                try:
                    resp = await self.httpx_client.get(image_url)
                    resp.raise_for_status()
                    image_data = resp.content
                except httpx.HTTPError as e:
                    logger.error(f"Network error during image download: {e}")
                    raise

                # Convert to WebP and save
                try:
                    await asyncio.to_thread(self._save_as_webp, image_data, final_path)
                except Exception as e:
                    logger.error(f"Image processing error: {e}")
                    raise

                logger.info(f"Image saved to {final_path}")
                return final_path

            except openai.OpenAIError as e:
                logger.error(f"OpenAI API error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in image generation: {e}")
                raise

    def _save_as_webp(self, image_data: bytes, output_path: str):
        """Converts raw image data (PNG/JPG) to WebP using Pillow."""
        try:
            img = Image.open(io.BytesIO(image_data))
            # Ensure directory exists for final_path
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            # Add RGB conversion for maximum compatibility
            img = img.convert("RGB")
            img.save(output_path, format="WEBP", quality=80)
        except Exception as e:
            logger.error(f"Failed to save image as WebP: {e}")
            raise
