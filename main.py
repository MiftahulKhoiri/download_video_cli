import argparse
import curses

from src.dashboard import run_dashboard_menu
from src.download_menu import run_download_menu
from src.media_info import expand_playlist
from src.download_core import download_many, download_audio_many
from src.loading import clear_screen
from src.logo import show_logo, show_intro
from src.config import load_config, _settings_loop, check_config_integrity
from src.lock import AppLock
from src.updater import startup_check_and_notify
from src import tui


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="YouTube/X Video & Audio Downloader — mode non-interaktif (CLI)."
    )
    parser.add_argument("--url", action="append", dest="urls", metavar="URL",
                         help="URL video/playlist yang mau diunduh. Bisa dipakai berkali-kali.")
    parser.add_argument("--url-file", default=None, metavar="FILE",
                         help="Baca daftar URL dari file .txt (satu URL per baris, baris berawalan # diabaikan).")
    parser.add_argument("--res", type=int, default=None,
                         help="Resolusi target dalam angka (misal 720). Kosongkan buat kualitas terbaik.")
    parser.add_argument("--audio", action="store_true",
                         help="Unduh sebagai audio, bukan video.")
    parser.add_argument("--audio-format", default=None, choices=["mp3", "m4a", "opus", "flac", "wav"],
                         help="Format audio, cuma berlaku dengan --audio.")
    parser.add_argument("--quality", default=None,
                         help="Kualitas audio dalam kbps (128/192/256/320), cuma berlaku format lossy.")
    parser.add_argument("--parallel", type=int, default=None,
                         help="Jumlah download paralel (override pengaturan tersimpan).")
    parser.add_argument("--retry", type=int, default=None,
                         help="Jumlah percobaan ulang kalau gagal (override pengaturan tersimpan).")
    parser.add_argument("--sub", default=None, metavar="LANG1,LANG2",
                         help="Kode bahasa subtitle yang mau diunduh, pisah koma (misal id,en).")
    parser.add_argument("--cookies", default=None, metavar="FILE",
                         help="Path ke file cookies.txt (override pengaturan tersimpan).")
    parser.add_argument("--output-dir", default=None, metavar="FOLDER",
                         help="Folder tujuan hasil download (override pengaturan tersimpan).")
    parser.add_argument("--rate-limit", default=None, metavar="2M/500K",
                         help="Batas kecepatan download (override pengaturan tersimpan).")
    return parser


def run_cli(args):
    config = load_config()
    if args.parallel is not None:
        config["parallel_workers"] = args.parallel
    if args.retry is not None:
        config["retry_count"] = args.retry
    if args.cookies is not None:
        config["cookies_file"] = args.cookies
    if args.output_dir is not None:
        config["download_folder"] = args.output_dir
    if args.audio_format is not None:
        config["audio_format"] = args.audio_format
    if args.quality is not None:
        config["mp3_quality"] = args.quality
    if args.sub is not None:
        config["subtitle_langs"] = [x.strip() for x in args.sub.split(",") if x.strip()]
    if args.rate_limit is not None:
        config["rate_limit"] = args.rate_limit

    raw_urls = list(args.urls or [])
    if args.url_file:
        try:
            with open(args.url_file, "r", encoding="utf-8") as f:
                raw_urls.extend(line.strip() for line in f if line.strip() and not line.strip().startswith("#"))
        except OSError as e:
            print(f"❌ Gagal membaca --url-file: {e}")

    all_urls = []
    for u in raw_urls:
        all_urls.extend(expand_playlist(u, cookies_file=config.get("cookies_file"),
                                         retries=config.get("retry_count", 1)))

    if not all_urls:
        print("Tidak ada URL yang bisa diproses.")
        return

    if args.audio:
        download_audio_many(all_urls, config=config)
    else:
        label = f"{args.res}p" if args.res else "terbaik"
        download_many(all_urls, target_height=args.res, resolution_label=label, config=config)


APP_VERSION = "1.0.0"


def _show_about(stdscr):
    from src.updater import get_installed_version
    from src.media_info import get_ffmpeg_version, is_ffmpeg_available
    import platform as _platform

    ytdlp_v = get_installed_version() or "tidak terdeteksi"
    ffmpeg_v = get_ffmpeg_version() if is_ffmpeg_available() else None
    tui.message_box(stdscr, "Tentang", [
        f"YouTube/X Video & Audio Downloader v{APP_VERSION}",
        "",
        f"yt-dlp  : {ytdlp_v}",
        f"ffmpeg  : {ffmpeg_v or 'tidak ditemukan'}",
        f"Python  : {_platform.python_version()}",
    ])


def _interactive_app(stdscr):
    """Satu sesi curses yang membungkus seluruh menu interaktif (Dashboard, Download, Pengaturan)."""
    cfg = load_config()
    tui.init_theme(stdscr, cfg.get("bg_color", "putih"), cfg.get("text_color", "hitam"))
    while True:
        idx = tui.menu(
            stdscr, "MENU UTAMA",
            ["Dashboard", "Download video", "Pengaturan", "Tentang", "Keluar"],
            banner="🎬 YouTube Video & Audio Downloader 🎵",
        )
        if idx is None or idx == 4:
            return
        elif idx == 0:
            run_dashboard_menu(stdscr)
        elif idx == 1:
            run_download_menu(stdscr)
        elif idx == 2:
            _settings_loop(stdscr)
        elif idx == 3:
            _show_about(stdscr)


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    with AppLock() as locked:
        if not locked:
            print("⚠️  Ada proses download_video_cli lain yang masih jalan (menu atau CLI).")
            print("    Tunggu sampai selesai, atau hapus 'download/.lock' manual kalau yakin itu sisa proses yang crash.")
            return

        if args.urls or args.url_file:
            try:
                run_cli(args)
            except KeyboardInterrupt:
                print("\n\n⏹️  Dibatalkan oleh user.")
            return

        try:
            show_intro()
            clear_screen()
            show_logo()
            check_config_integrity()
            startup_check_and_notify()
            input("Tekan Enter untuk masuk ke menu...")
            curses.wrapper(_interactive_app)
            clear_screen()
            print("Sampai jumpa!")
        except KeyboardInterrupt:
            print("\n\n👋 Dibatalkan, sampai jumpa!")


if __name__ == "__main__":
    main()