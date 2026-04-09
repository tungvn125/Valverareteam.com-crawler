import random
from pathlib import Path


class BGMManager:
    """
    Manages background music library organized by mood.
    The library should have subdirectories named by mood,
    each containing audio files (mp3, wav, ogg).
    """

    SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

    def __init__(self, base_dir: str = "bgm"):
        self.library_path = Path(base_dir)
        self.moods: dict[str, list[Path]] = {}
        self._scan_library()

    def _scan_library(self):
        """Scans the library directory for moods and tracks."""
        if not self.library_path.exists() or not self.library_path.is_dir():
            return

        for mood_dir in self.library_path.iterdir():
            if mood_dir.is_dir():
                tracks = [
                    f for f in mood_dir.iterdir() if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
                ]
                if tracks:
                    self.moods[mood_dir.name.lower()] = tracks

    @property
    def available_moods(self) -> list[str]:
        """Returns a list of moods that have at least one track."""
        return list(self.moods.keys())

    def refresh(self):
        """Re-scans the library for updates."""
        self.moods = {}
        self._scan_library()

    def get_random_track(self, mood: str | None = None, refresh: bool = False) -> str | None:
        """
        Retrieves a random track for the specified mood.
        Returns None if the mood is not found or if no tracks are available for that mood.
        """
        if refresh:
            self.refresh()

        if not mood:
            return None

        mood_lower = mood.lower()
        if mood_lower not in self.moods:
            return None

        return str(random.choice(self.moods[mood_lower]))
