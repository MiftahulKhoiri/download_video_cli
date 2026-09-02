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


def is_already_downloaded(title, resolution=None, video_id=None):
    """
    Cek apakah video/audio ini sudah pernah diunduh.

    Prioritas pencocokan:
    1. Kalau video_id diberikan DAN item riwayat punya "id" -> cocokkan by id
       (lebih akurat, tahan terhadap judul yang berubah/typo/mirip).
    2. Kalau tidak, fallback ke judul (case-insensitive) seperti perilaku lama.

    resolution=None -> cocokkan judul/id saja, abaikan resolusi.
    """
    history = load_history()
    title_norm = title.strip().lower()

    for item in history:
        item_id = item.get("id")
        if video_id and item_id:
            if item_id != video_id:
                continue
        else:
            if item.get("title", "").strip().lower() != title_norm:
                continue

        if resolution is None:
            return True, item
        if item.get("resolution", "").strip().lower() == resolution.strip().lower():
            return True, item

    return False, None


def save_file_record(title, filename, url, resolution, video_id=None):
    """Simpan catatan hasil download ke download.json."""
    history = load_history()
    already, _ = is_already_downloaded(title, resolution, video_id=video_id)
    if already:
        return False
    history.append({
        "id": video_id,
        "title": title,
        "filename": filename,
        "url": url,
        "resolution": resolution,
    })
    return save_history(history)


def delete_entry(index, remove_file=False):
    """
    Hapus satu entri riwayat berdasarkan nomor urut (1-based, sesuai tampilan dashboard).
    Kalau remove_file=True, file fisiknya juga dihapus dari disk (kalau ada).
    Return (True, item_yang_dihapus) atau (False, None) kalau index tidak valid.
    """
    history = load_history()
    if not (1 <= index <= len(history)):
        return False, None

    item = history.pop(index - 1)

    if remove_file:
        filename = item.get("filename")
        if filename and os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError as e:
                print(f"⚠️  Gagal menghapus file {filename}: {e}")

    save_history(history)
    return True, item


def clear_history(remove_files=False):
    """
    Hapus SEMUA riwayat download. Kalau remove_files=True, semua file fisiknya
    juga ikut dihapus dari disk. Return jumlah entri yang dihapus.
    """
    history = load_history()
    count = len(history)

    if remove_files:
        for item in history:
            filename = item.get("filename")
            if filename and os.path.exists(filename):
                try:
                    os.remove(filename)
                except OSError as e:
                    print(f"⚠️  Gagal menghapus file {filename}: {e}")

    save_history([])
    return count