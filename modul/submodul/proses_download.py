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

def hapus_file_sementara(*file_paths):
    for file_path in file_paths:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                print(Fore.RED + f"Gagal menghapus file sementara {file_path}: {e}")

def get_video_duration(file_path):
    # Ambil durasi video (detik) dengan ffprobe
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        return float(result.stdout.strip())
    except Exception:
        return None

def parse_ffmpeg_time(time_str):
    # Ubah string time ffmpeg ke detik
    if not time_str:
        return 0.0
    try:
        h, m, s = time_str.split(':')
        return float(h) * 3600 + float(m) * 60 + float(s)
    except Exception:
        return 0.0

def tampilkan_progress_ffmpeg(perintah, sumber_video):
    total_duration = get_video_duration(sumber_video)
    proses = subprocess.Popen(perintah, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    regex_time = re.compile(r'time=(\d+:\d+:\d+\.\d+)')
    last_percent = -1
    for line in proses.stdout:
        line = line.strip()
        match = regex_time.search(line)
        if match and total_duration:
            now_sec = parse_ffmpeg_time(match.group(1))
            percent = int((now_sec / total_duration) * 100)
            if percent != last_percent:
                sys.stdout.write(f"\rProgress ffmpeg: {percent}%")
                sys.stdout.flush()
                last_percent = percent
    proses.wait()
    print()
    return proses.returncode

def get_video_resolutions(alamat):
    """
    Mengambil daftar resolusi video yang tersedia dari link YouTube.
    """
    with YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(alamat, download=False)
        formats = info.get('formats', [])
        resolutions = []
        for fmt in formats:
            if fmt.get('vcodec', 'none') != 'none' and fmt.get('acodec', 'none') == 'none':
                height = fmt.get('height')
                ext = fmt.get('ext')
                if height:
                    resolutions.append((height, ext))
        # Hilangkan duplikat dan urutkan dari tinggi ke rendah
        resolutions = sorted(list(set(resolutions)), reverse=True)
    return resolutions
    
