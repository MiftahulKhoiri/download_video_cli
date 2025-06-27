
import os
import shutil
from yt_dlp import YoutubeDL
from colorama import init, Fore
from modul.submodul.proses_download import *
from modul.submodul.program import *

init(autoreset=True)
NAMA_FOLDER = "VidioDownload"
os.makedirs(NAMA_FOLDER, exist_ok=True)

def unduh_video_audio_terpisah(alamat, resolusi=None):
    temp_video = None
    temp_audio = None

    try:
        # Pilih resolusi
        if not resolusi:
            daftar_resolusi = get_video_resolutions(alamat)
            if not daftar_resolusi:
                print(Fore.RED + "Tidak ada opsi resolusi yang ditemukan!")
                return
            print(Fore.CYAN + "Pilihan resolusi video yang tersedia:")
            for i, (height, ext) in enumerate(daftar_resolusi):
                print(f"{i+1}. {height}p ({ext})")
            # Minta input user
            while True:
                pilihan = input("Pilih nomor resolusi yang diinginkan: ")
                if pilihan.isdigit() and 1 <= int(pilihan) <= len(daftar_resolusi):
                    resolusi = daftar_resolusi[int(pilihan)-1][0]
                    break
                else:
                    print("Pilihan tidak valid. Silakan coba lagi.")

        temp_video_tpl = "temp_video.%(ext)s"
        temp_audio_tpl = "temp_audio.%(ext)s"

        opsi_video = {
            'format': f"bestvideo[height<={resolusi}]" if resolusi else "bestvideo",
            'outtmpl': temp_video_tpl,
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [yt_progress_hook],
        }
        opsi_audio = {
            'format': "bestaudio",
            'outtmpl': temp_audio_tpl,
            'noplaylist': True,
            'quiet': True,
            'progress_hooks': [yt_progress_hook],
        }

        print(Fore.YELLOW + "Mengunduh video...")
        try:
            with YoutubeDL(opsi_video) as ydl:
                info_video = ydl.extract_info(alamat, download=True)
                video_ext = info_video.get('ext', 'mp4')
                judul = info_video.get('title', 'video')
                temp_video = f"temp_video.{video_ext}"
        except Exception as e:
            print(Fore.RED + f"Gagal mengunduh video: {e}")
            if temp_video and os.path.exists(temp_video):
                os.remove(temp_video)
            return

        print(Fore.YELLOW + "Mengunduh audio...")
        try:
            with YoutubeDL(opsi_audio) as ydl:
                info_audio = ydl.extract_info(alamat, download=True)
                audio_ext = info_audio.get('ext', 'm4a')
                temp_audio = f"temp_audio.{audio_ext}"
        except Exception as e:
            print(Fore.RED + f"Gagal mengunduh audio: {e}")
            if temp_audio and os.path.exists(temp_audio):
                os.remove(temp_audio)
            if temp_video and os.path.exists(temp_video):
                os.remove(temp_video)
            return

        tanggal = tanggal_hari_ini()
        judul_bersih = bersihkan_nama_file(judul)
        nama_file = cek_file_dan_konfirmasi(judul_bersih, "mp4", tanggal)
        if not nama_file:
            hapus_file_sementara(temp_video, temp_audio)
            return

        hasil_output = os.path.join(NAMA_FOLDER, nama_file)
        print(Fore.CYAN + "Menggabungkan video dan audio dengan ffmpeg...")

        perintah = [
            'ffmpeg', '-y',
            '-i', temp_video,
            '-i', temp_audio,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', 'experimental',
            hasil_output
        ]
        try:
            retcode = tampilkan_progress_ffmpeg(perintah, temp_video)
            if retcode != 0:
                print(Fore.RED + "Terjadi kesalahan saat menggabungkan video dan audio!")
                hapus_file_sementara(temp_video, temp_audio)
                return
        except Exception as e:
            print(Fore.RED + f"Gagal menggabungkan video dan audio: {e}")
            hapus_file_sementara(temp_video, temp_audio)
            return

        hapus_file_sementara(temp_video, temp_audio)
        print(Fore.GREEN + f"Video hasil gabungan disimpan di: {hasil_output}")

    except Exception as e:
        print(Fore.RED + "Terjadi kesalahan tak terduga!")
        print(Fore.RED + f"Detail error: {e}")
        try:
            hapus_file_sementara(temp_video, temp_audio)
        except Exception:
            pass


