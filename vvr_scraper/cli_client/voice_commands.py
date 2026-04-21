"""Voice Bank CLI command handlers."""

import os
import shutil
import subprocess
import tempfile

from prompt_toolkit import PromptSession
from rich.console import Console

from .client import APIClient, CLIError
from .display import print_error, print_success, print_voice_detail, print_voice_table

console = Console()


async def login(client: APIClient, args) -> None:
    """Authenticate with the server and save token."""
    username = getattr(args, "username", None)
    password = getattr(args, "password", None)

    if not username:
        session = PromptSession()
        username = (await session.prompt_async("Username: ")).strip()
    if not password:
        session = PromptSession()
        password = (await session.prompt_async("Password: ", is_password=True)).strip()

    if not username or not password:
        print_error("Username và password là bắt buộc.")
        return

    result = await client.request(
        "POST",
        "/api/auth/login",
        json_data={
            "username": username,
            "password": password,
        },
    )

    token_data = {
        "token": result["token"],
        "username": result["user"]["username"],
        "user_id": result["user"]["id"],
        "role": result["user"]["role"],
        "created_at": result["user"].get("created_at", ""),
    }
    client.token_manager.save_token(token_data)
    print_success(f"Đăng nhập thành công! Xin chào, {token_data['username']}.")


async def logout(client: APIClient, args) -> None:
    """Remove stored authentication token."""
    client.token_manager.logout()
    print_success("Đã đăng xuất.")


async def upload(client: APIClient, args) -> None:
    """Upload a new voice sample."""
    audio_path = getattr(args, "audio", None)
    name = getattr(args, "name", None)
    ref_text = getattr(args, "ref_text", None)
    gender = getattr(args, "gender", None)
    age_group = getattr(args, "age_group", None)
    description = getattr(args, "description", None)
    language = getattr(args, "language", "vi")
    mood = getattr(args, "mood", None)
    tags = getattr(args, "tags", None)

    # Interactive prompts for missing required fields
    session = PromptSession()

    if not audio_path:
        audio_path = (await session.prompt_async("Đường dẫn file audio: ")).strip()
    if not name:
        name = (await session.prompt_async("Tên voice (3-100 ký tự): ")).strip()
    if not ref_text:
        ref_text = (await session.prompt_async("Văn bản tham chiếu (tối thiểu 10 ký tự): ")).strip()
    if not gender:
        console.print("[yellow]Chọn giới tính:[/yellow]")
        idx = _choose_option(["male", "female", "other"], "Giới tính")
        if idx is None:
            return
        gender = ["male", "female", "other"][idx]
    if not age_group:
        console.print("[yellow]Chọn nhóm tuổi:[/yellow]")
        idx = _choose_option(["child", "teen", "young_adult", "adult", "elder"], "Nhóm tuổi")
        if idx is None:
            return
        age_group = ["child", "teen", "young_adult", "adult", "elder"][idx]

    # Validate required fields
    if not audio_path or not os.path.exists(audio_path):
        print_error(f"File không tồn tại: {audio_path}")
        return
    if not name or len(name) < 3:
        print_error("Tên voice phải từ 3-100 ký tự.")
        return
    if not ref_text or len(ref_text) < 10:
        print_error("Văn bản tham chiếu phải tối thiểu 10 ký tự.")
        return

    # Build form fields
    fields = {
        "name": name,
        "ref_text": ref_text,
        "gender": gender,
        "age_group": age_group,
    }
    if description:
        fields["description"] = description
    if language:
        fields["language"] = language
    if mood:
        fields["mood"] = mood
    if tags:
        fields["tags"] = tags

    result = await client.upload_file("/api/voices/upload", audio_path, file_field="audio", fields=fields)
    print_success(f"Đã upload voice '{result.get('name', name)}'!")
    print_voice_detail(result)


async def list_voices(client: APIClient, args) -> None:
    """List your voices."""
    params = {
        "limit": getattr(args, "limit", 20),
        "offset": getattr(args, "offset", 0),
    }
    result = await client.request("GET", "/api/voices/me", params=params)
    items = result.get("items", [])
    total = result.get("total", 0)
    print_voice_table(items, title=f"Voices của bạn ({total} tổng)")
    if total > len(items):
        console.print(f"[dim]Hiển thị {len(items)}/{total}. Dùng --offset để xem thêm.[/dim]")


async def community(client: APIClient, args) -> None:
    """Browse public voice gallery."""
    params = {
        "limit": getattr(args, "limit", 20),
        "offset": getattr(args, "offset", 0),
    }
    if getattr(args, "tag", None):
        params["tag"] = args.tag
    if getattr(args, "gender", None):
        params["gender"] = args.gender
    if getattr(args, "age_group", None):
        params["age_group"] = args.age_group
    if getattr(args, "sort", None):
        params["sort"] = args.sort

    result = await client.request("GET", "/api/voices/community", params=params)
    items = result.get("items", [])
    total = result.get("total", 0)
    print_voice_table(items, title=f"Community Voices ({total} tổng)")
    if total > len(items):
        console.print(f"[dim]Hiển thị {len(items)}/{total}. Dùng --offset để xem thêm.[/dim]")


