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
    jawab = input("Update sekarang? (y/N): ").strip().lower()
    if jawab != "y":
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
        pilihan = input("Pilih pengaturan yang mau diubah: ").strip()

        if pilihan == "1":
            nilai = input("Resolusi default (angka misal 720, kosongkan buat selalu tanya): ").strip()
            set_value("default_resolution", int(nilai) if nilai.isdigit() else None)
        elif pilihan == "2":
            print(f"Pilihan: {', '.join(_AUDIO_FORMATS)}")
            nilai = input("Format audio default: ").strip().lower()
            if nilai in _AUDIO_FORMATS:
                set_value("audio_format", nilai)
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "3":
            nilai = input("Kualitas audio default (128/192/256/320): ").strip()
            if nilai in ("128", "192", "256", "320"):
                set_value("mp3_quality", nilai)
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "4":
            nilai = input("Aktifkan embed thumbnail/metadata ke audio? (y/N): ").strip().lower()
            set_value("embed_metadata", nilai == "y")
        elif pilihan == "5":
            nilai = input("Kode bahasa subtitle, pisah koma (misal id,en) atau kosongkan buat nonaktif: ").strip()
            langs = [x.strip() for x in nilai.split(",") if x.strip()]
            set_value("subtitle_langs", langs)
        elif pilihan == "6":
            nilai = input("Jumlah download paralel (1 = berurutan): ").strip()
            if nilai.isdigit() and int(nilai) >= 1:
                set_value("parallel_workers", int(nilai))
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "7":
            nilai = input("Jumlah percobaan ulang kalau gagal (1 = tanpa retry): ").strip()
            if nilai.isdigit() and int(nilai) >= 1:
                set_value("retry_count", int(nilai))
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "8":
            nilai = input("Path file cookies (kosongkan buat tidak dipakai): ").strip()
            set_value("cookies_file", nilai or None)
        elif pilihan == "9":
            nilai = input("Aktifkan notifikasi Termux? (y/N): ").strip().lower()
            set_value("notify_termux", nilai == "y")
        elif pilihan == "10":
            print(f"Pilihan: {', '.join(_ORGANIZE_OPTIONS)} (none = tanpa subfolder)")
            nilai = input("Susun folder berdasarkan: ").strip().lower()
            if nilai in _ORGANIZE_OPTIONS:
                set_value("organize_by", nilai)
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "11":
            nilai = input("Salin hasil download ke ~/storage/downloads (Termux)? (y/N): ").strip().lower()
            set_value("termux_shared_storage", nilai == "y")
        elif pilihan == "12":
            nilai = input("Batas kecepatan (misal 2M, 500K, kosongkan = tanpa batas): ").strip()
            set_value("rate_limit", nilai or None)
        elif pilihan == "13":
            _cek_update_yt_dlp_interaktif()
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")