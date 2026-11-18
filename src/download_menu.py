# src/download_menu.py
"""
Lapisan menu interaktif -- SEMUANYA pakai TUI (curses): navigasi, input,
DAN proses kerjanya (cek URL/playlist, ambil info, download + progress).
Proses yang lama dijalankan di thread terpisah lewat src/tui_progress.py,
sementara thread utama menggambar layar progress-nya.
"""
from urllib.parse import urlparse, parse_qs

from src.config import load_config
from src.media_info import is_ffmpeg_available, get_video_info, expand_playlist, get_available_resolutions
from src.download_core import (
    LOSSY_AUDIO_FORMATS,
    download_single, download_many, download_audio_single, download_audio_many,
)
from src.logger import get_logger
from src.utils import strip_ansi
from src.errors import explain_error
from src.reporter import report
from src import tui
from src.tui_progress import run_busy, run_download_screen

log = get_logger()

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
            end_sec = None
        else:
            if end_sec <= start_sec:
                tui.message_box(
                    stdscr, "Nilai Tidak Valid",
                    f"Waktu selesai ({selesai.strip()}) harus lebih besar dari waktu mulai ({mulai.strip()}). "
                    "Diabaikan, unduh sampai akhir.",
                )
                end_sec = None
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
        prompt = []
        if urls:
            prompt.append("URL yang sudah dimasukkan:")
            prompt.extend(f"{i}. {u}" for i, u in enumerate(urls, 1))
            prompt.append("")
        prompt.append(f"URL ke-{len(urls) + 1} (kosongkan buat selesai):")

        u = tui.input_box(stdscr, "Ketik URL", prompt)
        if not u or not u.strip():
            break
        urls.append(u.strip())
    return urls


def _cookies_used(config=None):
    """True kalau file cookies diset (buat milih petunjuk error yang pas)."""
    try:
        cfg = config if config is not None else load_config()
        return bool(cfg.get("cookies_file"))
    except Exception:
        return False


def _error_lines(e, config):
    """Pesan error + petunjuk sebagai list baris, buat tui.message_box."""
    lines = explain_error(e, cookies_used=_cookies_used(config), indent="").split("\n")
    return [f"❌ {lines[0]}"] + ([""] + lines[1:] if len(lines) > 1 else [])


def _jalankan(stdscr, fn, heading="Download"):
    """
    Jalankan proses download (fn) dengan layar progress TUI. Error atau pembatalan
    di tengah jalan nggak pernah menutup seluruh app -- ditampilkan di layar progress,
    lalu balik ke menu setelah user menekan Enter.
    """
    run_download_screen(stdscr, heading, fn)


