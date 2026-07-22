from colorama import init, Fore, Style
init(autoreset=True)  # otomatis reset warna setelah setiap print

def show_logo_color():
    print(Fore.CYAN + " __   _____   ___          _")
    print(Fore.YELLOW + " \\ \\ / /_   ) |   \\ _ __  | |")
    print(Fore.GREEN + "  \\ V / / /  | |) | '  \\ | |__")
    print(Fore.MAGENTA + "   \\_/ /___| |___/|_|_|_||____|")
    print()
    print(Fore.RED + "🎬 " + Fore.BLUE + "YouTube" + Fore.WHITE + " / " + Fore.CYAN + "X" + Fore.WHITE + " Video & " + Fore.GREEN + "MP3 Downloader" + Fore.RED + " 🎵")

if __name__ == "__main__":
    show_logo_color()