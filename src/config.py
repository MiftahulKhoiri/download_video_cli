import curses
import json
import os

from src import tui

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "default_resolution": None,     # None = selalu tanya; atau angka misal 720
    "audio_format": "mp3",          # mp3, m4a, opus, flac, wav
    "mp3_quality": "192",           # kbps: "128", "192", "256", "320" (cuma berlaku format lossy: mp3/m4a/opus)
    "embed_metadata": True,         # sisipkan thumbnail + metadata (judul dll) ke file audio
    "subtitle_langs": [],           # contoh: ["id", "en"]; kosong = jangan ambil subtitle
    "parallel_workers": 1,          # 1 = download berurutan (default, paling aman)
    "retry_count": 1,               # jumlah percobaan per video (1 = tanpa retry)
    "cookies_file": None,           # path ke cookies.txt (format Netscape), None = tidak dipakai
    "notify_termux": True,          # kirim notifikasi Termux kalau tersedia
    "organize_by": "none",          # none, channel, date -- susun folder hasil download
    "termux_shared_storage": False, # salin juga hasil download ke ~/storage/downloads (Termux)
    "rate_limit": None,             # batas kecepatan, contoh "2M" / "500K"; None = tanpa batas
}

_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
_QUALITIES = ["128", "192", "256", "320"]
_ORGANIZE_OPTIONS = ["none", "channel", "date"]
_TOGGLE_OPTIONS = ["Aktif", "Nonaktif"]


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  Gagal membaca {CONFIG_FILE}: {e}. Menggunakan pengaturan default.")
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"⚠️  Gagal menyimpan {CONFIG_FILE}: {e}")
        return False


def get(key):
    return load_config().get(key, DEFAULT_CONFIG.get(key))


def set_value(key, value):
    if key not in DEFAULT_CONFIG:
        raise KeyError(f"Kunci pengaturan tidak dikenal: {key}")
    config = load_config()
    config[key] = value
    return save_config(config)


def _label_bool(v):
    return "aktif" if v else "nonaktif"


# ---------- Handler tiap item pengaturan (satu fungsi = satu layar TUI) ----------

def _h_default_resolution(stdscr, config):
    current = config.get("default_resolution")
    raw = tui.input_box(
        stdscr, "Resolusi Default",
        "Angka misal 720. Kosongkan = selalu tanya tiap download.",
        initial=str(current) if current else "",
    )
    if raw is None:
        return
    raw = raw.strip()
    if raw and not raw.isdigit():
        tui.message_box(stdscr, "Nilai Tidak Valid", "Harus berupa angka, atau dikosongkan.")
        return
    set_value("default_resolution", int(raw) if raw else None)


def _h_audio_format(stdscr, config):
    current = config.get("audio_format", "mp3")
    start = _AUDIO_FORMATS.index(current) if current in _AUDIO_FORMATS else 0
    idx = tui.menu(stdscr, "Format Audio Default", _AUDIO_FORMATS, selected=start)
    if idx is not None:
        set_value("audio_format", _AUDIO_FORMATS[idx])


def _h_mp3_quality(stdscr, config):
    current = config.get("mp3_quality", "192")
    start = _QUALITIES.index(current) if current in _QUALITIES else 1
    idx = tui.menu(stdscr, "Kualitas Audio Default", [f"{q} kbps" for q in _QUALITIES],
                   selected=start, message="Cuma berlaku buat format lossy (mp3/m4a/opus).")
    if idx is not None:
        set_value("mp3_quality", _QUALITIES[idx])


def _h_embed_metadata(stdscr, config):
    current = config.get("embed_metadata", True)
    idx = tui.menu(stdscr, "Embed Thumbnail/Metadata", _TOGGLE_OPTIONS, selected=0 if current else 1)
    if idx is not None:
        set_value("embed_metadata", idx == 0)


def _h_subtitle_langs(stdscr, config):
    current = ", ".join(config.get("subtitle_langs") or [])
    raw = tui.input_box(
        stdscr, "Subtitle Default",
        "Kode bahasa pisah koma, misal id,en. Kosongkan = nonaktif.",
        initial=current,
    )
    if raw is None:
        return
    langs = [x.strip() for x in raw.split(",") if x.strip()]
    set_value("subtitle_langs", langs)


def _h_parallel_workers(stdscr, config):
    current = config.get("parallel_workers", 1)
    raw = tui.input_box(stdscr, "Jumlah Download Paralel", "Angka >= 1. 1 = berurutan (paling aman).",
                         initial=str(current))
    if raw is None:
        return
    raw = raw.strip()
    if not (raw.isdigit() and int(raw) >= 1):
        tui.message_box(stdscr, "Nilai Tidak Valid", "Harus angka, minimal 1.")
        return
    set_value("parallel_workers", int(raw))


def _h_retry_count(stdscr, config):
    current = config.get("retry_count", 1)
    raw = tui.input_box(stdscr, "Jumlah Percobaan Ulang", "Angka >= 1. 1 = tanpa retry.",
                         initial=str(current))
    if raw is None:
        return
    raw = raw.strip()
    if not (raw.isdigit() and int(raw) >= 1):
        tui.message_box(stdscr, "Nilai Tidak Valid", "Harus angka, minimal 1.")
        return
    set_value("retry_count", int(raw))


