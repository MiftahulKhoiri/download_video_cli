# src/download.py
import glob
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp
from yt_dlp.utils import download_range_func

from src.manager import ensure_download_folder, is_already_downloaded, save_file_record
from src.loading import (
    progress_hook, postprocessor_hook, clear_screen, reset_progress,
    Spinner, safe_print, noop_hook, format_size,
)
from src.config import load_config
from src import notify
from src.logger import get_logger

log = get_logger()

LOSSY_AUDIO_FORMATS = {"mp3", "m4a", "opus"}
TERMUX_SHARED_DOWNLOADS = os.path.expanduser("~/storage/downloads")
MIN_FREE_SPACE_WARN = 500 * 1024 * 1024   # di bawah ini: warning, tetap lanjut
MIN_FREE_SPACE_ABORT = 50 * 1024 * 1024   # di bawah ini: batalkan otomatis (aman buat mode CLI/cron)


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


def _build_outtmpl(base_folder, organize_by):
    if organize_by == "channel":
        return f"{base_folder}/%(uploader)s/%(title)s.%(ext)s"
    if organize_by == "date":
        return f"{base_folder}/%(upload_date>%Y-%m-%d)s/%(title)s.%(ext)s"
    return f"{base_folder}/%(title)s.%(ext)s"


def _parse_rate_limit(text):
    """'500K' -> 512000, '2M' -> 2097152, angka polos -> byte/detik. None/invalid -> None."""
    if not text:
        return None
    text = str(text).strip().upper()
    multiplier = 1
    if text.endswith("K"):
        multiplier, text = 1024, text[:-1]
    elif text.endswith("M"):
        multiplier, text = 1024 * 1024, text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return None


def _parse_time_to_seconds(text):
    parts = [int(p) for p in text.strip().split(":")]
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + p
    return seconds


def pilih_rentang_waktu():
    """Tanya rentang waktu buat motong video/audio. Return (start, end) detik, atau None kalau full."""
    print("\n✂️  Potong ke rentang waktu tertentu? (format MM:SS atau HH:MM:SS, kosongkan = unduh penuh)")
    mulai = input("Mulai [Enter = dari awal / lewati]: ").strip()
    if not mulai:
        return None
    try:
        start_sec = _parse_time_to_seconds(mulai)
    except ValueError:
        print("Format waktu tidak valid, unduh penuh.")
        return None
    selesai = input("Selesai [Enter = sampai akhir]: ").strip()
    end_sec = None
    if selesai:
        try:
            end_sec = _parse_time_to_seconds(selesai)
        except ValueError:
            print("Format waktu selesai tidak valid, diabaikan (unduh sampai akhir).")
    return (start_sec, end_sec)


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


def _cleanup_partial_files(folder):
    """Hapus sisa file .part/.ytdl kalau download dibatalkan (Ctrl+C) di tengah jalan."""
    try:
        for pattern in ("*.part", "*.ytdl", "*.part-Frag*"):
            for fp in glob.glob(os.path.join(folder, "**", pattern), recursive=True):
                try:
                    os.remove(fp)
                except OSError:
                    pass
    except OSError:
        pass


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
        except KeyboardInterrupt:
            _cleanup_partial_files(ensure_download_folder())
            print("\n⏹️  Download dibatalkan (Ctrl+C), file sementara sudah dibersihkan.")
            raise
        except Exception as e:
            last_exc = e
            log.warning(f"Percobaan {attempt}/{retries} gagal untuk {url}: {e}")
            if attempt < retries:
                print(f"⚠️  Percobaan {attempt}/{retries} gagal ({e}). Mencoba lagi...")
                reset_progress()
    log.error(f"Gagal unduh {url} setelah {retries} percobaan: {last_exc}")
    raise last_exc


def _verify_downloaded_file(filepath):
    """
    Verifikasi file hasil download valid -- bukan 0 byte atau rusak
    (misal koneksi putus di tengah jalan tapi yt-dlp nggak sempat nge-flag error).
    Pakai ffprobe (bagian dari ffmpeg) kalau tersedia buat validasi lebih dalam;
    kalau ffprobe nggak ada/gagal dijalankan, cek ukuran file aja.
    Return (True, None) kalau valid, (False, alasan) kalau tidak.
    """
    if not filepath or not os.path.exists(filepath):
        return False, "file tidak ditemukan di disk"

    size = os.path.getsize(filepath)
    if size == 0:
        return False, "file berukuran 0 byte (kemungkinan unduhan terputus)"

    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", filepath],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return False, "file tidak valid / gagal dibaca ffprobe (kemungkinan rusak)"
        except (subprocess.SubprocessError, OSError):
            pass  # ffprobe gagal dijalankan -> jangan gagalkan verifikasi cuma karena ini

    return True, None