async def show(client: APIClient, args) -> None:
    """Show voice details."""
    voice = await client.request("GET", f"/api/voices/{args.voice_id}")
    print_voice_detail(voice)


async def update(client: APIClient, args) -> None:
    """Update voice metadata."""
    update_data = {}
    if getattr(args, "name", None):
        update_data["name"] = args.name
    if getattr(args, "description", None):
        update_data["description"] = args.description
    if getattr(args, "mood", None):
        update_data["mood"] = args.mood
    if getattr(args, "tags", None):
        update_data["tags"] = [t.strip().lower() for t in args.tags.split(",") if t.strip()]

    if not update_data:
        print_error("Không có gì để cập nhật. Dùng --name, --description, --mood, hoặc --tags.")
        return

    result = await client.request("PATCH", f"/api/voices/{args.voice_id}", json_data=update_data)
    print_success(f"Đã cập nhật voice '{result.get('name', args.voice_id)}'.")
    print_voice_detail(result)


async def delete(client: APIClient, args) -> None:
    """Delete a voice sample."""
    confirm = input(f"Bạn có chắc muốn xóa voice '{args.voice_id}'? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        console.print("[yellow]Hủy xóa.[/yellow]")
        return

    await client.request("DELETE", f"/api/voices/{args.voice_id}")
    print_success(f"Đã xóa voice '{args.voice_id}'.")


async def publish(client: APIClient, args) -> None:
    """Make voice public."""
    result = await client.request("PATCH", f"/api/voices/{args.voice_id}/publish")
    print_success(f"Đã đăng voice '{result.get('name', args.voice_id)}' lên cộng đồng.")
    print_voice_detail(result)


async def delist(client: APIClient, args) -> None:
    """Make voice private (delist from community)."""
    result = await client.request("PATCH", f"/api/voices/{args.voice_id}/delist")
    print_success(f"Đã gỡ voice '{result.get('name', args.voice_id)}' khỏi cộng đồng.")
    print_voice_detail(result)


async def vote(client: APIClient, args) -> None:
    """Upvote or downvote a voice sample."""
    vote_value = 1 if args.direction == "up" else -1
    result = await client.request("POST", f"/api/voices/{args.voice_id}/vote", json_data={"vote": vote_value})
    score = result.get("vote_score", "?")
    direction = "👍" if vote_value == 1 else "👎"
    print_success(f"{direction} Vote recorded! Điểm mới: {score}")


async def download(client: APIClient, args) -> None:
    """Download voice audio file."""
    output_path = getattr(args, "output", None) or f"{args.voice_id}.wav"
    saved_path = await client.download_file(f"/api/voices/{args.voice_id}/audio", output_path)
    print_success(f"Đã tải về: {saved_path}")


async def preview(client: APIClient, args) -> None:
    """Generate TTS preview and play it."""
    text = getattr(args, "text", None)
    if not text:
        session = PromptSession()
        text = (await session.prompt_async("Nhập văn bản để preview: ")).strip()

    if not text:
        print_error("Văn bản không được để trống.")
        return

    # The preview endpoint returns raw audio bytes, not JSON
    # We need to use httpx directly for binary response
    import httpx

    from .auth_manager import AuthenticationRequired

    try:
        token = client.token_manager.get_token()
    except AuthenticationRequired as e:
        raise CLIError(str(e)) from e

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(base_url=client.base_url, headers=headers, timeout=60.0) as http_client:
        response = await http_client.post(f"/api/voices/{args.voice_id}/preview", json={"text": text})

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise CLIError(f"Lỗi preview: {detail}")

    # Save to temp file
    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"vvr_preview_{args.voice_id}.wav")
    with open(tmp_path, "wb") as f:
        f.write(response.content)

    print_success(f"Preview saved to: {tmp_path}")

    # Try to play
    played = False
    for player in ["aplay", "ffplay", "mpv"]:
        if shutil.which(player):
            try:
                if player == "ffplay":
                    subprocess.run([player, "-nodisp", "-autoexit", tmp_path], capture_output=True, timeout=30)
                elif player == "mpv":
                    subprocess.run([player, "--no-video", tmp_path], capture_output=True, timeout=30)
                else:
                    subprocess.run([player, tmp_path], capture_output=True, timeout=30)
                played = True
                break
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    if not played:
        console.print("[dim]Không tìm thấy audio player. Mở file thủ công.[/dim]")


def _choose_option(options: list[str], title: str) -> int | None:
    """Show a simple numbered menu and return the selected index."""
    for i, opt in enumerate(options):
        console.print(f"  {i + 1}. {opt}")
    try:
        choice = input(f"{title} [1-{len(options)}]: ").strip()
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            return idx
    except (ValueError, EOFError):
        pass
    return None
