"""
Utility functions for the web novel scraper.
"""
import os
import re
from typing import Dict, List


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def sanitize_filename(name: str) -> str:
    """
    Sanitizes a string to be used as a valid filename or directory name.
    It removes illegal characters for most OSes.
    """
    if not name:
        return ""
    sanitized_name = re.sub(r'[\\/*?:\"<>|]', "", name)
    sanitized_name = sanitized_name.strip(' .')
    sanitized_name = re.sub(r'\s+', ' ', sanitized_name).strip()
    return sanitized_name


def create_folders_from_tree(tree_file: str, base_folder: str) -> None:
    """Creates directory structure based on a tree map file."""
    try:
        with open(tree_file, 'r', encoding='utf-8') as f:
            tree_data = f.readlines()
        for line in tree_data:
            folder_name = sanitize_filename(line.strip())
            if folder_name:
                folder_path = os.path.join(base_folder, folder_name)
                os.makedirs(folder_path, exist_ok=True)
    except FileNotFoundError:
        print(f"Lưu ý: file tree_map.txt không tồn tại, sẽ tạo thư mục gốc.")
        os.makedirs(base_folder, exist_ok=True)


# Vietnamese character normalization map for URL processing
VIETNAMESE_MAP = {
    'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a', 'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a', 'đ': 'd', 'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e',
    'ẹ': 'e', 'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e', 'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i',
    'ị': 'i', 'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o', 'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o',
    'ộ': 'o', 'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o', 'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u',
    'ụ': 'u', 'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u', 'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y'
}


def normalize_vietnamese_url(text: str) -> str:
    """Normalize Vietnamese characters for URL matching."""
    normalized = text.lower().replace(" ", "-")
    for key, value in VIETNAMESE_MAP.items():
        normalized = normalized.replace(key, value)
    return normalized