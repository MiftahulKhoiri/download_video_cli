import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "default_resolution": None,     # None = selalu tanya; atau angka misal 720
    "audio_format": "mp3",          # mp3, m4a, opus, flac, wav
    "mp3_quality": "192",           # kbps: "128", "192", "256", "320" (cuma berlaku format lossy: mp3/m4a/opus)
    "embed_metadata": True,         # sisipkan thumbnail + metadata (judul dll) ke file audio
    "subtitle_langs": [],           # contoh: ["id", "en"]; kosong = jangan ambil subtitle
    "parallel_workers": 1,          # 1 = download berurutan (default, paling aman)
    "retry_count": 1,               # jumlah percobaan per video (1 = tanpa retry)
    "cookies_file": None,           # path ke cookies.txt (format Netscape), None = tidak dipakai
    "notify_termux": True,          # kirim notifikasi Termux kalau tersedia
    "organize_by": "none",          # none, channel, date -- susun folder hasil download
    "termux_shared_storage": False, # salin juga hasil download ke ~/storage/downloads (Termux)
    "rate_limit": None,             # batas kecepatan, contoh "2M" / "500K"; None = tanpa batas
}

_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
_ORGANIZE_OPTIONS = ["none", "channel", "date"]
_YA = ("y", "ya")
_TIDAK = ("n", "tidak")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Gagal membaca {CONFIG_FILE}: {e}. Menggunakan pengaturan default.")
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"⚠️  Gagal menyimpan {CONFIG_FILE}: {e}")
        return False


def get(key):
    return load_config().get(key, DEFAULT_CONFIG.get(key))


def set_value(key, value):
    if key not in DEFAULT_CONFIG:
        raise KeyError(f"Kunci pengaturan tidak dikenal: {key}")
    config = load_config()
    config[key] = value
    return save_config(config)


def _batal():
    print("Dibatalkan, kembali ke menu Pengaturan tanpa perubahan.")
    input("\nTekan Enter untuk lanjut...")


def _invalid():
    print("❌ Nilai tidak valid.")
    input("\nTekan Enter untuk lanjut...")


def _konfirmasi_simpan(ringkasan):
    """Tampilkan ringkasan perubahan, minta konfirmasi. Enter/y/ya = simpan, selain itu = batal."""
    jawab = input(f"Simpan -- {ringkasan}? (Y/n): ").strip().lower()
    return jawab in ("", "y", "ya")


def _terapkan(key, value, ringkasan):
    """Alur simpan seragam: konfirmasi dulu, baru ditulis ke config.json."""
    if _konfirmasi_simpan(ringkasan):
        set_value(key, value)
        print("✅ Tersimpan.")
    else:
        print("Dibatalkan, nilai tidak diubah.")
    input("\nTekan Enter untuk lanjut...")


def _cek_update_yt_dlp_interaktif():
    from src.updater import check_for_update, update_yt_dlp

    print("\n🔍 Mengecek versi yt-dlp...")
    installed, latest, is_outdated = check_for_update(timeout=5)

    if installed is None:
        print("❌ Tidak bisa mendeteksi yt-dlp yang terpasang.")
        input("\nTekan Enter untuk lanjut...")
        return
    if latest is None:
        print(f"Versi terpasang: {installed}. Tidak bisa mengecek versi terbaru (cek koneksi internet).")
        input("\nTekan Enter untuk lanjut...")
        return
    if not is_outdated:
        print(f"✅ yt-dlp kamu sudah versi terbaru ({installed}).")
        input("\nTekan Enter untuk lanjut...")
        return

    print(f"⚠️  Versi terpasang: {installed} | Versi terbaru: {latest}")
    jawab = input("Update sekarang? (y/N, '0' = kembali): ").strip().lower()
    if jawab not in _YA:
        print("Dibatalkan.")
        input("\nTekan Enter untuk lanjut...")
        return

    print("⬇️  Mengupdate yt-dlp...")
    ok, output = update_yt_dlp()
    if ok:
        print("✅ yt-dlp berhasil diupdate. Restart aplikasi biar perubahan kepakai.")
    else:
        print(f"❌ Gagal update: {output}")
    input("\nTekan Enter untuk lanjut...")


