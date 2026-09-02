# src/download.py
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp
from src.manager import ensure_download_folder, is_already_downloaded, save_file_record
from src.loading import (
    progress_hook, postprocessor_hook, clear_screen, reset_progress,
    Spinner, safe_print, noop_hook,
)
from src.config import load_config
from src import notify


def is_ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def get_video_info(url, cookies_file=None):
    with Spinner("🔍 Mengambil info video..."):
        ydl_opts = {"quiet": True, "no_warnings": True}
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)


def _video_needs_merge(info):
    """
    Heuristik konservatif: True kalau situsnya punya stream video-only terpisah
    (bakal digabung sama audio via ffmpeg oleh format selector 'bestvideo+bestaudio'),
    False kalau semua format yang tersedia sudah gabungan video+audio.
    """
    formats = info.get("formats", [])
    return any(
        f.get("vcodec") not in (None, "none") and f.get("acodec") in (None, "none")
        for f in formats
    )


def expand_playlist(url, cookies_file=None):
    """
    Kalau url adalah playlist, kembalikan list URL video di dalamnya
    (pakai extract_flat biar cepat, nggak fetch semua format tiap video).
    Kalau url video tunggal, kembalikan [url] apa adanya.
    """
    with Spinner("🔍 Memeriksa URL / playlist..."):
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
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
                vid = entry.get("id") or entry_url
                entry_url = f"https://www.youtube.com/watch?v={vid}"
            else:
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
    dari template nama file.
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

    return candidates[0] if candidates else None


def _run_download(ydl_opts, url, expected_ext, retries):
    """
    Jalankan extract_info(download=True) dengan retry otomatis kalau gagal.
    Return (result_info, filepath). Melempar exception terakhir kalau semua percobaan gagal.
    """
    retries = max(1, retries)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)
                filename = _resolve_final_filepath(ydl, result, expected_ext=expected_ext)
            return result, filename
        except Exception as e:
            last_exc = e
            if attempt < retries:
                print(f"⚠️  Percobaan {attempt}/{retries} gagal ({e}). Mencoba lagi...")
                reset_progress()
    raise last_exc


def notify_download_done(title):
    config = load_config()
    if config.get("notify_termux", True):
        notify.notify("Download selesai", f"'{title}' berhasil diunduh")


def download_single(url, target_height=None, resolution_label="terbaik", info=None,
                     retries=1, subtitle_langs=None, cookies_file=None, quiet_progress=False):
    """Fungsi download 1 video dari YouTube/X. quiet_progress=True dipakai pas mode paralel."""
    folder = ensure_download_folder()
    subtitle_langs = subtitle_langs or []
    printer = safe_print if quiet_progress else print

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file)
    title = info.get("title", "video")
    video_id = info.get("id")

    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        return False

    if _video_needs_merge(info) and not is_ffmpeg_available():
        printer(f"❌ '{title}' butuh ffmpeg buat menggabungkan video+audio, tapi ffmpeg belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return False

    if not quiet_progress:
        reset_progress()

    ydl_opts = {
        "format": _build_format_string(target_height),
        "outtmpl": f"{folder}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
        "continuedl": True,
        "progress_hooks": [noop_hook] if quiet_progress else [progress_hook],
        "postprocessor_hooks": [noop_hook] if quiet_progress else [postprocessor_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if subtitle_langs:
        ydl_opts.update({
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": subtitle_langs,
            "subtitlesformat": "srt/best",
        })
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    if quiet_progress:
        safe_print(f"⬇️  Mulai unduh: {title}")

    result, filename = _run_download(ydl_opts, url, expected_ext="mp4", retries=retries)

    save_file_record(title, filename, url, resolution_label, video_id=video_id)
    printer(f"\n✅ Selesai! '{title}' berhasil diunduh.")
    notify_download_done(title)
    return True


def download_many(url_list, target_height=None, resolution_label="terbaik", first_info=None, config=None):
    """Fungsi download banyak video sekaligus (list URL). Jalan paralel kalau config parallel_workers > 1."""
    config = config or load_config()
    workers = max(1, int(config.get("parallel_workers", 1) or 1))
    retries = max(1, int(config.get("retry_count", 1) or 1))
    subtitle_langs = config.get("subtitle_langs") or []
    cookies_file = config.get("cookies_file")

    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    if workers <= 1:
        for i, url in enumerate(url_list, 1):
            print(f"\n=== [{i}/{len(url_list)}] {url} ===")
            try:
                info = first_info if (i == 1 and first_info is not None) else None
                sukses = download_single(
                    url, target_height=target_height, resolution_label=resolution_label,
                    info=info, retries=retries, subtitle_langs=subtitle_langs,
                    cookies_file=cookies_file, quiet_progress=False,
                )
                hasil["berhasil" if sukses else "dilewati"] += 1
            except Exception as e:
                print(f"❌ Gagal mengunduh {url}: {e}")
                hasil["gagal"] += 1
    else:
        safe_print(f"\n⚡ Mode paralel aktif: {workers} download sekaligus.\n")
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    download_single, url, target_height, resolution_label, None,
                    retries, subtitle_langs, cookies_file, True,
                ): url
                for url in url_list
            }
            for i, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    sukses = future.result()
                    with lock:
                        hasil["berhasil" if sukses else "dilewati"] += 1
                    safe_print(f"[{i}/{len(url_list)}] Selesai: {url}")
                except Exception as e:
                    with lock:
                        hasil["gagal"] += 1
                    safe_print(f"[{i}/{len(url_list)}] ❌ Gagal: {url} ({e})")

    print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), {hasil['gagal']} gagal.")
    return hasil


