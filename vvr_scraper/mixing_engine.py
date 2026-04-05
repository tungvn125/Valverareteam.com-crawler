from pydub import AudioSegment
from loguru import logger
import math

class MixingEngine:
    """
    Core audio logic for mixing background music (BGM) with voice segments.
    """
    
    def create_looped_background(
        self, 
        bgm_segment: AudioSegment, 
        duration_ms: int, 
        gain_db: float = -18.0
    ) -> AudioSegment:
        """
        Creates a looped background track from a BGM segment to match the target duration.
        
        Args:
            bgm_segment: The BGM audio segment to loop.
            duration_ms: Target duration in milliseconds.
            gain_db: Fixed gain in dB to apply to the background.
            
        Returns:
            The looped and truncated AudioSegment with gain applied.
        """
        if len(bgm_segment) == 0:
            return AudioSegment.silent(duration=duration_ms, frame_rate=bgm_segment.frame_rate)
            
        # Calculate how many times we need to loop
        loops_needed = math.ceil(duration_ms / len(bgm_segment))
        
        # Loop the segment
        looped = bgm_segment * loops_needed
        
        # Truncate to exact duration
        truncated = looped[:duration_ms]
        
        # Apply fixed gain
        return truncated.apply_gain(gain_db)

    def overlay_voice_on_background(
        self, 
        background: AudioSegment, 
        voice_track: AudioSegment,
        position: int = 1000
    ) -> AudioSegment:
        """
        Overlays a voice track onto a background track.
        
        Args:
            background: The background audio segment.
            voice_track: The voice audio segment to overlay.
            position: Offset in milliseconds for the voice track.
            
        Returns:
            The mixed AudioSegment.
        """
        return background.overlay(voice_track, position=position)
