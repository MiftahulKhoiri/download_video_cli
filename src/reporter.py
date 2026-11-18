# src/reporter.py
"""
Lapisan pelapor. Mesin download (download_core, media_info, manager, config)
nggak pernah print() langsung -- semuanya melapor "kejadian" ke reporter yang
sedang aktif:

    from src.reporter import report
    report().message("⚠️  ada yang aneh")
    report().progress(url, d)          # dari progress hook yt-dlp

Reporter yang aktif bisa diganti selama satu blok kode:

    with use_reporter(TuiDownloadReporter()):
        download_many(urls)

Implementasi:
  - TextReporter (default): output teks biasa, PERSIS seperti versi sebelumnya
    (progress bar colorama, spinner). Dipakai mode CLI -- output-nya harus tetap
    teks biasa biar bisa dialihkan ke file/log dari cron atau script.
  - BufferReporter: menampung pesan selama sesi menu curses, buat ditampilkan
    belakangan di kotak pesan (print() di tengah curses bikin layar berantakan).
  - TuiDownloadReporter (src/tui_progress.py): layar progress download curses.

Reporter dipakai dari banyak thread sekaligus (mode download paralel), jadi
semua implementasi wajib thread-safe.
"""
import contextlib
import threading


class Reporter:
    """Basis: semua kejadian diabaikan. Turunan cukup override yang dibutuhkan."""

    # ----- pesan umum -----
    def message(self, text):
        """Pesan satu kali (info/peringatan/error). Boleh berisi beberapa baris (\\n)."""

    def status(self, text):
        """Context manager selama proses tanpa progress sendiri berjalan (mis. ambil info video)."""
        return contextlib.nullcontext()

    # ----- batch -----
    def batch_start(self, urls, workers):
        """Batch dimulai. workers > 1 = mode paralel."""

    def batch_item(self, index, total, key):
        """Mode berurutan: item ke-index mulai diproses."""

    def batch_tick(self, index, total, key, status, detail=None):
        """Mode paralel: satu item selesai (index = urutan selesainya, bukan urutan antrean)."""

    def summary(self, hasil):
        """Batch selesai. hasil = {"berhasil": n, "dilewati": n, "gagal": n}."""

    # ----- per item (key = URL) -----
    def item_info(self, key, title, label=None):
        """Judul & label (resolusi/format) item sudah diketahui."""

    def item_start(self, key, title, tag=""):
        """Download item benar-benar dimulai."""

    def progress(self, key, d):
        """Dict progress hook yt-dlp (status downloading/finished/error)."""

    def postprocess(self, key, d):
        """Dict postprocessor hook yt-dlp (merge/convert)."""

    def retry(self, key, text):
        """Percobaan gagal dan akan diulang."""

    def item_done(self, key, status, detail=None, shown=False):
        """
        Item selesai: status 'berhasil'/'dilewati'/'gagal'. detail = alasan gagal (opsional).
        shown=True: alasannya sudah dilaporkan lewat message(), jangan dicetak ulang.
        """


class TextReporter(Reporter):
    """Output teks biasa -- perilaku asli aplikasi, dipakai mode CLI."""

    def __init__(self):
        self._parallel = False

    def message(self, text):
        from src.loading import safe_print
        safe_print(text)

    def status(self, text):
        if self._parallel:
            return contextlib.nullcontext()   # spinner dari banyak thread bakal saling timpa
        from src.loading import Spinner
        return Spinner(text)

    def batch_start(self, urls, workers):
        self._parallel = workers > 1

    def batch_item(self, index, total, key):
        print(f"\n=== [{index}/{total}] {key} ===")

    def batch_tick(self, index, total, key, status, detail=None):
        from src.loading import safe_print
        if status == "gagal":
            safe_print(f"[{index}/{total}] ❌ Gagal: {key}" + (f"\n   {detail}" if detail else ""))
        else:
            safe_print(f"[{index}/{total}] Selesai: {key}")

    def summary(self, hasil):
        self._parallel = False
        print(f"\nRingkasan: {hasil['berhasil']} berhasil, {hasil['dilewati']} dilewati (duplikat), "
              f"{hasil['gagal']} gagal.")

    def item_start(self, key, title, tag=""):
        from src.loading import reset_progress, safe_print
        if self._parallel:
            safe_print(f"⬇️  Mulai unduh{f' ({tag})' if tag else ''}: {title}")
        else:
            reset_progress()

    def progress(self, key, d):
        if not self._parallel:
            from src.loading import progress_hook
            progress_hook(d)

    def postprocess(self, key, d):
        if not self._parallel:
            from src.loading import postprocessor_hook
            postprocessor_hook(d)

    def retry(self, key, text):
        from src.loading import reset_progress, safe_print
        safe_print(text)
        reset_progress()

    def item_done(self, key, status, detail=None, shown=False):
        # Mode paralel: baris "[i/n] Gagal" dicetak batch_tick. Mode berurutan: pesan
        # sukses/duplikat sudah dicetak lewat message(), tinggal error dari exception.
        if detail and status == "gagal" and not shown and not self._parallel:
            print(f"❌ Gagal mengunduh {key}: {detail}")


class BufferReporter(Reporter):
    """Tampung pesan (buat ditampilkan belakangan di kotak curses), abaikan kejadian lain."""

    def __init__(self):
        self._lock = threading.Lock()
        self._messages = []

    def message(self, text):
        with self._lock:
            self._messages.append(str(text).strip("\n"))

    def drain(self):
        """Ambil & kosongkan semua pesan yang tertampung."""
        with self._lock:
            out, self._messages = self._messages, []
        return out


_default = TextReporter()
_current = _default
_current_lock = threading.Lock()


def report():
    """Reporter yang sedang aktif (default: TextReporter)."""
    return _current


@contextlib.contextmanager
def use_reporter(reporter):
    """Pakai `reporter` selama blok with, lalu kembalikan reporter sebelumnya."""
    global _current
    with _current_lock:
        previous, _current = _current, reporter
    try:
        yield reporter
    finally:
        with _current_lock:
            _current = previous
