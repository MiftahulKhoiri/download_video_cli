import sys
import os
import time  # Untuk menambah jeda waktu
from modul.submodul.program import *
from modul.pembaruan_program import proses_update,pengaturan_data

def main():
    # Bersihkan layar sebelum mulai
    hapus_layar()
    # Jalankan proses update terlebih dahulu
    proses_update()

    # Jeda waktu setelah update
    time.sleep(2)
    hapus_layar()

    # Cek dan install modul, juga buat folder VidioDownload
    pengaturan_data()

    # Jeda lagi setelah proses cek modul
    time.sleep(4)

    # Setelah update & cek modul, jalankan main.py
    try:
        import main as main_modul
        if hasattr(main_modul, 'main') and callable(main_modul.main):
            main_modul.main()
        else:
            print("[ERROR] Modul 'main.py' tidak memiliki fungsi main().")
    except ImportError as e:
        print(f"[ERROR] Tidak dapat mengimpor modul 'main.py': {e}")

if __name__ == "__main__":
    main()
