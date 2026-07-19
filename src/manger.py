import os
import json

DOWNLOAD_DIR = "download"
HISTORY_FILE = os.path.join(DOWNLOAD_DIR, "download.json")


def ensure_download_folder():
    """Buat folder download jika belum ada."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    return DOWNLOAD_DIR


def load_history():
    ensure_download_folder()
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_history(data):
    ensure_download_folder()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_already_downloaded(title):
    """Cek apakah judul video sudah pernah diunduh (case-insensitive)."""
    history = load_history()
    for item in history:
        if item.get("title", "").strip().lower() == title.strip().lower():
            return True, item
    return False, None


def save_file_record(title, filename, url, resolution):
    """Simpan catatan hasil download ke download.json."""
    history = load_history()
    already, _ = is_already_downloaded(title)
    if already:
        return False
    history.append({
        "title": title,
        "filename": filename,
        "url": url,
        "resolution": resolution,
    })
    save_history(history)
    return True