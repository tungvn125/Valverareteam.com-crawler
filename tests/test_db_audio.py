import pytest
from vvr_scraper.db import DatabaseManager

@pytest.mark.asyncio
async def test_character_voice_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    db = DatabaseManager(str(db_path))
    await db.init_db()
    
    await db.save_character_voice("story1", "Character A", "Hung")
    voice = await db.get_character_voice("story1", "Character A")
    assert voice == "Hung"
    
    assert await db.get_character_voice("story1", "Unknown") is None
