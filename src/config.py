import curses
import json
import os
import tempfile

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
    "bg_color": "putih",            # warna latar tampilan menu (lihat tui.COLOR_NAMES)
    "text_color": "hitam",          # warna tulisan tampilan menu (lihat tui.COLOR_NAMES)
}

_AUDIO_FORMATS = ["mp3", "m4a", "opus", "flac", "wav"]
_QUALITIES = ["128", "192", "256", "320"]
_ORGANIZE_OPTIONS = ["none", "channel", "date"]
_TOGGLE_OPTIONS = ["Aktif", "Nonaktif"]


def _validate_config(config):
    """
    Perbaiki nilai yang tipe/isinya nggak masuk akal (misal config.json rusak
    atau diedit manual jadi berantakan) dengan mengembalikannya ke default.
    Dipanggil diam-diam (nggak print apa pun) karena load_config() sering
    kepanggil dari dalam sesi curses -- print() di situ bisa ngerusak tampilan.
    Return (config_yang_sudah_bersih, list_nama_field_yang_direset).
    """
    reset = []

    def _cek(key, valid):
        if not valid:
            config[key] = DEFAULT_CONFIG[key]
            reset.append(key)

    v = config.get("default_resolution")
    _cek("default_resolution", v is None or (isinstance(v, int) and not isinstance(v, bool) and v > 0))

    _cek("audio_format", config.get("audio_format") in _AUDIO_FORMATS)

    _cek("mp3_quality", str(config.get("mp3_quality")) in _QUALITIES)
    if "mp3_quality" not in reset:
        config["mp3_quality"] = str(config["mp3_quality"])

    _cek("embed_metadata", isinstance(config.get("embed_metadata"), bool))

    v = config.get("subtitle_langs")
    _cek("subtitle_langs", isinstance(v, list) and all(isinstance(x, str) for x in v))

    v = config.get("parallel_workers")
    _cek("parallel_workers", isinstance(v, int) and not isinstance(v, bool) and v >= 1)

    v = config.get("retry_count")
    _cek("retry_count", isinstance(v, int) and not isinstance(v, bool) and v >= 1)

    v = config.get("cookies_file")
    _cek("cookies_file", v is None or isinstance(v, str))

    _cek("notify_termux", isinstance(config.get("notify_termux"), bool))

    _cek("organize_by", config.get("organize_by") in _ORGANIZE_OPTIONS)

    _cek("termux_shared_storage", isinstance(config.get("termux_shared_storage"), bool))

    v = config.get("rate_limit")
    _cek("rate_limit", v is None or isinstance(v, str))

    _cek("bg_color", config.get("bg_color") in tui.COLOR_NAMES)
    _cek("text_color", config.get("text_color") in tui.COLOR_NAMES)
    if config["bg_color"] == config["text_color"]:
        # Dua-duanya lolos cek individual tapi identik (mis. config.json diedit
        # manual) -- kalau dibiarkan tulisan jadi nggak kelihatan sama sekali.
        config["text_color"] = DEFAULT_CONFIG["text_color"]
        if "text_color" not in reset:
            reset.append("text_color")

    return config, reset


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)

    if not isinstance(data, dict):
        return dict(DEFAULT_CONFIG)

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    merged, _ = _validate_config(merged)
    return merged


def check_config_integrity():
    """
    Dipanggil SEKALI pas startup (mode teks biasa, sebelum curses jalan).
    Kalau config.json ada nilai yang nggak valid, kasih tau user dan simpan
    versi yang sudah diperbaiki balik ke disk. Aman kalau file belum ada
    atau memang belum pernah diubah dari default.
    """
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"⚠️  {CONFIG_FILE} rusak/nggak valid, pakai pengaturan default sampai diubah lagi lewat menu Pengaturan.")
        return

    if not isinstance(data, dict):
        print(f"⚠️  Isi {CONFIG_FILE} bukan format yang diharapkan, pakai pengaturan default.")
        return

    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    fixed, reset = _validate_config(merged)
    if reset:
        print(f"⚠️  Nilai pengaturan nggak valid buat: {', '.join(reset)} -- direset ke default.")
        save_config(fixed)


def _atomic_write_json(path, data):
    """
    Tulis JSON ke `path` secara atomic: tulis dulu ke file sementara di folder
    yang sama, baru dipindah lewat os.replace() ke nama aslinya. os.replace()
    itu operasi atomik di level filesystem -- kalau proses mati/crash/force-close
    di tengah penulisan, file ASLI tetap utuh (isi lama) atau LANGSUNG jadi versi
    baru yang lengkap. Nggak ada kondisi "setengah nulis" yang bikin file kepotong/rusak.
    """
    folder = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def save_config(config):
    try:
        _atomic_write_json(CONFIG_FILE, config)
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


def _label_color(name):
    return (name or "").capitalize()


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


def _h_bg_color(stdscr, config):
    current = config.get("bg_color", "putih")
    text_now = config.get("text_color", "hitam")
    names = tui.COLOR_NAMES
    labels = [_label_color(n) for n in names]
    start = names.index(current) if current in names else 0
    idx = tui.menu(stdscr, "Warna Latar Belakang", labels, selected=start,
                   message="Warna latar tampilan menu. Nggak boleh sama dengan warna tulisan.")
    if idx is None:
        return
    chosen = names[idx]
    if chosen == text_now:
        tui.message_box(stdscr, "Tidak Bisa Dipakai",
                        f"Warna latar nggak boleh sama dengan warna tulisan ({_label_color(text_now)}).")
        return
    set_value("bg_color", chosen)
    tui.apply_theme(stdscr, chosen, text_now)


def _h_text_color(stdscr, config):
    current = config.get("text_color", "hitam")
    bg_now = config.get("bg_color", "putih")
    names = tui.COLOR_NAMES
    labels = [_label_color(n) for n in names]
    start = names.index(current) if current in names else 0
    idx = tui.menu(stdscr, "Warna Tulisan", labels, selected=start,
                   message="Warna teks menu. Nggak boleh sama dengan warna latar.")
    if idx is None:
        return
    chosen = names[idx]
    if chosen == bg_now:
        tui.message_box(stdscr, "Tidak Bisa Dipakai",
                        f"Warna tulisan nggak boleh sama dengan warna latar ({_label_color(bg_now)}).")
        return
    set_value("text_color", chosen)
    tui.apply_theme(stdscr, bg_now, chosen)


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
    _h_bg_color, _h_text_color,
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
        f"Warna latar belakang      : {_label_color(config.get('bg_color', 'putih'))}",
        f"Warna tulisan             : {_label_color(config.get('text_color', 'hitam'))}",
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