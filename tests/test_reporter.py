"""
Uji lapisan pelapor (src/reporter.py) & state layar progress TUI (src/tui_progress.py)
-- tanpa jaringan dan tanpa terminal/curses beneran.

    python3 -m unittest discover -s tests -v
"""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DVC_NO_LOG"] = "1"   # jangan sampai tes nulis ke download/app.log asli

from src import reporter as rp
from src.tui_progress import TuiDownloadReporter


class TestUseReporter(unittest.TestCase):
    def test_swap_and_restore(self):
        default = rp.report()
        buf = rp.BufferReporter()
        with rp.use_reporter(buf):
            self.assertIs(rp.report(), buf)
            rp.report().message("halo")
        self.assertIs(rp.report(), default)
        self.assertEqual(buf.drain(), ["halo"])
        self.assertEqual(buf.drain(), [])

    def test_restored_even_on_error(self):
        default = rp.report()
        with self.assertRaises(ValueError):
            with rp.use_reporter(rp.BufferReporter()):
                raise ValueError("boom")
        self.assertIs(rp.report(), default)

    def test_buffer_is_thread_safe(self):
        buf = rp.BufferReporter()
        threads = [threading.Thread(target=lambda: [buf.message("x") for _ in range(200)]) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(buf.drain()), 1600)


class TestTextReporter(unittest.TestCase):
    """Mode CLI: output harus tetap sama seperti versi sebelum ada lapisan reporter."""

    def _run(self, fn):
        out = io.StringIO()
        r = rp.TextReporter()
        with contextlib.redirect_stdout(out):
            fn(r)
        return out.getvalue()

    def test_sequential_batch_output(self):
        def fn(r):
            r.batch_start(["u1"], 1)
            r.batch_item(1, 1, "u1")
            r.item_done("u1", "gagal", "alasannya")
            r.summary({"berhasil": 0, "dilewati": 0, "gagal": 1})
        out = self._run(fn)
        self.assertIn("=== [1/1] u1 ===", out)
        self.assertIn("❌ Gagal mengunduh u1: alasannya", out)
        self.assertIn("Ringkasan: 0 berhasil, 0 dilewati (duplikat), 1 gagal.", out)

    def test_already_shown_failure_not_repeated(self):
        out = self._run(lambda r: r.item_done("u1", "gagal", "ffmpeg belum terpasang", shown=True))
        self.assertEqual(out, "")

    def test_parallel_mode_no_progress_bar(self):
        def fn(r):
            r.batch_start(["a", "b"], 2)
            r.item_start("a", "Judul A")
            r.progress("a", {"status": "downloading", "_percent_str": "50%", "filename": "x.mp4"})
            r.batch_tick(1, 2, "a", "berhasil")
            r.batch_tick(2, 2, "b", "gagal", "rusak")
        out = self._run(fn)
        self.assertIn("⬇️  Mulai unduh: Judul A", out)
        self.assertNotIn("50.0%", out)       # progress bar realtime dimatikan di mode paralel
        self.assertIn("[1/2] Selesai: a", out)
        self.assertIn("[2/2] ❌ Gagal: b\n   rusak", out)


