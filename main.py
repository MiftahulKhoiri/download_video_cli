import argparse
import curses
import sys

from src.dashboard import run_dashboard_menu
from src.download_menu import run_download_menu
from src.media_info import expand_playlist
from src.download_core import download_many, download_audio_many
from src.loading import clear_screen
from src.logo import show_logo, show_intro
from src.config import load_config, _settings_loop, check_config_integrity, MAX_PARALLEL_WORKERS, MAX_RETRY_COUNT
from src.lock import AppLock
from src.updater import startup_check_and_notify
from src.utils import parse_rate_limit, strip_ansi
from src import tui

APP_VERSION = "1.1.0"

# Kode keluar mode CLI (penting buat cron/script): 0 = semua beres, selain itu ada masalah.
EXIT_OK = 0
EXIT_FAILED = 1         # ada unduhan/URL yang gagal, atau nggak ada URL yang bisa diproses
EXIT_LOCKED = 3         # ada proses download_video_cli lain yang lagi jalan
EXIT_INTERRUPTED = 130  # dibatalkan (Ctrl+C)


def _positive_int(value):
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' bukan angka")
    if n < 1:
        raise argparse.ArgumentTypeError("harus angka >= 1")
    return n


def _bounded_int(lo, hi):
    def _conv(value):
        n = _positive_int(value)
        if not (lo <= n <= hi):
            raise argparse.ArgumentTypeError(f"harus angka antara {lo}-{hi}")
        return n
    return _conv


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="YouTube/X Video & Audio Downloader — mode non-interaktif (CLI)."
    )
    parser.add_argument("--url", action="append", dest="urls", metavar="URL",
                         help="URL video/playlist yang mau diunduh. Bisa dipakai berkali-kali.")
    parser.add_argument("--url-file", default=None, metavar="FILE",
                         help="Baca daftar URL dari file .txt (satu URL per baris, baris berawalan # diabaikan).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--res", type=_positive_int, default=None,
                         help="Resolusi target dalam angka (misal 720). Kosong = pakai resolusi default di pengaturan, "
                              "atau kualitas terbaik kalau itu juga kosong.")
    parser.add_argument("--no-playlist", action="store_true", dest="no_playlist",
                         help="URL video yang nyempil di playlist (watch?v=..&list=..) cuma diunduh videonya, "
                              "bukan seluruh playlist.")
    parser.add_argument("--no-intro", action="store_true", dest="no_intro",
                         help="Lewati animasi splash screen pas start (mode menu). Nggak berlaku kalau sudah "
                              "dimatikan permanen lewat Pengaturan.")
    parser.add_argument("--audio", action="store_true",
                         help="Unduh sebagai audio, bukan video.")
    parser.add_argument("--audio-format", default=None, choices=["mp3", "m4a", "opus", "flac", "wav"],
                         help="Format audio, cuma berlaku dengan --audio.")
    parser.add_argument("--quality", default=None, choices=["128", "192", "256", "320"],
                         help="Kualitas audio dalam kbps (128/192/256/320), cuma berlaku format lossy.")
    parser.add_argument("--parallel", type=_bounded_int(1, MAX_PARALLEL_WORKERS), default=None,
                         help=f"Jumlah download paralel, 1-{MAX_PARALLEL_WORKERS} (override pengaturan tersimpan).")
    parser.add_argument("--retry", type=_bounded_int(1, MAX_RETRY_COUNT), default=None,
                         help=f"Jumlah percobaan ulang kalau gagal, 1-{MAX_RETRY_COUNT} (override pengaturan tersimpan).")
    parser.add_argument("--sub", default=None, metavar="LANG1,LANG2",
                         help="Kode bahasa subtitle yang mau diunduh, pisah koma (misal id,en).")
    parser.add_argument("--cookies", default=None, metavar="FILE",
                         help="Path ke file cookies.txt (override pengaturan tersimpan).")
    parser.add_argument("--output-dir", default=None, metavar="FOLDER",
                         help="Folder tujuan hasil download (override pengaturan tersimpan).")
    parser.add_argument("--rate-limit", default=None, metavar="2M/500K",
                         help="Batas kecepatan download TOTAL, misal 2M atau 500K (override pengaturan tersimpan).")
    return parser


def run_cli(args):
    """Jalankan mode non-interaktif. Return kode keluar (EXIT_OK / EXIT_FAILED)."""
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

    problems = 0   # URL/file yang gagal diproses SEBELUM masuk tahap download

    raw_urls = list(args.urls or [])
    if args.url_file:
        try:
            with open(args.url_file, "r", encoding="utf-8") as f:
                raw_urls.extend(line.strip() for line in f if line.strip() and not line.strip().startswith("#"))
        except OSError as e:
            print(f"❌ Gagal membaca --url-file: {e}")
            problems += 1

    all_urls = []
    for u in raw_urls:
        try:
            expanded = expand_playlist(u, cookies_file=config.get("cookies_file"),
                                        retries=config.get("retry_count", 1),
                                        no_playlist=args.no_playlist)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            # Satu URL bermasalah nggak boleh menggagalkan URL lain.
            print(f"❌ Gagal memeriksa {u}: {strip_ansi(e)}")
            problems += 1
            continue
        if len(expanded) > 1:
            print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} item.")
        all_urls.extend(expanded)

    if not all_urls:
        print("Tidak ada URL yang bisa diproses.")
        return EXIT_FAILED

    if args.audio:
        hasil = download_audio_many(all_urls, config=config)
    else:
        height = args.res or config.get("default_resolution")   # tanpa --res: ikut resolusi default di pengaturan
        label = f"{height}p" if height else "terbaik"
        hasil = download_many(all_urls, target_height=height, resolution_label=label, config=config)

    return EXIT_FAILED if (hasil["gagal"] or problems) else EXIT_OK


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

    if args.rate_limit is not None and parse_rate_limit(args.rate_limit) is None:
        parser.error(f"--rate-limit '{args.rate_limit}' tidak valid. Contoh: 2M, 500K, 1.5M")

    with AppLock() as locked:
        if not locked:
            print("⚠️  Ada proses download_video_cli lain yang masih jalan (menu atau CLI).")
            print("    Tunggu sampai selesai, lalu coba lagi.")
            print("    (Kalau yakin nggak ada prosesnya, hapus 'download/.lock' lalu ulangi.)")
            return EXIT_LOCKED

        if args.urls or args.url_file:
            try:
                return run_cli(args)
            except KeyboardInterrupt:
                print("\n\n⏹️  Dibatalkan oleh user.")
                return EXIT_INTERRUPTED

        try:
            check_config_integrity()
            config = load_config()
            if config.get("show_intro", True) and not args.no_intro:
                show_intro()
            clear_screen()
            show_logo()
            startup_check_and_notify()
            input("Tekan Enter untuk masuk ke menu...")
            curses.wrapper(_interactive_app)
            clear_screen()
            print("Sampai jumpa!")
        except KeyboardInterrupt:
            print("\n\n👋 Dibatalkan, sampai jumpa!")
        return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
