import re
from hypothesis import given, strategies as st
from urllib.parse import urlparse

from vvr_scraper.utils import sanitize_filename, normalize_vietnamese_url

# Strategy that generates challenging filename strings
# Includes invalid characters across different platforms, spaces, dots
problematic_chars = ["\\", "/", "*", "?", ":", "\"", "<", ">", "|"]
filename_strategy = st.text(
    alphabet=st.characters(blacklist_categories=("Cc", "Cs")),
    min_size=1, max_size=255
)

@given(filename_strategy)
def test_sanitize_filename_properties(name):
    """
    Property: sanitize_filename must never return a string containing illegal characters.
    Property: sanitized_name must not have leading or trailing dots or spaces.
    Property: sanitized_name must not have consecutive spaces.
    """
    sanitized = sanitize_filename(name)
    
    # 1. No illegal characters
    for char in problematic_chars:
        assert char not in sanitized
        
    # 2. No consecutive spaces
    assert "  " not in sanitized
    
    # 3. No leading/trailing spaces or dots
    if sanitized:
        assert not sanitized.startswith(" ")
        assert not sanitized.endswith(" ")
        assert not sanitized.startswith(".")
        assert not sanitized.endswith(".")
        
    # 4. Same underlying characters (alphanumerics) shouldn't be lost
    # (Though we can't easily assert exactly since multiple spaces map to one)

url_strategy = st.text(alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Pd", "Po", "Zs")), min_size=1)

@given(url_strategy)
def test_normalize_vietnamese_url_properties(raw_text):
    """
    Property: normalize_vietnamese_url takes string text and formats it as a slug.
    It should not contain uppercase, spaces, or Vietnamese accents.
    """
    normalized = normalize_vietnamese_url(raw_text)
    
    # Should not have spaces
    assert " " not in normalized
    
    # Needs to be lowercase
    assert normalized == normalized.lower()

def test_normalize_base_cases():
    assert normalize_vietnamese_url("Cái tên tiếng Việt") == "cai-ten-tieng-viet"
    assert normalize_vietnamese_url("Hello World!") == "hello-world"
