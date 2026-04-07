"""
Module for rendering cinematic novels into MP4 videos using Playwright and FFmpeg.
"""
import asyncio
import os
import subprocess
import json
import tempfile
import shutil
from typing import Dict, List, Optional
from loguru import logger
from playwright.async_api import async_playwright

class VideoRenderer:
    def __init__(
        self, 
        manifest_path: str, 
        output_path: str, 
        fps: int = 30, 
        render_format: str = 'landscape',
        vfx_scale: int = 100,
        job_id: Optional[str] = None,
        db: Optional[Any] = None
    ):
        self.manifest_path = manifest_path
        self.output_path = output_path
        self.fps = fps
        self.render_format = render_format
        self.vfx_scale = vfx_scale
        self.job_id = job_id
        self.db = db
        
        # Resolutions
        if render_format == 'portrait':
            self.width, self.height = 1080, 1920
        else: # landscape
            self.width, self.height = 1920, 1080

    async def render(self, job_id: Optional[str] = None, db: Optional[Any] = None):
        """Renders the cinematic novel to an MP4 video (without audio)."""
        logger.info(f"Bắt đầu render video ({self.width}x{self.height}, {self.fps} FPS)...")
        
        # Load manifest to get duration
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        
        # Calculate total duration from the last event
        total_duration_ms = 0
        for event in manifest.get('events', []):
            end_time = event.get('end', event.get('start', 0))
            if end_time > total_duration_ms:
                total_duration_ms = end_time
        
        # Add a small buffer at the end
        total_duration_ms += 1000
        total_frames = int((total_duration_ms / 1000) * self.fps)
        if total_frames <= 0:
            total_frames = 1
        
        logger.info(f"Tổng thời gian: {total_duration_ms/1000:.2f}s, Tổng số frame: {total_frames}")

        # Start FFmpeg process for video only
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'image2pipe',
            '-vcodec', 'png',
            '-r', str(self.fps),
            '-i', '-',
            '-vcodec', 'libx264',
            '-pix_fmt', 'yuv420p',
            '-crf', '18',
            '-preset', 'veryfast',
            self.output_path
        ]
        
        process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            # Use a large viewport to match target resolution
            context = await browser.new_context(
                viewport={'width': self.width, 'height': self.height},
                device_scale_factor=1
            )
            page = await context.new_page()
            
            # Construct the local server to serve the novel folder
            # We use the parent folder of manifest.json as the root for images
            root_dir = os.path.dirname(self.manifest_path)
            static_dir = os.path.join(os.path.dirname(__file__), 'static')
            
            # Start a temporary FastAPI server in the background
            from fastapi import FastAPI
            from fastapi.staticfiles import StaticFiles
            import uvicorn
            import threading
            import time

            app = FastAPI()
            # Serve the novel content (images, audio)
            # Find the library root (novels/)
            novels_root = os.path.abspath(os.path.join(root_dir, ".."))
            app.mount("/novels", StaticFiles(directory=novels_root), name="novels")
            # Serve the cinema player (js, css, html)
            app.mount("/static", StaticFiles(directory=static_dir), name="static")

            # Find a free port
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()

            config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
            server = uvicorn.Server(config)
            
            thread = threading.Thread(target=server.run)
            thread.daemon = True
            thread.start()
            
            try:
                # Wait for server to be ready
                time.sleep(1)

                # Get the slug from manifest path (folder name)
                novel_slug = os.path.basename(root_dir)
                file_url = f"http://127.0.0.1:{port}/static/cinema.html?vfx={self.vfx_scale}&path={novel_slug}"
                
                await page.goto(file_url)
                
                # Wait for the player to initialize
                await page.wait_for_function("window.player !== undefined")
                
                # Inject manifest and prepare for rendering
                await page.evaluate("window.player.prepareForRendering();")
                
                # Loop through each frame
                from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    transient=True
                ) as progress:
                    task = progress.add_task("[cyan]Rendering frames...", total=total_frames)
                    
                    for frame_idx in range(total_frames):
                        # Check if FFmpeg is still alive
                        if process.poll() is not None:
                            stdout, stderr = process.communicate()
                            raise RuntimeError(f"FFmpeg exited unexpectedly with code {process.returncode}. Error: {stderr.decode()}")

                        current_time_ms = (frame_idx / self.fps) * 1000
                        
                        # Seek player to the exact time
                        await page.evaluate(f"window.player.seekTo({current_time_ms});")
                        
                        # Capture screenshot as PNG
                        screenshot = await page.screenshot(type='png', full_page=False)
                        
                        # Write to FFmpeg pipe
                        try:
                            process.stdin.write(screenshot)
                        except BrokenPipeError:
                            stdout, stderr = process.communicate()
                            raise RuntimeError(f"FFmpeg pipe broken. Error: {stderr.decode()}")
                        
                        progress.update(task, advance=1)
                        
                        # Update DB progress every 30 frames
                        if self.db and self.job_id and frame_idx % 30 == 0:
                            db_progress = 10.0 + (frame_idx / total_frames) * 80.0
                            await self.db.update_job_status(self.job_id, "running", progress=db_progress)

            finally:
                # Always ensure cleanup
                if process.stdin:
                    try: process.stdin.close()
                    except: pass
                
                # Wait for FFmpeg to finish writing file
                process.wait()
                
                # Stop server
                server.should_exit = True
                if thread.is_alive():
                    thread.join(timeout=2)
                
                await browser.close()
                logger.debug("Render resources cleaned up.")

        logger.success(f"Đã render xong video (không âm thanh): {self.output_path}")

    @staticmethod
    async def mux_audio(video_path: str, audio_path: str, final_path: str):
        """Muxes the rendered video with the generated audio drama file."""
        logger.info(f"Đang trộn âm thanh vào video...")
        
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            final_path
        ]
        
        # Run ffmpeg synchronously but wrapped in thread for async
        def run():
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            
        await asyncio.to_thread(run)
        logger.success(f"Đã tạo video hoàn chỉnh: {final_path}")
