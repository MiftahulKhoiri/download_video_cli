from src.manager import load_history, delete_entry, clear_history
from src.loading import clear_screen


def show_dashboard():
    history = load_history()
    print("\n" + "=" * 50)
    print("📊 DASHBOARD DOWNLOAD")
    print("=" * 50)

    if not history:
        print("Belum ada video yang diunduh.")
        print("=" * 50)
        return history

    print(f"Total video diunduh: {len(history)}\n")
    for i, item in enumerate(history, 1):
        print(f"[{i}] {item.get('title')}")
        print(f"    Resolusi : {item.get('resolution')}")
        print(f"    File     : {item.get('filename')}")
        print(f"    URL      : {item.get('url')}")
        print("-" * 50)
    print("=" * 50)
    return history


def _hapus_satu():
    nomor = input("Masukkan nomor entri yang mau dihapus: ").strip()
    if not nomor.isdigit():
        print("Nomor tidak valid.")
        input("\nTekan Enter untuk lanjut...")
        return
    hapus_file = input("Hapus file fisiknya juga dari disk? (y/N): ").strip().lower() == "y"
    sukses, item = delete_entry(int(nomor), remove_file=hapus_file)
    if sukses:
        print(f"✅ Entri '{item.get('title')}' dihapus dari riwayat" + (" beserta filenya." if hapus_file else "."))
    else:
        print("❌ Nomor entri tidak ditemukan.")
    input("\nTekan Enter untuk lanjut...")


def _hapus_semua():
    konfirmasi = input("Yakin hapus SEMUA riwayat? Ketik 'ya' untuk konfirmasi: ").strip().lower()
    if konfirmasi != "ya":
        print("Dibatalkan.")
        input("\nTekan Enter untuk lanjut...")
        return
    hapus_file = input("Hapus semua file fisiknya juga dari disk? (y/N): ").strip().lower() == "y"
    count = clear_history(remove_files=hapus_file)
    print(f"✅ {count} entri riwayat dihapus" + (" beserta filenya." if hapus_file else "."))
    input("\nTekan Enter untuk lanjut...")


def run_dashboard_menu():
    """Loop menu dashboard, dipanggil dari main."""
    while True:
        clear_screen()
        history = show_dashboard()
        print("\n1. Hapus satu entri")
        print("2. Hapus semua riwayat")
        print("0. Kembali")
        pilihan = input("Pilih opsi: ").strip()
        if pilihan == "1":
            if not history:
                print("Tidak ada riwayat untuk dihapus.")
                input("\nTekan Enter untuk lanjut...")
                continue
            _hapus_satu()
        elif pilihan == "2":
            if not history:
                print("Tidak ada riwayat untuk dihapus.")
                input("\nTekan Enter untuk lanjut...")
                continue
            _hapus_semua()
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")