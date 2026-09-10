# src/media_info.py
"""Lapisan info: semua fungsi yang cuma NANYA ke yt-dlp, nggak download beneran."""
import shutil
import subprocess

import yt_dlp

from src.loading import Spinner


def is_ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_version():
    """Return versi ffmpeg (str) kalau terpasang, None kalau nggak ada / gagal dibaca."""
    if not is_ffmpeg_available():
        return None
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        # contoh baris asli: "ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 ..."
        version = first_line.replace("ffmpeg version", "").split(" Copyright")[0].strip()
        return version or None
    except (subprocess.SubprocessError, OSError, IndexError):
        return None


def _fetch_info_with_retry(ydl_opts, url, spinner_message, retries=1):
    """
    Jalankan extract_info(download=False) dengan retry otomatis kalau gagal
    (mis. koneksi putus sesaat pas baru mau ambil info/metadata) -- semangatnya
    sama kayak retry di proses download beneran (_run_download di download_core.py),
    tapi buat panggilan info-only ini (get_video_info & expand_playlist).

    Tiap percobaan dapat Spinner-nya sendiri yang dibuka-tutup bersih, dan pesan
    retry dicetak SETELAH spinner ditutup (bukan pas animasinya lagi jalan) biar
    nggak tabrakan/nge-garbled tampilannya di terminal.
    """
    retries = max(1, int(retries or 1))
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            with Spinner(spinner_message):
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            last_exc = e
            if attempt < retries:
                print(f"⚠️  Percobaan {attempt}/{retries} gagal ambil info ({e}). Mencoba lagi...")
    raise last_exc


def get_video_info(url, cookies_file=None, retries=1):
    ydl_opts = {"quiet": True, "no_warnings": True}
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    return _fetch_info_with_retry(ydl_opts, url, "🔍 Mengambil info video...", retries=retries)


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


def expand_playlist(url, cookies_file=None, retries=1):
    """
    Kalau url adalah playlist, kembalikan list URL video di dalamnya
    (pakai extract_flat biar cepat, nggak fetch semua format tiap video).
    Kalau url video tunggal, kembalikan [url] apa adanya.
    """
    ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    info = _fetch_info_with_retry(ydl_opts, url, "🔍 Memeriksa URL / playlist...", retries=retries)

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