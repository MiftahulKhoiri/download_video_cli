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
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Gagal membaca riwayat download ({HISTORY_FILE}): {e}. Menggunakan riwayat kosong.")
        return []


def save_history(data):
    """Simpan riwayat ke disk. Return True kalau berhasil, False kalau gagal (tanpa crash)."""
    ensure_download_folder()
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"⚠️  Gagal menyimpan riwayat download ke {HISTORY_FILE}: {e}")
        return False


def is_already_downloaded(title, resolution=None):
    """
    Cek apakah judul + resolusi/format tertentu sudah pernah diunduh (case-insensitive).
    resolution=None -> cocokkan judul saja (perilaku lama, buat caller yang nggak
    peduli resolusi/format spesifik).
    """
    history = load_history()
    title_norm = title.strip().lower()
    for item in history:
        if item.get("title", "").strip().lower() != title_norm:
            continue
        if resolution is None:
            return True, item
        if item.get("resolution", "").strip().lower() == resolution.strip().lower():
            return True, item
    return False, None


def save_file_record(title, filename, url, resolution):
    """Simpan catatan hasil download ke download.json."""
    history = load_history()
    already, _ = is_already_downloaded(title, resolution)
    if already:
        return False
    history.append({
        "title": title,
        "filename": filename,
        "url": url,
        "resolution": resolution,
    })
    return save_history(history)