def _h_cookies_file(stdscr, config):
    current = config.get("cookies_file") or ""
    raw = tui.input_box(stdscr, "File Cookies", "Path ke cookies.txt. Kosongkan = tidak dipakai.",
                         initial=current)
    if raw is None:
        return
    raw = raw.strip()
    set_value("cookies_file", raw or None)


def _h_notify_termux(stdscr, config):
    current = config.get("notify_termux", True)
    idx = tui.menu(stdscr, "Notifikasi Termux", _TOGGLE_OPTIONS, selected=0 if current else 1)
    if idx is not None:
        set_value("notify_termux", idx == 0)


def _h_organize_by(stdscr, config):
    current = config.get("organize_by", "none")
    start = _ORGANIZE_OPTIONS.index(current) if current in _ORGANIZE_OPTIONS else 0
    idx = tui.menu(stdscr, "Susun Folder Hasil", _ORGANIZE_OPTIONS, selected=start,
                   message="none = rata, channel = per uploader, date = per tanggal upload.")
    if idx is not None:
        set_value("organize_by", _ORGANIZE_OPTIONS[idx])


def _h_termux_shared_storage(stdscr, config):
    current = config.get("termux_shared_storage", False)
    idx = tui.menu(stdscr, "Salin ke Storage Termux", _TOGGLE_OPTIONS, selected=0 if current else 1,
                   message="Butuh 'termux-setup-storage' sudah dijalankan.")
    if idx is not None:
        set_value("termux_shared_storage", idx == 0)


def _h_rate_limit(stdscr, config):
    current = config.get("rate_limit") or ""
    raw = tui.input_box(stdscr, "Batas Kecepatan Unduh", "Misal 2M atau 500K. Kosongkan = tanpa batas.",
                         initial=current)
    if raw is None:
        return
    raw = raw.strip()
    set_value("rate_limit", raw or None)


def _h_update_ytdlp(stdscr, config):
    from src.updater import check_for_update, update_yt_dlp

    tui.loading_box(stdscr, "Cek Update", "🔍 Mengecek versi yt-dlp...")
    installed, latest, is_outdated = check_for_update(timeout=5)

    if installed is None:
        tui.message_box(stdscr, "Cek Update", "❌ Tidak bisa mendeteksi yt-dlp yang terpasang.")
        return
    if latest is None:
        tui.message_box(stdscr, "Cek Update", [
            f"Versi terpasang: {installed}",
            "Tidak bisa mengecek versi terbaru.",
            "(cek koneksi internet)",
        ])
        return
    if not is_outdated:
        tui.message_box(stdscr, "Cek Update", f"✅ Sudah versi terbaru ({installed}).")
        return

    idx = tui.menu(stdscr, "Update Tersedia", ["Ya, update sekarang", "Tidak"],
                   message=[f"Terpasang: {installed}", f"Terbaru  : {latest}"])
    if idx != 0:
        return

    tui.loading_box(stdscr, "Update yt-dlp", "⬇️  Mengupdate, mohon tunggu...")
    ok, output = update_yt_dlp()
    if ok:
        tui.message_box(stdscr, "Update Selesai", ["✅ yt-dlp berhasil diupdate.", "Restart aplikasi biar kepakai."])
    else:
        tui.message_box(stdscr, "Update Gagal", f"❌ {output[:200]}")


# Urutan HARUS selaras sama urutan item di _build_items()
_HANDLERS = [
    _h_default_resolution, _h_audio_format, _h_mp3_quality, _h_embed_metadata,
    _h_subtitle_langs, _h_parallel_workers, _h_retry_count, _h_cookies_file,
    _h_notify_termux, _h_organize_by, _h_termux_shared_storage, _h_rate_limit,
    _h_update_ytdlp,
]


def _build_items(config):
    return [
        f"Resolusi default          : {config.get('default_resolution') or 'selalu tanya'}",
        f"Format audio default      : {config.get('audio_format')}",
        f"Kualitas audio default    : {config.get('mp3_quality')} kbps",
        f"Embed thumbnail/metadata  : {_label_bool(config.get('embed_metadata'))}",
        f"Subtitle default          : {', '.join(config.get('subtitle_langs') or []) or 'nonaktif'}",
        f"Jumlah download paralel   : {config.get('parallel_workers')}",
        f"Jumlah percobaan ulang    : {config.get('retry_count')}",
        f"File cookies              : {config.get('cookies_file') or 'tidak dipakai'}",
        f"Notifikasi Termux         : {_label_bool(config.get('notify_termux'))}",
        f"Susun folder hasil        : {config.get('organize_by')}",
        f"Salin ke storage Termux   : {_label_bool(config.get('termux_shared_storage'))}",
        f"Batas kecepatan unduh     : {config.get('rate_limit') or 'tanpa batas'}",
        "Cek & update yt-dlp",
    ]


def _settings_loop(stdscr):
    selected = 0
    while True:
        config = load_config()
        items = _build_items(config)
        idx = tui.menu(stdscr, "PENGATURAN", items + ["Kembali"], selected=selected)
        if idx is None or idx == len(items):
            return
        selected = idx
        _HANDLERS[idx](stdscr, config)


def run_settings_menu():
    curses.wrapper(_settings_loop)