from src.dashboard import run_dashboard_menu
from src.download import run_download_menu
from src.loading import show_logo


def main():

    while True:
        show_logo()
        print("1. Dashboard")
        print("2. Download video")
        print("0. Keluar")
        pilihan = input("Pilih menu: ").strip()

        if pilihan == "1":
            run_dashboard_menu()
        elif pilihan == "2":
            run_download_menu()
        elif pilihan == "0":
            print("Sampai jumpa!")
            break
        else:
            print("Pilihan tidak valid.")
            input("\nTekan Enter untuk lanjut...")


if __name__ == "__main__":
    main()