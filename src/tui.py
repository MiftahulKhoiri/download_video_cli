# src/tui.py
"""
Widget TUI ala raspi-config/whiptail, dibangun pakai curses (bawaan Python,
nggak perlu install apa-apa tambahan). Semua fungsi di sini menerima stdscr
(atau parent screen) dan dipanggil dari dalam curses.wrapper().

Navigasi standar: ↑/↓ (atau k/j) pindah, Enter pilih/konfirmasi, Esc/q batal.
"""
import contextlib
import curses
import os
import textwrap
import unicodedata

os.environ.setdefault("ESCDELAY", "25")  # biar Esc nggak kerasa lag (default ncurses ~1 detik)

ESC = 27

PAIR_NORMAL = 1    # warna tulisan di atas warna latar -- dasar kotak & background
PAIR_SELECT = 2    # dibalik dari PAIR_NORMAL -- item yang lagi disorot
PAIR_TITLE = 3     # sama kayak PAIR_NORMAL, dipakai buat judul kotak (dicetak tebal)

# Nama warna (Indonesia) yang bisa dipilih user buat latar & tulisan lewat
# menu Pengaturan -- dibatasi ke 8 warna standar terminal biar aman di semua
# perangkat (termasuk Termux), nggak butuh dukungan warna 256/truecolor.
COLOR_NAME_MAP = {
    "hitam": curses.COLOR_BLACK,
    "merah": curses.COLOR_RED,
    "hijau": curses.COLOR_GREEN,
    "kuning": curses.COLOR_YELLOW,
    "biru": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "putih": curses.COLOR_WHITE,
}
COLOR_NAMES = list(COLOR_NAME_MAP.keys())  # urutan tampil di menu pilih warna

# Tombol navigasi -- dicek dengan `key in (...)`, jadi campuran kode tombol khusus
# (int, dari curses.KEY_*/get_wch) dan karakter biasa (str, dari get_wch) di tuple
# yang sama itu aman: Python cuma membandingkan tiap elemen apa adanya.
_UP_KEYS = (curses.KEY_UP, "k", "K")
_DOWN_KEYS = (curses.KEY_DOWN, "j", "J")
_ENTER_KEYS = (curses.KEY_ENTER, 10, 13, "\n", "\r")
_ESC_KEYS = (ESC, "\x1b")
_QUIT_KEYS = ("q", "Q")
_BACKSPACE_KEYS = (curses.KEY_BACKSPACE, 127, 8, "\x7f", "\x08")

_color_ready = None  # None = belum diinisialisasi, True/False setelah init_theme() dipanggil
_current_bg = "putih"
_current_text = "hitam"


# ---------- Lebar tampilan (display width) ----------
# len(teks) menghitung jumlah CODEPOINT, bukan lebar tampilnya di terminal --
# karakter CJK (Cina/Jepang/Korea, umum di judul video Asia) tampil selebar 2
# kolom, sedangkan emoji (umum juga di judul video) macam-macam: kebanyakan 2
# kolom di terminal modern. Tanpa ini, perataan kotak/list bisa geser atau
# bagian ujung teks (misal tag "[720p]") kepotong lebih cepat dari perkiraan.
_WIDE_EA_CATEGORIES = ("W", "F")  # East Asian Width: Wide, Fullwidth
_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),  # simbol & piktograf, emoticon, transport, tambahan
    (0x2600, 0x27BF),    # simbol lain-lain & dingbat (☀☂✂️ dll)
    (0x1F1E6, 0x1F1FF),  # regional indicator (bendera, 2 kode per bendera)
    (0x2B00, 0x2BFF),    # panah & simbol tambahan (⭐⬆️ dll)
)


def _char_width(ch):
    cp = ord(ch)
    if cp == 0:
        return 0
    if unicodedata.combining(ch):  # aksen/diakritik yang nempel ke karakter sebelumnya
        return 0
    if unicodedata.east_asian_width(ch) in _WIDE_EA_CATEGORIES:
        return 2
    for lo, hi in _EMOJI_RANGES:
        if lo <= cp <= hi:
            return 2
    return 1


def display_width(text):
    """Lebar tampil suatu teks di terminal (kolom), bukan jumlah karakternya."""
    return sum(_char_width(c) for c in text)


