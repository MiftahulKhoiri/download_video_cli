import os
from yt_dlp import YoutubeDL
from colorama import init, Fore, Style
from modul.submodul.proses_download import *
from modul.submodul.program import *

ILLEGAL_FILENAME_CHARS = r'<>:"/\|?*' 
init(autoreset=True)
NAMA_FOLDER = "hasil_download"
os.makedirs(NAMA_FOLDER, exist_ok=True)

def unduh_facebook(alamat, cookies_path=None, resolusi=None):
    try:
        with YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(alamat, download=False)
            judul = info.get('title', 'facebook_video')
            ekstensi = info.get('ext', 'mp4')
        tanggal = tanggal_hari_ini()
        nama_file = cek_file_dan_konfirmasi(judul, ekstensi, tanggal)
        if not nama_file:
            return  # Batal
        hasil_output = os.path.join(NAMA_FOLDER, nama_file)
        opsi = {
            'format': f"bestvideo[height<={resolusi}]+bestaudio/best[height<={resolusi}]" if resolusi else "bestvideo+bestaudio/best",
            'outtmpl': hasil_output,
            'noplaylist': True,
            'quiet': False,
            'progress_hooks': [yt_progress_hook],
        }
        if cookies_path:
            opsi['cookiefile'] = cookies_path
        with YoutubeDL(opsi) as ydl:
            ydl.download([alamat])
        print(Fore.GREEN + f"Download Facebook sukses. File: {hasil_output}")
    except Exception as e:
        print(Fore.RED + f"Download Facebook gagal! {e}")