def download_audio_single(url, info=None, quality="192", retries=1, cookies_file=None, quiet_progress=False):
    """Fungsi download 1 audio (MP3) dari YouTube/X."""
    folder = ensure_download_folder()
    printer = safe_print if quiet_progress else print

    if not is_ffmpeg_available():
        printer("❌ Convert ke MP3 butuh ffmpeg, tapi belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return False

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file)
    title = info.get("title", "audio")
    video_id = info.get("id")

    resolution_label = f"mp3-{quality}kbps"
    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        return False

    if not quiet_progress:
        reset_progress()

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{folder}/%(title)s.%(ext)s",
        "continuedl": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": str(quality),
        }],
        "progress_hooks": [noop_hook] if quiet_progress else [progress_hook],
        "postprocessor_hooks": [noop_hook] if quiet_progress else [postprocessor_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file

    if quiet_progress:
        safe_print(f"⬇️  Mulai unduh (MP3): {title}")

    result, filename = _run_download(ydl_opts, url, expected_ext="mp3", retries=retries)

    save_file_record(title, filename, url, resolution_label, video_id=video_id)
    printer(f"\n✅ Selesai! '{title}' (MP3 {quality}kbps) berhasil diunduh.")
    notify_download_done(f"{title} (MP3)")
    return True


def download_audio_many(url_list, first_info=None, config=None):
    """Fungsi download banyak audio (MP3) sekaligus. Jalan paralel kalau config parallel_workers > 1."""
    config = config or load_config()
    workers = max(1, int(config.get("parallel_workers", 1) or 1))
    retries = max(1, int(config.get("retry_count", 1) or 1))
    quality = config.get("mp3_quality", "192")
    cookies_file = config.get("cookies_file")

    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    if workers <= 1:
        for i, url in enumerate(url_list, 1):
            print(f"\n=== [{i}/{len(url_list)}] {url} ===")
            try:
                info = first_info if (i == 1 and first_info is not None) else None
                sukses = download_audio_single(
                    url, info=info, quality=quality, retries=retries,
                    cookies_file=cookies_file, quiet_progress=False,
                )
                hasil["berhasil" if sukses else "dilewati"] += 1
            except Exception as e:
                print(f"❌ Gagal mengunduh {url}: {e}")
                hasil["gagal"] += 1
    else:
        safe_print(f"\n⚡ Mode paralel aktif: {workers} download sekaligus.\n")
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    download_audio_single, url, None, quality, retries, cookies_file, True,
                ): url
                for url in url_list
            }
            for i, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    sukses = future.result()
                    with lock:
                        hasil["berhasil" if sukses else "dilewati"] += 1
                    safe_print(f"[{i}/{len(url_list)}] Selesai: {url}")
                except Exception as e:
                    with lock:
                        hasil["gagal"] += 1
                    safe_print(f"[{i}/{len(url_list)}] ❌ Gagal: {url} ({e})")

    print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), {hasil['gagal']} gagal.")
    return hasil


# ---------- Logika menu (input/print) ----------

