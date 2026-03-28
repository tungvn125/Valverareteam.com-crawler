import os
import subprocess
import asyncio
from typing import List, Optional
from loguru import logger

class VideoEngine:
    def __init__(self, stock_bg_path: Optional[str] = None):
        # Default stock background if none provided
        self.stock_bg_path = stock_bg_path or os.getenv("VVR_STOCK_BG", "stock_bg.mp4")
        self.font_path = self._find_best_font()

    def _find_best_font(self) -> str:
        """Finds a font that supports Vietnamese characters."""
        possible_paths = [
            "/usr/share/fonts/truetype/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return "DejaVuSans"  # Fallback to system font name

    def _get_drawtext_filter(self, title: str, input_node: str = "[v]", output_node: str = "[v_titled]") -> str:
        """Generates a drawtext filter string for the title overlay."""
        # FFmpeg drawtext escaping:
        # ':' must be escaped with '\:'
        # "'" must be escaped with '\' or use complex shell-style escaping.
        # Inside 'text=...', we use single quotes and escape ' with '\''.
        escaped_title = title.replace("'", "'\\''").replace(":", "\\:")
        # '%' also needs escaping to avoid format expansion
        escaped_title = escaped_title.replace("%", "%%")
        
        font_arg = f"fontfile={self.font_path}" if "/" in self.font_path else f"font='{self.font_path}'"
        
        return (
            f"{input_node}drawtext={font_arg}:text='{escaped_title}':"
            "x=(w-text_w)/2:y=h-th-50:fontsize=48:fontcolor=white:"
            "box=1:boxcolor=black@0.5:boxborderw=5"
            f"{output_node}"
        )

    def calculate_duration_per_image(self, total_audio_duration: float, num_images: int) -> float:
        """Calculates how long each image should be displayed."""
        if num_images == 0:
            return 0
        return total_audio_duration / num_images

    def _build_slideshow_ffmpeg_args(self, image_paths: List[str], audio_path: str, output_path: str, duration_per_image: float, title: Optional[str] = None) -> List[str]:
        """Builds the FFmpeg arguments for a slideshow with Ken Burns effect and optional title overlay."""
        args = ["ffmpeg", "-y"]
        for img in image_paths:
            args.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])
        
        args.extend(["-i", audio_path])
        
        filter_parts = []
        for i in range(len(image_paths)):
            filter_parts.append(f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.001,1.5)':d={int(duration_per_image*25)}:s=1920x1080[v{i}]")
        
        concat = "".join([f"[v{i}]" for i in range(len(image_paths))])
        filter_complex = f"{';'.join(filter_parts)};{concat}concat=n={len(image_paths)}:v=1:a=0[v]"
        
        if title:
            drawtext_filter = self._get_drawtext_filter(title, input_node="[v]", output_node="[v_titled]")
            filter_complex += f";{drawtext_filter}"
            video_map = "[v_titled]"
        else:
            video_map = "[v]"

        args.extend(["-filter_complex", filter_complex, "-map", video_map, "-map", f"{len(image_paths)}:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", output_path])
        return args

    def _build_loop_background_ffmpeg_args(self, bg_video_path: str, audio_path: str, output_path: str, total_duration: float, title: Optional[str] = None) -> List[str]:
        """Builds the FFmpeg arguments for a looping stock background with optional title overlay."""
        args = [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", bg_video_path,
            "-i", audio_path, "-t", str(total_duration)
        ]

        if title:
            # We need to use -vf for simple filter chain or -filter_complex
            # Using -vf is easier here.
            vf = self._get_drawtext_filter(title, input_node="", output_node="")
            args.extend(["-vf", vf, "-c:v", "libx264"])
        else:
            args.extend(["-c:v", "copy"])

        args.extend(["-c:a", "aac", "-shortest", output_path])
        return args

    async def generate_video(self, image_paths: List[str], audio_path: str, output_path: str, total_duration: float, title: Optional[str] = None):
        """Generates the final video file with optional title overlay."""
        if image_paths:
            duration = self.calculate_duration_per_image(total_duration, len(image_paths))
            args = self._build_slideshow_ffmpeg_args(image_paths, audio_path, output_path, duration, title=title)
        else:
            if not os.path.exists(self.stock_bg_path):
                logger.warning(f"Stock background {self.stock_bg_path} not found. Using solid black.")
                
                if title:
                    vf = self._get_drawtext_filter(title, input_node="", output_node="")
                    args = [
                        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={total_duration}",
                        "-i", audio_path, "-t", str(total_duration),
                        "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-shortest", output_path
                    ]
                else:
                    args = [
                        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s=1920x1080:d={total_duration}",
                        "-i", audio_path, "-t", str(total_duration),
                        "-c:v", "libx264", "-c:a", "aac", "-shortest", output_path
                    ]
            else:
                args = self._build_loop_background_ffmpeg_args(self.stock_bg_path, audio_path, output_path, total_duration, title=title)

        logger.info(f"Rendering video to {output_path}...")
        process = await asyncio.create_subprocess_exec(
            args[0], *args[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg failed with exit code {process.returncode}")
            logger.error(stderr.decode())
            raise Exception("Video rendering failed")
        
        logger.success(f"Video rendered successfully: {output_path}")