def run_settings_menu():
    from src.loading import clear_screen
    while True:
        clear_screen()
        config = load_config()
        print("===== PENGATURAN =====")
        print(f" 1. Resolusi default        : {config.get('default_resolution') or 'selalu tanya'}")
        print(f" 2. Format audio default    : {config.get('audio_format')}")
        print(f" 3. Kualitas audio default  : {config.get('mp3_quality')} kbps (lossy saja)")
        print(f" 4. Embed thumbnail/metadata: {'aktif' if config.get('embed_metadata') else 'nonaktif'}")
        print(f" 5. Subtitle default        : {', '.join(config.get('subtitle_langs') or []) or 'nonaktif'}")
        print(f" 6. Jumlah download paralel : {config.get('parallel_workers')}")
        print(f" 7. Jumlah percobaan ulang  : {config.get('retry_count')}")
        print(f" 8. File cookies            : {config.get('cookies_file') or 'tidak dipakai'}")
        print(f" 9. Notifikasi Termux       : {'aktif' if config.get('notify_termux') else 'nonaktif'}")
        print(f"10. Susun folder hasil      : {config.get('organize_by')}")
        print(f"11. Salin ke storage Termux : {'aktif' if config.get('termux_shared_storage') else 'nonaktif'}")
        print(f"12. Batas kecepatan unduh   : {config.get('rate_limit') or 'tanpa batas'}")
        print("13. Cek & update yt-dlp")
        print(" 0. Kembali")
        print("(pas diminta nilai baru: ketik '0' buat batal tanpa ubah apa-apa)")
        pilihan = input("Pilih pengaturan yang mau diubah: ").strip()

        if pilihan == "1":
            print(f"\nResolusi default sekarang: {config.get('default_resolution') or 'selalu tanya'}")
            nilai = input("Resolusi baru (angka misal 720; kosongkan = selalu tanya; '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            elif nilai and not nilai.isdigit():
                _invalid()
            else:
                baru = int(nilai) if nilai else None
                tampil = f"{baru}p" if baru else "selalu tanya"
                _terapkan("default_resolution", baru, f"resolusi default jadi {tampil}")

        elif pilihan == "2":
            print(f"\nFormat audio sekarang: {config.get('audio_format')}")
            print(f"Pilihan: {', '.join(_AUDIO_FORMATS)} ('0' = kembali)")
            nilai = input("Format audio baru: ").strip().lower()
            if nilai == "0":
                _batal()
            elif nilai not in _AUDIO_FORMATS:
                _invalid()
            else:
                _terapkan("audio_format", nilai, f"format audio default jadi {nilai}")

        elif pilihan == "3":
            print(f"\nKualitas audio sekarang: {config.get('mp3_quality')} kbps")
            nilai = input("Kualitas baru (128/192/256/320, '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            elif nilai not in ("128", "192", "256", "320"):
                _invalid()
            else:
                _terapkan("mp3_quality", nilai, f"kualitas audio default jadi {nilai}kbps")

        elif pilihan == "4":
            status = "aktif" if config.get("embed_metadata") else "nonaktif"
            print(f"\nEmbed thumbnail/metadata sekarang: {status}")
            nilai = input("Aktifkan? (y/n, '0' = kembali): ").strip().lower()
            if nilai == "0":
                _batal()
            elif nilai not in _YA + _TIDAK:
                _invalid()
            else:
                baru = nilai in _YA
                tampil = "aktif" if baru else "nonaktif"
                _terapkan("embed_metadata", baru, f"embed thumbnail/metadata jadi {tampil}")

        elif pilihan == "5":
            current = ", ".join(config.get("subtitle_langs") or []) or "nonaktif"
            print(f"\nSubtitle default sekarang: {current}")
            nilai = input("Kode bahasa pisah koma (misal id,en); kosongkan = nonaktif; '0' = kembali: ").strip()
            if nilai == "0":
                _batal()
            else:
                langs = [x.strip() for x in nilai.split(",") if x.strip()]
                tampil = ", ".join(langs) or "nonaktif"
                _terapkan("subtitle_langs", langs, f"subtitle default jadi {tampil}")

        elif pilihan == "6":
            print(f"\nJumlah download paralel sekarang: {config.get('parallel_workers')}")
            nilai = input("Jumlah baru (1 = berurutan; '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            elif not (nilai.isdigit() and int(nilai) >= 1):
                _invalid()
            else:
                baru = int(nilai)
                _terapkan("parallel_workers", baru, f"jumlah download paralel jadi {baru}")

        elif pilihan == "7":
            print(f"\nJumlah percobaan ulang sekarang: {config.get('retry_count')}")
            nilai = input("Jumlah baru (1 = tanpa retry; '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            elif not (nilai.isdigit() and int(nilai) >= 1):
                _invalid()
            else:
                baru = int(nilai)
                _terapkan("retry_count", baru, f"jumlah percobaan ulang jadi {baru}")

        elif pilihan == "8":
            print(f"\nFile cookies sekarang: {config.get('cookies_file') or 'tidak dipakai'}")
            nilai = input("Path file cookies baru (kosongkan = tidak dipakai; '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            else:
                tampil = nilai or "tidak dipakai"
                _terapkan("cookies_file", nilai or None, f"file cookies jadi {tampil}")

        elif pilihan == "9":
            status = "aktif" if config.get("notify_termux") else "nonaktif"
            print(f"\nNotifikasi Termux sekarang: {status}")
            nilai = input("Aktifkan? (y/n, '0' = kembali): ").strip().lower()
            if nilai == "0":
                _batal()
            elif nilai not in _YA + _TIDAK:
                _invalid()
            else:
                baru = nilai in _YA
                tampil = "aktif" if baru else "nonaktif"
                _terapkan("notify_termux", baru, f"notifikasi Termux jadi {tampil}")

        elif pilihan == "10":
            print(f"\nSusun folder hasil sekarang: {config.get('organize_by')}")
            print(f"Pilihan: {', '.join(_ORGANIZE_OPTIONS)} ('0' = kembali)")
            nilai = input("Nilai baru: ").strip().lower()
            if nilai == "0":
                _batal()
            elif nilai not in _ORGANIZE_OPTIONS:
                _invalid()
            else:
                _terapkan("organize_by", nilai, f"susun folder hasil jadi {nilai}")

        elif pilihan == "11":
            status = "aktif" if config.get("termux_shared_storage") else "nonaktif"
            print(f"\nSalin ke storage Termux sekarang: {status}")
            nilai = input("Aktifkan? (y/n, '0' = kembali): ").strip().lower()
            if nilai == "0":
                _batal()
            elif nilai not in _YA + _TIDAK:
                _invalid()
            else:
                baru = nilai in _YA
                tampil = "aktif" if baru else "nonaktif"
                _terapkan("termux_shared_storage", baru, f"salin ke storage Termux jadi {tampil}")

        elif pilihan == "12":
            print(f"\nBatas kecepatan sekarang: {config.get('rate_limit') or 'tanpa batas'}")
            nilai = input("Batas baru (misal 2M, 500K; kosongkan = tanpa batas; '0' = kembali): ").strip()
            if nilai == "0":
                _batal()
            else:
                tampil = nilai or "tanpa batas"
                _terapkan("rate_limit", nilai or None, f"batas kecepatan unduh jadi {tampil}")

        elif pilihan == "13":
            _cek_update_yt_dlp_interaktif()

        elif pilihan == "0":
            break

        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")