import os
import sys


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def show_logo():
    logo = r"""
 __   _____   ___          _
 \ \ / /_   ) |   \ _ __  | |
  \ V / / /  | |) | '  \ | |__
   \_/ /___| |___/|_|_|_||____|

  🎬 YouTube / X Video & MP3 Downloader 🎵
    """
    print(logo)


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