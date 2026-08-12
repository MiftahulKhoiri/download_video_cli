# src/download.py
import os
import shutil
import yt_dlp
from src.manager import ensure_download_folder, is_already_downloaded, save_file_record
from src.loading import progress_hook, clear_screen, reset_progress


def is_ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def get_video_info(url):
    ydl_opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def expand_playlist(url):
    """
    Kalau url adalah playlist, kembalikan list URL video di dalamnya
    (pakai extract_flat biar cepat, nggak fetch semua format tiap video).
    Kalau url video tunggal, kembalikan [url] apa adanya.
    """
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info or (info.get("_type") != "playlist" and "entries" not in info):
        return [url]

    is_youtube = "youtube.com" in url or "youtu.be" in url

    urls = []
    for entry in info.get("entries") or []:
        if not entry:
            continue
        entry_url = entry.get("url") or entry.get("webpage_url")
        if entry_url and not entry_url.startswith("http"):
            if is_youtube:
                # sebagian extractor cuma kasih video ID di field 'url' pas extract_flat
                vid = entry.get("id") or entry_url
                entry_url = f"https://www.youtube.com/watch?v={vid}"
            else:
                # Bukan YouTube dan URL-nya nggak lengkap: skip drpd nebak domain yang salah
                print(f"⚠️  Melewati entri playlist tanpa URL lengkap: {entry.get('id') or entry_url}")
                continue
        if entry_url:
            urls.append(entry_url)
    return urls


def get_available_resolutions(info):
    formats = info.get("formats", [])
    video_formats = []
    seen_res = set()
    for f in formats:
        height = f.get("height")
        if height and f.get("vcodec") != "none":
            if height not in seen_res:
                seen_res.add(height)
                video_formats.append(f)
    video_formats.sort(key=lambda x: x["height"], reverse=True)
    return video_formats


def _build_format_string(target_height):
    if target_height is None:
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]"


def _resolve_final_filepath(ydl, result_info, expected_ext=None):
    """
    Cari path file hasil download yang BENAR-BENAR ada di disk, bukan cuma tebakan
    dari template nama file. Perlu karena setelah merge (video) atau convert (audio),
    ekstensi asli bisa beda dari yang dihitung sebelum proses download berjalan.
    """
    if not result_info:
        return None

    candidates = []
    for item in result_info.get("requested_downloads") or []:
        fp = item.get("filepath") or item.get("_filename")
        if fp:
            candidates.append(fp)

    candidates.append(ydl.prepare_filename(result_info))

    if expected_ext:
        for c in list(candidates):
            base, _ = os.path.splitext(c)
            candidates.append(f"{base}.{expected_ext}")

    for c in candidates:
        if c and os.path.exists(c):
            return c

    # Fallback terakhir: tebakan terbaik meski belum tentu 100% akurat
    return candidates[0] if candidates else None


def download_single(url, target_height=None, resolution_label="terbaik"):
    """Fungsi download 1 video dari YouTube/X."""
    folder = ensure_download_folder()

    info = get_video_info(url)
    title = info.get("title", "video")

    already, existing = is_already_downloaded(title, resolution_label)
    if already:
        print(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        return False

    reset_progress()
    ydl_opts = {
        "format": _build_format_string(target_height),
        "outtmpl": f"{folder}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=True)
        filename = _resolve_final_filepath(ydl, result, expected_ext="mp4")

    save_file_record(title, filename, url, resolution_label)
    print(f"\n✅ Selesai! '{title}' berhasil diunduh.")
    return True


def download_many(url_list, target_height=None, resolution_label="terbaik"):
    """Fungsi download banyak video sekaligus (list URL)."""
    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    for i, url in enumerate(url_list, 1):
        print(f"\n=== [{i}/{len(url_list)}] {url} ===")
        try:
            sukses = download_single(url, target_height=target_height, resolution_label=resolution_label)
            hasil["berhasil" if sukses else "dilewati"] += 1
        except Exception as e:
            print(f"❌ Gagal mengunduh {url}: {e}")
            hasil["gagal"] += 1

    print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), {hasil['gagal']} gagal.")
    return hasil


def download_audio_single(url):
    """Fungsi download 1 audio (MP3) dari YouTube/X."""
    folder = ensure_download_folder()

    info = get_video_info(url)
    title = info.get("title", "audio")
    resolution_label = "mp3 (audio)"

    already, existing = is_already_downloaded(title, resolution_label)
    if already:
        print(f"⚠️  '{title}' (MP3) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        return False

    reset_progress()
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{folder}/%(title)s.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=True)
        filename = _resolve_final_filepath(ydl, result, expected_ext="mp3")

    save_file_record(title, filename, url, resolution_label)
    print(f"\n✅ Selesai! '{title}' (MP3) berhasil diunduh.")
    return True


def download_audio_many(url_list):
    """Fungsi download banyak audio (MP3) sekaligus."""
    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    for i, url in enumerate(url_list, 1):
        print(f"\n=== [{i}/{len(url_list)}] {url} ===")
        try:
            sukses = download_audio_single(url)
            hasil["berhasil" if sukses else "dilewati"] += 1
        except Exception as e:
            print(f"❌ Gagal mengunduh {url}: {e}")
            hasil["gagal"] += 1

    print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), {hasil['gagal']} gagal.")
    return hasil


