# src/logo.py
import sys
import time
from colorama import init, Fore, Style, Cursor

from src.loading import clear_screen

init(autoreset=True)  # otomatis reset warna setelah setiap print


def show_logo():
    print(Fore.CYAN + " __   _____   ___          _")
    print(Fore.YELLOW + " \\ \\ / /_   ) |   \\ _ __  | |")
    print(Fore.GREEN + "  \\ V / / /  | |) | '  \\ | |__")
    print(Fore.MAGENTA + "   \\_/ /___| |___/|_|_|_||____|")
    print()
    print(Fore.RED + "🎬 " + Fore.BLUE + "YouTube" + Fore.WHITE + " / " + Fore.CYAN + "X" + Fore.WHITE + " Video & " + Fore.GREEN + "MP3 Downloader" + Fore.RED + " 🎵")
    print()


# ---------- Logo pembuka animasi (splash screen) ----------

_LOGO_LINES = [
    " __   _____   ___          _",
    " \\ \\ / /_   ) |   \\ _ __  | |",
    "  \\ V / / /  | |) | '  \\ | |__",
    "   \\_/ /___| |___/|_|_|_||____|",
]

_TAGLINE = "🎬 YouTube / X Video & MP3 Downloader 🎵"

# Urutan warna buat efek gelombang -- ini yang bikin kelihatan "mengalir" tiap frame.
_RAINBOW = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]

_BLOCK_HEIGHT = len(_LOGO_LINES) + 2  # logo + 1 baris kosong + tagline


def _wave_color(position, offset):
    return _RAINBOW[(position + offset) % len(_RAINBOW)]


def _colorize_line(text, row_seed, frame_offset):
    """Warnai tiap karakter non-spasi sesuai posisi + waktu, biar warnanya kelihatan bergerak."""
    out = []
    for col, ch in enumerate(text):
        if ch == " ":
            out.append(ch)
        else:
            out.append(f"{_wave_color(col + row_seed, frame_offset)}{ch}{Style.RESET_ALL}")
    return "".join(out)


def _typewriter(lines, row_seed_start=0, delay=0.03):
    """Tampilkan baris demi baris, karakter demi karakter, kesan 'diketik'."""
    for i, line in enumerate(lines):
        buffer = ""
        for ch in line:
            buffer += ch
            color = _wave_color(len(buffer), row_seed_start + i)
            sys.stdout.write(f"\r{color}{buffer}{Style.RESET_ALL}\x1b[K")
            sys.stdout.flush()
            time.sleep(delay)
        print()


def _animate_wave(seconds):
    """
    Render ulang logo + tagline di posisi yang sama (cursor naik tiap frame)
    dengan warna yang terus bergeser, sampai durasi habis.
    """
    start = time.time()
    frame = 0

    while time.time() - start < seconds:
        for row, line in enumerate(_LOGO_LINES):
            sys.stdout.write(_colorize_line(line, row * 3, frame) + "\x1b[K\n")
        sys.stdout.write("\x1b[K\n")
        sys.stdout.write(_colorize_line(_TAGLINE, 0, frame + 3) + "\x1b[K\n")
        sys.stdout.flush()

        time.sleep(0.08)
        frame += 1
        sys.stdout.write(Cursor.UP(_BLOCK_HEIGHT))

    # Bersihkan blok animasi biar nggak numpuk sama tampilan berikutnya
    for _ in range(_BLOCK_HEIGHT):
        sys.stdout.write("\x1b[K\n")
    sys.stdout.write(Cursor.UP(_BLOCK_HEIGHT))
    sys.stdout.flush()


def show_intro(wave_seconds=8):
    """
    Splash screen animasi, dipanggil SEKALI di awal program (main.py) sebelum
    masuk ke menu utama. Total durasi kira-kira 12-13 detik.
    Tekan Ctrl+C buat langsung lewati kalau nggak mau nunggu.
    """
    try:
        clear_screen()
        print("\n" * 2)
        _typewriter(_LOGO_LINES)
        print()
        _typewriter([_TAGLINE], row_seed_start=len(_LOGO_LINES), delay=0.02)
        time.sleep(0.4)

        sys.stdout.write(Cursor.UP(_BLOCK_HEIGHT))
        _animate_wave(wave_seconds)

        print(f"\n{Fore.CYAN}⏳ Memuat aplikasi...{Style.RESET_ALL}")
        time.sleep(0.6)
    except KeyboardInterrupt:
        print()  # biar prompt berikutnya nggak nempel di baris animasi


if __name__ == "__main__":
    show_logo()