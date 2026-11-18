# src/tui_progress.py
"""
Layar proses versi TUI (curses) -- pengganti output teks biasa di mode menu.

  run_download_screen(stdscr, judul, fn)
      Jalankan fn (download_single / download_many / ...) di thread terpisah,
      sambil thread utama menggambar layar progress: tiap item punya baris
      sendiri (judul, bar %, ukuran, kecepatan, ETA) -- di mode paralel semua
      download yang lagi jalan kelihatan bergerak bersamaan. Pesan (peringatan,
      error + petunjuk 💡) masuk ke panel "Pesan" di bawah. Esc 2x / Ctrl+C =
      batalkan. Setelah selesai, layar tetap tampil (ringkasan + pesan bisa
      digulir) sampai user menekan Enter/Esc.

  run_busy(stdscr, judul, fn, teks_awal)
      Buat proses singkat tanpa progress bar (cek URL/playlist, ambil info video,
      update yt-dlp): kotak kecil dengan spinner. Return (hasil, pesan_pesan).

Kenapa thread: curses cuma boleh disentuh dari SATU thread (thread utama),
sedangkan download (apalagi paralel) jalan di thread lain. Jadi reporter di
sini cuma mencatat kejadian ke state (dikunci lock), dan thread utama yang
menggambar ulang layar ~10x per detik dari state itu.
"""
import contextlib
import curses
import re
import threading
import time

from src import tui
from src.reporter import Reporter, use_reporter
from src.loading import format_size

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_FRAME_SECONDS = 0.1
_ESC_CONFIRM_SECONDS = 3.0
_MAX_LOG_LINES = 500

# Simbol status: sengaja karakter selebar 1 kolom yang aman di semua terminal
# (emoji lebarnya beda-beda antar terminal dan bisa bikin baris geser).
_ICONS = {
    "antri": "·", "info": "…", "unduh": "↓", "proses": "≈",
    "berhasil": "√", "dilewati": "=", "gagal": "×", "batal": "×",
}
_ACTIVE = ("info", "unduh", "proses")
_DONE = ("berhasil", "dilewati", "gagal", "batal")

_PP_LABELS = {
    "Merger": "Menggabungkan video & audio...",
    "FFmpegExtractAudio": "Mengonversi audio...",
    "FFmpegMetadata": "Menulis metadata...",
    "EmbedThumbnail": "Menyematkan thumbnail...",
    "FFmpegVideoRemuxer": "Merapikan kontainer video...",
    "FFmpegFixupM3u8": "Merapikan file...",
    "FFmpegFixupM4a": "Merapikan file...",
}


def _parse_percent(d):
    total = d.get("total_bytes") or d.get("total_bytes_estimate")
    done = d.get("downloaded_bytes")
    if total and done is not None:
        return max(0.0, min(100.0, done * 100.0 / total))
    try:
        return float(str(d.get("_percent_str", "0")).strip().rstrip("%"))
    except ValueError:
        return 0.0


