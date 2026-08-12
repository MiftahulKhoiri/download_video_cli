# src/loading.py
import os
import sys


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def _parse_percent(d):
    pct_str = d.get("_percent_str", "0%").strip()
    try:
        return float(pct_str.replace("%", ""))
    except ValueError:
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes")
        if total and downloaded:
            return (downloaded / total) * 100
        return 0.0


def _render_bar(percent, width=30):
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    return "█" * filled + "░" * (width - filled)


_first_line = True


def reset_progress():
    """Panggil sebelum tiap download baru, biar progress bar nggak nyangkut kalau download sebelumnya error."""
    global _first_line
    _first_line = True


def progress_hook(d):
    global _first_line

    if d["status"] == "downloading":
        filename = d.get("filename", "")
        short_name = filename.split("/")[-1]
        if len(short_name) > 35:
            short_name = short_name[:32] + "..."

        percent = _parse_percent(d)
        bar = _render_bar(percent)

        if _first_line:
            print(f"📄 {short_name}")
            _first_line = False

        sys.stdout.write(f"\r[{bar}] {percent:5.1f}%")
        sys.stdout.flush()

    elif d["status"] == "finished":
        _first_line = True
        print()

    elif d["status"] == "error":
        _first_line = True
        print("\n❌ Terjadi error saat mengunduh.")


# Pesan (mulai, selesai) buat tiap postprocessor yang relevan buat user.
# Postprocessor lain (MoveFiles, Fixup, dll) sengaja didiamkan biar nggak berisik.
_PP_MESSAGES = {
    "Merger": ("🔗 Menggabungkan video & audio...", "✅ Video & audio berhasil digabung."),
    "FFmpegExtractAudio": ("🎵 Mengonversi ke MP3...", "✅ Konversi ke MP3 selesai."),
}


def postprocessor_hook(d):
    """
    Dipanggil yt-dlp pas proses pasca-download (merge/convert) berjalan.
    Tanpa ini, layar diam total selama ffmpeg bekerja dan user bisa ngira
    program hang, terutama buat video panjang atau convert MP3.
    """
    pp = d.get("postprocessor", "")
    status = d.get("status")
    messages = _PP_MESSAGES.get(pp)
    if not messages:
        return

    started_msg, finished_msg = messages
    if status == "started":
        print(started_msg)
    elif status == "finished":
        print(finished_msg)