def _pad_display(text, width):
    """ljust() versi sadar lebar-tampil -- padding spasi dihitung dari display_width, bukan len()."""
    pad = width - display_width(text)
    return text if pad <= 0 else text + (" " * pad)


def _truncate_display(text, width):
    """Potong teks dari KANAN sampai muat di `width` kolom tampilan (nggak pernah motong di tengah karakter lebar)."""
    if display_width(text) <= width:
        return text
    out, w = [], 0
    for ch in text:
        cw = _char_width(ch)
        if w + cw > width:
            break
        out.append(ch)
        w += cw
    return "".join(out)


def _fit_display(text, width, keep_suffix=16):
    """
    Paksa `text` jadi PERSIS `width` kolom tampilan: dipotong kalau kepanjangan
    (pakai "…" di TENGAH, bukan di ujung -- ekor teks macam ' [720p]' atau
    ' [a1b2c3d4]' sering menyimpan info penting, jadi diusahakan tetap kelihatan),
    dipadding spasi kalau kependekan.
    """
    if display_width(text) <= width:
        return _pad_display(text, width)
    if width <= 1:
        return _truncate_display(text, max(0, width))

    budget = min(keep_suffix, width - 1)
    suffix_chars, w = [], 0
    for ch in reversed(text):
        cw = _char_width(ch)
        if w + cw > budget:
            break
        suffix_chars.append(ch)
        w += cw
    suffix = "".join(reversed(suffix_chars))

    prefix_width = width - w - 1  # -1 buat karakter "…"
    prefix_src = text[:len(text) - len(suffix)]
    prefix = _truncate_display(prefix_src, max(0, prefix_width))
    result = prefix + "…" + suffix
    return _pad_display(result, width)


def _wrap_lines(lines, width):
    """textwrap.wrap tiap baris (berbasis JUMLAH KARAKTER -- cukup akurat buat teks
    Latin/Indonesia; CJK panjang bisa wrap sedikit lebih lebar dari kolom yang tersedia,
    kasus langka untuk pesan/prompt aplikasi ini)."""
    out = []
    for line in lines:
        out.extend(textwrap.wrap(line, max(10, width)) or [""])
    return out


def _read_key(win):
    """
    Baca satu input: get_wch() (bukan getch()) biar karakter Unicode non-ASCII
    (huruf beraksen, dll -- bukan cuma huruf A-Z biasa) bisa diketik langsung di
    kotak input, nggak cuma diam-diam ditolak. Return int buat tombol khusus
    (panah, Enter di sebagian terminal, dll) atau str 1-karakter buat karakter biasa.
    """
    try:
        return win.get_wch()
    except curses.error:
        return -1  # gangguan sesaat (mis. sinyal resize) -- diperlakukan sebagai "nggak ada tombol"


# ---------- Warna & tema ----------

def _apply_colors(stdscr, bg_name, text_name):
    """Set ulang isi pasangan warna curses sesuai bg_name/text_name yang dipilih."""
    global _current_bg, _current_text
    try:
        if not curses.has_colors():
            return False
        curses.start_color()
        curses.use_default_colors()
        bg = COLOR_NAME_MAP.get(bg_name, curses.COLOR_WHITE)
        fg = COLOR_NAME_MAP.get(text_name, curses.COLOR_BLACK)
        curses.init_pair(PAIR_NORMAL, fg, bg)
        curses.init_pair(PAIR_SELECT, bg, fg)  # dibalik dari NORMAL -- otomatis selalu kontras
        curses.init_pair(PAIR_TITLE, fg, bg)
        _current_bg, _current_text = bg_name, text_name
    except curses.error:
        return False

    try:
        stdscr.bkgd(" ", curses.color_pair(PAIR_NORMAL))
    except curses.error:
        pass
    return True


def init_theme(stdscr, bg_name="putih", text_name="hitam"):
    """
    Aktifkan tema warna sesuai pengaturan (default: latar putih, tulisan
    hitam). Dipanggil SEKALI pas sesi curses dimulai. Aman kalau terminal
    nggak dukung warna -- otomatis fallback ke tampilan monokrom
    (reverse-video) yang sudah ada, nggak pernah error.
    """
    global _color_ready
    _color_ready = _apply_colors(stdscr, bg_name, text_name)
    return _color_ready


