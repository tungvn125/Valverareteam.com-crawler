"""
Utility functions for the web novel scraper.
"""
import sys
import shutil
from typing import Dict, List, Optional
from loguru import logger
import re
import os


BASE_URL = "https://valvrareteam.net"

def configure_logger(verbose: bool = False):
    """Configures the loguru logger with appropriate levels."""
    logger.remove()  # Remove default handler
    
    # Custom format for nice output
    log_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{message}</cyan>"
    )
    
    # Show only INFO and above for non-verbose, DEBUG and above for verbose
    level = "DEBUG" if verbose else "INFO"
    
    logger.add(sys.stderr, level=level, format=log_format, colorize=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8,en-GB;q=0.7",
    "Referer": "https://valvrareteam.net/",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Sec-GPC": "1",
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
    """Normalize Vietnamese characters and strip ALL punctuation/special chars for URL matching."""
    if not text:
        return ""
    
    # 1. Lowercase
    text = text.lower()
    
    # 2. Replace Vietnamese characters with ASCII
    for key, value in VIETNAMESE_MAP.items():
        text = text.replace(key, value)
    
    # 3. Remove all non-alphanumeric characters except spaces
    # This removes commas, dots, tildes (~), colons, etc.
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    
    # 4. Replace spaces with hyphens
    normalized = text.replace(" ", "-")
    
    # 5. Collapse multiple hyphens and strip leading/trailing hyphens
    normalized = re.sub(r'-+', '-', normalized).strip('-')
    
    return normalized


def get_config_dir() -> str:
    """Returns the config directory path (~/.config/vvr-scraper/), creating it if needed."""
    config_dir = os.path.join(os.path.expanduser("~"), ".config", "vvr-scraper")
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def get_config_path(filename: str) -> str:
    """Returns path for a config file in ~/.config/vvr-scraper/.
    
    Auto-migrates from CWD to config dir if the CWD file exists but the
    config dir file doesn't.
    """
    config_path = os.path.join(get_config_dir(), filename)
    # Auto-migrate from CWD to config dir
    if not os.path.exists(config_path):
        cwd_path = os.path.join(os.getcwd(), filename)
        if os.path.exists(cwd_path):
            shutil.copy2(cwd_path, config_path)
            logger.info(f"Migrated {filename} to {config_path}")
    return config_path


def get_token_from_state(state: Dict) -> Optional[str]:
    """
    Extracts the JWT token from Playwright's storage state (localStorage).
    Looks for common token keys like 'accessToken', 'token', or within 'auth-storage'.
    """
    if not state or 'origins' not in state:
        return None
    
    for origin in state['origins']:
        if "valvrareteam.net" in origin['origin']:
            ls = origin.get('localStorage', [])
            for item in ls:
                name = item.get('name', '')
                value = item.get('value', '')
                
                # Direct match
                if name in ['accessToken', 'token', 'jwt']:
                    return value
                
                # Check for auth-storage (often a JSON string)
                if name == 'auth-storage':
                    try:
                        import json
                        data = json.loads(value)
                        # Check for state.token or similar structures
                        if isinstance(data, dict):
                            state_data = data.get('state', {})
                            if isinstance(state_data, dict):
                                return state_data.get('token') or state_data.get('accessToken')
                    except Exception:
                        pass
    return None