def _fmt_eta(sec):
    if sec is None:
        return ""
    try:
        sec = int(sec)
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(max(0, sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _bar(pct, width):
    width = max(4, width)
    filled = int(width * max(0.0, min(100.0, pct)) / 100)
    return "█" * filled + "░" * (width - filled)


class _Item:
    __slots__ = ("key", "title", "label", "state", "pct", "speed", "eta", "done_bytes",
                 "total_bytes", "phase", "detail", "parts_done")

    def __init__(self, key):
        self.key = key
        self.title = key
        self.label = ""
        self.state = "antri"
        self.pct = 0.0
        self.speed = None
        self.eta = None
        self.done_bytes = None
        self.total_bytes = None
        self.phase = ""
        self.detail = ""
        self.parts_done = 0

    def copy(self):
        c = _Item(self.key)
        for name in self.__slots__:
            setattr(c, name, getattr(self, name))
        return c


class TuiDownloadReporter(Reporter):
    """Reporter yang menyimpan semua kejadian ke state buat digambar thread utama."""

    def __init__(self):
        self._lock = threading.Lock()
        self.items = {}          # key -> _Item (urutan sisip = urutan antrean)
        self.log = []            # baris pesan (belum di-wrap)
        self.status_stack = []   # teks status (spinner) yang lagi aktif
        self.total = 0
        self.finished = 0
        self.parallel = False
        self.hasil = None

    # ----- util -----
    def _item(self, key):
        it = self.items.get(key)
        if it is None:
            it = self.items[key] = _Item(key)
        return it

    def _add_log(self, text):
        text = str(text).strip("\n")
        if not text.strip():
            return
        self.log.extend(text.split("\n"))
        if len(self.log) > _MAX_LOG_LINES:
            del self.log[:len(self.log) - _MAX_LOG_LINES]

    def snapshot(self):
        with self._lock:
            return {
                "items": [it.copy() for it in self.items.values()],
                "log": list(self.log),
                "status": self.status_stack[-1] if self.status_stack else None,
                "total": self.total,
                "finished": self.finished,
                "parallel": self.parallel,
                "hasil": dict(self.hasil) if self.hasil else None,
            }

    # ----- kejadian dari mesin download -----
    def message(self, text):
        with self._lock:
            self._add_log(text)

    @contextlib.contextmanager
    def _status_cm(self, text):
        with self._lock:
            self.status_stack.append(str(text).strip())
        try:
            yield
        finally:
            with self._lock:
                try:
                    self.status_stack.remove(str(text).strip())
                except ValueError:
                    pass

    def status(self, text):
        return self._status_cm(text)

    def batch_start(self, urls, workers):
        with self._lock:
            self.parallel = workers > 1
            self.total = len(urls)
            for u in urls:
                self._item(u)

    def batch_item(self, index, total, key):
        with self._lock:
            it = self._item(key)
            if it.state == "antri":
                it.state = "info"

    def batch_tick(self, index, total, key, status, detail=None):
        pass  # jumlah selesai dihitung dari item_done (berlaku juga buat mode berurutan)

    def summary(self, hasil):
        with self._lock:
            self.hasil = dict(hasil)

    def item_info(self, key, title, label=None):
        with self._lock:
            it = self._item(key)
            if title:
                it.title = title
            if label:
                it.label = label
            if it.state == "antri":
                it.state = "info"

    def item_start(self, key, title, tag=""):
        with self._lock:
            it = self._item(key)
            it.title = title or it.title
            it.state = "unduh"
            it.pct = 0.0
            it.phase = ""

    def progress(self, key, d):
        with self._lock:
            it = self._item(key)
            st = d.get("status")
            if st == "downloading":
                it.state = "unduh"
                it.pct = _parse_percent(d)
                it.speed = d.get("speed")
                it.eta = d.get("eta")
                it.done_bytes = d.get("downloaded_bytes")
                it.total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
                it.phase = f"file ke-{it.parts_done + 1}" if it.parts_done else ""
            elif st == "finished":
                it.pct = 100.0
                it.parts_done += 1
                it.speed = None
                it.eta = None

    def postprocess(self, key, d):
        with self._lock:
            it = self._item(key)
            if d.get("status") == "started":
                pp = d.get("postprocessor", "")
                it.state = "proses"
                it.phase = _PP_LABELS.get(pp, f"Memproses ({pp})..." if pp else "Memproses...")

    def retry(self, key, text):
        with self._lock:
            self._add_log(text)
            it = self._item(key)
            it.state = "info"
            it.pct = 0.0
            it.parts_done = 0
            it.phase = "mengulang..."

    def item_done(self, key, status, detail=None, shown=False):
        with self._lock:
            it = self._item(key)
            if it.state in _DONE:
                return
            it.state = status if status in _DONE else "gagal"
            if (detail or "").strip() == "dibatalkan":
                it.state = "batal"
                detail, shown = "dibatalkan", True   # cukup satu pesan "Dibatalkan" di akhir
            # Ringkas: baris pertama saja, tanpa awalan "[twitter] 12345: " -- detail lengkapnya ada di panel Pesan.
            it.detail = re.sub(r"^\[[^\]]+\]\s*[^:\s]*:\s*", "", (detail or "").split("\n")[0].strip())
            if it.state == "berhasil":
                it.pct = 100.0
            if detail and not shown:
                name = it.title if it.title != key else key
                self._add_log(f"❌ {name}:\n   {detail.strip()}")
            self.finished += 1

    # ----- dipanggil runner (thread utama) -----
    def finalize(self, cancelled, error_text=None):
        with self._lock:
            if error_text:
                self._add_log(error_text)
            for it in self.items.values():
                if it.state not in _DONE:
                    if cancelled:
                        it.state = "batal"
                        it.detail = "dibatalkan"
                    elif error_text:
                        it.state = "gagal"
                        it.detail = error_text.split("\n")[0].lstrip("❌ ").strip()
                    else:
                        it.state = "gagal"
                        it.detail = "berhenti tanpa hasil"
                    self.finished += 1
            if cancelled:
                self._add_log("⏹️  Dibatalkan oleh user. File sementara download yang terputus sudah dibersihkan.")


# ---------- menggambar ----------

def _put(stdscr, y, x, text, width, attr=0):
    if width <= 0:
        return
    try:
        stdscr.addstr(y, x, tui._fit_display(text, width), attr or tui.normal_attr())
    except curses.error:
        pass


def _item_lines(it, inner_w, frame):
    """1 baris buat item yang belum/sudah selesai, 2 baris buat item yang lagi jalan."""
    icon = _ICONS.get(it.state, "?")
    label = f"  [{it.label}]" if it.label else ""
    if it.state == "antri":
        return [(f" {icon} {it.title}", curses.A_DIM)]
    if it.state in _DONE:
        kind = {"berhasil": "ok", "dilewati": "warn", "batal": "warn"}.get(it.state, "err")
        tail = {"berhasil": "selesai", "dilewati": "sudah ada, dilewati"}.get(it.state, it.detail or "gagal")
        # Judul dipotong duluan (maks ~separuh lebar) biar alasan gagal tetap kebaca.
        head = f" {icon} {it.title}{label}"
        head_max = max(20, inner_w // 2)
        if tui.display_width(head) > head_max and tui.display_width(head) + 3 + tui.display_width(tail) > inner_w:
            head = tui._fit_display(head, head_max).rstrip()
        return [(f"{head} — {tail}", tui.accent_attr(kind))]

    # sedang jalan
    first = (f" {icon} {it.title}{label}", curses.A_BOLD | tui.normal_attr())
    if it.state == "info":
        second = f"   {_SPINNER[frame % len(_SPINNER)]} {it.phase or 'Mengambil info video...'}"
        return [first, (second, tui.normal_attr())]
    if it.state == "proses":
        second = f"   {_SPINNER[frame % len(_SPINNER)]} {it.phase}"
        return [first, (second, tui.accent_attr("accent"))]

    info = f" {it.pct:5.1f}%"
    if it.total_bytes:
        info += f"  {format_size(it.done_bytes or 0)}/{format_size(it.total_bytes)}"
    if it.speed:
        info += f"  {format_size(it.speed)}/s"
    if it.eta is not None:
        info += f"  sisa {_fmt_eta(it.eta)}"
    if it.phase:
        info += f"  ({it.phase})"
    bar_w = max(8, min(30, inner_w - tui.display_width(info) - 5))
    second = f"   [{_bar(it.pct, bar_w)}]{info}"
    return [first, (second, tui.accent_attr("accent"))]


def _select_items(items, budget, inner_w, frame, done):
    """
    Pilih baris item yang muat di `budget` baris. Kalau nggak muat semua, prioritas:
    lagi diunduh/diproses > lagi ambil info > gagal > antrean terdekat > sisanya.
    (Tampilan akhir: yang gagal duluan, karena biasanya itu yang perlu dibaca.)
    Item terpilih tetap ditampilkan sesuai urutan antrean aslinya.
    """
    blocks = [_item_lines(it, inner_w, frame) for it in items]
    if sum(len(b) for b in blocks) <= budget:
        return [line for b in blocks for line in b]

    if done:
        rank = {"gagal": 0, "batal": 1}
    else:
        rank = {"unduh": 0, "proses": 0, "info": 1, "gagal": 2, "antri": 3}
    order = sorted(range(len(items)), key=lambda i: (rank.get(items[i].state, 4), i))

    chosen, used = set(), 0
    for i in order:
        if used + len(blocks[i]) > budget - 1:   # sisakan 1 baris buat "… N item lainnya"
            continue
        chosen.add(i)
        used += len(blocks[i])
    out = [line for i in sorted(chosen) for line in blocks[i]]
    hidden = len(items) - len(chosen)
    if hidden > 0:
        out.append((f"   … {hidden} item lainnya", curses.A_DIM))
    return out


def _compose_rows(heading, snap, h, w, frame, log_scroll, done):
    """
    Susun isi layar progress jadi list (teks, attr) -- dipisah dari proses menggambar
    biar bisa diuji tanpa terminal. Return (rows, max_scroll_pesan).
    """
    inner_w = w - 4
    usable = h - 2
    rows = []

    items = snap["items"]
    n_ok = sum(1 for it in items if it.state == "berhasil")
    n_skip = sum(1 for it in items if it.state == "dilewati")
    n_fail = sum(1 for it in items if it.state == "gagal")
    n_cancel = sum(1 for it in items if it.state == "batal")
    total = max(snap["total"], len(items))
    finished = n_ok + n_skip + n_fail + n_cancel

    if total > 1:
        mode = " (paralel)" if snap["parallel"] else ""
        cancel_part = f"  ×{n_cancel} batal" if n_cancel else ""
        rows.append((f"Total {finished}/{total}{mode}  √{n_ok} berhasil  ={n_skip} dilewati  ×{n_fail} gagal"
                     f"{cancel_part}", curses.A_BOLD | tui.normal_attr()))
        pct = finished * 100.0 / total if total else 0
        rows.append((f"[{_bar(pct, max(8, inner_w - 9))}] {pct:3.0f}%", tui.accent_attr("ok")))
        rows.append(("", 0))
    elif done and items:
        it = items[0]
        verdict = {"berhasil": ("√ Selesai, berhasil diunduh.", "ok"),
                   "dilewati": ("= Dilewati: sudah pernah diunduh.", "warn"),
                   "batal": ("× Dibatalkan.", "warn")}.get(
            it.state, ("× Gagal. Lihat pesan di bawah.", "err"))
        rows.append((verdict[0], tui.accent_attr(verdict[1])))
        rows.append(("", 0))

    if snap["status"] and not done and not any(it.state in _ACTIVE for it in items):
        rows.append((f"{_SPINNER[frame % len(_SPINNER)]} {snap['status']}", tui.normal_attr()))
        rows.append(("", 0))

    log_lines_all = tui._wrap_lines(snap["log"], max(10, inner_w - 1)) if snap["log"] else []
    log_min = min(len(log_lines_all), 3 if not done else 6)
    log_block_min = (log_min + 1) if log_lines_all else 0

    budget_items = max(1, usable - len(rows) - log_block_min)
    rows.extend(_select_items(items, budget_items, inner_w, frame, done))

    max_scroll = 0
    space = usable - len(rows) - 1
    if log_lines_all and space >= 1:
        rows.append(("─ Pesan " + "─" * max(0, inner_w - 8), curses.A_DIM))
        max_scroll = max(0, len(log_lines_all) - space)
        scroll = max_scroll if not done else max(0, min(log_scroll, max_scroll))
        for line in log_lines_all[scroll:scroll + space]:
            attr = tui.normal_attr()
            st = line.lstrip()
            if st.startswith(("❌", "×")):
                attr = tui.accent_attr("err")
            elif st.startswith(("⚠", "⏹")):
                attr = tui.accent_attr("warn")
            elif st.startswith(("✅", "√")):
                attr = tui.accent_attr("ok")
            elif st.startswith("💡"):
                attr = tui.accent_attr("accent")
            rows.append((line, attr))
    return rows[:usable], max_scroll


def _draw_download(stdscr, heading, snap, frame, footer, log_scroll, done):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    try:
        stdscr.bkgd(" ", tui.normal_attr())
    except curses.error:
        pass
    if h < 8 or w < 30:
        _put(stdscr, 0, 0, "Layar terlalu kecil -- perbesar terminal.", w - 1)
        stdscr.refresh()
        return 0
    try:
        stdscr.attron(tui.normal_attr())
        stdscr.box()
        stdscr.attroff(tui.normal_attr())
    except curses.error:
        pass
    title = f" {heading} "
    _put(stdscr, 0, max(1, (w - tui.display_width(title)) // 2), title,
         min(tui.display_width(title), w - 2), tui.title_attr())

    rows, max_scroll = _compose_rows(heading, snap, h, w, frame, log_scroll, done)
    for i, (text, attr) in enumerate(rows):
        _put(stdscr, 1 + i, 2, text, w - 4, attr)

    _put(stdscr, h - 1, max(1, (w - tui.display_width(footer) - 2) // 2), f" {footer} ",
         min(tui.display_width(footer) + 2, w - 2), curses.A_DIM | tui.normal_attr())
    stdscr.refresh()
    return max_scroll


def _prepare_screen(stdscr):
    """
    Matikan optimasi geser-baris ncurses (insert/delete line & karakter). Layar progress
    berubah isi tiap frame; kalau ncurses "menghemat" dengan menggeser baris, sebagian
    terminal (terutama emulator ringan) salah menggambar -- baris jadi dobel/hilang.
    Gambar ulang penuh per baris lebih aman, dan tetap ringan buat layar sekecil ini.
    """
    for fn in ("idlok", "idcok"):
        try:
            getattr(stdscr, fn)(False)
        except (curses.error, AttributeError):
            pass
    try:
        stdscr.clear()
    except curses.error:
        pass


def _read_key_nowait(stdscr):
    try:
        return stdscr.get_wch()
    except curses.error:
        return None


def run_download_screen(stdscr, heading, fn):
    """
    Jalankan fn() (proses download) di thread terpisah sambil menampilkan layar
    progress TUI. Return dict ringkasan dari fn kalau ada, atau None.
    """
    from src import download_core
    from src.errors import explain_error

    reporter = TuiDownloadReporter()
    result = {}

    def worker():
        try:
            result["value"] = fn()
        except download_core.DownloadAborted:
            result["aborted"] = True
        except BaseException as e:   # noqa: BLE001 -- apa pun error-nya, tampilkan di layar, jangan crash
            result["error"] = e

    download_core.reset_cancel()
    _prepare_screen(stdscr)
    tui._safe_curs_set(0)
    stdscr.timeout(int(_FRAME_SECONDS * 1000))
    frame = 0
    esc_deadline = 0.0
    cancelled = False

    with use_reporter(reporter):
        t = threading.Thread(target=worker, name="download-tui", daemon=True)
        t.start()
        while t.is_alive():
            if cancelled:
                footer = "Membatalkan... tunggu sebentar"
            elif time.time() < esc_deadline:
                footer = "Tekan Esc sekali lagi untuk MEMBATALKAN"
            else:
                footer = "Esc 2x / Ctrl+C = batalkan"
            try:
                _draw_download(stdscr, heading, reporter.snapshot(), frame, footer, 0, False)
                key = _read_key_nowait(stdscr)
                if key in tui._ESC_KEYS or key in tui._QUIT_KEYS:
                    if time.time() < esc_deadline:
                        cancelled = True
                        download_core.request_cancel()
                    else:
                        esc_deadline = time.time() + _ESC_CONFIRM_SECONDS
            except KeyboardInterrupt:
                cancelled = True
                download_core.request_cancel()
            frame += 1
        t.join()

    err = result.get("error")
    error_text = None
    if err is not None and not isinstance(err, KeyboardInterrupt):
        cookies_used = False
        try:
            from src.config import load_config
            cookies_used = bool(load_config().get("cookies_file"))
        except Exception:
            pass
        error_text = f"❌ Gagal: {explain_error(err, cookies_used=cookies_used)}"
    reporter.finalize(cancelled or result.get("aborted", False), error_text)

    # Layar akhir: tetap tampil sampai user menekan Enter/Esc. Pesan bisa digulir.
    stdscr.timeout(-1)
    _prepare_screen(stdscr)   # isi layar berubah total -> gambar ulang penuh sekali
    snap = reporter.snapshot()
    scroll = 10 ** 9   # mulai dari pesan paling bawah (paling baru)
    footer = "↑↓ gulir pesan   Enter/Esc kembali ke menu"
    while True:
        max_scroll = _draw_download(stdscr, heading, snap, 0, footer, scroll, True)
        scroll = min(scroll, max_scroll)
        try:
            key = tui._read_key(stdscr)
        except KeyboardInterrupt:
            break
        if key in tui._ENTER_KEYS or key in tui._ESC_KEYS or key in tui._QUIT_KEYS:
            break
        if key in tui._UP_KEYS:
            scroll = max(0, scroll - 1)
        elif key in tui._DOWN_KEYS:
            scroll = min(max_scroll, scroll + 1)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - 10)
        elif key == curses.KEY_NPAGE:
            scroll = min(max_scroll, scroll + 10)
    return result.get("value")


# ---------- proses singkat (spinner) ----------

class _BusyReporter(Reporter):
    def __init__(self, text):
        self._lock = threading.Lock()
        self.base = text
        self.stack = []
        self.messages = []

    def message(self, text):
        text = str(text).strip("\n")
        if text.strip():
            with self._lock:
                self.messages.append(text)

    @contextlib.contextmanager
    def _cm(self, text):
        with self._lock:
            self.stack.append(str(text).strip())
        try:
            yield
        finally:
            with self._lock:
                if self.stack:
                    self.stack.pop()

    def status(self, text):
        return self._cm(text)

    def snapshot(self):
        with self._lock:
            # Status paling LUAR yang ditampilkan (mis. "Memeriksa URL 2/5: ..."), bukan
            # status bawaan fungsi di dalamnya yang lebih umum.
            return (self.stack[0] if self.stack else self.base), list(self.messages)


def _draw_busy(stdscr, heading, text, messages, frame):
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    try:
        stdscr.bkgd(" ", tui.normal_attr())
    except curses.error:
        pass
    inner_max = max(20, w - 8)
    lines = [f"{_SPINNER[frame % len(_SPINNER)]} {text}"]
    if messages:
        lines.append("")
        lines.extend(tui._wrap_lines(messages[-200:], inner_max))
    max_lines = max(1, h - 6)
    if len(lines) > max_lines:
        lines = [lines[0], "…"] + lines[-(max_lines - 2):]
    box_w = min(max(tui.display_width(l) for l in lines) + 6, w - 2)
    box_w = max(box_w, tui.display_width(heading) + 6, 30)
    box_h = min(len(lines) + 4, h - 2)
    stdscr.refresh()
    win = tui._new_box(stdscr, box_h, box_w, heading)
    for i, line in enumerate(lines[:box_h - 4]):
        attr = tui.normal_attr()
        s = line.lstrip()
        if s.startswith("❌"):
            attr = tui.accent_attr("err")
        elif s.startswith("⚠"):
            attr = tui.accent_attr("warn")
        elif s.startswith("💡"):
            attr = tui.accent_attr("accent")
        try:
            win.addstr(2 + i, 2, tui._truncate_display(line, box_w - 4), attr)
        except curses.error:
            pass
    win.refresh()


def run_busy(stdscr, heading, fn, text="Memproses..."):
    """
    Jalankan fn() di thread terpisah sambil menampilkan kotak spinner.
    Return (hasil, pesan) -- `pesan` = semua report().message() selama proses.
    Exception dari fn dilempar ulang ke pemanggil (setelah kotaknya ditutup).
    Ctrl+C selama proses -> KeyboardInterrupt dilempar setelah fn selesai.
    """
    reporter = _BusyReporter(text)
    result = {}

    def worker():
        try:
            result["value"] = fn()
        except BaseException as e:   # noqa: BLE001
            result["error"] = e

    tui._safe_curs_set(0)
    stdscr.timeout(int(_FRAME_SECONDS * 1000))
    frame = 0
    interrupted = False
    with use_reporter(reporter):
        t = threading.Thread(target=worker, name="busy-tui", daemon=True)
        t.start()
        while t.is_alive():
            try:
                cur, msgs = reporter.snapshot()
                if interrupted:
                    cur = "Membatalkan setelah langkah ini selesai..."
                _draw_busy(stdscr, heading, cur, msgs, frame)
                _read_key_nowait(stdscr)
            except KeyboardInterrupt:
                interrupted = True
            frame += 1
        t.join()
    stdscr.timeout(-1)

    _, messages = reporter.snapshot()
    if interrupted:
        raise KeyboardInterrupt
    if "error" in result:
        raise result["error"]
    return result.get("value"), messages
