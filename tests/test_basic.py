"""
Uji unit ringan: cuma fungsi murni / logika file, TANPA jaringan dan TANPA
yt-dlp beneran. Jalankan dari folder root proyek:

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import paths, manager
from src.utils import parse_rate_limit, strip_ansi
from src.config import DEFAULT_CONFIG, _validate_config, MAX_PARALLEL_WORKERS


class TestUtils(unittest.TestCase):
    def test_parse_rate_limit(self):
        self.assertEqual(parse_rate_limit("2M"), 2 * 1024 ** 2)
        self.assertEqual(parse_rate_limit("500K"), 500 * 1024)
        self.assertEqual(parse_rate_limit("2MB"), 2 * 1024 ** 2)
        self.assertEqual(parse_rate_limit("2M/s"), 2 * 1024 ** 2)
        self.assertEqual(parse_rate_limit("1000"), 1000)
        for bad in ("abc", "", "0", "-5M", None):
            self.assertIsNone(parse_rate_limit(bad), bad)

    def test_strip_ansi(self):
        self.assertEqual(strip_ansi("\x1b[0;31mERROR:\x1b[0m gagal"), "ERROR: gagal")
        self.assertEqual(strip_ansi("teks biasa"), "teks biasa")


class TestPaths(unittest.TestCase):
    def test_anchored_to_project_folder(self):
        self.assertTrue(paths.HISTORY_FILE.startswith(paths.BASE_DIR))
        self.assertTrue(paths.CONFIG_FILE.startswith(paths.BASE_DIR))

    def test_resolve_path(self):
        self.assertEqual(paths.resolve_path("download/x.mp4"),
                          os.path.join(paths.BASE_DIR, "download/x.mp4"))
        self.assertEqual(paths.resolve_path("/abs/sudah/lengkap.mp4"), "/abs/sudah/lengkap.mp4")
        self.assertIsNone(paths.resolve_path(None))


class TestConfigValidation(unittest.TestCase):
    def test_invalid_values_reset_to_default(self):
        c = dict(DEFAULT_CONFIG)
        c["rate_limit"] = "bukan angka"
        c["parallel_workers"] = MAX_PARALLEL_WORKERS + 100
        c["retry_count"] = 0
        c["bg_color"] = "warna-ngasal"
        fixed, reset = _validate_config(c)
        for key in ("rate_limit", "parallel_workers", "retry_count", "bg_color"):
            self.assertIn(key, reset)
        self.assertEqual(fixed["parallel_workers"], DEFAULT_CONFIG["parallel_workers"])

    def test_valid_values_untouched(self):
        c = dict(DEFAULT_CONFIG)
        c["rate_limit"] = "2M"
        c["parallel_workers"] = MAX_PARALLEL_WORKERS
        _, reset = _validate_config(c)
        self.assertNotIn("rate_limit", reset)
        self.assertNotIn("parallel_workers", reset)


class TestHistoryAndDuplicates(unittest.TestCase):
    """Riwayat/duplikat diuji di folder proyek SUNGGUHAN (paths.BASE_DIR) tapi dengan
    HISTORY_FILE dialihkan sementara ke folder temp, biar nggak nyentuh download.json asli."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="dvc-test-")
        self._orig_history = paths.HISTORY_FILE
        self._orig_download_dir = paths.DOWNLOAD_DIR
        paths.DOWNLOAD_DIR = self._tmp
        paths.HISTORY_FILE = os.path.join(self._tmp, "download.json")
        manager.DOWNLOAD_DIR = self._tmp
        manager.HISTORY_FILE = paths.HISTORY_FILE
        manager._reserved_names.clear()

    def tearDown(self):
        paths.HISTORY_FILE = self._orig_history
        paths.DOWNLOAD_DIR = self._orig_download_dir
        manager.DOWNLOAD_DIR = self._orig_download_dir
        manager.HISTORY_FILE = self._orig_history
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_save_and_detect_duplicate(self):
        fp = os.path.join(self._tmp, "Judul Video.mp4")
        open(fp, "wb").write(b"isi")
        manager.save_file_record("Judul Video", fp, "http://u", "720p", video_id="abc")
        already, item = manager.is_already_downloaded("Judul Video", "720p", video_id="abc")
        self.assertTrue(already)
        self.assertIn("downloaded_at", item)

    def test_redownload_allowed_if_file_missing(self):
        fp = os.path.join(self._tmp, "Video Hilang.mp4")
        open(fp, "wb").write(b"isi")
        manager.save_file_record("Video Hilang", fp, "http://u", "720p", video_id="xyz")
        os.remove(fp)  # user hapus manual
        already, item = manager.is_already_downloaded("Video Hilang", "720p", video_id="xyz")
        self.assertFalse(already, "harusnya BOLEH diunduh ulang kalau file lama sudah hilang")
        self.assertIsNotNone(item)  # tapi entri lamanya tetap dikembalikan buat referensi

    def test_corrupt_history_backed_up(self):
        manager.ensure_download_folder()
        open(paths.HISTORY_FILE, "w").write('{"bukan": "list"')  # JSON rusak
        with contextlib.redirect_stdout(io.StringIO()):
            history = manager.load_history()
        self.assertEqual(history, [])
        backups = [f for f in os.listdir(self._tmp) if ".corrupt-" in f]
        self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)