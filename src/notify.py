import contextlib
import shutil
import subprocess
import threading


def is_termux_notify_available():
    return shutil.which("termux-notification") is not None


def notify(title, content):
    """
    Kirim notifikasi Android lewat Termux:API (termux-notification).
    Aman dipanggil di sistem manapun -- kalau perintahnya nggak ada, cuma di-skip diam-diam.
    Butuh paket 'termux-api' terpasang (pkg install termux-api) + app Termux:API dari F-Droid/Play Store.
    """
    if not is_termux_notify_available():
        return False
    try:
        subprocess.run(
            ["termux-notification", "--title", title, "--content", content],
            check=False,
            timeout=5,
            capture_output=True,
        )
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def _wakelock_available():
    return shutil.which("termux-wake-lock") is not None and shutil.which("termux-wake-unlock") is not None


# Melindungi _wakelock_refcount dari race condition pas mode download paralel --
# beberapa thread bisa masuk/keluar wake_lock() hampir bersamaan.
_wakelock_state_lock = threading.Lock()
_wakelock_refcount = 0


@contextlib.contextmanager
def wake_lock():
    """
    Cegah HP tidur (layar mati -> proses ke-suspend Android) selama proses di
    dalam blok ini jalan. Aman dipanggil di sistem manapun -- kalau
    termux-wake-lock nggak ada, cuma di-skip diam-diam tanpa error.
    Butuh paket 'termux-api' terpasang (pkg install termux-api).

    Thread-safe & reentrant lewat reference counter: kalau dipanggil dari
    beberapa thread sekaligus (mode download paralel), wake-lock cuma
    BENAR-BENAR di-acquire sekali (pas pemanggil pertama masuk) dan cuma
    dilepas pas pemanggil TERAKHIR keluar. Sebelumnya tiap thread lock/unlock
    sendiri-sendiri, jadi thread yang selesai duluan bisa nge-unlock HP
    padahal thread lain masih download.

        with notify.wake_lock():
            ...proses lama (download) di sini...
    """
    global _wakelock_refcount

    acquired_here = False
    if _wakelock_available():
        with _wakelock_state_lock:
            if _wakelock_refcount == 0:
                try:
                    subprocess.run(["termux-wake-lock"], check=False, timeout=5, capture_output=True)
                    _wakelock_refcount = 1
                    acquired_here = True
                except (subprocess.SubprocessError, OSError):
                    pass  # gagal acquire -- jangan dihitung sebagai pemegang lock
            else:
                _wakelock_refcount += 1
                acquired_here = True

    try:
        yield
    finally:
        if acquired_here:
            with _wakelock_state_lock:
                _wakelock_refcount = max(0, _wakelock_refcount - 1)
                release_now = _wakelock_refcount == 0
            if release_now:
                try:
                    subprocess.run(["termux-wake-unlock"], check=False, timeout=5, capture_output=True)
                except (subprocess.SubprocessError, OSError):
                    pass