def _check_disk_space(folder, printer=print):
    """
    Cek ruang kosong di disk tempat folder download berada, sebelum mulai
    download banyak/paralel. Nggak pernah nge-block lewat input() (biar aman
    dipanggil dari mode CLI/cron non-interaktif):
      - Di bawah MIN_FREE_SPACE_ABORT -> batalkan otomatis.
      - Di bawah MIN_FREE_SPACE_WARN  -> kasih warning aja, tetap lanjut.
    Return True kalau boleh lanjut, False kalau harus dibatalkan.
    """
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        return True  # nggak bisa dicek -- jangan halangi proses cuma karena ini

    if free < MIN_FREE_SPACE_ABORT:
        printer(f"❌ Ruang kosong tersisa cuma {format_size(free)}, terlalu sedikit buat mulai download. Dibatalkan.")
        return False
    if free < MIN_FREE_SPACE_WARN:
        printer(f"⚠️  Ruang kosong tersisa cuma {format_size(free)}. Download bisa gagal kalau habis di tengah jalan.")
    return True


def notify_download_done(title):
    config = load_config()
    if config.get("notify_termux", True):
        notify.notify("Download selesai", f"'{title}' berhasil diunduh")


def _copy_to_termux_shared_storage(filepath, printer):
    if not filepath or not os.path.exists(filepath):
        return
    if not os.path.isdir(TERMUX_SHARED_DOWNLOADS):
        printer("⚠️  Folder shared storage Termux belum siap. Jalankan 'termux-setup-storage' lalu izinkan akses storage.")
        return
    try:
        dest = os.path.join(TERMUX_SHARED_DOWNLOADS, os.path.basename(filepath))
        shutil.copy2(filepath, dest)
        printer(f"📤 Disalin juga ke folder Download Android: {dest}")
    except OSError as e:
        printer(f"⚠️  Gagal menyalin ke shared storage: {e}")


