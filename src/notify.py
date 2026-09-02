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