"""
OPDS 1.1 catalog routes for e-book reader apps (Moon+ Reader, KyBook, etc.).
"""

import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from ... import opds
from ...utils import sanitize_filename
from ..deps import get_current_user, get_db

router = APIRouter(prefix="/opds/v1", tags=["OPDS"])


@router.get("/root")
async def opds_root(request: Request, user: str = Depends(get_current_user)):
    base_url = str(request.base_url).rstrip("/")
    feed = opds.create_feed("Valvrare Library", f"{base_url}/opds/v1/root")

    from lxml import etree

    # Search link
    etree.SubElement(
        feed,
        f"{{{opds.ATOM_NS}}}link",
        rel="search",
        href=f"{base_url}/opds/v1/search?q={{searchTerms}}",
        type="application/atom+xml",
    )

    # Navigation entries
    nav_items = [
        ("Mới tải", "newest"),
        ("Tất cả truyện", "all"),
        ("Theo Thể loại", "genres"),
        ("Theo Tác giả", "authors"),
    ]

    for title, path in nav_items:
        entry = etree.SubElement(feed, "{http://www.w3.org/2005/Atom}entry")
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}title").text = title
        etree.SubElement(
            entry,
            "{http://www.w3.org/2005/Atom}link",
            rel="subsection",
            href=f"{base_url}/opds/v1/{path}",
            type="application/atom+xml;profile=opds-catalog;kind=navigation",
        )
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}id").text = f"{base_url}/opds/v1/{path}"
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}updated").text = datetime.now(timezone.utc).isoformat()

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=navigation"
    )


@router.get("/newest")
async def opds_newest(request: Request, page: int = 1, size: int = 20, user: str = Depends(get_current_user)):
    db = get_db()
    base_url = str(request.base_url).rstrip("/")

    novels = await db.get_newest_novels(limit=size + 1, page=page, offset=(page - 1) * size)

    next_url = None
    if len(novels) > size:
        next_url = f"{base_url}/opds/v1/newest?page={page + 1}&size={size}"
        novels = novels[:size]

    feed = opds.create_feed("Mới tải", f"{base_url}/opds/v1/newest?page={page}&size={size}", next_url=next_url)

    for novel in novels:
        opds.add_entry(feed, novel, base_url)

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=acquisition"
    )


@router.get("/all")
async def opds_all(request: Request, page: int = 1, size: int = 20, user: str = Depends(get_current_user)):
    db = get_db()
    base_url = str(request.base_url).rstrip("/")

    novels = await db.get_all_novels(page=page, size=size + 1, offset=(page - 1) * size)

    next_url = None
    if len(novels) > size:
        next_url = f"{base_url}/opds/v1/all?page={page + 1}&size={size}"
        novels = novels[:size]

    feed = opds.create_feed("Tất cả truyện", f"{base_url}/opds/v1/all?page={page}&size={size}", next_url=next_url)

    for novel in novels:
        opds.add_entry(feed, novel, base_url)

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=acquisition"
    )


@router.get("/search")
async def opds_search(
    request: Request, q: str = Query(...), page: int = 1, size: int = 20, user: str = Depends(get_current_user)
):
    db = get_db()
    base_url = str(request.base_url).rstrip("/")

    novels = await db.search_novels(query=q, page=page, size=size + 1)

    next_url = None
    if len(novels) > size:
        next_url = f"{base_url}/opds/v1/search?q={quote_plus(q)}&page={page + 1}&size={size}"
        novels = novels[:size]

    feed = opds.create_feed(
        f"Kết quả tìm kiếm: {q}",
        f"{base_url}/opds/v1/search?q={quote_plus(q)}&page={page}&size={size}",
        next_url=next_url,
    )

    for novel in novels:
        opds.add_entry(feed, novel, base_url)

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=acquisition"
    )


@router.get("/genres")
async def opds_genres(request: Request, user: str = Depends(get_current_user)):
    db = get_db()
    base_url = str(request.base_url).rstrip("/")
    feed = opds.create_feed("Theo Thể loại", f"{base_url}/opds/v1/genres")

    genres = await db.get_unique_genres()
    from lxml import etree

    for genre in genres:
        entry = etree.SubElement(feed, "{http://www.w3.org/2005/Atom}entry")
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}title").text = genre
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}id").text = f"genre:{genre}"
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}updated").text = datetime.now(timezone.utc).isoformat()

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=navigation"
    )


@router.get("/authors")
async def opds_authors(request: Request, user: str = Depends(get_current_user)):
    db = get_db()
    base_url = str(request.base_url).rstrip("/")
    feed = opds.create_feed("Theo Tác giả", f"{base_url}/opds/v1/authors")

    authors = await db.get_unique_authors()
    from lxml import etree

    for author in authors:
        entry = etree.SubElement(feed, "{http://www.w3.org/2005/Atom}entry")
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}title").text = author
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}id").text = f"author:{author}"
        etree.SubElement(entry, "{http://www.w3.org/2005/Atom}updated").text = datetime.now(timezone.utc).isoformat()

    return Response(
        content=opds.to_string(feed), media_type="application/atom+xml;profile=opds-catalog;kind=navigation"
    )


# OPDS download is under /api/ but logically belongs with OPDS
opds_download_router = APIRouter(tags=["OPDS"])


ALLOWED_OPDS_FORMATS = {"epub", "pdf", "mobi", "azw3"}


@opds_download_router.get("/api/opds/download/{slug:path}")
async def opds_download(slug: str, fmt: str = "epub", user: str = Depends(get_current_user)):
    """Streams a novel file based on its slug and requested format."""
    if fmt.lower() not in ALLOWED_OPDS_FORMATS:
        raise HTTPException(status_code=400, detail="Unsupported format")

    db = get_db()
    novel = await db.get_novel_by_slug(slug)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found in database")

    output_folder = novel.get("output_folder")
    if not output_folder or not os.path.exists(output_folder):
        raise HTTPException(status_code=404, detail="Novel output folder not found on disk")

    filename = sanitize_filename(novel["title"])
    file_path = os.path.join(output_folder, f"{filename}.{fmt.lower()}")

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {filename}.{fmt} not found in output folder")

    media_types = {
        "epub": "application/epub+zip",
        "pdf": "application/pdf",
        "mobi": "application/x-mobipocket-ebook",
        "azw3": "application/vnd.amazon.mobi8-ebook",
    }

    return FileResponse(
        path=file_path,
        media_type=media_types.get(fmt.lower(), "application/octet-stream"),
        filename=f"{filename}.{fmt.lower()}",
    )
