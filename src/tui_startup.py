# src/tui_startup.py
"""
Layar pembuka versi TUI (curses), pengganti intro/logo/"Tekan Enter" teks biasa:

  intro_tui(stdscr)        animasi "hujan digital" (sama kayak versi teks), tombol apa saja = lewati
  welcome_screen(stdscr)   logo + cek update yt-dlp (spinner) + pemberitahuan startup,
                           Enter = masuk menu, q/Esc = keluar
"""
import curses
import random
import threading
import time

from src import tui
from src.logo import _INTRO_BLOCK, _MATRIX_CHARS

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

_LOGO = [
    (" __   _____   ___          _", "accent"),
    (" \\ \\ / /_   ) |   \\ _ __  | |", "warn"),
    ("  \\ V / / /  | |) | '  \\ | |__", "ok"),
    ("   \\_/ /___| |___/|_|_|_||____|", "err"),
]
_TAGLINE = "🎬 YouTube / X Video & MP3 Downloader 🎵"


def _put_center(stdscr, y, text, attr=0):
    h, w = stdscr.getmaxyx()
    if not (0 <= y < h):
        return
    x = max(0, (w - tui.display_width(text)) // 2)
    try:
        stdscr.addstr(y, x, tui._truncate_display(text, max(0, w - x - 1)), attr or tui.normal_attr())
    except curses.error:
        pass


def _clear(stdscr):
    stdscr.erase()
    try:
        stdscr.bkgd(" ", tui.normal_attr())
    except curses.error:
        pass


def intro_tui(stdscr, duration=7.0, frame_delay=0.06, trail_len=5):
    """
    Animasi pembuka: tiap kolom punya "tetesan" karakter acak yang jatuh, makin lama
    makin banyak sel berhenti dan menampilkan logo asli. Tombol apa saja = lewati.
    """
    lines = _INTRO_BLOCK
    width = max(len(l) for l in lines)
    target = [l.ljust(width) for l in lines]
    height = len(target)
    revealed = [[target[r][c] == " " for c in range(width)] for r in range(height)]
    col_head = [random.randint(-height * 2, 0) for _ in range(width)]
    col_speed = [random.choice([1, 1, 2]) for _ in range(width)]

    tui._safe_curs_set(0)
    stdscr.timeout(int(frame_delay * 1000))
    rain = tui.accent_attr("ok")
    head_attr = curses.A_BOLD | tui.normal_attr()
    logo_attr = curses.A_BOLD | tui.title_attr()
    start = time.time()
    try:
        while True:
            elapsed = time.time() - start
            finished = elapsed >= duration
            if finished:
                for r in range(height):
                    for c in range(width):
                        revealed[r][c] = True
            else:
                reveal_prob = 0.01 + min(1.0, elapsed / duration) * 0.25
                for c in range(width):
                    col_head[c] += col_speed[c]
                    if col_head[c] - trail_len > height:
                        col_head[c] = random.randint(-height, 0)
                    for r in range(height):
                        if not revealed[r][c] and r <= col_head[c] and random.random() < reveal_prob:
                            revealed[r][c] = True

            h, w = stdscr.getmaxyx()
            _clear(stdscr)
            top = max(0, (h - height - 4) // 2)
            x0 = max(0, (w - width) // 2)
            _put_center(stdscr, top, "[SYSTEM] Terhubung ke server...", rain)
            for r in range(height):
                for c in range(width):
                    if c + x0 >= w - 1 or top + 2 + r >= h:
                        continue
                    if revealed[r][c]:
                        ch, attr = target[r][c], logo_attr
                    else:
                        head = col_head[c]
                        if head - trail_len <= r <= head:
                            ch = random.choice(_MATRIX_CHARS)
                            attr = head_attr if r == head else rain
                        else:
                            continue
                    try:
                        stdscr.addstr(top + 2 + r, x0 + c, ch, attr)
                    except curses.error:
                        pass
            _put_center(stdscr, min(h - 1, top + height + 3),
                        "✅ Koneksi stabil." if finished else "tekan tombol apa saja untuk lewati", curses.A_DIM)
            stdscr.refresh()
            if finished:
                time.sleep(0.6)
                break
            try:
                key = stdscr.get_wch()
            except curses.error:
                key = None
            if key is not None and key != curses.KEY_RESIZE:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stdscr.timeout(-1)


def _status_lines(update_state, ffmpeg_ok):
    """Baris info di bawah logo: hasil cek update yt-dlp & ffmpeg."""
    out = []
    st = update_state.get("result")
    if st is None:
        out.append((f"{_SPINNER[update_state.get('frame', 0) % len(_SPINNER)]} Memeriksa versi yt-dlp...",
                    tui.normal_attr()))
    else:
        installed, latest, outdated = st
        if installed is None:
            out.append(("× yt-dlp tidak terdeteksi -- jalankan: pip install yt-dlp", tui.accent_attr("err")))
        elif latest is None:
            out.append((f"· yt-dlp {installed} (nggak bisa cek versi terbaru -- offline?)", curses.A_DIM))
        elif outdated:
            out.append((f"! yt-dlp {installed} -- versi terbaru {latest} tersedia", tui.accent_attr("warn")))
            out.append(("  Update lewat Pengaturan > Cek & update yt-dlp (biar terhindar dari error 403)",
                        tui.accent_attr("warn")))
        else:
            out.append((f"√ yt-dlp {installed} (terbaru)", tui.accent_attr("ok")))
    if not ffmpeg_ok:
        out.append(("! ffmpeg tidak ditemukan -- merge video+audio & convert audio bakal gagal",
                    tui.accent_attr("warn")))
    return out


def welcome_screen(stdscr, notices=None):
    """
    Logo + cek update yt-dlp (di thread, dengan spinner) + pemberitahuan startup.
    Return True kalau user lanjut ke menu (Enter), False kalau keluar (q/Esc).
    """
    from src.updater import check_for_update
    from src.media_info import is_ffmpeg_available

    notices = [n for n in (notices or []) if str(n).strip()]
    state = {"result": None, "frame": 0}

    def _check():
        try:
            state["result"] = check_for_update(timeout=3)
        except Exception:
            state["result"] = (None, None, False)

    threading.Thread(target=_check, name="update-check", daemon=True).start()
    ffmpeg_ok = is_ffmpeg_available()

    tui._safe_curs_set(0)
    stdscr.timeout(100)
    try:
        while True:
            h, w = stdscr.getmaxyx()
            _clear(stdscr)
            body = [(text, tui.accent_attr(kind) | curses.A_BOLD) for text, kind in _LOGO]
            body += [("", 0), (_TAGLINE, tui.title_attr()), ("", 0)]
            body += _status_lines(state, ffmpeg_ok)
            if notices:
                body.append(("", 0))
                body.append(("Pemberitahuan:", curses.A_BOLD | tui.normal_attr()))
                for line in tui._wrap_lines(notices, max(20, w - 8)):
                    body.append((line, tui.accent_attr("warn")))
            body += [("", 0), ("Enter = masuk ke menu    q = keluar", curses.A_DIM | tui.normal_attr())]

            body = body[:max(1, h - 1)]
            top = max(0, (h - len(body)) // 2)
            logo_w = max(len(t) for t, _ in _LOGO)
            for i, (text, attr) in enumerate(body):
                if i < len(_LOGO):   # logo rata kiri sebagai satu blok, biar bentuknya nggak geser
                    x = max(0, (w - logo_w) // 2)
                    try:
                        stdscr.addstr(top + i, x, text[:max(0, w - x - 1)], attr)
                    except curses.error:
                        pass
                else:
                    _put_center(stdscr, top + i, text, attr)
            stdscr.refresh()

            try:
                key = stdscr.get_wch()
            except curses.error:
                key = None
            if key in tui._ENTER_KEYS:
                return True
            if key in tui._QUIT_KEYS or key in tui._ESC_KEYS:
                return False
            state["frame"] += 1
    finally:
        stdscr.timeout(-1)
