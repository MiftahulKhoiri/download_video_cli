# src/download_core.py
"""Mesin download inti: verifikasi, retry, disk check -- dipakai mode menu MAUPUN mode CLI."""
import glob
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp
from yt_dlp.utils import download_range_func

from src.manager import ensure_download_folder, is_already_downloaded, save_file_record
from src.media_info import is_ffmpeg_available, get_video_info, _video_needs_merge
from src.loading import (
    progress_hook, postprocessor_hook, reset_progress,
    safe_print, noop_hook, format_size,
)
from src.config import load_config
from src import notify
from src.logger import get_logger

log = get_logger()

LOSSY_AUDIO_FORMATS = {"mp3", "m4a", "opus"}
TERMUX_SHARED_DOWNLOADS = os.path.expanduser("~/storage/downloads")
MIN_FREE_SPACE_WARN = 500 * 1024 * 1024   # di bawah ini: warning, tetap lanjut
MIN_FREE_SPACE_ABORT = 50 * 1024 * 1024   # di bawah ini: batalkan otomatis (aman buat mode CLI/cron)


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