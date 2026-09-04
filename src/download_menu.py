# src/download_menu.py
"""Lapisan menu interaktif: semua input()/print() buat UI, manggil download_core buat kerja beneran."""
from src.loading import clear_screen
from src.config import load_config
from src.media_info import is_ffmpeg_available, get_video_info, expand_playlist, get_available_resolutions
from src.download_core import (
    LOSSY_AUDIO_FORMATS,
    download_single, download_many, download_audio_single, download_audio_many,
)


def _parse_time_to_seconds(text):
    parts = [int(p) for p in text.strip().split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def pilih_rentang_waktu():
    """Tanya rentang waktu buat motong video/audio. Return (start, end) detik, atau None kalau full."""
    print("\n✂️  Potong ke rentang waktu tertentu? (format MM:SS atau HH:MM:SS, kosongkan = unduh penuh)")
    mulai = input("Mulai [Enter = dari awal / lewati]: ").strip()
    if not mulai:
        return None
    try:
        start_sec = _parse_time_to_seconds(mulai)
    except ValueError:
        print("Format waktu tidak valid, unduh penuh.")
        return None
    selesai = input("Selesai [Enter = sampai akhir]: ").strip()
    end_sec = None
    if selesai:
        try:
            end_sec = _parse_time_to_seconds(selesai)
        except ValueError:
            print("Format waktu selesai tidak valid, diabaikan (unduh sampai akhir).")
    return (start_sec, end_sec)


def pilih_resolusi(video_formats, config=None):
    config = config or {}
    if not video_formats:
        return None, "terbaik"

    default_res = config.get("default_resolution")
    if default_res:
        for f in video_formats:
            if f["height"] == default_res:
                print(f"\n▶️  Pakai resolusi default dari pengaturan: {default_res}p")
                return f["height"], f"{f['height']}p"
        print(f"\n⚠️  Resolusi default ({default_res}p) tidak tersedia untuk video ini, silakan pilih manual.")

    print("\nResolusi tersedia:")
    for i, f in enumerate(video_formats):
        print(f"  [{i}] {f['height']}p ({f.get('ext', '?')})")
    print(f"  [{len(video_formats)}] Terbaik (auto)")

    while True:
        pilihan = input("Pilih nomor resolusi: ").strip()
        if pilihan.isdigit() and 0 <= int(pilihan) <= len(video_formats):
            pilihan = int(pilihan)
            break
        print("Input tidak valid.")

    if pilihan == len(video_formats):
        return None, "terbaik"
    return video_formats[pilihan]["height"], f"{video_formats[pilihan]['height']}p"


def pilih_format_audio(config=None):
    config = config or {}
    default_format = config.get("audio_format", "mp3")
    opsi = ["mp3", "m4a", "opus", "flac", "wav"]
    print("\nFormat audio:")
    for i, f in enumerate(opsi):
        tanda = " (default)" if f == default_format else ""
        print(f"  [{i}] {f}{tanda}")
    pilihan = input(f"Pilih nomor format [Enter = default {default_format}]: ").strip()
    if pilihan == "":
        audio_format = default_format
    elif pilihan.isdigit() and 0 <= int(pilihan) < len(opsi):
        audio_format = opsi[int(pilihan)]
    else:
        print("Input tidak valid, pakai default.")
        audio_format = default_format

    if audio_format not in LOSSY_AUDIO_FORMATS:
        return audio_format, None

    default_quality = str(config.get("mp3_quality", "192"))
    opsi_kualitas = ["128", "192", "256", "320"]
    print("\nKualitas (kbps):")
    for i, q in enumerate(opsi_kualitas):
        tanda = " (default)" if q == default_quality else ""
        print(f"  [{i}] {q} kbps{tanda}")
    pilihan_k = input(f"Pilih nomor kualitas [Enter = default {default_quality}kbps]: ").strip()
    if pilihan_k == "":
        quality = default_quality
    elif pilihan_k.isdigit() and 0 <= int(pilihan_k) < len(opsi_kualitas):
        quality = opsi_kualitas[int(pilihan_k)]
    else:
        print("Input tidak valid, pakai default.")
        quality = default_quality

    return audio_format, quality


def _kumpulkan_urls_dari_input_atau_file():
    print("Sumber URL:")
    print("  [1] Ketik manual (satu per baris)")
    print("  [2] Import dari file .txt (satu URL per baris)")
    sumber = input("Pilih [1/2, Enter = 1]: ").strip()

    if sumber == "2":
        path = input("Path file .txt: ").strip()
        try:
            with open(path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            print(f"📄 {len(urls)} URL dibaca dari {path}")
            return urls
        except OSError as e:
            print(f"❌ Gagal membaca file: {e}")
            return []

    print("Masukkan URL satu per baris (video/playlist). Ketik 'selesai' jika sudah:")
    urls_input = []
    while True:
        u = input("> ").strip()
        if u.lower() == "selesai":
            break
        if u:
            urls_input.append(u)
    return urls_input


def menu_download_1():
    clear_screen()
    print("===== DOWNLOAD 1 VIDEO =====")
    config = load_config()
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url, cookies_file=config.get("cookies_file"))
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} video ditemukan.")

        info = get_video_info(urls[0], cookies_file=config.get("cookies_file"))
        formats = get_available_resolutions(info)
        height, label = pilih_resolusi(formats, config=config)

        if len(urls) > 1:
            download_many(urls, target_height=height, resolution_label=label, first_info=info, config=config)
        else:
            section_range = pilih_rentang_waktu()
            download_single(
                urls[0], target_height=height, resolution_label=label, info=info,
                config=config, section_range=section_range,
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_banyak():
    clear_screen()
    print("===== DOWNLOAD BANYAK VIDEO =====")
    config = load_config()
    urls_input = _kumpulkan_urls_dari_input_atau_file()
    if not urls_input:
        print("Tidak ada URL yang dimasukkan.")
        input("\nTekan Enter untuk lanjut...")
        return

    try:
        urls = []
        for u in urls_input:
            expanded = expand_playlist(u, cookies_file=config.get("cookies_file"))
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} video ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada video yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        contoh_info = get_video_info(urls[0], cookies_file=config.get("cookies_file"))
        formats = get_available_resolutions(contoh_info)
        height, label = pilih_resolusi(formats, config=config)
        download_many(urls, target_height=height, resolution_label=label, first_info=contoh_info, config=config)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_1():
    clear_screen()
    print("===== DOWNLOAD AUDIO (1 ITEM) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert audio nggak bisa jalan.")
        print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        input("\nTekan Enter untuk lanjut...")
        return
    config = load_config()
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url, cookies_file=config.get("cookies_file"))
        audio_format, quality = pilih_format_audio(config)
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} audio akan diunduh.")
            cfg_override = {**config, "audio_format": audio_format}
            if quality:
                cfg_override["mp3_quality"] = quality
            download_audio_many(urls, config=cfg_override)
        else:
            section_range = pilih_rentang_waktu()
            download_audio_single(
                urls[0], audio_format=audio_format, quality=quality,
                config=config, section_range=section_range,
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_banyak():
    clear_screen()
    print("===== DOWNLOAD AUDIO (BANYAK ITEM) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert audio nggak bisa jalan.")
        print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        input("\nTekan Enter untuk lanjut...")
        return
    config = load_config()
    urls_input = _kumpulkan_urls_dari_input_atau_file()
    if not urls_input:
        print("Tidak ada URL yang dimasukkan.")
        input("\nTekan Enter untuk lanjut...")
        return

    try:
        urls = []
        for u in urls_input:
            expanded = expand_playlist(u, cookies_file=config.get("cookies_file"))
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} audio ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada audio yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        audio_format, quality = pilih_format_audio(config)
        cfg_override = {**config, "audio_format": audio_format}
        if quality:
            cfg_override["mp3_quality"] = quality
        download_audio_many(urls, config=cfg_override)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def run_download_menu():
    """Loop menu download, dipanggil dari main."""
    while True:
        clear_screen()
        print("===== MENU DOWNLOAD =====")
        if not is_ffmpeg_available():
            print("⚠️  ffmpeg tidak ditemukan. Download yang butuh merge/convert bakal ditolak otomatis.")
            print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).\n")
        config = load_config()
        if config.get("parallel_workers", 1) > 1:
            print(f"⚡ Mode paralel aktif: {config['parallel_workers']} download sekaligus (ubah di menu Pengaturan)\n")
        print("1. Download video (1)")
        print("2. Download video (banyak)")
        print("3. Download audio (1)")
        print("4. Download audio (banyak)")
        print("0. Kembali")
        pilihan = input("Pilih opsi: ").strip()

        if pilihan == "1":
            menu_download_1()
        elif pilihan == "2":
            menu_download_banyak()
        elif pilihan == "3":
            menu_download_mp3_1()
        elif pilihan == "4":
            menu_download_mp3_banyak()
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")