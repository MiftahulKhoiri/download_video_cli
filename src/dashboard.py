from src.manager import load_history
from src.loading import clear_screen


def show_dashboard():
    history = load_history()
    print("\n" + "=" * 50)
    print("📊 DASHBOARD DOWNLOAD")
    print("=" * 50)

    if not history:
        print("Belum ada video yang diunduh.")
        print("=" * 50)
        return

    print(f"Total video diunduh: {len(history)}\n")
    for i, item in enumerate(history, 1):
        print(f"[{i}] {item.get('title')}")
        print(f"    Resolusi : {item.get('resolution')}")
        print(f"    File     : {item.get('filename')}")
        print(f"    URL      : {item.get('url')}")
        print("-" * 50)
    print("=" * 50)


def run_dashboard_menu():
    """Loop menu dashboard, dipanggil dari main."""
    while True:
        clear_screen()
        show_dashboard()
        print("\n0. Kembali")
        pilihan = input("Pilih opsi: ").strip()
        if pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")