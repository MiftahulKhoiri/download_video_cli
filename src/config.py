import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "default_resolution": None,   # None = selalu tanya; atau angka misal 720
    "mp3_quality": "192",         # kbps: "128", "192", "256", "320"
    "subtitle_langs": [],         # contoh: ["id", "en"]; kosong = jangan ambil subtitle
    "parallel_workers": 1,        # 1 = download berurutan (default, paling aman)
    "retry_count": 1,             # jumlah percobaan per video (1 = tanpa retry)
    "cookies_file": None,         # path ke cookies.txt (format Netscape), None = tidak dipakai
    "notify_termux": True,        # kirim notifikasi Termux kalau tersedia
}


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


def run_settings_menu():
    from src.loading import clear_screen
    while True:
        clear_screen()
        config = load_config()
        print("===== PENGATURAN =====")
        print(f"1. Resolusi default        : {config.get('default_resolution') or 'selalu tanya'}")
        print(f"2. Kualitas MP3 default    : {config.get('mp3_quality')} kbps")
        print(f"3. Subtitle default        : {', '.join(config.get('subtitle_langs') or []) or 'nonaktif'}")
        print(f"4. Jumlah download paralel : {config.get('parallel_workers')}")
        print(f"5. Jumlah percobaan ulang  : {config.get('retry_count')}")
        print(f"6. File cookies            : {config.get('cookies_file') or 'tidak dipakai'}")
        print(f"7. Notifikasi Termux       : {'aktif' if config.get('notify_termux') else 'nonaktif'}")
        print("0. Kembali")
        pilihan = input("Pilih pengaturan yang mau diubah: ").strip()

        if pilihan == "1":
            nilai = input("Resolusi default (angka misal 720, kosongkan buat selalu tanya): ").strip()
            set_value("default_resolution", int(nilai) if nilai.isdigit() else None)
        elif pilihan == "2":
            nilai = input("Kualitas MP3 default (128/192/256/320): ").strip()
            if nilai in ("128", "192", "256", "320"):
                set_value("mp3_quality", nilai)
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "3":
            nilai = input("Kode bahasa subtitle, pisah koma (misal id,en) atau kosongkan buat nonaktif: ").strip()
            langs = [x.strip() for x in nilai.split(",") if x.strip()]
            set_value("subtitle_langs", langs)
        elif pilihan == "4":
            nilai = input("Jumlah download paralel (1 = berurutan): ").strip()
            if nilai.isdigit() and int(nilai) >= 1:
                set_value("parallel_workers", int(nilai))
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "5":
            nilai = input("Jumlah percobaan ulang kalau gagal (1 = tanpa retry): ").strip()
            if nilai.isdigit() and int(nilai) >= 1:
                set_value("retry_count", int(nilai))
            else:
                print("Nilai tidak valid.")
                input("\nTekan Enter untuk lanjut...")
        elif pilihan == "6":
            nilai = input("Path file cookies (kosongkan buat tidak dipakai): ").strip()
            set_value("cookies_file", nilai or None)
        elif pilihan == "7":
            nilai = input("Aktifkan notifikasi Termux? (y/N): ").strip().lower()
            set_value("notify_termux", nilai == "y")
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")