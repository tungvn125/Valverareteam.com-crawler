from pydub import AudioSegment
from loguru import logger

class MixingEngine:
    """
    Core audio logic for mixing background music (BGM) with voice segments.
    """
    
    def mix_with_ducking(
        self, 
        bgm_segment: AudioSegment, 
        voice_segment: AudioSegment, 
        start_ms: int, 
        duck_db: float = -15.0,
        crossfade_ms: int = 100
    ) -> AudioSegment:
        """
        Overlays voice on BGM with a ducking effect.
        The BGM volume is lowered during the voice segment.
        
        Args:
            bgm_segment: The background music audio segment.
            voice_segment: The voice audio segment to overlay.
            start_ms: Start time in milliseconds for the voice segment.
            duck_db: Gain in dB to apply to the BGM during the voice segment.
            crossfade_ms: Duration of crossfade in milliseconds.
            
        Returns:
            The mixed AudioSegment.
        """
        voice_duration = len(voice_segment)
        end_ms = start_ms + voice_duration
        
        # Ensure BGM is long enough to cover the voice segment
        if end_ms > len(bgm_segment):
            padding_duration = end_ms - len(bgm_segment)
            silence = AudioSegment.silent(duration=padding_duration, frame_rate=bgm_segment.frame_rate)
            bgm_segment = bgm_segment + silence
            
        # Split BGM into three parts: before, during, after
        before = bgm_segment[:start_ms]
        during = bgm_segment[start_ms:end_ms]
        after = bgm_segment[end_ms:]
        
        # Apply ducking gain to the "during" segment
        during = during.apply_gain(duck_db)
        
        # Overlay the voice segment on the ducked portion
        during_mixed = during.overlay(voice_segment)
        
        # Reassemble with crossfades
        # Using a small crossfade to smooth the volume transitions
        try:
            # Reassemble: before + during_mixed + after
            # We use append for crossfades if durations allow
            result = before
            
            if len(before) > crossfade_ms and len(during_mixed) > crossfade_ms:
                result = result.append(during_mixed, crossfade=crossfade_ms)
            else:
                result = result + during_mixed
                
            if len(after) > crossfade_ms and len(during_mixed) > crossfade_ms:
                result = result.append(after, crossfade=crossfade_ms)
            else:
                result = result + after
                
            return result
        except Exception as e:
            logger.warning(f"Crossfade failed, falling back to simple concatenation: {e}")
            return before + during_mixed + after
