import os
import subprocess
import sys

def pasang_dan_cek_modul(
    nama_file_requirements=os.path.join('data', 'requirements.txt'),
    file_pengaturan=os.path.join('data', 'pengaturan.txt')
):
    """
    Memasang dan mengecek modul-modul yang diperlukan sesuai daftar pada requirements.txt.
    Jika modul belum terpasang, maka akan diinstall otomatis.
    Nama modul yang sudah terpasang atau baru diinstall akan dicatat ke pengaturan.txt (tanpa duplikat).
    """
    print("\n\033[1;36m=== Mendapatkan Modul yang Dibutuhkan ===\033[0m")
    print("\033[1;34mSedang memeriksa dan memasang modul-modul yang di butuhkan ...\033[0m")
    try:
        if not os.path.exists(nama_file_requirements):
            print(f"\033[1;31mFile {nama_file_requirements} tidak ditemukan.\033[0m")
            return

        # Baca file pengaturan.txt untuk daftar modul yang sudah dicatat
        if os.path.exists(file_pengaturan):
            with open(file_pengaturan, 'r') as f:
                modul_tercatat = set([baris.strip() for baris in f if baris.strip()])
        else:
            modul_tercatat = set()

        with open(nama_file_requirements, 'r') as f:
            modul_modul = [baris.strip() for baris in f if baris.strip() and not baris.startswith('#')]

        for modul in modul_modul:
            nama_modul = modul.split('==')[0].split('>=')[0].split('<=')[0]
            try:
                __import__(nama_modul)
                print(f"\033[1;32m✔ Modul [{modul}] sudah terpasang.\033[0m")
            except ImportError:
                print(f"\033[1;33m✖ Modul [{modul}] belum terpasang. Memasang...\033[0m")
                try:
                    subprocess.check_call([sys.executable, '-m', 'pip', 'install', modul])
                    print(f"\033[1;32m✔ Modul [{modul}] berhasil dipasang.\033[0m")
                except Exception as e:
                    print(f"\033[1;31mGagal memasang modul [{modul}]: {e}\033[0m")
                    continue  # lanjut ke modul berikutnya jika gagal install

            # Jika nama_modul belum ada di pengaturan.txt, tambahkan
            if nama_modul not in modul_tercatat:
                with open(file_pengaturan, 'a') as f_pengaturan:
                    f_pengaturan.write(nama_modul + '\n')
                modul_tercatat.add(nama_modul)
                print(f"\033[1;35mNama modul [{nama_modul}] ditambahkan ke {file_pengaturan}.\033[0m")

    except Exception as e:
        print(f"\033[1;31mTerjadi kesalahan saat memproses file requirements: {e}\033[0m")