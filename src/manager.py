import os
import json
import tempfile
import threading

DOWNLOAD_DIR = "download"
HISTORY_FILE = os.path.join(DOWNLOAD_DIR, "download.json")

# Melindungi urutan baca-ubah-tulis download.json dari race condition pas
# mode download paralel (beberapa thread worker bisa manggil save_file_record
# hampir bersamaan). Cuma efektif dalam SATU proses -- perlindungan lintas
# proses (mode menu vs CLI/cron) sudah ditangani terpisah oleh AppLock (lock.py).
_history_lock = threading.Lock()


def _atomic_write_json(path, data):
    """
    Tulis JSON ke `path` secara atomic: tulis dulu ke file sementara di folder
    yang sama, baru dipindah lewat os.replace() ke nama aslinya. os.replace()
    itu operasi atomik di level filesystem -- kalau proses mati/crash/force-close
    di tengah penulisan, file ASLI tetap utuh (isi lama) atau LANGSUNG jadi versi
    baru yang lengkap. Nggak ada kondisi "setengah nulis" yang bikin file kepotong/rusak.
    """
    folder = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


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
        _atomic_write_json(HISTORY_FILE, data)
        return True
    except OSError as e:
        print(f"⚠️  Gagal menyimpan riwayat download ke {HISTORY_FILE}: {e}")
        return False


def _find_existing(history, title, resolution=None, video_id=None):
    """
    Cari entri yang cocok di dalam LIST riwayat yang sudah dimuat (bukan baca ulang
    dari disk) -- dipakai bareng dengan _history_lock biar cek-lalu-tulis jadi atomik.

    Prioritas pencocokan:
    1. Kalau video_id diberikan DAN item riwayat punya "id" -> cocokkan by id
       (lebih akurat, tahan terhadap judul yang berubah/typo/mirip).
    2. Kalau tidak, fallback ke judul (case-insensitive) seperti perilaku lama.

    resolution=None -> cocokkan judul/id saja, abaikan resolusi.
    """
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
            return item
        if item.get("resolution", "").strip().lower() == resolution.strip().lower():
            return item
    return None


def is_already_downloaded(title, resolution=None, video_id=None):
    """Cek apakah video/audio ini sudah pernah diunduh. Lihat _find_existing() buat detail pencocokan."""
    history = load_history()
    item = _find_existing(history, title, resolution=resolution, video_id=video_id)
    return (item is not None), item


def save_file_record(title, filename, url, resolution, video_id=None):
    """
    Simpan catatan hasil download ke download.json.
    Thread-safe: aman dipanggil dari beberapa thread sekaligus (mode download
    paralel) -- baca, cek duplikat, dan tulis dilakukan sebagai satu blok atomik
    lewat _history_lock, jadi nggak ada entri yang saling menimpa/hilang.
    """
    with _history_lock:
        history = load_history()
        if _find_existing(history, title, resolution=resolution, video_id=video_id):
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
    with _history_lock:
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
    with _history_lock:
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