# src/download_core.py
"""Mesin download inti: verifikasi, retry, disk check -- dipakai mode menu MAUPUN mode CLI."""
import glob
import hashlib
import importlib.util
import os
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import yt_dlp
from yt_dlp.utils import download_range_func

from src.manager import ensure_output_folder, is_already_downloaded, save_file_record, claim_title
from src.media_info import is_ffmpeg_available, get_video_info, _video_needs_merge, base_ydl_opts
from src.loading import (
    progress_hook, postprocessor_hook, reset_progress,
    safe_print, noop_hook, format_size,
)
from src.config import load_config
from src import notify
from src.logger import get_logger
from src.utils import parse_rate_limit as _parse_rate_limit, strip_ansi

log = get_logger()

LOSSY_AUDIO_FORMATS = {"mp3", "m4a", "opus"}
MUTAGEN_THUMBNAIL_FORMATS = {"opus", "flac"}   # embed thumbnail format ini butuh paket 'mutagen'
TERMUX_SHARED_DOWNLOADS = os.path.expanduser("~/storage/downloads")
MIN_FREE_SPACE_WARN = 500 * 1024 * 1024   # di bawah ini: warning, tetap lanjut
MIN_FREE_SPACE_ABORT = 50 * 1024 * 1024   # di bawah ini: batalkan otomatis (aman buat mode CLI/cron)
MAX_FILENAME_CHARS = 120                  # batas panjang nama file (di luar ekstensi), biar nggak "File name too long"

# Hasil satu unduhan -- sekaligus nama kunci di ringkasan download_many/download_audio_many.
STATUS_OK = "berhasil"
STATUS_SKIP = "dilewati"   # duplikat: sudah ada di riwayat
STATUS_FAIL = "gagal"      # ffmpeg nggak ada, verifikasi gagal, dll

_cancel_event = threading.Event()   # di-set pas Ctrl+C di mode paralel, biar thread yang lagi jalan ikut berhenti
_mutagen_warned = False


class DownloadAborted(Exception):
    """Dilempar dari hook progress kalau batch dibatalkan (Ctrl+C di mode paralel)."""


def _cancel_hook(d):
    if _cancel_event.is_set():
        raise DownloadAborted("dibatalkan")


def _mutagen_available():
    return importlib.util.find_spec("mutagen") is not None


def _build_format_string(target_height):
    if target_height is None:
        return "bestvideo+bestaudio/best"
    return f"bestvideo[height<={target_height}]+bestaudio/best[height<={target_height}]"


def _build_outtmpl(base_folder, organize_by, filename_tag=""):
    """
    filename_tag: disisipkan sebelum ekstensi file (mis. " [01.30-02.45]" buat hasil
    potong durasi, atau " [ID]" kalau judulnya bentrok), biar nggak menimpa file
    versi penuh/potongan lain yang judulnya sama.
    """
    name_part = f"%(title)s{filename_tag.replace('%', '%%')}.%(ext)s"
    if organize_by == "channel":
        return f"{base_folder}/%(uploader)s/{name_part}"
    if organize_by == "date":
        return f"{base_folder}/%(upload_date>%Y-%m-%d)s/{name_part}"
    return f"{base_folder}/{name_part}"


def _format_range_label(section_range):
    """
    'MM:SS-MM:SS' (atau 'HH:MM:SS-...' kalau >= 1 jam) dari section_range (start_sec, end_sec).
    Return '' kalau section_range None (unduh penuh, nggak dipotong).
    """
    if not section_range:
        return ""
    start_sec, end_sec = section_range

    def _fmt(sec):
        sec = int(sec)
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    end_part = _fmt(end_sec) if end_sec is not None else "akhir"
    return f"{_fmt(start_sec)}-{end_part}"


def _collision_tag(title, ext, video_id, url):
    """
    ' [ID]' kalau nama file 'judul.ext' berisiko bentrok sama file lain (biar dua video
    berjudul sama nggak saling menimpa), '' kalau aman.
    """
    if not claim_title(title, ext):
        return ""
    ident = video_id or hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f" [{ident}]"


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


