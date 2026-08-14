# src/logo.py
import random
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


# ---------- Logo pembuka animasi: efek decrypt/hacker ----------

_LOGO_LINES = [
    " __   _____   ___          _",
    " \\ \\ / /_   ) |   \\ _ __  | |",
    "  \\ V / / /  | |) | '  \\ | |__",
    "   \\_/ /___| |___/|_|_|_||____|",
]

_TAGLINE = "YouTube / X Video & MP3 Downloader"

_INTRO_BLOCK = _LOGO_LINES + ["", _TAGLINE]

# Karakter acak yang dipakai buat efek "belum ke-decrypt"
_SCRAMBLE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*<>/\\|=+-_"


def _decrypt_reveal(lines, duration=15.0, frame_delay=0.045,
                     scramble_color=Fore.GREEN, reveal_color=Fore.CYAN):
    """
    Render 'lines' berulang di posisi yang sama (cursor naik tiap frame).
    Tiap karakter non-spasi mulai sebagai simbol acak, lalu satu-satu
    di-'lock' jadi karakter asli secara acak sampai semua ke-reveal.
    """
    positions = [(r, c) for r, line in enumerate(lines) for c, ch in enumerate(line) if ch != " "]
    random.shuffle(positions)

    total_frames = max(1, int(duration / frame_delay))
    batch_size = max(1, -(-len(positions) // total_frames))  # ceil division

    revealed = [[False] * len(line) for line in lines]
    idx = 0

    def render():
        out = []
        for row, line in enumerate(lines):
            chars = []
            for col, ch in enumerate(line):
                if ch == " ":
                    chars.append(" ")
                elif revealed[row][col]:
                    chars.append(f"{reveal_color}{ch}{Style.RESET_ALL}")
                else:
                    chars.append(f"{scramble_color}{random.choice(_SCRAMBLE_CHARS)}{Style.RESET_ALL}")
            out.append("".join(chars))
        return out

    while idx < len(positions):
        for _ in range(batch_size):
            if idx >= len(positions):
                break
            r, c = positions[idx]
            revealed[r][c] = True
            idx += 1

        for line in render():
            sys.stdout.write(line + "\x1b[K\n")
        sys.stdout.flush()
        time.sleep(frame_delay)
        sys.stdout.write(Cursor.UP(len(lines)))

    for line in render():
        sys.stdout.write(line + "\x1b[K\n")
    sys.stdout.flush()


def show_intro(duration=9.0):
    """
    Splash screen animasi, dipanggil SEKALI di awal program (main.py) sebelum
    masuk ke menu utama. Total durasi kira-kira duration + 1.5 detik.
    Tekan Ctrl+C buat langsung lewati kalau nggak mau nunggu.
    """
    try:
        clear_screen()
        print("\n" * 2)
        print(f"{Fore.GREEN}[SYSTEM] Mendekripsi data...{Style.RESET_ALL}\n")

        _decrypt_reveal(_INTRO_BLOCK, duration=duration)

        print(f"\n{Fore.GREEN}🔓 Akses diterima.{Style.RESET_ALL}")
        time.sleep(0.6)
        print(f"{Fore.CYAN}⏳ Memuat aplikasi...{Style.RESET_ALL}")
        time.sleep(0.6)
    except KeyboardInterrupt:
        print()  # biar prompt berikutnya nggak nempel di baris animasi


if __name__ == "__main__":
    show_intro()