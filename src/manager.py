import datetime
import os
import json
import tempfile
import threading

from src.logger import get_logger
from src.paths import DOWNLOAD_DIR, HISTORY_FILE, resolve_path  # noqa: F401  (DOWNLOAD_DIR/HISTORY_FILE tetap bisa diimpor dari sini)
from src.utils import backup_corrupt_file

log = get_logger()

# Melindungi urutan baca-ubah-tulis download.json dari race condition pas
# mode download paralel (beberapa thread worker bisa manggil save_file_record
# hampir bersamaan). Cuma efektif dalam SATU proses -- perlindungan lintas
# proses (mode menu vs CLI/cron) sudah ditangani terpisah oleh AppLock (lock.py).
_history_lock = threading.Lock()

# Pasangan (judul, ekstensi) yang sudah "dipesan" download lain di sesi ini,
# biar dua download paralel berjudul sama nggak saling menimpa file (lihat claim_title).
_reserved_names = set()


def _now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _file_exists(item):
    fp = resolve_path(item.get("filename")) if item else None
    return bool(fp) and os.path.exists(fp)


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
    """Buat folder download (folder INTERNAL app: tempat download.json/.lock/app.log) jika belum ada."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return DOWNLOAD_DIR


def ensure_output_folder(custom_path=None, printer=print):
    """
    Pastikan folder TUJUAN hasil download (video/audio beneran) ada & bisa
    ditulisi, lalu return path-nya. Beda dari ensure_download_folder(): itu
    folder internal app yang TETAP di "download/" (buat download.json, .lock,
    app.log), sedangkan ini folder tempat FILE HASIL DOWNLOAD ditaruh -- bisa
    dikustomisasi lewat pengaturan "Folder Penyimpanan".

    custom_path kosong/None -> pakai folder default yang sama kayak sebelumnya
    (DOWNLOAD_DIR). Path relatif dihitung dari folder PROYEK (bukan dari folder
    tempat program dijalankan). Kalau folder custom gagal dibuat/ditulisi (path
    salah, SD card belum ke-mount, izin ditolak, dll), otomatis fallback ke folder
    default + kasih warning -- biar download nggak gagal total gara-gara satu
    pengaturan yang keliru.
    """
    if not custom_path:
        return ensure_download_folder()

    folder = resolve_path(custom_path)
    try:
        os.makedirs(folder, exist_ok=True)
        fd, probe_path = tempfile.mkstemp(prefix=".write_test-", dir=folder)
        os.close(fd)
        os.remove(probe_path)
        return folder
    except OSError as e:
        printer(f"⚠️  Folder penyimpanan '{folder}' nggak bisa dipakai ({e}). Pakai folder default 'download/' dulu.")
        return ensure_download_folder()


def load_history():
    ensure_download_folder()
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("isinya bukan daftar (list)")
        return [item for item in data if isinstance(item, dict)]
    except OSError as e:
        # Gagal BACA (izin/IO), bukan isinya yang rusak -- jangan diapa-apain filenya.
        print(f"⚠️  Gagal membaca riwayat download ({HISTORY_FILE}): {e}. Menggunakan riwayat kosong.")
        return []
    except ValueError as e:
        # Isinya rusak. Selamatkan dulu ke file backup, kalau nggak riwayat lama bakal
        # ketimpa begitu ada download berikutnya yang menyimpan riwayat baru.
        backup = backup_corrupt_file(HISTORY_FILE)
        note = f" File lama diselamatkan ke '{os.path.basename(backup)}'." if backup else ""
        print(f"⚠️  Riwayat download ({HISTORY_FILE}) rusak: {e}.{note} Memulai riwayat kosong.")
        log.error(f"Riwayat rusak ({e}); backup: {backup}")
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
    title_norm = (title or "").strip().lower()
    for item in history:
        item_id = item.get("id")
        if video_id and item_id:
            if item_id != video_id:
                continue
        else:
            if (item.get("title") or "").strip().lower() != title_norm:
                continue

        if resolution is None:
            return item
        if (item.get("resolution") or "").strip().lower() == resolution.strip().lower():
            return item
    return None


def is_already_downloaded(title, resolution=None, video_id=None):
    """
    Cek apakah video/audio ini sudah pernah diunduh. Lihat _find_existing() buat detail pencocokan.

    Kalau ADA catatannya di riwayat tapi file fisiknya udah nggak ada di disk (dihapus manual,
    pindah folder, dll), dianggap BUKAN duplikat -- boleh diunduh ulang -- meski entrinya tetap
    dikembalikan (item kedua) biar pemanggil bisa kasih tau "file sebelumnya hilang" kalau perlu.
    """
    history = load_history()
    item = _find_existing(history, title, resolution=resolution, video_id=video_id)
    if item is None:
        return False, None
    return _file_exists(item), item


def claim_title(title, ext):
    """
    Cek apakah nama file 'judul.ext' berisiko bentrok sama file lain: sudah ada di riwayat,
    ATAU lagi dipakai download paralel lain di sesi ini. Return True kalau bentrok (pemanggil
    sebaiknya nambahin ID video ke nama file); sekaligus 'memesan' judul ini buat pemanggil
    berikutnya. Dipanggil SETELAH cek duplikat, jadi entri berjudul sama di riwayat itu
    pasti video/format lain -- bukan video yang sama.
    """
    title_norm = (title or "").strip().lower()
    ext_norm = (ext or "").lower().lstrip(".")
    key = (title_norm, ext_norm)
    with _history_lock:
        in_use = key in _reserved_names
        if not in_use:
            for item in load_history():
                if (item.get("title") or "").strip().lower() != title_norm:
                    continue
                item_ext = os.path.splitext(item.get("filename") or "")[1].lower().lstrip(".")
                # File riwayat lama yang udah nggak ada di disk nggak dianggap bentrok --
                # nggak ada file nyata yang bakal ketiban/rebutan nama.
                if item_ext == ext_norm and _file_exists(item):
                    in_use = True
                    break
        _reserved_names.add(key)
        return in_use


def save_file_record(title, filename, url, resolution, video_id=None):
    """
    Simpan catatan hasil download ke download.json (dengan timestamp "downloaded_at").
    Thread-safe: aman dipanggil dari beberapa thread sekaligus (mode download
    paralel) -- baca, cek duplikat, dan tulis dilakukan sebagai satu blok atomik
    lewat _history_lock, jadi nggak ada entri yang saling menimpa/hilang.

    Kalau entri lama buat video/resolusi ini masih ada tapi file fisiknya udah hilang
    (unduh ulang setelah file dihapus manual), entri lama itu DIPERBARUI di tempat
    (bukan nambah entri baru) -- riwayat nggak numpuk duplikat.
    """
    with _history_lock:
        history = load_history()
        existing = _find_existing(history, title, resolution=resolution, video_id=video_id)
        if existing is not None:
            if _file_exists(existing):
                return False  # beneran masih ada -- jangan dicatat dobel
            existing.update({
                "id": video_id, "title": title, "filename": filename,
                "url": url, "resolution": resolution, "downloaded_at": _now_iso(),
            })
            return save_history(history)
        history.append({
            "id": video_id,
            "title": title,
            "filename": filename,
            "url": url,
            "resolution": resolution,
            "downloaded_at": _now_iso(),
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
            filename = resolve_path(item.get("filename"))
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
                filename = resolve_path(item.get("filename"))
                if filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except OSError as e:
                        print(f"⚠️  Gagal menghapus file {filename}: {e}")

        save_history([])
        return count