class TestTuiDownloadReporterState(unittest.TestCase):
    def test_item_lifecycle(self):
        r = TuiDownloadReporter()
        r.batch_start(["u1", "u2"], 2)
        r.item_info("u1", "Video Satu", "720p")
        r.item_start("u1", "Video Satu")
        r.progress("u1", {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200,
                          "speed": 1000, "eta": 3})
        snap = r.snapshot()
        it = snap["items"][0]
        self.assertEqual((it.title, it.label, it.state), ("Video Satu", "720p", "unduh"))
        self.assertAlmostEqual(it.pct, 25.0)
        self.assertTrue(snap["parallel"])

        r.postprocess("u1", {"status": "started", "postprocessor": "Merger"})
        self.assertEqual(r.snapshot()["items"][0].state, "proses")
        r.item_done("u1", "berhasil")
        r.item_done("u1", "gagal", "nggak boleh menimpa status yang sudah final")
        self.assertEqual(r.snapshot()["items"][0].state, "berhasil")

    def test_failure_detail_is_short_but_log_has_full_text(self):
        r = TuiDownloadReporter()
        r.item_done("u1", "gagal", "[twitter] 123: No video could be found in this tweet\n   💡 petunjuk")
        snap = r.snapshot()
        self.assertEqual(snap["items"][0].detail, "No video could be found in this tweet")
        self.assertTrue(any("💡 petunjuk" in line for line in snap["log"]))

    def test_cancel_marks_remaining(self):
        r = TuiDownloadReporter()
        r.batch_start(["a", "b", "c"], 1)
        r.item_done("a", "berhasil")
        r.item_done("b", "gagal", "dibatalkan")
        r.finalize(cancelled=True)
        states = [it.state for it in r.snapshot()["items"]]
        self.assertEqual(states, ["berhasil", "batal", "batal"])
        log = r.snapshot()["log"]
        self.assertEqual(sum("Dibatalkan" in line for line in log), 1)   # satu pesan, bukan per item

    def test_status_stack(self):
        r = TuiDownloadReporter()
        with r.status("Mengambil info video..."):
            self.assertEqual(r.snapshot()["status"], "Mengambil info video...")
        self.assertIsNone(r.snapshot()["status"])


class TestComposeRows(unittest.TestCase):
    """Isi layar progress harus selalu muat di layar (termasuk layar HP yang sempit)."""

    def _reporter(self):
        r = TuiDownloadReporter()
        r.batch_start([f"u{i}" for i in range(12)], 2)
        for i in range(12):
            r.item_info(f"u{i}", f"Video dengan judul yang cukup panjang nomor {i} 🎬", "720p")
            r.message(f"⚠️  pesan nomor {i} yang lumayan panjang biar kena wrap di layar sempit")
        r.item_start("u3", "Video dengan judul yang cukup panjang nomor 3 🎬")
        r.progress("u3", {"status": "downloading", "downloaded_bytes": 10, "total_bytes": 100})
        return r

    def test_fits_screen_and_single_separator(self):
        from src.tui_progress import _compose_rows
        for h, w in ((24, 80), (16, 50), (10, 32)):
            for done in (False, True):
                rows, _ = _compose_rows("judul", self._reporter().snapshot(), h, w, 0, 0, done)
                with self.subTest(h=h, w=w, done=done):
                    self.assertLessEqual(len(rows), h - 2)
                    self.assertLessEqual(sum(t.startswith("─ Pesan") for t, _ in rows), 1)

    def test_active_item_visible_when_list_too_long(self):
        from src.tui_progress import _compose_rows
        rows, _ = _compose_rows("judul", self._reporter().snapshot(), 12, 60, 0, 0, False)
        self.assertTrue(any("nomor 3" in t for t, _ in rows), "item yang lagi diunduh harus kelihatan")


class TestIntermediateCleanup(unittest.TestCase):
    def test_finished_stream_before_merge_is_removed(self):
        from src.download_core import _cleanup_partial_files
        tmp = tempfile.mkdtemp(prefix="dvc-test-")
        try:
            stream = os.path.join(tmp, "Judul.f137.mp4")      # video-only, nunggu audio buat digabung
            final = os.path.join(tmp, "Judul.mp4")            # file final milik download LAIN: jangan disentuh
            part = os.path.join(tmp, "Judul.f140.m4a.part")
            for fp in (stream, final, part):
                with open(fp, "wb") as f:
                    f.write(b"x")
            _cleanup_partial_files({stream, part})
            self.assertFalse(os.path.exists(stream))
            self.assertFalse(os.path.exists(part))
            self.assertTrue(os.path.exists(final))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