# ---------- Logika menu (input/print) ----------

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


def menu_download_1():
    clear_screen()
    print("===== DOWNLOAD 1 VIDEO =====")
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url)
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} video ditemukan.")

        info = get_video_info(urls[0])
        formats = get_available_resolutions(info)
        height, label = pilih_resolusi(formats)

        if len(urls) > 1:
            download_many(urls, target_height=height, resolution_label=label)
        else:
            download_single(urls[0], target_height=height, resolution_label=label)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_banyak():
    clear_screen()
    print("===== DOWNLOAD BANYAK VIDEO =====")
    print("Masukkan URL satu per baris (video/playlist). Ketik 'selesai' jika sudah:")
    urls_input = []
    while True:
        u = input("> ").strip()
        if u.lower() == "selesai":
            break
        if u:
            urls_input.append(u)
    if not urls_input:
        print("Tidak ada URL yang dimasukkan.")
        input("\nTekan Enter untuk lanjut...")
        return

    try:
        urls = []
        for u in urls_input:
            expanded = expand_playlist(u)
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} video ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada video yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        contoh_info = get_video_info(urls[0])
        formats = get_available_resolutions(contoh_info)
        height, label = pilih_resolusi(formats)
        download_many(urls, target_height=height, resolution_label=label)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_1():
    clear_screen()
    print("===== DOWNLOAD MP3 (1 AUDIO) =====")
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url)
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} audio akan diunduh.")
            download_audio_many(urls)
        else:
            download_audio_single(urls[0])
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_banyak():
    clear_screen()
    print("===== DOWNLOAD MP3 (BANYAK AUDIO) =====")
    print("Masukkan URL satu per baris (video/playlist). Ketik 'selesai' jika sudah:")
    urls_input = []
    while True:
        u = input("> ").strip()
        if u.lower() == "selesai":
            break
        if u:
            urls_input.append(u)
    if not urls_input:
        print("Tidak ada URL yang dimasukkan.")
        input("\nTekan Enter untuk lanjut...")
        return

    try:
        urls = []
        for u in urls_input:
            expanded = expand_playlist(u)
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} audio ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada audio yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        download_audio_many(urls)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def run_download_menu():
    """Loop menu download, dipanggil dari main."""
    while True:
        clear_screen()
        print("===== MENU DOWNLOAD =====")
        if not is_ffmpeg_available():
            print("⚠️  ffmpeg tidak ditemukan. Merge video+audio & convert ke MP3 bisa gagal.")
            print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).\n")
        print("1. Download video (1)")
        print("2. Download video (banyak)")
        print("3. Download MP3 (1)")
        print("4. Download MP3 (banyak)")
        print("0. Kembali")
        pilihan = input("Pilih opsi: ").strip()

        if pilihan == "1":
            menu_download_1()
        elif pilihan == "2":
            menu_download_banyak()
        elif pilihan == "3":
            menu_download_mp3_1()
        elif pilihan == "4":
            menu_download_mp3_banyak()
        elif pilihan == "0":
            break
        else:
            print("Opsi tidak valid.")
            input("\nTekan Enter untuk lanjut...")