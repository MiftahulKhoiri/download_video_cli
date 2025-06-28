from modul.submodul.program import *
import subprocess
import sys
import os

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    HIJAU = Fore.GREEN
    MERAH = Fore.RED
    KUNING = Fore.YELLOW
    BIRU = Fore.BLUE
    RESET = Style.RESET_ALL
except ImportError:
    HIJAU = MERAH = KUNING = BIRU = RESET = ""

# --- UTILS ---

def is_git_repo():
    """Cek apakah folder ini adalah repository git."""
    return os.path.isdir(".git")

def get_active_branch():
    """Ambil nama branch aktif saat ini."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=True,
            capture_output=True,
            text=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"{MERAH}[ERROR] Gagal mendapatkan branch aktif: {e}{RESET}")
        return "main"

def has_uncommitted_changes():
    """Cek apakah ada perubahan lokal yang belum di-commit."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True
    )
    return bool(result.stdout.strip())

# --- LOGIC ---

def check_updates(branch):
    """
    Fetch dan cek apakah ada pembaruan dari remote.
    Return: (bool, str)
        - True jika ada update, False jika tidak/ada error.
        - String log commit pembaruan atau pesan error.
    """
    try:
        subprocess.run(["git", "fetch"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        log_result = subprocess.run(
            ["git", "log", f"HEAD..origin/{branch}", "--oneline"],
            capture_output=True,
            text=True
        )
        if log_result.returncode != 0:
            return False, log_result.stderr.strip()
        log_commit = log_result.stdout.strip()
        if log_commit:
            return True, log_commit
        else:
            return False, f"{HIJAU}Tidak ada pembaruan pada branch {branch}.{RESET}"
    except subprocess.CalledProcessError as e:
        return False, f"{MERAH}[ERROR] Gagal fetch: {e.stderr}{RESET}"
    except Exception as error:
        return False, f"{MERAH}[ERROR] {error}{RESET}"

def perform_git_pull(branch):
    """
    Lakukan git pull dari remote branch.
    Return: (bool, str)
        - True jika sukses, False jika gagal.
        - Output atau error dari git pull.
    """
    try:
        result = subprocess.run(
            ["git", "pull", "origin", branch],
            capture_output=True,
            text=True,
            check=True
        )
        return True, f"{HIJAU}[SUKSES] Pembaruan selesai!\n{result.stdout}{RESET}"
    except subprocess.CalledProcessError as e:
        return False, f"{MERAH}[ERROR] Gagal melakukan git pull!\n{e.stderr or e.stdout}{RESET}"
    except Exception as error:
        return False, f"{MERAH}[ERROR] {error}{RESET}"

# --- USER INTERFACE ---

def tampilkan_salam():
    """Tampilkan salam atau logo jika diinginkan."""
    print(f"{BIRU}=== Download Video CLI Updater ==={RESET}")

def tampilkan_log_pembaruan(log_commit, branch):
    """Tampilkan daftar pembaruan yang belum di-pull."""
    print(f"\n{KUNING}[INFO]{RESET} Daftar pembaruan terbaru di branch '{branch}':")
    print(log_commit)

def konfirmasi_pembaruan(force=False):
    """
    Konfirmasi dengan user sebelum melakukan git pull.
    Jika force=True, langsung return True tanpa konfirmasi.
    """
    if force:
        return True
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

def proses_update(branch=None, force=False):
    """
    Proses utama untuk melakukan update program.
    :param branch: Nama branch yang ingin diupdate (default branch aktif)
    :param force: Jika True, skip konfirmasi user
    """
    if not is_git_repo():
        print(f"{MERAH}[ERROR] Folder ini bukan repository git!{RESET}")
        return

    tampilkan_salam()

    if branch is None:
        branch = get_active_branch()

    # Cek perubahan lokal
    if has_uncommitted_changes():
        print(f"{KUNING}[PERINGATAN]{RESET} Ada perubahan lokal yang belum di-commit!")
        print(f"{KUNING}Sebaiknya commit/stash dulu sebelum update untuk menghindari konflik.{RESET}")

    ada_update, log_or_msg = check_updates(branch)
    if not ada_update:
        print(log_or_msg)
        print(f"{HIJAU}Program sudah versi terbaru.{RESET}")
        return

    tampilkan_log_pembaruan(log_or_msg, branch)

    if not konfirmasi_pembaruan(force):
        return

    sukses, hasil = perform_git_pull(branch)
    print(hasil)

# --- PENGATURAN DATA (Contoh Placeholder) ---

def pengaturan_data():
    """Konfigurasi modul yang dibutuhkan (placeholder)."""
    print("konfigurasi modul yang dibutuhkan")
    # Panggil fungsi-fungsi setup lain di sini
    cek_data_buat()
    cek_isi()

# --- MAIN ---

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Updater Download Video CLI")
    parser.add_argument("--branch", type=str, help="Nama branch yang akan diupdate (default=branch aktif)")
    parser.add_argument("--force", action="store_true", help="Langsung update tanpa konfirmasi")
    args = parser.parse_args()

    proses_update(branch=args.branch, force=args.force)