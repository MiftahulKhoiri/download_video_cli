import subprocess
import sys
import os
from modul.submodul.logo import *
from modul.submodul.program import *

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    HIJAU = Fore.GREEN
    MERAH = Fore.RED
    KUNING = Fore.YELLOW
    BIRU = Fore.BLUE
    RESET = Style.RESET_ALL
except ImportError:
    HIJAU = MERAH = KUNING = BIRU = RESET = ""

def is_git_repo():
    return os.path.isdir(".git")


def tampilkan_pembaruan(branch="main"):
    print("cek pembaruan program ")
    print(f"\n{KUNING}[INFO]{RESET} Daftar pembaruan terbaru di repository:")
    try:
        subprocess.run(
            ["git", "fetch"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        hasil = subprocess.run(
            ["git", "log", f"HEAD..origin/{branch}", "--oneline"],
            check=False,
            capture_output=True,
            text=True
        )
        if hasil.stdout.strip():
            print(hasil.stdout)
            return True
        else:
            print(f"{HIJAU} Tidak ada pembaruan.{RESET}")
            return False
    except Exception as error:
        print(f"{MERAH}[ERROR] Gagal mengambil log pembaruan: {error}{RESET}")
        return False

def konfirmasi_pembaruan():
    while True:
        try:
            jawaban = input(f"\nLanjutkan pembaruan dengan git pull? ({HIJAU}y{RESET}/{MERAH}n{RESET}): ").strip().lower()
            if jawaban == "y":
                return True
            elif jawaban == "n":
                print(f"{KUNING}Pembaruan dibatalkan oleh pengguna.{RESET}")
                return False
            else:
                print(f"{MERAH}Input tidak valid. Masukkan 'y' untuk setuju, atau 'n' untuk membatalkan.{RESET}")
        except Exception as error:
            print(f"{MERAH}[ERROR] Terjadi kesalahan saat input: {error}{RESET}")

def lakukan_git_pull(branch="main"):
    print(f"\n{KUNING}[PROSES]{RESET} Menjalankan git pull...")
    try:
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"{HIJAU}[SUKSES] Pembaruan selesai!{RESET}")
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"{MERAH}[ERROR] Gagal melakukan git pull!{RESET}")
        print(e.stderr if e.stderr else str(e))
    except Exception as error:
        print(f"{MERAH}[ERROR] Terjadi kesalahan saat menjalankan git pull: {error}{RESET}")

def proses_update(branch="main"):
    if not is_git_repo():
        print(f"{MERAH}[ERROR] Folder ini bukan repository git!{RESET}")
        return
    try:
        tampilkan_salam()
        ada_pembaruan = tampilkan_pembaruan(branch)
        if not ada_pembaruan:
            # Jika tidak ada pembaruan, selesai di sini
            print(f"{HIJAU}Program sudah versi terbaru.{RESET}")
            return
        if konfirmasi_pembaruan():
            lakukan_git_pull(branch)
    except KeyboardInterrupt:
        print(f"\n{KUNING}[INFO] Proses dibatalkan oleh pengguna (Ctrl+C).{RESET}")
    except Exception as error:
        print(f"{MERAH}[ERROR] Terjadi kesalahan fatal: {error}{RESET}")
      
def pengaturan_data():
    print("konfigurasi modulyang di butuhkan")
    cek_data_buat()
    cek_isi()

