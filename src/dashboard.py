import os

from src.manager import load_history, delete_entry, clear_history
from src.loading import clear_screen, format_size


def _total_size(history):
    total = 0
    for item in history:
        fn = item.get("filename")
        if fn and os.path.exists(fn):
            try:
                total += os.path.getsize(fn)
            except OSError:
                pass
    return total


def show_dashboard(keyword=None):
    history = load_history()
    print("\n" + "=" * 50)
    print("📊 DASHBOARD DOWNLOAD")
    print("=" * 50)

    if not history:
        print("Belum ada video yang diunduh.")
        print("=" * 50)
        return history

    print(f"Total: {len(history)} item · {format_size(_total_size(history))}\n")

    if keyword:
        indexed = [(i, item) for i, item in enumerate(history, 1) if keyword.lower() in item.get("title", "").lower()]
        print(f"🔍 Filter: \"{keyword}\" ({len(indexed)} dari {len(history)} cocok)\n")
    else:
        indexed = list(enumerate(history, 1))

    if not indexed:
        print("Tidak ada entri yang cocok dengan kata kunci ini.")

    for i, item in indexed:
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
    keyword = None
    while True:
        clear_screen()
        history = show_dashboard(keyword=keyword)
        print("\n1. Hapus satu entri")
        print("2. Hapus semua riwayat")
        label_cari = f"Cari/filter (aktif: \"{keyword}\")" if keyword else "Cari/filter"
        print(f"3. {label_cari}")
        if keyword:
            print("4. Hapus filter")
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
        elif pilihan == "3":
            kata = input("Kata kunci judul (kosongkan buat hapus filter): ").strip()
            keyword = kata or None
        elif pilihan == "4" and keyword:
            keyword = None
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")