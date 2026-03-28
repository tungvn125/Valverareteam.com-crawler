import asyncio
import os
import json
import tempfile
from typing import List, Dict, Any, Optional
import httpx
from playwright.async_api import async_playwright
from loguru import logger

from .db import DatabaseManager
from .scraper_core import lay_thong_tin_truyen, scrape_chapters
from .exporter import tao_file_mp3
from .ai_helper import AIHelper
from .video_engine import VideoEngine
from .youtube_api import YouTubeClient
from .models import ContentItem, story_info_to_dict
from .utils import HEADERS, sanitize_filename
from . import tao_so_do_cay

BASE_URL = "https://valvrareteam.net"

class Publisher:
    def __init__(self, db_path: str = "vvr_library.db"):
        self.db = DatabaseManager(db_path)
        self.ai = AIHelper()
        self.video = VideoEngine()
        self.yt = YouTubeClient()

    async def run_pipeline(self, slug: str, chapters: Optional[List[int]] = None, dry_run: bool = False, ai_off: bool = False):
        """Orchestrates the scraping, tts, ai, video, and youtube publication for a specific novel."""
        await self.db.init_db()
        
        # 1. Resolve Story Info & Chapter Tree
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            story_info_obj = await lay_thong_tin_truyen(client, slug)
            story_info = story_info_to_dict(story_info_obj)

        logger.info(f"Fetching chapter list for {slug}...")
        temp_list = f"temp_{slug}_chapters.json"
        await tao_so_do_cay.get_chapter_tree_list(f"{BASE_URL}/{slug}", output_file=temp_list)
        
        with open(temp_list, "r", encoding="utf-8") as f:
            full_tree = json.load(f)
        
        flat_chapters = [c for v in full_tree for c in v['chapters']]
        
        # Filter chapters if specific indices provided
        selected_chapters = []
        if chapters:
            for idx in chapters:
                if 0 < idx <= len(flat_chapters):
                    selected_chapters.append(flat_chapters[idx-1])
        else:
            # If no chapters specified, we might want to check the queue first 
            # or just take the latest. For run_pipeline(slug), let's assume 
            # we want to queue all new chapters.
            selected_chapters = flat_chapters

        if os.path.exists(temp_list):
            os.remove(temp_list)

        # 2. Queue the chapters
        for chap in selected_chapters:
            url = f"{BASE_URL}{chap['url']}" if chap['url'].startswith('/') else chap['url']
            
            existing_task = await self.db.get_task_by_url(url)
            if existing_task:
                if existing_task['status'] == 'FAILED':
                    # Retry failed tasks
                    logger.info(f"Retrying failed task: {url}")
                    await self.db.update_task_status(url, "PENDING")
                else:
                    # Preserve progress (AUDIO_READY, VIDEO_READY, PUBLISHED)
                    logger.info(f"Task for {url} already exists with status: {existing_task['status']}")
            else:
                task_data = {
                    "novel_slug": slug,
                    "chapter_url": url,
                    "status": "PENDING"
                }
                await self.db.upsert_publishing_task(task_data)
        
        # 3. Process the queue for this slug
        await self.process_queue(slug=slug, dry_run=dry_run, ai_off=ai_off)

    async def process_queue(self, slug: Optional[str] = None, dry_run: bool = False, ai_off: bool = False):
        """Processes pending tasks in the publishing queue."""
        await self.db.init_db()
        tasks = await self.db.get_pending_tasks()
        
        if slug:
            tasks = [t for t in tasks if t['novel_slug'] == slug]
        
        if not tasks:
            logger.info("No pending tasks to process.")
            return

        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        from rich.console import Console
        console = Console()

        logger.info(f"Processing {len(tasks)} tasks from the queue...")
        
        # Cache for story info to avoid redundant fetches
        story_info_cache = {}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=False
            ) as progress:
                overall_task = progress.add_task(f"[cyan]Processing queue...", total=len(tasks))
                
                for task in tasks:
                    url = task['chapter_url']
                    novel_slug = task['novel_slug']
                    status = task['status']
                    
                    progress.update(overall_task, description=f"[yellow]Current: {url} ({status})")
                    logger.info(f"--- Task: {url} (Status: {status}) ---")
                    
                    try:
                        # 0. Resolve Story Info
                        if novel_slug not in story_info_cache:
                            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
                                info_obj = await lay_thong_tin_truyen(client, novel_slug)
                                story_info_cache[novel_slug] = story_info_to_dict(info_obj)
                        
                        story_info = story_info_cache[novel_slug]
                        
                        # 1. Scrape (if needed)
                        # We need content for AI Metadata, TTS, and Video (images)
                        content = None
                        
                        # 2. AI Metadata (if needed)
                        from .ai_helper import VideoMetadata
                        metadata = None
                        if task.get('ai_metadata_json'):
                            metadata = VideoMetadata(**json.loads(task['ai_metadata_json']))
                        elif not ai_off:
                            progress.update(overall_task, description="[magenta]Generating AI Metadata...")
                            if not content:
                                progress.update(overall_task, description=f"[green]Scraping {url} for AI...")
                                scraped = await scrape_chapters(browser, [url])
                                content = scraped.get(url)
                            
                            if content:
                                text_content = "\n".join([item.data for item in content if item.type == 'text'])
                                metadata = await self.ai.generate_metadata(text_content, story_info)
                                await self.db.update_task_status(url, status, ai_metadata_json=metadata.model_dump_json())
                        
                        if not metadata:
                            metadata = self.ai._get_fallback_metadata(story_info)
                            # Try to get chapter title from URL or content
                            chap_title = url.split('/')[-1].replace('-', ' ').title()
                            metadata.title = f"{story_info['title']} - {chap_title}"

                        # 3. Audio (TTS) (if needed)
                        audio_path = task.get('audio_path')
                        if status == 'PENDING' or status == 'FAILED' or not audio_path or not os.path.exists(audio_path):
                            progress.update(overall_task, description=f"[blue]Generating TTS Audio...")
                            if not content:
                                progress.update(overall_task, description=f"[green]Scraping {url} for TTS...")
                                scraped = await scrape_chapters(browser, [url])
                                content = scraped.get(url)
                            
                            if not content:
                                logger.error(f"Cannot generate audio: No content for {url}")
                                await self.db.update_task_status(url, "FAILED")
                                progress.advance(overall_task)
                                continue
                            
                            chap_title = metadata.title.split(' - ')[-1] # Heuristic
                            audio_path = f"{sanitize_filename(chap_title)}.mp3"
                            logger.info(f"Generating audio: {audio_path}")
                            await tao_file_mp3(content, audio_path, title=chap_title)
                            await self.db.update_task_status(url, "AUDIO_READY", audio_path=audio_path)
                            status = "AUDIO_READY"
                        
                        # 4. Video Rendering (if needed)
                        video_path = task.get('video_path')
                        if status == 'AUDIO_READY' or not video_path or not os.path.exists(video_path):
                            video_path = audio_path.replace('.mp3', '.mp4')
                            
                            if not dry_run:
                                progress.update(overall_task, description=f"[purple]Rendering Video...")
                                # We need image URLs for video
                                if not content:
                                    progress.update(overall_task, description=f"[green]Scraping {url} for Images...")
                                    scraped = await scrape_chapters(browser, [url])
                                    content = scraped.get(url)
                                
                                image_urls = [item.data for item in content if item.type == 'image'] if content else []
                                
                                # Estimate duration
                                duration = 300 # 5 mins default if can't estimate
                                
                                logger.info(f"Generating video: {video_path}")
                                await self.video.generate_video(image_urls, audio_path, video_path, duration)
                                await self.db.update_task_status(url, "VIDEO_READY", video_path=video_path)
                                status = "VIDEO_READY"
                            else:
                                logger.info(f"[DRY-RUN] Would generate video: {video_path}")
                                # In dry run, we don't update status to VIDEO_READY unless it was already there
                                # or we mock the path

                        # 5. Upload (if needed)
                        if status == 'VIDEO_READY':
                            if not dry_run:
                                if self.yt.get_remaining_quota() < 1600:
                                    logger.error("Insufficient YouTube quota. Stopping queue processing.")
                                    break
                                
                                progress.update(overall_task, description=f"[red]Uploading to YouTube...")
                                logger.info(f"Uploading to YouTube: {metadata.title}")
                                try:
                                    video_id = await self.yt.upload_video(video_path, metadata.model_dump())
                                    await self.db.update_task_status(url, "PUBLISHED", youtube_id=video_id)
                                    
                                    # Cleanup
                                    if os.path.exists(audio_path): os.remove(audio_path)
                                    if os.path.exists(video_path): os.remove(video_path)
                                except Exception as e:
                                    logger.error(f"YouTube upload failed: {e}")
                                    await self.db.update_task_status(url, "FAILED")
                            else:
                                logger.info(f"[DRY-RUN] Would publish: {metadata.title}")
                        else:
                             if not dry_run:
                                 logger.warning(f"Task {url} is not yet VIDEO_READY (current: {status}). Skipping upload.")

                    except Exception as e:
                        logger.exception(f"Error processing task {url}: {e}")
                        await self.db.update_task_status(url, "FAILED")
                    
                    progress.advance(overall_task)


            await browser.close()

    async def sync_library_and_queue_new_chapters(self):
        """Synchronizes the library with live site and queues any new chapters found."""
        novels = await self.db.get_all_novels()
        for novel in novels:
            slug = novel['slug']
            last_count = novel.get('last_chapter_count') or 0
            
            logger.info(f"Syncing {slug} (last known count: {last_count})...")
            
            # Get live chapter tree
            tree = await tao_so_do_cay.get_chapter_tree_list(f"{BASE_URL}/{slug}")
            if not tree:
                logger.warning(f"Could not fetch chapter tree for {slug}")
                continue
            
            flat_chapters = [c for v in tree for c in v['chapters']]
            live_count = len(flat_chapters)
            
            if live_count > last_count:
                new_chapters = flat_chapters[last_count:]
                logger.info(f"Found {len(new_chapters)} new chapters for {slug}")
                
                for chap in new_chapters:
                    url = f"{BASE_URL}{chap['url']}" if chap['url'].startswith('/') else chap['url']
                    
                    existing_task = await self.db.get_task_by_url(url)
                    if existing_task:
                        if existing_task['status'] == 'FAILED':
                            await self.db.update_task_status(url, "PENDING")
                    else:
                        task_data = {
                            "novel_slug": slug,
                            "chapter_url": url,
                            "status": "PENDING"
                        }
                        await self.db.upsert_publishing_task(task_data)
                
                # Update last_chapter_count in library
                await self.db.update_novel_status(slug, status="synced", last_chapter_count=live_count)
            else:
                logger.info(f"No new chapters for {slug}")

    async def discover_and_publish_all(self, dry_run: bool = False, ai_off: bool = False):
        """Finds all new chapters in library, queues them, and publishes everything pending."""
        logger.info("Syncing library and checking for new chapters...")
        await self.sync_library_and_queue_new_chapters()
        
        logger.info("Processing all pending tasks in the publishing queue...")
        await self.process_queue(dry_run=dry_run, ai_off=ai_off)