def _is_video_in_playlist(url):
    """True kalau URL menunjuk ke SATU video tapi nyempil di playlist (watch?v=..&list=.. atau youtu.be/..?list=..)."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
    except ValueError:
        return False
    if "list" not in query:
        return False
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        return True
    return "v" in query and parsed.path.rstrip("/") == "/watch"


def _expand_urls_tui(stdscr, raw_urls, config, label, unit="item"):
    """
    Expand playlist (kotak spinner TUI selama proses; URL yang gagal dirangkum di kotak pesan).
    URL video yang nyempil di playlist ditanyakan dulu: unduh semua, atau video itu saja.
    Return list URL, atau None kalau gagal/kosong/dibatalkan (pesan sudah ditampilkan ke user).
    """
    retries = config.get("retry_count", 1)
    cookies_used = _cookies_used(config)

    def _periksa():
        pairs, failed = [], 0
        for i, u in enumerate(raw_urls, 1):
            try:
                with report().status(f"Memeriksa URL {i}/{len(raw_urls)}: {u}"):
                    expanded = expand_playlist(u, cookies_file=config.get("cookies_file"), retries=retries)
            except Exception as e:
                # Satu URL bermasalah (video dihapus/private/typo) nggak boleh
                # menggagalkan URL LAIN yang udah ditulis user di layar ini.
                failed += 1
                report().message(f"❌ Gagal memeriksa {u}:\n   {explain_error(e, cookies_used=cookies_used)}")
                log.warning(f"Gagal expand URL {u}: {strip_ansi(e)}")
                continue
            if len(expanded) > 1:
                report().message(f"📋 Playlist terdeteksi ({u}): {len(expanded)} {unit} ditemukan.")
            pairs.append((u, expanded))
        return pairs, failed

    try:
        (pairs, failed), messages = run_busy(stdscr, label, _periksa, "Memeriksa URL / playlist...")
    except KeyboardInterrupt:
        return None
    except Exception as e:
        tui.message_box(stdscr, "Error", _error_lines(e, config))
        return None

    if failed:
        lines = []
        for m in messages:
            lines.extend(m.split("\n"))
        if not pairs:
            # Semua gagal: cukup SATU kotak (alasan + kesimpulan), bukan dua kotak berturut-turut.
            tui.message_box(stdscr, label, lines + ["", f"Tidak ada {unit} yang bisa diunduh."])
            return None
        tui.message_box(stdscr, "Ada URL yang Gagal Diperiksa", lines + ["", f"{len(pairs)} URL lain tetap dilanjutkan."])

    urls = []
    for u, expanded in pairs:
        if len(expanded) > 1 and _is_video_in_playlist(u):
            idx = tui.menu(
                stdscr, "Playlist Terdeteksi",
                [f"Unduh semua ({len(expanded)} {unit})", "Hanya video ini", "Lewati URL ini"],
                message=["URL ini video yang nyempil di playlist:", u],
            )
            if idx is None or idx == 2:
                continue
            if idx == 1:
                urls.append(u)   # download_core memakai noplaylist, jadi cuma videonya yang diunduh
                continue
        urls.extend(expanded)

    if not urls:
        tui.message_box(stdscr, label, f"Tidak ada {unit} yang bisa diunduh dari URL yang dimasukkan.")
        return None
    return urls


def _resolve_urls_and_info(stdscr, raw_urls, config, label):
    """
    Expand playlist + ambil info + resolusi tersedia. Return (urls, info, formats)
    atau None kalau gagal/kosong/dibatalkan (pesan udah ditampilkan ke user).
    """
    urls = _expand_urls_tui(stdscr, raw_urls, config, label)
    if urls is None:
        return None

    def _ambil_info():
        info = get_video_info(urls[0], cookies_file=config.get("cookies_file"),
                              retries=config.get("retry_count", 1))
        return info, get_available_resolutions(info)

    try:
        (info, formats), _ = run_busy(stdscr, label, _ambil_info, "Mengambil info video...")
        return urls, info, formats
    except KeyboardInterrupt:
        return None
    except Exception as e:
        tui.message_box(stdscr, "Error", _error_lines(e, config))
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
        _jalankan(stdscr, lambda: download_many(
            urls, target_height=height, resolution_label=label, first_info=info, config=config),
            f"Download Playlist ({len(urls)} video, {label})")
    else:
        section_range = _pilih_rentang_waktu_tui(stdscr)
        _jalankan(stdscr, lambda: download_single(
            urls[0], target_height=height, resolution_label=label, info=info,
            config=config, section_range=section_range,
        ), f"Download Video ({label})")


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

    _jalankan(stdscr, lambda: download_many(
        urls, target_height=height, resolution_label=label, first_info=info, config=config),
        f"Download {len(urls)} Video ({label})")


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

    urls = _expand_urls_tui(stdscr, [url.strip()], config, "DOWNLOAD AUDIO (1 ITEM)", unit="audio")
    if not urls:
        return

    cfg_override = {**config, "audio_format": audio_format}
    if quality:
        cfg_override["mp3_quality"] = quality

    fmt_label = f"{audio_format} {quality}kbps" if quality else audio_format
    if len(urls) > 1:
        _jalankan(stdscr, lambda: download_audio_many(urls, config=cfg_override),
                  f"Download Audio Playlist ({len(urls)} item, {fmt_label})")
    else:
        section_range = _pilih_rentang_waktu_tui(stdscr)
        _jalankan(stdscr, lambda: download_audio_single(
            urls[0], audio_format=audio_format, quality=quality,
            config=config, section_range=section_range,
        ), f"Download Audio ({fmt_label})")


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

    urls = _expand_urls_tui(stdscr, urls_input, config, "DOWNLOAD AUDIO (BANYAK ITEM)", unit="audio")
    if not urls:
        return

    cfg_override = {**config, "audio_format": audio_format}
    if quality:
        cfg_override["mp3_quality"] = quality

    fmt_label = f"{audio_format} {quality}kbps" if quality else audio_format
    _jalankan(stdscr, lambda: download_audio_many(urls, config=cfg_override),
              f"Download {len(urls)} Audio ({fmt_label})")


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