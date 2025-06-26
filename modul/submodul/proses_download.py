import sys
import os
from colorama import Fore, Style, init
from modul.submodul.program import *

def print_progress_bar(percent, width=32, color=Fore.GREEN, msg=""):
    fill_len = int(width * percent // 100)
    empty_len = width - fill_len
    bar = color + '█' * fill_len + Style.RESET_ALL + '░' * empty_len
    progress = f"{percent:6.2f}%"
    sys.stdout.write(f"\r{bar} {progress} {msg}")
    sys.stdout.flush()
    if percent >= 100:
        print()
        sys.stdout.flush()

# Perbaikan utama: progress hook lebih robust, memakai field yang benar untuk persen, speed, dan ETA
def yt_progress_hook(status):
    if status['status'] == 'downloading':
        downloaded = status.get('downloaded_bytes', 0)
        total = status.get('total_bytes') or status.get('total_bytes_estimate') or 0
        if total:
            percent = downloaded / total * 100
        else:
            percent = 0.0

        speed = status.get('speed', 0)
        speed_str = f"{speed/1024:.1f} KB/s" if speed else "N/A"
        eta = status.get('eta', 0)
        eta_str = f"{int(eta)}s" if eta else "-"

        color = (
            Fore.RED if percent < 33 else
            Fore.YELLOW if percent < 66 else
            Fore.GREEN if percent < 99.99 else
            Fore.CYAN
        )
        msg = f"Speed: {speed_str} ETA: {eta_str}"
        print_progress_bar(percent, width=32, color=color, msg=msg)
    elif status['status'] == 'finished':
        print_progress_bar(100, width=32, color=Fore.CYAN, msg="Done!")

