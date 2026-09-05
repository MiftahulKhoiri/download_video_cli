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

os.environ.setdefault("ESCDELAY", "25")  # biar Esc nggak kerasa lag (default ncurses ~1 detik)

ESC = 27


def _safe_curs_set(visibility):
    try:
        curses.curs_set(visibility)
    except curses.error:
        pass  # sebagian terminal nggak dukung ubah visibilitas kursor -- aman diabaikan


def _center_title(win, title, width):
    if not title:
        return
    text = f" {title} "
    x = max(1, (width - len(text)) // 2)
    try:
        win.addstr(0, x, text[:max(0, width - x - 1)], curses.A_BOLD)
    except curses.error:
        pass  # nulis persis di sudut kanan-bawah kadang error di ncurses, aman diabaikan


def _new_box(stdscr, height, width, title=None):
    h, w = stdscr.getmaxyx()
    height = min(height, max(h - 2, 3))
    width = min(width, max(w - 2, 10))
    y0 = max(0, (h - height) // 2)
    x0 = max(0, (w - width) // 2)
    win = curses.newwin(height, width, y0, x0)
    win.keypad(True)
    win.box()
    _center_title(win, title, width)
    return win


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


def menu(stdscr, title, items, selected=0, message=None):
    """
    Menu box gaya raspi-config: judul di border atas, pesan info opsional
    di atas daftar, item ter-highlight (reverse video) pas dinavigasi.

    items: list[str]
    message: None, str, atau list[str] -- ditampilkan di atas daftar item
    Return: index item yang dipilih (int), atau None kalau dibatalkan (Esc/q).
    """
    if not items:
        return None
    selected = max(0, min(selected, len(items) - 1))

    msg_lines = []
    if message:
        msg_lines = message if isinstance(message, list) else [message]

    h, w = stdscr.getmaxyx()
    content_w = max([len(i) for i in items] + [len(m) for m in msg_lines] + [len(title or "")])
    box_w = min(content_w + 6, w - 2)
    box_w = max(box_w, 24)
    footer = "↑↓ pilih  Enter pilih  Esc kembali"
    box_w = max(box_w, min(len(footer) + 4, w - 2))

    max_visible = max(1, (h - 2) - 4 - len(msg_lines))
    visible = min(len(items), max_visible)
    box_h = min(visible + 4 + len(msg_lines), h - 2)

    scroll = 0
    _safe_curs_set(0)
    stdscr.erase()
    stdscr.refresh()

    while True:
        win = _new_box(stdscr, box_h, box_w, title)
        inner_w = box_w - 4

        for i, line in enumerate(msg_lines):
            try:
                win.addstr(2 + i, 2, line[:inner_w])
            except curses.error:
                pass

        list_top = 2 + len(msg_lines)

        if selected < scroll:
            scroll = selected
        elif selected >= scroll + visible:
            scroll = selected - visible + 1

        for row in range(visible):
            idx = scroll + row
            if idx >= len(items):
                break
            attr = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            text = items[idx][:inner_w].ljust(inner_w)
            try:
                win.addstr(list_top + row, 2, text, attr)
            except curses.error:
                pass

        try:
            win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
        except curses.error:
            pass

        win.refresh()
        key = win.getch()

        if key in (curses.KEY_UP, ord("k")):
            selected = (selected - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord("j")):
            selected = (selected + 1) % len(items)
        elif key in (curses.KEY_ENTER, 10, 13):
            _safe_curs_set(0)
            return selected
        elif key in (ESC, ord("q")):
            _safe_curs_set(0)
            return None
        elif key == curses.KEY_RESIZE:
            h, w = stdscr.getmaxyx()


def input_box(stdscr, title, prompt, initial=""):
    """
    Kotak input teks satu baris. Enter konfirmasi & kembalikan isinya (str),
    Esc batal & kembalikan None. Panah kiri/kanan geser kursor, Backspace/Delete hapus.
    """
    h, w = stdscr.getmaxyx()
    prompt_lines = textwrap.wrap(prompt, max(20, w - 8)) or [prompt]
    box_w = min(max(max((len(l) for l in prompt_lines), default=20), len(title or "")) + 6, w - 2)
    box_w = max(box_w, 30)
    box_h = min(len(prompt_lines) + 6, h - 2)

    text = list(initial)
    cursor = len(text)
    _safe_curs_set(1)
    stdscr.erase()
    stdscr.refresh()

    while True:
        win = _new_box(stdscr, box_h, box_w, title)
        inner_w = box_w - 4

        for i, line in enumerate(prompt_lines):
            try:
                win.addstr(2 + i, 2, line[:inner_w], curses.A_DIM)
            except curses.error:
                pass

        field_row = 2 + len(prompt_lines)
        display = "".join(text)
        if len(display) >= inner_w:
            start = max(0, cursor - inner_w + 1)
        else:
            start = 0
        shown = display[start:start + inner_w]
        try:
            win.addstr(field_row, 2, shown.ljust(inner_w), curses.A_UNDERLINE)
        except curses.error:
            pass

        footer = "Enter simpan  Esc batal"
        try:
            win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
        except curses.error:
            pass

        win.move(field_row, 2 + (cursor - start))
        win.refresh()
        key = win.getch()

        if key in (curses.KEY_ENTER, 10, 13):
            _safe_curs_set(0)
            return "".join(text)
        elif key == ESC:
            _safe_curs_set(0)
            return None
        elif key in (curses.KEY_BACKSPACE, 127, 8):
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
            h, w = stdscr.getmaxyx()
        elif 32 <= key <= 126:
            text.insert(cursor, chr(key))
            cursor += 1


def message_box(stdscr, title, message):
    """Tampilkan pesan, tunggu sembarang tombol ditekan buat lanjut."""
    h, w = stdscr.getmaxyx()
    lines = message if isinstance(message, list) else [message]
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, max(20, w - 8)) or [""])

    box_w = min(max((len(l) for l in wrapped), default=20) + 6, w - 2)
    box_w = max(box_w, len(title or "") + 6, 24)
    box_h = min(len(wrapped) + 4, h - 2)

    stdscr.erase()
    stdscr.refresh()
    win = _new_box(stdscr, box_h, box_w, title)
    inner_w = box_w - 4
    for i, line in enumerate(wrapped):
        try:
            win.addstr(2 + i, 2, line[:inner_w])
        except curses.error:
            pass
    footer = "Tekan tombol apa saja..."
    try:
        win.addstr(box_h - 1, max(1, (box_w - len(footer)) // 2), footer[:box_w - 2], curses.A_DIM)
    except curses.error:
        pass
    win.refresh()
    win.getch()


def loading_box(stdscr, title, message):
    """Tampilkan pesan tanpa nunggu tombol -- buat kasih tau proses lagi jalan (mis. request jaringan)."""
    h, w = stdscr.getmaxyx()
    lines = message if isinstance(message, list) else [message]
    box_w = min(max((len(l) for l in lines), default=20) + 6, w - 2)
    box_w = max(box_w, len(title or "") + 6, 24)
    box_h = min(len(lines) + 4, h - 2)

    stdscr.erase()
    stdscr.refresh()
    win = _new_box(stdscr, box_h, box_w, title)
    inner_w = box_w - 4
    for i, line in enumerate(lines):
        try:
            win.addstr(2 + i, 2, line[:inner_w])
        except curses.error:
            pass
    win.refresh()
    return win