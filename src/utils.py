# src/utils.py
"""Fungsi kecil yang dipakai banyak modul (sengaja tanpa dependensi ke modul lain di proyek)."""
import os
import re
import time

# Kode warna/format terminal (ANSI), mis. "\x1b[0;31mERROR:\x1b[0m" -- sering ikut
# nempel di pesan error yt-dlp dan merusak tampilan curses / isi app.log.
_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# Angka + satuan opsional (K/M/G), boleh diikuti B/iB dan /s: 500K, 2M, 2MB, 1.5M, 2MiB/s
_RATE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?|\.\d+)\s*([KMG]?)(?:I?B)?(?:/S)?\s*$", re.IGNORECASE)
_RATE_UNITS = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}


def strip_ansi(text):
    """Buang kode warna ANSI dari teks (atau dari pesan exception)."""
    return _ANSI_RE.sub("", str(text))


def parse_rate_limit(text):
    """
    '500K' -> 512000, '2M' / '2MB' / '2M/s' -> 2097152, angka polos -> byte/detik.
    Return None kalau kosong atau formatnya nggak valid (dipakai juga buat validasi input).
    """
    if text is None:
        return None
    m = _RATE_RE.match(str(text))
    if not m:
        return None
    value = float(m.group(1)) * _RATE_UNITS[m.group(2).upper()]
    return int(value) if value >= 1 else None


def backup_corrupt_file(path):
    """
    Pindahkan file yang rusak ke '<path>.corrupt-<waktu>' biar isinya nggak ketimpa
    file baru dan masih bisa diselamatkan manual. Return path backup, atau None kalau gagal.
    """
    dest = f"{path}.corrupt-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        os.replace(path, dest)
        return dest
    except OSError:
        return None