def _make_partial_tracker():
    """
    Bikin hook yang mencatat file sementara milik download INI saja (dari info yang
    dilaporkan yt-dlp), buat dibersihkan kalau dibatalkan. Return (set_path, hook).
    """
    seen = set()

    def hook(d):
        for key in ("tmpfilename", "filename"):
            fp = d.get(key)
            if fp:
                seen.add(fp)

    return seen, hook


def _cleanup_partial_files(paths):
    """
    Hapus sisa .part/.ytdl/.part-Frag* HANYA untuk file yang tercatat di `paths`.
    Sengaja nggak nyapu seluruh folder: folder tujuan bisa aja folder Download Android
    yang isinya file .part milik app lain.
    """
    for fp in paths:
        base = fp[:-5] if fp.endswith(".part") else fp
        targets = [base + ".part", base + ".ytdl"] + glob.glob(glob.escape(base) + ".part-Frag*")
        for t in targets:
            try:
                if os.path.isfile(t):
                    os.remove(t)
            except OSError:
                pass


def _run_download(ydl_opts, url, expected_ext, retries, printer=print):
    """
    Jalankan extract_info(download=True) dengan retry otomatis kalau gagal.
    Return (result_info, filepath). Melempar exception terakhir kalau semua percobaan gagal.

    Kalau dibatalkan (Ctrl+C atau batch paralel dibatalkan), file sementara MILIK
    DOWNLOAD INI dibersihkan (file lain di folder yang sama nggak disentuh).
    """
    retries = max(1, retries)
    partials, tracker = _make_partial_tracker()
    opts = dict(ydl_opts)
    opts["progress_hooks"] = list(ydl_opts.get("progress_hooks") or []) + [tracker, _cancel_hook]

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=True)
                filename = _resolve_final_filepath(ydl, result, expected_ext=expected_ext)
            return result, filename
        except KeyboardInterrupt:
            _cleanup_partial_files(partials)
            printer("\n⏹️  Download dibatalkan (Ctrl+C), file sementara sudah dibersihkan.")
            raise
        except DownloadAborted:
            _cleanup_partial_files(partials)
            raise
        except Exception as e:
            last_exc = e
            msg = strip_ansi(e)
            log.warning(f"Percobaan {attempt}/{retries} gagal untuk {url}: {msg}")
            if attempt < retries:
                printer(f"⚠️  Percobaan {attempt}/{retries} gagal ({msg}). Mencoba lagi...")
                reset_progress()
    log.error(f"Gagal unduh {url} setelah {retries} percobaan: {strip_ansi(last_exc)}")
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


