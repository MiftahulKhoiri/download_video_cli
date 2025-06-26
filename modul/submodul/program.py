import sys
import os
import time  
from colorama import Fore, Style,init
from modul.submodul.logo import *

def folder():
    NAMA_FOLDER = "VidioDownload"
    os.makedirs(NAMA_FOLDER, exist_ok=True)
    ILLEGAL_FILENAME_CHARS = r'<>:"/\|?*'

def hapus_layar():
    """Membersihkan layar terminal di semua OS."""
    os.system('cls' if os.name == 'nt' else 'clear')

def bersihkan_nama_file(nama):
    for c in ILLEGAL_FILENAME_CHARS:
        nama = nama.replace(c, '')
    return nama.strip()

def tanggal_hari_ini():
    return datetime.datetime.now().strftime("%d-%m-%Y")

def safe_filename(name):
    return "".join(c for c in name if c.isalnum() or c in " ._-").rstrip()

def nama_file_unik(judul, ekstensi, tanggal):
    judul = safe_filename(judul)
    nama_dasar = f"{judul}_{tanggal}.{ekstensi}"
    nama_file = nama_dasar
    idx = 1
    while os.path.exists(os.path.join(NAMA_FOLDER, nama_file)):
        if idx == 1:
            nama_file = f"{judul}_{tanggal} (copy).{ekstensi}"
        else:
            nama_file = f"{judul}_{tanggal} (copy {idx}).{ekstensi}"
        idx += 1
    return nama_file

def cek_file_dan_konfirmasi(judul, ekstensi, tanggal):
    nama_file = f"{safe_filename(judul)}_{tanggal}.{ekstensi}"
    path_file = os.path.join(NAMA_FOLDER, nama_file)
    if os.path.exists(path_file):
        jawab = input(
            f"{Fore.YELLOW}File sudah ada: {nama_file}. Lanjutkan download dan simpan dengan nama baru? (y/n): "
        ).lower().strip()
        if jawab == "y":
            return nama_file_unik(judul, ekstensi, tanggal)
        else:
            print(Fore.CYAN + "Download dibatalkan.")
            return None
    else:
        return nama_file

def cek_data_buat():
    """Cek keberadaan file data/pengaturan.txt, buat jika belum ada"""
    folder = 'data'
    path_file = os.path.join(folder, 'pengaturan.txt')

    # Pastikan folder data ada
    if not os.path.exists(folder):
        os.makedirs(folder)

    # Cek dan buat file pengaturan.txt di dalam folder data
    if not os.path.exists(path_file):
        with open(path_file, 'w') as f:
            pass  # File kosong dibuat
        print("File pengaturan belum ada...\nMembuat file pengaturan di folder data...")
    else:
        print("File pengaturan sudah ada di folder data....")

def cek_isi():
    """Cek isi file data/pengaturan.txt terhadap modul pada data/requirements.txt dan update jika perlu"""
    folder = 'data'
    path_requirements = os.path.join(folder, 'requirements.txt')
    path_pengaturan = os.path.join(folder, 'pengaturan.txt')

    try:
        # Dapatkan nama modul dari requirements.txt (tanpa versi)
        with open(path_requirements, 'r') as req_file:
            required_moduls = set([
                baris.strip().split('==')[0].split('>=')[0].split('<=')[0]
                for baris in req_file if baris.strip() and not baris.startswith('#')
            ])

        # Dapatkan nama modul dari pengaturan.txt
        with open(path_pengaturan, 'r') as setting_file:
            current_moduls = set([
                baris.strip() for baris in setting_file if baris.strip()
            ])

        if required_moduls != current_moduls:
            modul_belumlengkap()
            buat_folder_vidio_download(nama_folder='VidioDownload')
            pasang_dan_cek_modul(
                nama_file_requirements=path_requirements,
                file_pengaturan=path_pengaturan
            )
        else:
            modul_lengkap()

    except FileNotFoundError:
        print("Error: requirements.txt atau pengaturan.txt tidak ditemukan di folder data.")

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


