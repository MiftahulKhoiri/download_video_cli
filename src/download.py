import yt_dlp
from src.manager import ensure_download_folder, is_already_downloaded, save_file_record
from src.loading import progress_hook


def get_video_info(url):
    ydl_opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


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


def download_single(url, target_height=None, resolution_label="terbaik"):
    """Fungsi download 1 video dari YouTube/X."""
    folder = ensure_download_folder()

    info = get_video_info(url)
    title = info.get("title", "video")

    already, existing = is_already_downloaded(title)
    if already:
        print(f"⚠️  '{title}' sudah pernah diunduh sebelumnya (file: {existing.get('filename')}). Dilewati.")
        return False

    ydl_opts = {
        "format": _build_format_string(target_height),
        "outtmpl": f"{folder}/%(title)s.%(ext)s",
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
        filename = ydl.prepare_filename(info)

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