def apply_theme(stdscr, bg_name, text_name):
    """
    Ganti tema warna di tengah sesi yang lagi jalan -- dipanggil dari menu
    Pengaturan begitu user pilih warna baru, jadi kepakai LANGSUNG tanpa
    perlu restart aplikasi.
    """
    global _color_ready
    ok = _apply_colors(stdscr, bg_name, text_name)
    _color_ready = ok
    if ok:
        try:
            stdscr.clear()
            stdscr.refresh()
        except curses.error:
            pass
    return ok


def _normal_attr():
    return curses.color_pair(PAIR_NORMAL) if _color_ready else curses.A_NORMAL


def _select_attr():
    return curses.color_pair(PAIR_SELECT) | curses.A_BOLD if _color_ready else curses.A_REVERSE


def _title_attr():
    return curses.color_pair(PAIR_TITLE) | curses.A_BOLD if _color_ready else curses.A_BOLD


def _safe_curs_set(visibility):
    try:
        curses.curs_set(visibility)
    except curses.error:
        pass  # sebagian terminal nggak dukung ubah visibilitas kursor -- aman diabaikan


def _center_title(win, title, width):
    if not title:
        return
    text = f" {title} "
    x = max(1, (width - display_width(text)) // 2)
    try:
        win.addstr(0, x, _truncate_display(text, max(0, width - x - 1)), _title_attr())
    except curses.error:
        pass  # nulis persis di sudut kanan-bawah kadang error di ncurses, aman diabaikan


def _new_box_at(stdscr, height, width, y0, x0, title=None):
    """Bikin box curses di posisi y0,x0 spesifik (dipangkas biar muat di layar SAAT INI)."""
    h, w = stdscr.getmaxyx()
    height = min(height, max(h - 2, 3))
    width = min(width, max(w - 2, 10))
    y0 = max(0, min(y0, max(0, h - height)))
    x0 = max(0, min(x0, max(0, w - width)))
    win = curses.newwin(height, width, y0, x0)
    win.keypad(True)
    if _color_ready:
        try:
            win.bkgd(" ", _normal_attr())
        except curses.error:
            pass
    win.box()
    _center_title(win, title, width)
    return win


def _new_box(stdscr, height, width, title=None):
    """Box di tengah layar SAAT INI -- dipakai fungsi yang nggak butuh banner di atasnya."""
    h, w = stdscr.getmaxyx()
    height = min(height, max(h - 2, 3))
    width = min(width, max(w - 2, 10))
    y0 = max(0, (h - height) // 2)
    x0 = max(0, (w - width) // 2)
    return _new_box_at(stdscr, height, width, y0, x0, title)


@contextlib.contextmanager
def suspend(stdscr):
    """
    Keluar sementara dari mode curses -- buat jalanin kode yang nyetak ke layar
    biasa (progress bar download, spinner, dll yang sudah ada & teruji), lalu
    otomatis balik ke mode curses & gambar ulang layar pas selesai.

        with tui.suspend(stdscr):
            print("proses non-curses di sini...")
            input("Tekan Enter...")
    """
    curses.endwin()
    try:
        yield
    finally:
        stdscr.touchwin()
        stdscr.refresh()


def menu(stdscr, title, items, selected=0, message=None, banner=None):
    """
    Menu box gaya raspi-config: judul di border atas, pesan info opsional
    di atas daftar (di DALAM kotak), item ter-highlight (reverse video) pas
    dinavigasi.

    items: list[str]
    message: None, str, atau list[str] -- ditampilkan di DALAM kotak, di atas daftar item
    banner: None, str, atau list[str] -- ditampilkan di LUAR kotak, di atasnya (mis. judul/branding app)
    Return: index item yang dipilih (int), atau None kalau dibatalkan (Esc/q).

    Layout (ukuran & posisi box, wrap banner, jumlah baris kelihatan) dihitung ULANG
    tiap frame dari ukuran terminal SAAT ITU -- jadi kalau terminal di-resize di
    tengah jalan (mis. keyboard Termux muncul/hilang, nyusutin tinggi layar), menu
    langsung menyesuaikan, bukan nyangkut pakai ukuran lama yang sudah nggak muat.
    """
    if not items:
        return None
    selected = max(0, min(selected, len(items) - 1))
    msg_lines_raw = (message if isinstance(message, list) else [message]) if message else []
    raw_banner = (banner if isinstance(banner, list) else [banner]) if banner else []

    footer = "↑↓ pilih  Enter pilih  Esc kembali"
    scroll = 0
    _safe_curs_set(0)

    while True:
        h, w = stdscr.getmaxyx()

        banner_lines = _wrap_lines(raw_banner, max(20, w - 4)) if raw_banner else []
        msg_lines = _wrap_lines(msg_lines_raw, max(20, w - 8)) if msg_lines_raw else []

        content_w = max([display_width(i) for i in items]
                         + [display_width(m) for m in msg_lines]
                         + [display_width(title or "")] + [0])
        box_w = max(min(content_w + 6, w - 2), 24)
        box_w = max(box_w, min(len(footer) + 4, w - 2))

        banner_block_h = (len(banner_lines) + 1) if banner_lines else 0
        max_visible = max(1, (h - 2) - 4 - len(msg_lines) - banner_block_h)
        visible = min(len(items), max_visible)
        box_h = min(visible + 4 + len(msg_lines), max(3, h - 2 - banner_block_h))

        total_h = banner_block_h + box_h
        top = max(0, (h - total_h) // 2)
        box_y0 = top + banner_block_h
        box_x0 = max(0, (w - box_w) // 2)

        stdscr.erase()
        if _color_ready:
            try:
                stdscr.bkgd(" ", _normal_attr())
            except curses.error:
                pass
        for i, line in enumerate(banner_lines):
            x = max(0, (w - display_width(line)) // 2)
            try:
                stdscr.addstr(top + i, x, _truncate_display(line, max(0, w - x - 1)), _title_attr())
            except curses.error:
                pass
        stdscr.refresh()

        win = _new_box_at(stdscr, box_h, box_w, box_y0, box_x0, title)
        inner_w = box_w - 4

        for i, line in enumerate(msg_lines):
            try:
                win.addstr(2 + i, 2, _truncate_display(line, inner_w))
            except curses.error:
                pass

        list_top = 2 + len(msg_lines)

        if selected < scroll:
            scroll = selected
        elif selected >= scroll + visible:
            scroll = selected - visible + 1
        scroll = max(0, min(scroll, max(0, len(items) - visible)))

        for row in range(visible):
            idx = scroll + row
            if idx >= len(items):
                break
            attr = _select_attr() if idx == selected else _normal_attr()
            text = _fit_display(items[idx], inner_w)
            try:
                win.addstr(list_top + row, 2, text, attr)
            except curses.error:
                pass

        try:
            win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
        except curses.error:
            pass

        win.refresh()
        key = _read_key(win)

        if key in _UP_KEYS:
            selected = (selected - 1) % len(items)
        elif key in _DOWN_KEYS:
            selected = (selected + 1) % len(items)
        elif key in _ENTER_KEYS:
            _safe_curs_set(0)
            return selected
        elif key in _ESC_KEYS or key in _QUIT_KEYS:
            _safe_curs_set(0)
            return None
        # curses.KEY_RESIZE dan input lain (termasuk -1 dari gangguan get_wch) cuma
        # bikin loop ini ulang -- layout dihitung ulang otomatis dari h, w yang baru.


def input_box(stdscr, title, prompt, initial=""):
    """
    Kotak input teks satu baris. Enter konfirmasi & kembalikan isinya (str),
    Esc batal & kembalikan None. Panah kiri/kanan geser kursor, Backspace/Delete
    hapus. Menerima karakter Unicode apa saja (bukan cuma ASCII) lewat get_wch().

    prompt: str atau list[str] -- kalau list, tiap elemen jadi baris terpisah
    (dibungkus/wrap masing-masing), berguna buat nunjukin konteks/riwayat
    di atas kotak input (mis. daftar URL yang udah dimasukkan sebelumnya).
    Kalau daftarnya kepanjangan buat muat di layar, baris paling lama
    dipotong dan diganti "..." di awal -- field input selalu dijamin kelihatan.

    Layout dihitung ulang tiap frame (lihat menu()) biar tahan resize terminal.
    """
    raw_lines = prompt if isinstance(prompt, list) else [prompt]

    text = list(initial)
    cursor = len(text)
    _safe_curs_set(1)

    while True:
        h, w = stdscr.getmaxyx()

        all_prompt_lines = _wrap_lines(raw_lines, max(20, w - 8)) or [""]
        max_prompt_lines = max(1, h - 6)  # sisa ruang wajib buat border+field+footer
        if len(all_prompt_lines) > max_prompt_lines:
            keep = max(1, max_prompt_lines - 1)
            prompt_lines = ["..."] + all_prompt_lines[-keep:]
        else:
            prompt_lines = all_prompt_lines

        content_w = max([display_width(l) for l in prompt_lines] + [display_width(title or "")])
        box_w = min(content_w + 6, w - 2)
        box_w = max(box_w, 30)
        box_h = min(len(prompt_lines) + 6, h - 2)

        stdscr.erase()
        stdscr.refresh()
        win = _new_box(stdscr, box_h, box_w, title)
        inner_w = box_w - 4

        for i, line in enumerate(prompt_lines):
            try:
                win.addstr(2 + i, 2, _truncate_display(line, inner_w), curses.A_DIM)
            except curses.error:
                pass

        field_row = min(2 + len(prompt_lines), box_h - 3)
        display = "".join(text)
        cursor_w = display_width(display[:cursor])
        if display_width(display) >= inner_w:
            # Geser jendela tampilan field biar kursor selalu kelihatan (dari kanan, karakter demi karakter).
            start = 0
            while cursor - start > 0 and display_width(display[start:cursor]) > inner_w - 1:
                start += 1
        else:
            start = 0
        shown = _truncate_display(display[start:], inner_w)
        try:
            win.addstr(field_row, 2, _pad_display(shown, inner_w), curses.A_UNDERLINE)
        except curses.error:
            pass

        footer = "Enter simpan  Esc batal"
        try:
            win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
        except curses.error:
            pass

        try:
            win.move(field_row, 2 + display_width(display[start:cursor]))
        except curses.error:
            pass
        win.refresh()
        key = _read_key(win)

        if key in _ENTER_KEYS:
            _safe_curs_set(0)
            return "".join(text)
        elif key in _ESC_KEYS:
            _safe_curs_set(0)
            return None
        elif key in _BACKSPACE_KEYS:
            if cursor > 0:
                del text[cursor - 1]
                cursor -= 1
        elif key == curses.KEY_DC:
            if cursor < len(text):
                del text[cursor]
        elif key == curses.KEY_LEFT:
            cursor = max(0, cursor - 1)
        elif key == curses.KEY_RIGHT:
            cursor = min(len(text), cursor + 1)
        elif key == curses.KEY_HOME:
            cursor = 0
        elif key == curses.KEY_END:
            cursor = len(text)
        elif key == curses.KEY_RESIZE:
            pass  # layout dihitung ulang otomatis di iterasi berikutnya
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            text.insert(cursor, key)
            cursor += 1


def message_box(stdscr, title, message):
    """Tampilkan pesan, tunggu sembarang tombol ditekan buat lanjut."""
    h, w = stdscr.getmaxyx()
    lines = message if isinstance(message, list) else [message]
    wrapped = _wrap_lines(lines, max(20, w - 8))

    box_w = min(max([display_width(l) for l in wrapped] + [0]) + 6, w - 2)
    box_w = max(box_w, display_width(title or "") + 6, 24)
    box_h = min(len(wrapped) + 4, h - 2)

    stdscr.erase()
    stdscr.refresh()
    win = _new_box(stdscr, box_h, box_w, title)
    inner_w = box_w - 4
    for i, line in enumerate(wrapped):
        try:
            win.addstr(2 + i, 2, _truncate_display(line, inner_w))
        except curses.error:
            pass
    footer = "Tekan tombol apa saja..."
    try:
        win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
    except curses.error:
        pass
    win.refresh()
    _read_key(win)


def loading_box(stdscr, title, message):
    """Tampilkan pesan tanpa nunggu tombol -- buat kasih tau proses lagi jalan (mis. request jaringan)."""
    h, w = stdscr.getmaxyx()
    lines = message if isinstance(message, list) else [message]
    box_w = min(max([display_width(l) for l in lines] + [0]) + 6, w - 2)
    box_w = max(box_w, display_width(title or "") + 6, 24)
    box_h = min(len(lines) + 4, h - 2)

    stdscr.erase()
    stdscr.refresh()
    win = _new_box(stdscr, box_h, box_w, title)
    inner_w = box_w - 4
    for i, line in enumerate(lines):
        try:
            win.addstr(2 + i, 2, _truncate_display(line, inner_w))
        except curses.error:
            pass
    win.refresh()
    return win
