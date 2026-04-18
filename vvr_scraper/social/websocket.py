from collections import defaultdict

from fastapi import WebSocket


class SocialConnectionManager:
    def __init__(self):
        self.rooms: dict[tuple[str, str], list[WebSocket]] = defaultdict(list)

    async def connect(self, book_slug: str, chapter_id: str, websocket: WebSocket):
        await websocket.accept()
        self.rooms[(book_slug, chapter_id)].append(websocket)

    def disconnect(self, book_slug: str, chapter_id: str, websocket: WebSocket):
        room = self.rooms[(book_slug, chapter_id)]
        if websocket in room:
            room.remove(websocket)

    async def broadcast(self, book_slug: str, chapter_id: str, message: dict):
        room = list(self.rooms[(book_slug, chapter_id)])
        dead = []
        for websocket in room:
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(book_slug, chapter_id, websocket)


social_ws_manager = SocialConnectionManager()
