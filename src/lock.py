import os

from src.manager import ensure_download_folder

LOCK_FILE = os.path.join("download", ".lock")


def _is_pid_running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # proses ada tapi milik user lain -- anggap masih jalan
    except Exception:
        return True  # nggak bisa dipastikan -- aman lebih baik anggap masih jalan
    return True


def _read_lock_pid():
    try:
        with open(LOCK_FILE, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


class AppLock:
    """
    Cegah dua proses download_video_cli (mode menu & mode CLI, atau dua
    proses CLI/cron sekaligus) jalan bersamaan dan rebutan baca-tulis
    download.json. Pakai sebagai context manager:

        with AppLock() as ok:
            if not ok:
                print("Lagi ada proses lain yang jalan.")
                return
            ...jalankan aplikasi...

    Lock otomatis dianggap basi (stale) dan diambil alih kalau PID di
    dalamnya sudah nggak jalan lagi (misal proses sebelumnya crash).
    """

    def __init__(self):
        self._acquired = False

    def __enter__(self):
        ensure_download_folder()
        existing_pid = _read_lock_pid()
        if existing_pid and existing_pid != os.getpid() and _is_pid_running(existing_pid):
            return False
        try:
            with open(LOCK_FILE, "w") as f:
                f.write(str(os.getpid()))
            self._acquired = True
        except OSError:
            self._acquired = False
        return self._acquired

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._acquired:
            try:
                if _read_lock_pid() == os.getpid():
                    os.remove(LOCK_FILE)
            except OSError:
                pass
        return False