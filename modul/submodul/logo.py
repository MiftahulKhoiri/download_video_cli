from colorama import Fore, Style, init

init(autoreset=True)  # Agar warna otomatis reset setiap print

def tampilkan_logo_utama():
    logo = (
        f"{Fore.CYAN}╔═══════════════════════╗\n"
        f"{Fore.CYAN}║ {Fore.GREEN}Vidio Unduh{Fore.CYAN}           ║\n"
        f"{Fore.CYAN}║ {Fore.BLUE}Vidio Download Tools {Fore.CYAN} ║\n"
        f"{Fore.CYAN}╚═══════════════════════╝{Style.RESET_ALL}"
    )
    print(logo)

def tampilkan_menu_utama():
    """Menampilkan menu utama dengan tampilan menarik dan warna."""
    print(Fore.CYAN + "\n" + "="*44)
    print(Fore.MAGENTA + Style.BRIGHT + "     Selamat Datang di " + Fore.GREEN + "Vidio Unduh")
    print(Fore.CYAN + "="*44)
    print(Fore.YELLOW + " 1." + Fore.RED + " Youtube")
    print(Fore.YELLOW + " 2." + Fore.BLUE + " Facebook")
    print(Fore.YELLOW + " 3." + Fore.BLUE + " Twitter/X")
    print(Fore.YELLOW + " 0. Keluar")
    print(Fore.CYAN + "="*44)

def tampilkan_salam():
    print(Fore.BLUE + "="*40)
    print(Fore.BLUE + "=" + Fore.RED + "       Update pembaruan script       " + Fore.BLUE + "=")
    print(Fore.BLUE + "="*40 + Style.RESET_ALL)


def modul_lengkap(detail="Semua modul telah terpasang dengan benar."):
    """
    Menampilkan pesan bahwa modul sudah lengkap.
    """
    print(Fore.GREEN + "[INFO] Modul sudah lengkap.")
    print(Fore.GREEN + f"       {detail}")
    print(Fore.GREEN + "       Tidak perlu melakukan pemasangan otomatis.")
    print(Style.RESET_ALL)

def modul_belumlengkap(detail="Beberapa modul belum terpasang atau perlu pembaruan."):
    """
    Menampilkan pesan bahwa modul belum lengkap dan akan dilakukan update/install otomatis.
    """
    print(Fore.RED + "[PERINGATAN] Modul belum lengkap!")
    print(Fore.RED + f"             {detail}")
    print(Fore.RED + "             Akan dilakukan update dan install otomatis...")
    print(Style.RESET_ALL)