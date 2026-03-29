import random
from pathlib import Path
from typing import Dict, List, Optional

class BGMManager:
    """
    Manages background music library organized by mood.
    The library should have subdirectories named by mood, 
    each containing audio files (mp3, wav).
    """
    
    SUPPORTED_EXTENSIONS = {".mp3", ".wav"}

    def __init__(self, library_path: str | Path):
        self.library_path = Path(library_path)
        self.moods: Dict[str, List[Path]] = {}
        self._scan_library()

    def _scan_library(self):
        """Scans the library directory for moods and tracks."""
        if not self.library_path.exists() or not self.library_path.is_dir():
            return

        for mood_dir in self.library_path.iterdir():
            if mood_dir.is_dir():
                tracks = [
                    f for f in mood_dir.iterdir() 
                    if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
                ]
                if tracks:
                    self.moods[mood_dir.name] = tracks

    @property
    def available_moods(self) -> List[str]:
        """Returns a list of moods that have at least one track."""
        return list(self.moods.keys())

    def get_random_track(self, mood: Optional[str] = None) -> Optional[Path]:
        """
        Retrieves a random track for the specified mood.
        If mood is not found or not specified, picks a random track from any mood.
        Returns None if no tracks are available in the entire library.
        """
        if not self.moods:
            return None

        # Try to get tracks for the requested mood
        mood_tracks = self.moods.get(mood) if mood else None
        
        if not mood_tracks:
            # Fallback: combine all tracks from all moods
            all_tracks = []
            for tracks in self.moods.values():
                all_tracks.extend(tracks)
            return random.choice(all_tracks) if all_tracks else None

        return random.choice(mood_tracks)
