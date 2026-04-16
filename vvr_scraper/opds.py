"""
OPDS XML Generator Module for Valvrare Team Web Novel Scraper.
Provides functions to create OPDS catalogs (Atom XML format).
"""

from datetime import datetime, timezone
from typing import Any

from lxml import etree

# Standard Namespaces
ATOM_NS = "http://www.w3.org/2005/Atom"
OPDS_NS = "http://opds-spec.org/2010/catalog"
NSMAP = {None: ATOM_NS, "opds": OPDS_NS}


def create_feed(title: str, url: str, icon: str | None = None, next_url: str | None = None) -> etree._Element:
    """
    Initializes the root <feed> element with standard namespaces.

    Args:
        title: The catalog title.
        url: The self-referencing URL of this feed.
        icon: Optional URL to an icon.
        next_url: Optional URL to the next page of the catalog.

    Returns:
        The root <feed> element.
    """
    feed = etree.Element(f"{{{ATOM_NS}}}feed", nsmap=NSMAP)

    etree.SubElement(feed, f"{{{ATOM_NS}}}title").text = title
    etree.SubElement(feed, f"{{{ATOM_NS}}}updated").text = datetime.now(timezone.utc).isoformat()
    etree.SubElement(feed, f"{{{ATOM_NS}}}id").text = url

    # Self link
    etree.SubElement(
        feed,
        f"{{{ATOM_NS}}}link",
        rel="self",
        href=url,
        type="application/atom+xml;profile=opds-catalog;kind=navigation",
    )

    if next_url:
        etree.SubElement(
            feed,
            f"{{{ATOM_NS}}}link",
            rel="next",
            href=next_url,
            type="application/atom+xml;profile=opds-catalog;kind=navigation",
        )

    if icon:
        etree.SubElement(feed, f"{{{ATOM_NS}}}icon").text = icon

    return feed


def add_entry(feed: etree._Element, novel_data: dict[str, Any], base_url: str) -> etree._Element:
    """
    Adds a <entry> element for a novel to the feed.

    Args:
        feed: The root <feed> element.
        novel_data: Dictionary containing novel information (from DB).
        base_url: Base URL for building absolute file/image URLs.

    Returns:
        The added <entry> element.
    """
    entry = etree.SubElement(feed, f"{{{ATOM_NS}}}entry")

    slug = novel_data.get("slug", "unknown")

    etree.SubElement(entry, f"{{{ATOM_NS}}}title").text = novel_data.get("title", "Unknown")
    etree.SubElement(entry, f"{{{ATOM_NS}}}id").text = f"urn:slug:{slug}"

    # Updated time - use last_downloaded_at if available
    updated = novel_data.get("last_downloaded_at")
    if not updated:
        updated = datetime.now(timezone.utc).isoformat()
    elif "Z" not in updated and "+" not in updated:
        updated += "Z"
    etree.SubElement(entry, f"{{{ATOM_NS}}}updated").text = updated

    # Author
    author_elem = etree.SubElement(entry, f"{{{ATOM_NS}}}author")
    etree.SubElement(author_elem, f"{{{ATOM_NS}}}name").text = novel_data.get("author", "Unknown Author")

    # Summary/Description
    summary = novel_data.get("description") or novel_data.get("summary") or "No description available."
    etree.SubElement(entry, f"{{{ATOM_NS}}}summary").text = summary

    # Genres/Categories
    genres_raw = novel_data.get("genres") or ""
    if isinstance(genres_raw, str):
        genres = [g.strip() for g in genres_raw.split(",") if g.strip()]
    else:
        genres = genres_raw if genres_raw else []

    for genre in genres:
        etree.SubElement(entry, f"{{{ATOM_NS}}}category", term=genre, label=genre)

    # Cover image
    cover_url = novel_data.get("cover_url")
    if cover_url:
        # If relative URL, prepend base_url
        if not cover_url.startswith(("http://", "https://")):
            # Ensure base_url ends with slash and cover_url doesn't start with slash
            if not base_url.endswith("/") and not cover_url.startswith("/"):
                full_cover_url = f"{base_url}/{cover_url}"
            else:
                full_cover_url = f"{base_url}{cover_url}"
        else:
            full_cover_url = cover_url

        etree.SubElement(
            entry, f"{{{ATOM_NS}}}link", rel="http://opds-spec.org/image", href=full_cover_url, type="image/jpeg"
        )
        etree.SubElement(
            entry,
            f"{{{ATOM_NS}}}link",
            rel="http://opds-spec.org/image/thumbnail",
            href=full_cover_url,
            type="image/jpeg",
        )

    # Acquisition links (EPUB, PDF)
    formats = novel_data.get("formats", "")
    if isinstance(formats, str):
        format_list = [f.strip().lower() for f in formats.split(",") if f.strip()]
    else:
        format_list = formats if formats else []

    mime_types = {"epub": "application/epub+zip", "pdf": "application/pdf"}

    for fmt in format_list:
        if fmt in mime_types:
            file_url = f"{base_url}/api/opds/download/{slug}?fmt={fmt}"
            etree.SubElement(
                entry, f"{{{ATOM_NS}}}link", rel="http://opds-spec.org/acquisition", href=file_url, type=mime_types[fmt]
            )

    return entry


def to_string(feed: etree._Element) -> bytes:
    """
    Returns the complete XML string (bytes).

    Args:
        feed: The root <feed> element.

    Returns:
        XML string as bytes with declaration.
    """
    return etree.tostring(feed, pretty_print=True, xml_declaration=True, encoding="UTF-8")