def download_single(url, target_height=None, resolution_label="terbaik", info=None,
                     config=None, quiet_progress=False, section_range=None):
    """Fungsi download 1 video dari YouTube/X. quiet_progress=True dipakai pas mode paralel."""
    config = config or load_config()
    retries = max(1, int(config.get("retry_count", 1) or 1))
    subtitle_langs = config.get("subtitle_langs") or []
    cookies_file = config.get("cookies_file")
    organize_by = config.get("organize_by", "none")
    rate_limit = _parse_rate_limit(config.get("rate_limit"))
    termux_shared = config.get("termux_shared_storage", False)

    folder = ensure_download_folder()
    printer = safe_print if quiet_progress else print

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file)
    title = info.get("title", "video")
    video_id = info.get("id")

    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        log.info(f"Duplikat dilewati: {title} ({resolution_label})")
        return False

    if _video_needs_merge(info) and not is_ffmpeg_available():
        printer(f"❌ '{title}' butuh ffmpeg buat menggabungkan video+audio, tapi ffmpeg belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return False

    if not quiet_progress:
        reset_progress()

    ydl_opts = {
        "format": _build_format_string(target_height),
        "outtmpl": _build_outtmpl(folder, organize_by),
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
    if rate_limit:
        ydl_opts["ratelimit"] = rate_limit
    if section_range:
        start_sec, end_sec = section_range
        ydl_opts["download_ranges"] = download_range_func(None, [(start_sec, end_sec)])
        ydl_opts["force_keyframes_at_cuts"] = True

    if quiet_progress:
        safe_print(f"⬇️  Mulai unduh: {title}")
    log.info(f"Mulai unduh: {title} ({url}) [{resolution_label}]")

    result, filename = _run_download(ydl_opts, url, expected_ext="mp4", retries=retries)

    valid, alasan = _verify_downloaded_file(filename)
    if not valid:
        printer(f"❌ '{title}' gagal diverifikasi: {alasan}. Tidak disimpan ke riwayat, coba unduh ulang.")
        log.error(f"Verifikasi gagal untuk {title} ({filename}): {alasan}")
        return False

    save_file_record(title, filename, url, resolution_label, video_id=video_id)
    printer(f"\n✅ Selesai! '{title}' berhasil diunduh.")
    log.info(f"Selesai: {title} -> {filename}")
    if termux_shared:
        _copy_to_termux_shared_storage(filename, printer)
    notify_download_done(title)
    return True


def download_many(url_list, target_height=None, resolution_label="terbaik", first_info=None, config=None):
    """Fungsi download banyak video sekaligus (list URL). Jalan paralel kalau config parallel_workers > 1."""
    config = config or load_config()
    workers = max(1, int(config.get("parallel_workers", 1) or 1))

    folder = ensure_download_folder()
    if not _check_disk_space(folder):
        return {"berhasil": 0, "dilewati": 0, "gagal": 0}

    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    if workers <= 1:
        for i, url in enumerate(url_list, 1):
            print(f"\n=== [{i}/{len(url_list)}] {url} ===")
            try:
                info = first_info if (i == 1 and first_info is not None) else None
                sukses = download_single(
                    url, target_height=target_height, resolution_label=resolution_label,
                    info=info, config=config, quiet_progress=False,
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
                    download_single, url,
                    target_height=target_height, resolution_label=resolution_label,
                    config=config, quiet_progress=True,
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


def _audio_resolution_label(audio_format, quality):
    if audio_format in LOSSY_AUDIO_FORMATS:
        return f"{audio_format}-{quality}kbps"
    return audio_format


def download_audio_single(url, info=None, audio_format=None, quality=None, config=None,
                           quiet_progress=False, section_range=None):
    """Fungsi download 1 audio dari YouTube/X, format bisa mp3/m4a/opus/flac/wav."""
    config = config or load_config()
    audio_format = (audio_format or config.get("audio_format", "mp3")).lower()
    quality = quality or config.get("mp3_quality", "192")
    retries = max(1, int(config.get("retry_count", 1) or 1))
    cookies_file = config.get("cookies_file")
    organize_by = config.get("organize_by", "none")
    rate_limit = _parse_rate_limit(config.get("rate_limit"))
    embed_metadata = config.get("embed_metadata", True)
    termux_shared = config.get("termux_shared_storage", False)

    folder = ensure_download_folder()
    printer = safe_print if quiet_progress else print

    if not is_ffmpeg_available():
        printer("❌ Convert audio butuh ffmpeg, tapi belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return False

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file)
    title = info.get("title", "audio")
    video_id = info.get("id")

    resolution_label = _audio_resolution_label(audio_format, quality)
    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        log.info(f"Duplikat dilewati: {title} ({resolution_label})")
        return False

    if not quiet_progress:
        reset_progress()

    postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": audio_format}]
    if audio_format in LOSSY_AUDIO_FORMATS:
        postprocessors[0]["preferredquality"] = str(quality)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": _build_outtmpl(folder, organize_by),
        "continuedl": True,
        "postprocessors": postprocessors,
        "progress_hooks": [noop_hook] if quiet_progress else [progress_hook],
        "postprocessor_hooks": [noop_hook] if quiet_progress else [postprocessor_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    if embed_metadata:
        ydl_opts["writethumbnail"] = True
        ydl_opts["postprocessors"].append({"key": "FFmpegMetadata", "add_metadata": True})
        if audio_format != "wav":  # wav nggak dukung embed thumbnail
            ydl_opts["postprocessors"].append({"key": "EmbedThumbnail"})
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    if rate_limit:
        ydl_opts["ratelimit"] = rate_limit
    if section_range:
        start_sec, end_sec = section_range
        ydl_opts["download_ranges"] = download_range_func(None, [(start_sec, end_sec)])
        ydl_opts["force_keyframes_at_cuts"] = True

    if quiet_progress:
        safe_print(f"⬇️  Mulai unduh ({audio_format}): {title}")
    log.info(f"Mulai unduh audio: {title} ({url}) [{resolution_label}]")

    result, filename = _run_download(ydl_opts, url, expected_ext=audio_format, retries=retries)

    valid, alasan = _verify_downloaded_file(filename)
    if not valid:
        printer(f"❌ '{title}' gagal diverifikasi: {alasan}. Tidak disimpan ke riwayat, coba unduh ulang.")
        log.error(f"Verifikasi gagal untuk {title} ({filename}): {alasan}")
        return False

    save_file_record(title, filename, url, resolution_label, video_id=video_id)
    printer(f"\n✅ Selesai! '{title}' ({resolution_label}) berhasil diunduh.")
    log.info(f"Selesai: {title} -> {filename}")
    if termux_shared:
        _copy_to_termux_shared_storage(filename, printer)
    notify_download_done(f"{title} ({audio_format})")
    return True


def download_audio_many(url_list, first_info=None, config=None):
    """Fungsi download banyak audio sekaligus. Jalan paralel kalau config parallel_workers > 1."""
    config = config or load_config()
    workers = max(1, int(config.get("parallel_workers", 1) or 1))

    folder = ensure_download_folder()
    if not _check_disk_space(folder):
        return {"berhasil": 0, "dilewati": 0, "gagal": 0}

    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}

    if workers <= 1:
        for i, url in enumerate(url_list, 1):
            print(f"\n=== [{i}/{len(url_list)}] {url} ===")
            try:
                info = first_info if (i == 1 and first_info is not None) else None
                sukses = download_audio_single(url, info=info, config=config, quiet_progress=False)
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
                    download_audio_single, url, config=config, quiet_progress=True,
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


def pilih_format_audio(config=None):
    config = config or {}
    default_format = config.get("audio_format", "mp3")
    opsi = ["mp3", "m4a", "opus", "flac", "wav"]
    print("\nFormat audio:")
    for i, f in enumerate(opsi):
        tanda = " (default)" if f == default_format else ""
        print(f"  [{i}] {f}{tanda}")
    pilihan = input(f"Pilih nomor format [Enter = default {default_format}]: ").strip()
    if pilihan == "":
        audio_format = default_format
    elif pilihan.isdigit() and 0 <= int(pilihan) < len(opsi):
        audio_format = opsi[int(pilihan)]
    else:
        print("Input tidak valid, pakai default.")
        audio_format = default_format

    if audio_format not in LOSSY_AUDIO_FORMATS:
        return audio_format, None

    default_quality = str(config.get("mp3_quality", "192"))
    opsi_kualitas = ["128", "192", "256", "320"]
    print("\nKualitas (kbps):")
    for i, q in enumerate(opsi_kualitas):
        tanda = " (default)" if q == default_quality else ""
        print(f"  [{i}] {q} kbps{tanda}")
    pilihan_k = input(f"Pilih nomor kualitas [Enter = default {default_quality}kbps]: ").strip()
    if pilihan_k == "":
        quality = default_quality
    elif pilihan_k.isdigit() and 0 <= int(pilihan_k) < len(opsi_kualitas):
        quality = opsi_kualitas[int(pilihan_k)]
    else:
        print("Input tidak valid, pakai default.")
        quality = default_quality

    return audio_format, quality


def _kumpulkan_urls_dari_input_atau_file():
    print("Sumber URL:")
    print("  [1] Ketik manual (satu per baris)")
    print("  [2] Import dari file .txt (satu URL per baris)")
    sumber = input("Pilih [1/2, Enter = 1]: ").strip()

    if sumber == "2":
        path = input("Path file .txt: ").strip()
        try:
            with open(path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
            print(f"📄 {len(urls)} URL dibaca dari {path}")
            return urls
        except OSError as e:
            print(f"❌ Gagal membaca file: {e}")
            return []

    print("Masukkan URL satu per baris (video/playlist). Ketik 'selesai' jika sudah:")
    urls_input = []
    while True:
        u = input("> ").strip()
        if u.lower() == "selesai":
            break
        if u:
            urls_input.append(u)
    return urls_input


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
            section_range = pilih_rentang_waktu()
            download_single(
                urls[0], target_height=height, resolution_label=label, info=info,
                config=config, section_range=section_range,
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_banyak():
    clear_screen()
    print("===== DOWNLOAD BANYAK VIDEO =====")
    config = load_config()
    urls_input = _kumpulkan_urls_dari_input_atau_file()
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
    print("===== DOWNLOAD AUDIO (1 ITEM) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert audio nggak bisa jalan.")
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
        audio_format, quality = pilih_format_audio(config)
        if len(urls) > 1:
            print(f"\n📋 Playlist terdeteksi: {len(urls)} audio akan diunduh.")
            cfg_override = {**config, "audio_format": audio_format}
            if quality:
                cfg_override["mp3_quality"] = quality
            download_audio_many(urls, config=cfg_override)
        else:
            section_range = pilih_rentang_waktu()
            download_audio_single(
                urls[0], audio_format=audio_format, quality=quality,
                config=config, section_range=section_range,
            )
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")
    input("\nTekan Enter untuk lanjut...")


def menu_download_mp3_banyak():
    clear_screen()
    print("===== DOWNLOAD AUDIO (BANYAK ITEM) =====")
    if not is_ffmpeg_available():
        print("❌ ffmpeg belum terpasang, convert audio nggak bisa jalan.")
        print("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        input("\nTekan Enter untuk lanjut...")
        return
    config = load_config()
    urls_input = _kumpulkan_urls_dari_input_atau_file()
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

        audio_format, quality = pilih_format_audio(config)
        cfg_override = {**config, "audio_format": audio_format}
        if quality:
            cfg_override["mp3_quality"] = quality
        download_audio_many(urls, config=cfg_override)
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
        print("3. Download audio (1)")
        print("4. Download audio (banyak)")
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