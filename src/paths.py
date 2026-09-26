# src/paths.py
"""
Lokasi file & folder internal app. Semua dihitung dari folder PROYEK (tempat
main.py berada), BUKAN dari folder kerja saat program dijalankan -- jadi
aman dipanggil dari cron / shortcut / folder mana pun, dan config.json,
riwayat, lock, dan log selalu ketemu di tempat yang sama.
"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "download")
HISTORY_FILE = os.path.join(DOWNLOAD_DIR, "download.json")
LOCK_FILE = os.path.join(DOWNLOAD_DIR, ".lock")
LOG_FILE = os.path.join(DOWNLOAD_DIR, "app.log")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
UPDATE_CACHE_FILE = os.path.join(DOWNLOAD_DIR, "update_cache.json")


def resolve_path(path):
    """
    Path relatif (dari pengaturan atau riwayat versi lama, mis. 'download/x.mp4')
    dianggap relatif ke folder proyek. '~' di-expand ke home directory.
    """
    if not path:
        return path
    path = os.path.expanduser(str(path))
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)
