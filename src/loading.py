# src/loading.py
import itertools
import os
import sys
import threading
import time
from colorama import Fore, Style


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


# Warna berubah tiap kelipatan 20%, dari merah (baru mulai) ke hijau (hampir kelar).
_COLOR_STEPS = [
    (0, Fore.RED),
    (20, Fore.YELLOW),
    (40, Fore.MAGENTA),
    (60, Fore.CYAN),
    (80, Fore.GREEN),
]


def _color_for_percent(percent):
    color = _COLOR_STEPS[0][1]
    for threshold, c in _COLOR_STEPS:
        if percent >= threshold:
            color = c
    return color


def _render_bar(percent, width=30):
    percent = max(0, min(100, percent))
    filled = int(width * percent / 100)
    color = _color_for_percent(percent)
    bar = (
        color + ("█" * filled) + Style.RESET_ALL
        + Fore.LIGHTBLACK_EX + ("░" * (width - filled)) + Style.RESET_ALL
    )
    return bar, color


_first_line = True


def reset_progress():
    """Panggil sebelum tiap download baru, biar progress bar nggak nyangkut kalau download sebelumnya error."""
    global _first_line
    _first_line = True


_print_lock = threading.Lock()


def safe_print(msg=""):
    """Print yang aman dipanggil dari banyak thread sekaligus (dipakai pas mode download paralel)."""
    with _print_lock:
        print(msg)


def noop_hook(d):
    """
    Progress/postprocessor hook kosong. Dipakai pas mode paralel biar progress bar
    per-karakter dari beberapa thread nggak saling tumpang tindih di terminal.
    """
    pass


def progress_hook(d):
    global _first_line

    if d["status"] == "downloading":
        filename = d.get("filename", "")
        short_name = filename.split("/")[-1]
        if len(short_name) > 35:
            short_name = short_name[:32] + "..."

        percent = _parse_percent(d)
        bar, color = _render_bar(percent)

        if _first_line:
            print(f"{Fore.CYAN}📄 {short_name}{Style.RESET_ALL}")
            _first_line = False

        sys.stdout.write(f"\r[{bar}] {color}{percent:5.1f}%{Style.RESET_ALL}")
        sys.stdout.flush()

    elif d["status"] == "finished":
        _first_line = True
        print()

    elif d["status"] == "error":
        _first_line = True
        print(f"\n{Fore.RED}❌ Terjadi error saat mengunduh.{Style.RESET_ALL}")


# Pesan (mulai, selesai) buat tiap postprocessor yang relevan buat user.
_PP_MESSAGES = {
    "Merger": (f"{Fore.CYAN}🔗 Menggabungkan video & audio...{Style.RESET_ALL}",
               f"{Fore.GREEN}✅ Video & audio berhasil digabung.{Style.RESET_ALL}"),
    "FFmpegExtractAudio": (f"{Fore.CYAN}🎵 Mengonversi ke MP3...{Style.RESET_ALL}",
                            f"{Fore.GREEN}✅ Konversi ke MP3 selesai.{Style.RESET_ALL}"),
}


def postprocessor_hook(d):
    """Dipanggil yt-dlp pas proses pasca-download (merge/convert) berjalan."""
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


class Spinner:
    """
    Spinner kecil biar user tau proses masih jalan (bukan macet) pas nunggu
    request jaringan yang nggak punya progress sendiri, misal ambil info video
    atau cek isi playlist. Dipakai sebagai context manager:

        with Spinner("Mengambil info video..."):
            info = get_video_info(url)
    """
    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message="Memuat..."):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = None

    def _spin(self):
        for frame in itertools.cycle(self._FRAMES):
            if self._stop_event.is_set():
                break
            sys.stdout.write(f"\r{Fore.CYAN}{frame}{Style.RESET_ALL} {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)

    def __enter__(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._stop_event.set()
        if self._thread:
            self._thread.join()
        clear_len = len(self.message) + 4
        sys.stdout.write("\r" + " " * clear_len + "\r")
        sys.stdout.flush()
        return False