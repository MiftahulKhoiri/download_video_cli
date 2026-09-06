import contextlib
import shutil
import subprocess


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


@contextlib.contextmanager
def wake_lock():
    """
    Cegah HP tidur (layar mati -> proses ke-suspend Android) selama proses di
    dalam blok ini jalan. Aman dipanggil di sistem manapun -- kalau
    termux-wake-lock nggak ada, cuma di-skip diam-diam tanpa error.
    Butuh paket 'termux-api' terpasang (pkg install termux-api).

        with notify.wake_lock():
            ...proses lama (download) di sini...
    """
    acquired = False
    if _wakelock_available():
        try:
            subprocess.run(["termux-wake-lock"], check=False, timeout=5, capture_output=True)
            acquired = True
        except (subprocess.SubprocessError, OSError):
            acquired = False
    try:
        yield
    finally:
        if acquired:
            try:
                subprocess.run(["termux-wake-unlock"], check=False, timeout=5, capture_output=True)
            except (subprocess.SubprocessError, OSError):
                pass