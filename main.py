from src.dashboard import show_dashboard
from src.download import get_video_info, get_available_resolutions, download_single, download_many


def pilih_resolusi(video_formats):
    if not video_formats:
        return None, "terbaik"

    print("\nResolusi tersedia:")
    for i, f in enumerate(video_formats):
        print(f"  [{i}] {f['height']}p ({f.get('ext', '?')})")
    print(f"  [{len(video_formats)}] Terbaik (auto)")

    while True:
        pilihan = input("Pilih nomor resolusi: ").strip()
        if pilihan.isdigit() and 0 <= int(pilihan) <= len(video_formats):
            pilihan = int(pilihan)
            break
        print("Input tidak valid.")

    if pilihan == len(video_formats):
        return None, "terbaik"
    return video_formats[pilihan]["height"], f"{video_formats[pilihan]['height']}p"


def menu_download():
    print("\n1. Download 1 video")
    print("2. Download banyak video")
    pilihan = input("Pilih opsi: ").strip()

    if pilihan == "1":
        url = input("Masukkan URL video: ").strip()
        if not url:
            print("URL tidak boleh kosong.")
            return
        info = get_video_info(url)
        formats = get_available_resolutions(info)
        height, label = pilih_resolusi(formats)
        download_single(url, target_height=height, resolution_label=label)

    elif pilihan == "2":
        print("Masukkan URL satu per baris. Ketik 'selesai' jika sudah:")
        urls = []
        while True:
            u = input("> ").strip()
            if u.lower() == "selesai":
                break
            if u:
                urls.append(u)
        if not urls:
            print("Tidak ada URL yang dimasukkan.")
            return

        contoh_info = get_video_info(urls[0])
        formats = get_available_resolutions(contoh_info)
        height, label = pilih_resolusi(formats)
        download_many(urls, target_height=height, resolution_label=label)
    else:
        print("Opsi tidak valid.")


def main():
    while True:
        print("\n===== YOUTUBE/X DOWNLOADER =====")
        print("1. Dashboard")
        print("2. Download video")
        print("3. Keluar")
        pilihan = input("Pilih menu: ").strip()

        if pilihan == "1":
            show_dashboard()
        elif pilihan == "2":
            menu_download()
        elif pilihan == "3":
            print("Sampai jumpa!")
            break
        else:
            print("Pilihan tidak valid.")


if __name__ == "__main__":
    main()