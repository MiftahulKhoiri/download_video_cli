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


# ---------- Logo pembuka animasi: efek hujan digital (Matrix) ----------

_LOGO_LINES = [
    " __    __  __    __    {●}",
    " \\ \\/ / /  \  /  \   {●}",
    "  \\ V / / /\ \/ /\ \  {●}",
    "   \\_/ /_/  \__/  \_\ {●}",
]

_TAGLINE = " Video & MP3 Downloader"

_INTRO_BLOCK = _LOGO_LINES + ["", _TAGLINE]

# Katakana setengah-lebar + angka, karakter khas efek "digital rain"
_MATRIX_CHARS = "ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀﾇﾍ0123456789"


def _matrix_rain_reveal(lines, duration=8.0, frame_delay=0.06,
                         trail_len=5, reveal_color=Fore.WHITE):
    """
    Render 'lines' berulang di posisi yang sama (cursor naik tiap frame).
    Tiap kolom punya 'tetesan' karakter acak yang jatuh terus-menerus (efek hujan
    digital); makin lama makin banyak sel yang berhenti dan menampilkan karakter
    asli logo, sampai semuanya ke-reveal di akhir durasi.
    """
    width = max(len(line) for line in lines)
    padded = [line.ljust(width) for line in lines]
    height = len(padded)

    target = padded
    revealed = [[padded[r][c] == " " for c in range(width)] for r in range(height)]

    col_head = [random.randint(-height * 2, 0) for _ in range(width)]
    col_speed = [random.choice([1, 1, 2]) for _ in range(width)]

    def render():
        out = []
        for r in range(height):
            row_chars = []
            for c in range(width):
                if revealed[r][c]:
                    ch = target[r][c]
                    row_chars.append(f"{reveal_color}{ch}{Style.RESET_ALL}" if ch != " " else " ")
                else:
                    head = col_head[c]
                    if head - trail_len <= r <= head:
                        if r == head:
                            row_chars.append(f"{Style.BRIGHT}{Fore.WHITE}{random.choice(_MATRIX_CHARS)}{Style.RESET_ALL}")
                        else:
                            row_chars.append(f"{Fore.GREEN}{random.choice(_MATRIX_CHARS)}{Style.RESET_ALL}")
                    else:
                        row_chars.append(" ")
            out.append("".join(row_chars))
        return out

    start = time.time()
    while time.time() - start < duration:
        elapsed = time.time() - start
        frac = min(1.0, elapsed / duration)
        reveal_prob = 0.01 + frac * 0.25  # makin lama makin cepat "kelar"

        for c in range(width):
            col_head[c] += col_speed[c]
            if col_head[c] - trail_len > height:
                col_head[c] = random.randint(-height, 0)

            head = col_head[c]
            for r in range(height):
                if not revealed[r][c] and r <= head and random.random() < reveal_prob:
                    revealed[r][c] = True

        for line in render():
            sys.stdout.write(line + "\x1b[K\n")
        sys.stdout.flush()
        time.sleep(frame_delay)
        sys.stdout.write(Cursor.UP(height))

    for r in range(height):
        for c in range(width):
            revealed[r][c] = True
    for line in render():
        sys.stdout.write(line + "\x1b[K\n")
    sys.stdout.flush()


def show_intro(duration=7):
    """
    Splash screen animasi, dipanggil SEKALI di awal program (main.py) sebelum
    masuk ke menu utama. Total durasi kira-kira duration + 1.5 detik.
    Tekan Ctrl+C buat langsung lewati kalau nggak mau nunggu.
    """
    try:
        clear_screen()
        print("\n" * 2)
        print(f"{Fore.GREEN}[SYSTEM] Terhubung ke server...{Style.RESET_ALL}\n")

        _matrix_rain_reveal(_INTRO_BLOCK, duration=duration)

        print(f"\n{Fore.GREEN}✅ Koneksi stabil.{Style.RESET_ALL}")
        time.sleep(0.6)
        print(f"{Fore.CYAN}⏳ Memuat aplikasi...{Style.RESET_ALL}")
        time.sleep(0.6)
    except KeyboardInterrupt:
        print()  # biar prompt berikutnya nggak nempel di baris animasi


if __name__ == "__main__":
    show_intro()