def _quarantine_bad_file(filepath):
    """
    Singkirkan file yang gagal verifikasi supaya percobaan unduh ulang nggak dilewati
    yt-dlp sebagai "sudah pernah diunduh" (yt-dlp nggak menimpa file yang namanya sama).
    File 0 byte dihapus; file rusak lainnya diganti nama jadi '<nama>.corrupt'.
    """
    try:
        if not filepath or not os.path.exists(filepath):
            return
        if os.path.getsize(filepath) == 0:
            os.remove(filepath)
        else:
            os.replace(filepath, filepath + ".corrupt")
    except OSError:
        pass


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
                     config=None, quiet_progress=False, section_range=None, rate_limit_bytes=None):
    """
    Fungsi download 1 video dari YouTube/X. quiet_progress=True dipakai pas mode paralel.
    rate_limit_bytes: batas kecepatan (byte/detik) khusus panggilan ini -- dipakai mode
    paralel buat membagi batas total ke tiap worker. Kosong = ikut pengaturan.
    Return STATUS_OK, STATUS_SKIP (duplikat), atau STATUS_FAIL.
    """
    config = config or load_config()
    retries = max(1, int(config.get("retry_count", 1) or 1))
    subtitle_langs = config.get("subtitle_langs") or []
    cookies_file = config.get("cookies_file")
    organize_by = config.get("organize_by", "none")
    rate_limit = rate_limit_bytes or _parse_rate_limit(config.get("rate_limit"))
    termux_shared = config.get("termux_shared_storage", False)

    range_label = _format_range_label(section_range)
    if range_label:
        # Potongan durasi dianggap versi BEDA dari video penuh (atau potongan lain
        # dengan rentang waktu berbeda) -- biar nggak salah dilewati sebagai
        # "duplikat", dan biar nggak saling menimpa file di disk.
        resolution_label = f"{resolution_label} [{range_label}]"
    filename_tag = f" [{range_label.replace(':', '.')}]" if range_label else ""

    printer = safe_print if quiet_progress else print
    folder = ensure_output_folder(config.get("download_folder"), printer=printer)

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file, retries=retries, quiet=quiet_progress)
    title = info.get("title") or "video"
    video_id = info.get("id")

    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        log.info(f"Duplikat dilewati: {title} ({resolution_label})")
        return STATUS_SKIP

    if _video_needs_merge(info) and not is_ffmpeg_available():
        printer(f"❌ '{title}' butuh ffmpeg buat menggabungkan video+audio, tapi ffmpeg belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return STATUS_FAIL

    filename_tag += _collision_tag(title, "mp4", video_id, url)

    if not quiet_progress:
        reset_progress()

    ydl_opts = {
        **base_ydl_opts(),
        "noplaylist": True,   # URL yang sampai sini sudah video tunggal -- jangan sampai ke-expand jadi satu playlist utuh
        "format": _build_format_string(target_height),
        "outtmpl": _build_outtmpl(folder, organize_by, filename_tag=filename_tag),
        "trim_file_name": MAX_FILENAME_CHARS,
        "merge_output_format": "mp4",
        "continuedl": True,
        "progress_hooks": [noop_hook] if quiet_progress else [progress_hook],
        "postprocessor_hooks": [noop_hook] if quiet_progress else [postprocessor_hook],
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

    with notify.wake_lock():
        result, filename = _run_download(ydl_opts, url, expected_ext="mp4", retries=retries, printer=printer)

        valid, alasan = _verify_downloaded_file(filename)
        if not valid:
            _quarantine_bad_file(filename)
            printer(f"❌ '{title}' gagal diverifikasi: {alasan}. Tidak disimpan ke riwayat, coba unduh ulang.")
            log.error(f"Verifikasi gagal untuk {title} ({filename}): {alasan}")
            return STATUS_FAIL

        save_file_record(title, filename, url, resolution_label, video_id=video_id)
        printer(f"\n✅ Selesai! '{title}' berhasil diunduh.")
        log.info(f"Selesai: {title} -> {filename}")
        if termux_shared:
            _copy_to_termux_shared_storage(filename, printer)
        notify_download_done(title)
        return STATUS_OK


def _run_batch(url_list, single_fn, config, first_info=None, **single_kwargs):
    """
    Jalankan single_fn buat tiap URL: berurutan, atau paralel kalau config parallel_workers > 1
    dan URL-nya lebih dari satu. Return dict ringkasan {"berhasil", "dilewati", "gagal"}.
    """
    _cancel_event.clear()
    config = config or load_config()
    workers = max(1, int(config.get("parallel_workers", 1) or 1))
    url_list = list(dict.fromkeys(url_list))   # buang URL dobel (urutan tetap): dua worker bisa rebutan file yang sama
    hasil = {"berhasil": 0, "dilewati": 0, "gagal": 0}
    if not url_list:
        return hasil

    folder = ensure_output_folder(config.get("download_folder"))
    if not _check_disk_space(folder):
        hasil["gagal"] = len(url_list)
        return hasil

    active = min(workers, len(url_list))

    if active <= 1:
        for i, url in enumerate(url_list, 1):
            print(f"\n=== [{i}/{len(url_list)}] {url} ===")
            try:
                info = first_info if (i == 1 and first_info is not None) else None
                status = single_fn(url, info=info, config=config, quiet_progress=False, **single_kwargs)
                hasil[status] += 1
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Gagal mengunduh {url}: {strip_ansi(e)}")
                hasil["gagal"] += 1
    else:
        # Batas kecepatan di yt-dlp berlaku PER download -- dibagi rata biar total tetap sesuai pengaturan.
        total_limit = _parse_rate_limit(config.get("rate_limit"))
        per_worker_limit = max(1, total_limit // active) if total_limit else None

        safe_print(f"\n⚡ Mode paralel aktif: {active} download sekaligus.")
        if total_limit:
            safe_print(f"   Batas kecepatan {config.get('rate_limit')} dibagi rata ke tiap download.")
        safe_print("")

        executor = ThreadPoolExecutor(max_workers=active)
        futures = {}
        try:
            for url in url_list:
                fut = executor.submit(
                    single_fn, url, config=config, quiet_progress=True,
                    rate_limit_bytes=per_worker_limit, **single_kwargs,
                )
                futures[fut] = url
            for i, future in enumerate(as_completed(futures), 1):
                url = futures[future]
                try:
                    status = future.result()
                    hasil[status] += 1
                    safe_print(f"[{i}/{len(url_list)}] Selesai: {url}")
                except Exception as e:
                    hasil["gagal"] += 1
                    safe_print(f"[{i}/{len(url_list)}] ❌ Gagal: {url} ({strip_ansi(e)})")
        except KeyboardInterrupt:
            # Antrean yang belum jalan dibatalkan, yang lagi jalan disuruh berhenti (lewat hook progress).
            # Tanpa ini, 'with ThreadPoolExecutor' baru lepas setelah SEMUA antrean selesai diunduh.
            _cancel_event.set()
            safe_print("\n⏹️  Dibatalkan (Ctrl+C), menghentikan antrean & download yang sedang jalan...")
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # Python 3.8: belum ada cancel_futures
                for fut in futures:
                    fut.cancel()
                executor.shutdown(wait=False)
            raise
        else:
            executor.shutdown(wait=True)

    print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), {hasil['gagal']} gagal.")
    return hasil


def download_many(url_list, target_height=None, resolution_label="terbaik", first_info=None, config=None):
    """Fungsi download banyak video sekaligus (list URL). Jalan paralel kalau config parallel_workers > 1."""
    return _run_batch(
        url_list, download_single, config, first_info=first_info,
        target_height=target_height, resolution_label=resolution_label,
    )


def _audio_resolution_label(audio_format, quality):
    if audio_format in LOSSY_AUDIO_FORMATS:
        return f"{audio_format}-{quality}kbps"
    return audio_format


def download_audio_single(url, info=None, audio_format=None, quality=None, config=None,
                           quiet_progress=False, section_range=None, rate_limit_bytes=None):
    """
    Fungsi download 1 audio dari YouTube/X, format bisa mp3/m4a/opus/flac/wav.
    Return STATUS_OK, STATUS_SKIP (duplikat), atau STATUS_FAIL.
    """
    global _mutagen_warned
    config = config or load_config()
    audio_format = (audio_format or config.get("audio_format", "mp3")).lower()
    quality = quality or config.get("mp3_quality", "192")
    retries = max(1, int(config.get("retry_count", 1) or 1))
    cookies_file = config.get("cookies_file")
    organize_by = config.get("organize_by", "none")
    rate_limit = rate_limit_bytes or _parse_rate_limit(config.get("rate_limit"))
    embed_metadata = config.get("embed_metadata", True)
    termux_shared = config.get("termux_shared_storage", False)

    printer = safe_print if quiet_progress else print
    folder = ensure_output_folder(config.get("download_folder"), printer=printer)

    if not is_ffmpeg_available():
        printer("❌ Convert audio butuh ffmpeg, tapi belum terpasang. Dilewati.")
        printer("    Install dulu: 'pkg install ffmpeg' (Termux) atau 'sudo apt install ffmpeg' (Linux).")
        return STATUS_FAIL

    if info is None:
        info = get_video_info(url, cookies_file=cookies_file, retries=retries, quiet=quiet_progress)
    title = info.get("title") or "audio"
    video_id = info.get("id")

    resolution_label = _audio_resolution_label(audio_format, quality)
    range_label = _format_range_label(section_range)
    if range_label:
        resolution_label = f"{resolution_label} [{range_label}]"
    filename_tag = f" [{range_label.replace(':', '.')}]" if range_label else ""

    already, existing = is_already_downloaded(title, resolution_label, video_id=video_id)
    if already:
        printer(f"⚠️  '{title}' ({resolution_label}) sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        log.info(f"Duplikat dilewati: {title} ({resolution_label})")
        return STATUS_SKIP

    filename_tag += _collision_tag(title, audio_format, video_id, url)

    if not quiet_progress:
        reset_progress()

    postprocessors = [{"key": "FFmpegExtractAudio", "preferredcodec": audio_format}]
    if audio_format in LOSSY_AUDIO_FORMATS:
        postprocessors[0]["preferredquality"] = str(quality)

    ydl_opts = {
        **base_ydl_opts(),
        "noplaylist": True,
        "format": "bestaudio/best",
        "outtmpl": _build_outtmpl(folder, organize_by, filename_tag=filename_tag),
        "trim_file_name": MAX_FILENAME_CHARS,
        "continuedl": True,
        "postprocessors": postprocessors,
        "progress_hooks": [noop_hook] if quiet_progress else [progress_hook],
        "postprocessor_hooks": [noop_hook] if quiet_progress else [postprocessor_hook],
        "noprogress": True,
    }
    if embed_metadata:
        ydl_opts["postprocessors"].append({"key": "FFmpegMetadata", "add_metadata": True})

        # Thumbnail cuma diunduh kalau memang bakal di-embed (dan file thumbnail-nya dibersihkan yt-dlp
        # setelah embed). WAV nggak mendukung embed thumbnail; opus/flac butuh paket 'mutagen'.
        embed_thumbnail = audio_format != "wav"
        if embed_thumbnail and audio_format in MUTAGEN_THUMBNAIL_FORMATS and not _mutagen_available():
            embed_thumbnail = False
            if not _mutagen_warned:
                _mutagen_warned = True
                printer(f"ℹ️  Thumbnail nggak di-embed ke file {audio_format}: butuh paket 'mutagen' (pip install mutagen).")
        if embed_thumbnail:
            ydl_opts["writethumbnail"] = True
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

    with notify.wake_lock():
        result, filename = _run_download(ydl_opts, url, expected_ext=audio_format, retries=retries, printer=printer)

        valid, alasan = _verify_downloaded_file(filename)
        if not valid:
            _quarantine_bad_file(filename)
            printer(f"❌ '{title}' gagal diverifikasi: {alasan}. Tidak disimpan ke riwayat, coba unduh ulang.")
            log.error(f"Verifikasi gagal untuk {title} ({filename}): {alasan}")
            return STATUS_FAIL

        save_file_record(title, filename, url, resolution_label, video_id=video_id)
        printer(f"\n✅ Selesai! '{title}' ({resolution_label}) berhasil diunduh.")
        log.info(f"Selesai: {title} -> {filename}")
        if termux_shared:
            _copy_to_termux_shared_storage(filename, printer)
        notify_download_done(f"{title} ({audio_format})")
        return STATUS_OK


def download_audio_many(url_list, first_info=None, config=None):
    """Fungsi download banyak audio sekaligus. Jalan paralel kalau config parallel_workers > 1."""
    return _run_batch(url_list, download_audio_single, config, first_info=first_info)
