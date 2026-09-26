import json
import os
import subprocess
import sys
import time
import urllib.request

from src.paths import UPDATE_CACHE_FILE

CACHE_TTL_SECONDS = 24 * 3600  # jangan cek PyPI tiap kali start -- cukup sekali per 24 jam


def _load_update_cache():
    try:
        with open(UPDATE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_update_cache(data):
    try:
        os.makedirs(os.path.dirname(UPDATE_CACHE_FILE), exist_ok=True)
        with open(UPDATE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass  # cache cuma optimisasi -- gagal nulis nggak boleh bikin cek update gagal


def get_installed_version():
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return None


def get_latest_version(timeout=3):
    """Cek versi terbaru yt-dlp di PyPI. Return None kalau nggak ada internet / gagal."""
    try:
        req = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json",
            headers={"User-Agent": "download_video_cli"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
            return data.get("info", {}).get("version")
    except Exception:
        return None


def check_for_update(timeout=3, use_cache=True):
    """
    Return (installed, latest, is_outdated).
    Kalau nggak bisa cek versi terbaru (offline dll), latest=None dan is_outdated=False.

    use_cache=True (dipakai startup_check_and_notify): kalau versi yt-dlp yang terpasang
    SAMA kayak terakhir kali dicek DAN itu kurang dari 24 jam lalu, pakai hasil cache --
    nggak nge-hit PyPI tiap kali aplikasi start. Cache otomatis basi begitu yt-dlp
    diupdate (versi terpasang berubah). use_cache=False (dipakai menu "Cek & update yt-dlp"
    manual) selalu cek langsung ke PyPI, karena user memang lagi nunggu hasil terbaru.
    """
    installed = get_installed_version()

    if use_cache and installed:
        cache = _load_update_cache()
        checked_at = cache.get("checked_at")
        if (cache.get("installed") == installed and "latest" in cache
                and isinstance(checked_at, (int, float))
                and 0 <= time.time() - checked_at < CACHE_TTL_SECONDS):
            latest = cache.get("latest")
            return installed, latest, bool(latest and installed != latest)

    latest = get_latest_version(timeout=timeout)
    if installed and latest is not None:
        _save_update_cache({"installed": installed, "latest": latest, "checked_at": time.time()})
    return installed, latest, bool(installed and latest and installed != latest)


def update_yt_dlp():
    """
    Jalankan pip install -U yt-dlp. Return (True, output) kalau berhasil,
    (False, pesan_error) kalau gagal.
    """
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0:
            return True, result.stdout

        # Beberapa sistem (Termux/Debian modern) butuh flag ini karena PEP 668.
        result2 = subprocess.run(cmd + ["--break-system-packages"], capture_output=True, text=True, timeout=180)
        if result2.returncode == 0:
            return True, result2.stdout
        return False, (result2.stderr or result2.stdout or result.stderr or "gagal tanpa pesan error").strip()
    except Exception as e:
        return False, str(e)


def startup_check_and_notify(timeout=3):
    """
    Dipanggil sekali pas start aplikasi (mode interaktif). Cek versi yt-dlp,
    dengan Spinner biar keliatan masih proses (bukan macet) selagi nunggu
    request ke PyPI. Nggak pernah bikin aplikasi gagal start kalau offline /
    PyPI nggak bisa diakses -- paling lama nunggu ~timeout detik lalu lanjut.
    """
    try:
        from src.loading import Spinner
        with Spinner("🔍 update perangkat lunak :..."):
            installed, latest, is_outdated = check_for_update(timeout=timeout)
        if is_outdated:
            print(f"⚠️  yt-dlp kamu versi {installed}, versi terbaru {latest} tersedia.")
            print("    Update lewat menu Pengaturan > Cek & update yt-dlp, biar terhindar dari error 403.\n")
    except Exception:
        pass  # startup check nggak boleh sampai bikin app gagal jalan