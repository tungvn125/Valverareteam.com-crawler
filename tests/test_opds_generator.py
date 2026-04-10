from vvr_scraper.opds import ATOM_NS, add_entry, create_feed, to_string


def test_create_feed():
    title = "Test OPDS Catalog"
    url = "http://example.com/opds"
    icon = "http://example.com/icon.png"

    feed = create_feed(title, url, icon)

    assert feed.tag == f"{{{ATOM_NS}}}feed"
    assert feed.find(f"{{{ATOM_NS}}}title").text == title
    assert feed.find(f"{{{ATOM_NS}}}id").text == url
    assert feed.find(f"{{{ATOM_NS}}}icon").text == icon

    # Check self link
    self_link = feed.find(f"{{{ATOM_NS}}}link[@rel='self']")
    assert self_link is not None
    assert self_link.get("href") == url
    assert "opds-catalog" in self_link.get("type")


def test_add_entry_basic():
    feed = create_feed("Catalog", "http://example.com")
    novel_data = {
        "title": "Novel Title",
        "slug": "novel-slug",
        "author": "Author Name",
        "description": "Novel summary",
        "genres": "Action, Adventure",
        "cover_url": "covers/novel.jpg",
        "formats": "epub,pdf",
    }
    base_url = "http://example.com"

    entry = add_entry(feed, novel_data, base_url)

    assert entry.tag == f"{{{ATOM_NS}}}entry"
    assert entry.find(f"{{{ATOM_NS}}}title").text == "Novel Title"
    assert entry.find(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name").text == "Author Name"
    assert entry.find(f"{{{ATOM_NS}}}summary").text == "Novel summary"

    # Check categories
    categories = entry.findall(f"{{{ATOM_NS}}}category")
    assert len(categories) == 2
    assert categories[0].get("term") == "Action"
    assert categories[1].get("term") == "Adventure"

    # Check cover link
    cover_link = entry.find(f"{{{ATOM_NS}}}link[@rel='http://opds-spec.org/image']")
    assert cover_link is not None
    assert cover_link.get("href") == "http://example.com/covers/novel.jpg"

    # Check acquisition links
    epub_link = entry.find(f"{{{ATOM_NS}}}link[@type='application/epub+zip']")
    assert epub_link is not None
    assert epub_link.get("rel") == "http://opds-spec.org/acquisition"
    assert epub_link.get("href") == "http://example.com/api/opds/download/novel-slug?fmt=epub"

    pdf_link = entry.find(f"{{{ATOM_NS}}}link[@type='application/pdf']")
    assert pdf_link is not None
    assert pdf_link.get("href") == "http://example.com/api/opds/download/novel-slug?fmt=pdf"


def test_to_string():
    feed = create_feed("Catalog", "http://example.com")
    xml_bytes = to_string(feed)

    assert isinstance(xml_bytes, bytes)
    assert b"<?xml" in xml_bytes
    assert b"<feed" in xml_bytes
    assert b'xmlns:opds="http://opds-spec.org/2010/catalog"' in xml_bytes
    assert b'xmlns="http://www.w3.org/2005/Atom"' in xml_bytes


def test_add_entry_no_formats():
    feed = create_feed("Catalog", "http://example.com")
    novel_data = {"title": "No Formats", "slug": "no-formats", "formats": ""}
    base_url = "http://example.com"

    entry = add_entry(feed, novel_data, base_url)

    acquisition_links = entry.findall(f"{{{ATOM_NS}}}link[@rel='http://opds-spec.org/acquisition']")
    assert len(acquisition_links) == 0


def test_add_entry_list_formats():
    feed = create_feed("Catalog", "http://example.com")
    novel_data = {"title": "List Formats", "slug": "list-formats", "formats": ["epub"]}
    base_url = "http://example.com"

    entry = add_entry(feed, novel_data, base_url)

    epub_link = entry.find(f"{{{ATOM_NS}}}link[@type='application/epub+zip']")
    assert epub_link is not None


def test_add_entry_none_genres():
    feed = create_feed("Catalog", "http://example.com")
    novel_data = {"title": "None Genres", "slug": "none-genres", "genres": None}
    base_url = "http://example.com"

    # This should not raise TypeError
    entry = add_entry(feed, novel_data, base_url)

    categories = entry.findall(f"{{{ATOM_NS}}}category")
    assert len(categories) == 0