def pilih_resolusi(video_formats, config=None):
    config = config or {}
    if not video_formats:
        return None, "terbaik"

    default_res = config.get("default_resolution")
    if default_res:
        for f in video_formats:
            if f["height"] == default_res:
                print(f"\n▶️  Pakai resolusi default dari pengaturan: {default_res}p")
                return f["height"], f"{f['height']}p"
        print(f"\n⚠️  Resolusi default ({default_res}p) tidak tersedia untuk video ini, silakan pilih manual.")

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


def pilih_kualitas_mp3(config=None):
    config = config or {}
    default_quality = str(config.get("mp3_quality", "192"))
    opsi = ["128", "192", "256", "320"]
    print("\nKualitas MP3 (kbps):")
    for i, q in enumerate(opsi):
        tanda = " (default)" if q == default_quality else ""
        print(f"  [{i}] {q} kbps{tanda}")
    pilihan = input(f"Pilih nomor kualitas [Enter = default {default_quality}kbps]: ").strip()
    if pilihan == "":
        return default_quality
    if pilihan.isdigit() and 0 <= int(pilihan) < len(opsi):
        return opsi[int(pilihan)]
    print("Input tidak valid, pakai default.")
    return default_quality


def menu_download_1():
    clear_screen()
    print("===== DOWNLOAD 1 VIDEO =====")
    config = load_config()
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url, cookies_file=config.get("cookies_file"))
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} video ditemukan.")

        info = get_video_info(urls[0], cookies_file=config.get("cookies_file"))
        formats = get_available_resolutions(info)
        height, label = pilih_resolusi(formats, config=config)

        if len(urls) > 1:
            download_many(urls, target_height=height, resolution_label=label, first_info=info, config=config)
        else:
            download_single(
                urls[0], target_height=height, resolution_label=label, info=info,
                retries=config.get("retry_count", 1),
                subtitle_langs=config.get("subtitle_langs") or [],
                cookies_file=config.get("cookies_file"),
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_banyak():
    clear_screen()
    print("===== DOWNLOAD BANYAK VIDEO =====")
    config = load_config()
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
            expanded = expand_playlist(u, cookies_file=config.get("cookies_file"))
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} video ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada video yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        contoh_info = get_video_info(urls[0], cookies_file=config.get("cookies_file"))
        formats = get_available_resolutions(contoh_info)
        height, label = pilih_resolusi(formats, config=config)
        download_many(urls, target_height=height, resolution_label=label, first_info=contoh_info, config=config)
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_1():
    clear_screen()
    print("===== DOWNLOAD MP3 (1 AUDIO) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert ke MP3 nggak bisa jalan.")
        print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        input("\nTekan Enter untuk lanjut...")
        return
    config = load_config()
    url = input("Masukkan URL video atau playlist: ").strip()
    if not url:
        print("URL tidak boleh kosong.")
        input("\nTekan Enter untuk lanjut...")
        return
    try:
        urls = expand_playlist(url, cookies_file=config.get("cookies_file"))
        quality = pilih_kualitas_mp3(config)
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} audio akan diunduh.")
            download_audio_many(urls, config={**config, "mp3_quality": quality})
        else:
            download_audio_single(
                urls[0], quality=quality, retries=config.get("retry_count", 1),
                cookies_file=config.get("cookies_file"),
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_banyak():
    clear_screen()
    print("===== DOWNLOAD MP3 (BANYAK AUDIO) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert ke MP3 nggak bisa jalan.")
        print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        input("\nTekan Enter untuk lanjut...")
        return
    config = load_config()
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
            expanded = expand_playlist(u, cookies_file=config.get("cookies_file"))
            if len(expanded) > 1:
                print(f"📋 Playlist terdeteksi ({u}): {len(expanded)} audio ditambahkan.")
            urls.extend(expanded)

        if not urls:
            print("Tidak ada audio yang bisa diunduh dari URL yang dimasukkan.")
            input("\nTekan Enter untuk lanjut...")
            return

        quality = pilih_kualitas_mp3(config)
        download_audio_many(urls, config={**config, "mp3_quality": quality})
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def run_download_menu():
    """Loop menu download, dipanggil dari main."""
    while True:
        clear_screen()
        print("===== MENU DOWNLOAD =====")
        if not is_ffmpeg_available():
            print("⚠️  ffmpeg tidak ditemukan. Download yang butuh merge/convert bakal ditolak otomatis.")
            print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).\n")
        config = load_config()
        if config.get("parallel_workers", 1) > 1:
            print(f"⚡ Mode paralel aktif: {config['parallel_workers']} download sekaligus (ubah di menu Pengaturan)\n")
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