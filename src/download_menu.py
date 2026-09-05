# src/download_menu.py
"""
Lapisan menu interaktif -- SEMUA navigasi & input pakai TUI (curses).
Proses kerja beneran (fetch info, download, progress bar) tetap pakai
output teks biasa yang sudah teruji, dijalankan lewat tui.suspend() biar
curses nggak tabrakan sama print()/spinner yang ada.
"""
from src.config import load_config
from src.media_info import is_ffmpeg_available, get_video_info, expand_playlist, get_available_resolutions
from src.download_core import (
    LOSSY_AUDIO_FORMATS,
    download_single, download_many, download_audio_single, download_audio_many,
)
from src import tui

_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
_QUALITIES = ["128", "192", "256", "320"]


def _parse_time_to_seconds(text):
    parts = [int(p) for p in text.strip().split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def _pilih_rentang_waktu_tui(stdscr):
    """Return (start, end) detik, atau None kalau nggak dipotong (kosong/Esc)."""
    mulai = tui.input_box(
        stdscr, "Potong Durasi (Opsional)",
        "Waktu mulai, format MM:SS atau HH:MM:SS. Kosongkan = unduh penuh.",
    )
    if not mulai or not mulai.strip():
        return None
    try:
        start_sec = _parse_time_to_seconds(mulai.strip())
    except ValueError:
        tui.message_box(stdscr, "Nilai Tidak Valid", "Format waktu salah, video diunduh penuh.")
        return None

    selesai = tui.input_box(
        stdscr, "Potong Durasi (Opsional)",
        "Waktu selesai, format sama. Kosongkan = sampai akhir.",
    )
    end_sec = None
    if selesai and selesai.strip():
        try:
            end_sec = _parse_time_to_seconds(selesai.strip())
        except ValueError:
            tui.message_box(stdscr, "Nilai Tidak Valid", "Format waktu selesai salah, diabaikan.")
    return (start_sec, end_sec)


def _pilih_resolusi_tui(stdscr, video_formats, config=None):
    """Return (height, label). label None berarti dibatalkan (Esc)."""
    config = config or {}
    if not video_formats:
        return None, "terbaik"

    default_res = config.get("default_resolution")
    msg = None
    if default_res:
        for f in video_formats:
            if f["height"] == default_res:
                return f["height"], f"{f['height']}p"
        msg = f"Resolusi default ({default_res}p) tidak tersedia untuk video ini."

    items = [f"{f['height']}p ({f.get('ext', '?')})" for f in video_formats] + ["Terbaik (auto)"]
    idx = tui.menu(stdscr, "Pilih Resolusi", items, message=msg)
    if idx is None:
        return None, None
    if idx == len(video_formats):
        return None, "terbaik"
    return video_formats[idx]["height"], f"{video_formats[idx]['height']}p"


def _pilih_format_audio_tui(stdscr, config=None):
    """Return (audio_format, quality). audio_format None berarti dibatalkan (Esc)."""
    config = config or {}
    default_format = config.get("audio_format", "mp3")
    start = _AUDIO_FORMATS.index(default_format) if default_format in _AUDIO_FORMATS else 0
    idx = tui.menu(stdscr, "Format Audio", _AUDIO_FORMATS, selected=start)
    if idx is None:
        return None, None
    audio_format = _AUDIO_FORMATS[idx]

    if audio_format not in LOSSY_AUDIO_FORMATS:
        return audio_format, None

    default_quality = str(config.get("mp3_quality", "192"))
    startk = _QUALITIES.index(default_quality) if default_quality in _QUALITIES else 1
    idxk = tui.menu(stdscr, "Kualitas Audio", [f"{q} kbps" for q in _QUALITIES], selected=startk)
    if idxk is None:
        return None, None
    return audio_format, _QUALITIES[idxk]


def _kumpulkan_urls_tui(stdscr):
    idx = tui.menu(stdscr, "Sumber URL", ["Ketik manual", "Import dari file .txt"])
    if idx is None:
        return []

    if idx == 1:
        path = tui.input_box(stdscr, "Import File", "Path file .txt (satu URL per baris):")
        if not path or not path.strip():
            return []
        try:
            with open(path.strip(), "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        except OSError as e:
            tui.message_box(stdscr, "Error", f"❌ Gagal membaca file: {e}")
            return []

    urls = []
    while True:
        u = tui.input_box(stdscr, "Ketik URL", f"URL ke-{len(urls) + 1} (kosongkan buat selesai):")
        if not u or not u.strip():
            break
        urls.append(u.strip())
    return urls


def _resolve_urls_and_info(stdscr, raw_urls, config, label):
    """
    Expand playlist + ambil info + resolusi tersedia. Dijalankan di mode
    teks biasa (curses disuspend) karena manggil get_video_info/expand_playlist
    yang punya spinner sendiri. Return (urls, info, formats) atau None kalau
    gagal/kosong (pesan udah ditampilkan ke user).
    """
    try:
        with tui.suspend(stdscr):
            print(f"===== {label} =====")
            urls = []
            for u in raw_urls:
                expanded = expand_playlist(u, cookies_file=config.get("cookies_file"))
                if len(expanded) > 1:
                    print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} item ditambahkan.")
                urls.extend(expanded)

            if not urls:
                print("Tidak ada item yang bisa diunduh dari URL yang dimasukkan.")
                input("\nTekan Enter untuk lanjut...")
                return None

            info = get_video_info(urls[0], cookies_file=config.get("cookies_file"))
            formats = get_available_resolutions(info)
            return urls, info, formats
    except Exception as e:
        tui.message_box(stdscr, "Error", f"❌ Terjadi kesalahan: {e}")
        return None


def menu_download_1(stdscr):
    config = load_config()
    url = tui.input_box(stdscr, "Download Video", "Masukkan URL video atau playlist:")
    if not url or not url.strip():
        return

    resolved = _resolve_urls_and_info(stdscr, [url.strip()], config, "DOWNLOAD 1 VIDEO")
    if resolved is None:
        return
    urls, info, formats = resolved

    height, label = _pilih_resolusi_tui(stdscr, formats, config)
    if label is None:
        return

    if len(urls) > 1:
        with tui.suspend(stdscr):
            download_many(urls, target_height=height, resolution_label=label, first_info=info, config=config)
            input("\nTekan Enter untuk lanjut...")
    else:
        section_range = _pilih_rentang_waktu_tui(stdscr)
        with tui.suspend(stdscr):
            download_single(
                urls[0], target_height=height, resolution_label=label, info=info,
                config=config, section_range=section_range,
            )
            input("\nTekan Enter untuk lanjut...")


def menu_download_banyak(stdscr):
    config = load_config()
    urls_input = _kumpulkan_urls_tui(stdscr)
    if not urls_input:
        return

    resolved = _resolve_urls_and_info(stdscr, urls_input, config, "DOWNLOAD BANYAK VIDEO")
    if resolved is None:
        return
    urls, info, formats = resolved

    height, label = _pilih_resolusi_tui(stdscr, formats, config)
    if label is None:
        return

    with tui.suspend(stdscr):
        download_many(urls, target_height=height, resolution_label=label, first_info=info, config=config)
        input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_1(stdscr):
    if not is_ffmpeg_available():
        tui.message_box(stdscr, "ffmpeg Tidak Ditemukan", [
            "Convert audio butuh ffmpeg.",
            "Install: pkg install ffmpeg (Termux)",
            "atau: sudo apt install ffmpeg (Linux)",
        ])
        return

    config = load_config()
    url = tui.input_box(stdscr, "Download Audio", "Masukkan URL video atau playlist:")
    if not url or not url.strip():
        return

    audio_format, quality = _pilih_format_audio_tui(stdscr, config)
    if audio_format is None:
        return

    try:
        with tui.suspend(stdscr):
            print("===== DOWNLOAD AUDIO (1 ITEM) =====")
            urls = expand_playlist(url.strip(), cookies_file=config.get("cookies_file"))
            if len(urls) > 1:
                print(f"\n📋 Playlist terdeteksi: {len(urls)} audio akan diunduh.")
    except Exception as e:
        tui.message_box(stdscr, "Error", f"❌ Terjadi kesalahan: {e}")
        return

    cfg_override = {**config, "audio_format": audio_format}
    if quality:
        cfg_override["mp3_quality"] = quality

    if len(urls) > 1:
        with tui.suspend(stdscr):
            download_audio_many(urls, config=cfg_override)
            input("\nTekan Enter untuk lanjut...")
    else:
        section_range = _pilih_rentang_waktu_tui(stdscr)
        with tui.suspend(stdscr):
            download_audio_single(
                urls[0], audio_format=audio_format, quality=quality,
                config=config, section_range=section_range,
            )
            input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_banyak(stdscr):
    if not is_ffmpeg_available():
        tui.message_box(stdscr, "ffmpeg Tidak Ditemukan", [
            "Convert audio butuh ffmpeg.",
            "Install: pkg install ffmpeg (Termux)",
            "atau: sudo apt install ffmpeg (Linux)",
        ])
        return

    config = load_config()
    urls_input = _kumpulkan_urls_tui(stdscr)
    if not urls_input:
        return

    audio_format, quality = _pilih_format_audio_tui(stdscr, config)
    if audio_format is None:
        return

    try:
        with tui.suspend(stdscr):
            print("===== DOWNLOAD AUDIO (BANYAK ITEM) =====")
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
    except Exception as e:
        tui.message_box(stdscr, "Error", f"❌ Terjadi kesalahan: {e}")
        return

    if not urls:
        return

    cfg_override = {**config, "audio_format": audio_format}
    if quality:
        cfg_override["mp3_quality"] = quality

    with tui.suspend(stdscr):
        download_audio_many(urls, config=cfg_override)
        input("\nTekan Enter untuk lanjut...")


def run_download_menu(stdscr):
    """Loop menu download TUI, dipanggil dari main dengan stdscr dari sesi curses yang sama."""
    while True:
        config = load_config()
        msg = []
        if not is_ffmpeg_available():
            msg.append("⚠️  ffmpeg tidak ditemukan, merge/convert bakal ditolak.")
        if config.get("parallel_workers", 1) > 1:
            msg.append(f"⚡ Mode paralel aktif: {config['parallel_workers']}x download sekaligus")

        items = ["Download video (1)", "Download video (banyak)",
                 "Download audio (1)", "Download audio (banyak)", "Kembali"]
        idx = tui.menu(stdscr, "MENU DOWNLOAD", items, message=msg or None)

        if idx is None or idx == len(items) - 1:
            return

        [menu_download_1, menu_download_banyak, menu_download_mp3_1, menu_download_mp3_banyak][idx](stdscr)