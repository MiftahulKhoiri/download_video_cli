import os
import time
from colorama import Fore, Style, init
from modul.submodul.program import *
from modul.submodul.logo import *
from modul.fb_download import unduh_facebook
from modul.twitter_download import unduh_twitter
from modul.youtube_download import unduh_video_audio_terpisah

init(autoreset=True)

def main():
    """Menu utama aplikasi unduhan video."""
    while True:
        time.sleep(1)
        hapus_layar()
        tampilkan_logo_utama()
        tampilkan_menu_utama()
        sumber = input(Fore.YELLOW + " Pilih sumber (1/2/3/4/0): ").strip()
        if sumber == "0":
            hapus_layar()
            time.sleep(1)
            tampilkan_logo_utama()
            print(Fore.GREEN + "\nTerima kasih telah menggunakan program VidioUnduh!\n")
            break
        elif sumber in ["1", "2", "3", "4"]:
            while True:
                print(Fore.MAGENTA + "\nPilih mode unduhan:")
                print(Fore.BLUE + " 1. Unduh 1 video")
                print(Fore.BLUE + " 2. Unduh banyak video")
                print(Fore.WHITE + " 4. Cek hasil download")
                print(Fore.RED + " 0. Kembali ke menu utama")
                mode = input(Fore.YELLOW + " Pilihan (no:0/1/2/3) : ").strip().lower()
                if mode == "0":
                    break
                elif mode == "3":
                    tampilkan_hasil_download()
                    continue
                elif mode not in ["1", "2"]:
                    print(Fore.RED + "Pilihan tidak dikenali. Silakan ulangi.")
                    continue
                daftar_url = []
                if mode == "2":
                    print(Fore.MAGENTA + "\nMasukkan alamat video satu per satu, tekan Enter tanpa input untuk mulai unduhan otomatis.")
                    while True:
                        alamat = input(Fore.YELLOW + " URL: ").strip()
                        if alamat == "":
                            break
                        daftar_url.append(alamat)
                else:
                    alamat = input(Fore.YELLOW + "\nMasukkan URL video: ").strip()
                    if alamat:
                        daftar_url.append(alamat)
                if not daftar_url:
                    print(Fore.RED + "Tidak ada URL yang dimasukkan.")
                    continue
                resolusi = input(Fore.YELLOW + "Pilih resolusi (misal: 720), kosongkan untuk terbaik: ").strip()
                if not resolusi:
                    resolusi = None
                if sumber == "1":  # Youtube
                    for alamat in daftar_url:
                        unduh_video_audio_terpisah(alamat, resolusi)
                elif sumber == "2":  # Facebook
                    cookies = input(Fore.YELLOW + "Masukkan path cookies.txt (atau kosongkan jika tidak perlu): ").strip()
                    for alamat in daftar_url:
                        unduh_facebook(alamat, cookies_path=cookies if cookies else None, resolusi=resolusi)
                elif sumber == "3":  # Twitter/X
                    cookies = input(Fore.YELLOW + "Masukkan path cookies.txt (atau kosongkan jika tidak perlu): ").strip()
                    for alamat in daftar_url:
                        unduh_twitter(alamat, cookies_path=cookies if cookies else None, resolusi=resolusi)
                print(Fore.GREEN + "\nUnduhan selesai untuk semua video yang didaftar.\n")
        else:
            print(Fore.RED + "Pilihan tidak dikenali. Silakan ulangi.")

if __name__ == "__main__":
    main()