import errno
import os

from src.manager import ensure_download_folder
from src.paths import LOCK_FILE

try:
    import fcntl  # Linux / macOS / Termux
except ImportError:  # pragma: no cover -- platform tanpa fcntl
    fcntl = None


def _is_pid_running(pid):
    if os.name == "nt":
        return True  # di Windows os.kill(pid, 0) justru MEMATIKAN proses -- jangan dipakai buat ngecek
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

    Cara kerja (urut prioritas):
      1. fcntl.flock -- dikunci oleh sistem operasi. Otomatis lepas begitu proses
         mati (crash, di-kill, HP restart), jadi TIDAK ADA lock "nyangkut" dan
         nggak ketipu PID yang dipakai ulang. Ngecek + ngunci berlangsung atomik.
      2. Fallback (sistem tanpa flock): bikin file lock secara eksklusif (O_EXCL)
         berisi PID. Lock dianggap basi kalau PID-nya sudah nggak jalan.
    """

    def __init__(self):
        self._fd = None
        self._excl = False

    def __enter__(self):
        ensure_download_folder()
        if fcntl is not None:
            result = self._acquire_flock()
            if result is not None:
                return result
        return self._acquire_excl()

    def _acquire_flock(self):
        """True = dapat lock, False = dipegang proses lain, None = flock nggak bisa dipakai di sini."""
        try:
            fd = os.open(LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            os.close(fd)
            if e.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                return False
            return None  # filesystem nggak mendukung flock -> pakai fallback
        try:
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())  # cuma informasi, bukan dasar penguncian
        except OSError:
            pass
        self._fd = fd
        return True

    def _acquire_excl(self):
        for _ in range(2):
            try:
                fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                pid = _read_lock_pid()
                if pid and pid != os.getpid() and _is_pid_running(pid):
                    return False
                try:
                    os.remove(LOCK_FILE)  # lock basi (proses sebelumnya crash) -> ambil alih
                except OSError:
                    return False
                continue
            except OSError:
                return False
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            self._excl = True
            return True
        return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            # File .lock sengaja nggak dihapus: kuncinya lepas otomatis begitu fd ditutup.
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        elif self._excl:
            try:
                if _read_lock_pid() == os.getpid():
                    os.remove(LOCK_FILE)
            except OSError:
                pass
            self._excl = False
        return False
