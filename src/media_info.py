# src/media_info.py
"""Lapisan info: semua fungsi yang cuma NANYA ke yt-dlp, nggak download beneran."""
import shutil

import yt_dlp

from src.loading import Spinner


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