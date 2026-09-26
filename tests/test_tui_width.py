"""
Uji fungsi lebar-tampilan (display width) & pemotongan teks di src/tui.py --
murni fungsi teks, TIDAK butuh terminal/curses beneran (curses cuma dipakai
buat konstanta warna di modul ini, aman diimpor tanpa initscr()).

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import tui


class TestDisplayWidth(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(tui.display_width("hello"), 5)
        self.assertEqual(tui.display_width(""), 0)

    def test_cjk_double_width(self):
        # Judul video Asia (Cina/Jepang/Korea) sering muncul -- tiap karakter selebar 2 kolom.
        self.assertEqual(tui.display_width("你好"), 4)

    def test_emoji_double_width(self):
        # Judul video juga sering diawali/diselipi emoji.
        self.assertEqual(tui.display_width("🎬"), 2)
        self.assertEqual(tui.display_width("🎬🎵 Judul"), 2 + 2 + 1 + 5)

    def test_combining_mark_zero_width(self):
        self.assertEqual(tui.display_width("e\u0301"), 1)  # e + aksen akut, nempel jadi 1 kolom


class TestTruncateAndPad(unittest.TestCase):
    def test_truncate_never_splits_wide_char(self):
        self.assertEqual(tui._truncate_display("hello world", 5), "hello")
        self.assertEqual(tui._truncate_display("你好吗", 3), "你")   # 好 bikin 4 kolom, nggak muat di 3
        self.assertEqual(tui._truncate_display("你好吗", 4), "你好")
        self.assertEqual(tui._truncate_display("short", 100), "short")

    def test_pad_uses_display_width(self):
        self.assertEqual(tui._pad_display("ab", 5), "ab   ")
        self.assertEqual(tui.display_width(tui._pad_display("你", 5)), 5)

    def test_fit_display_exact_width_and_keeps_suffix(self):
        # Kasus nyata: judul panjang + tag resolusi di ujung (dashboard/menu resolusi) --
        # tag-nya nggak boleh ikut kepotong pas judulnya kepanjangan.
        text = "Judul Video Yang Sangat Panjang Sekali Banget [720p]"
        res = tui._fit_display(text, 20, keep_suffix=10)
        self.assertEqual(tui.display_width(res), 20)
        self.assertTrue(res.endswith(text[-10:]))
        self.assertIn("…", res)

    def test_fit_display_short_text_padded(self):
        self.assertEqual(tui._fit_display("pendek", 20), "pendek".ljust(20))

    def test_fit_display_handles_wide_chars_without_crash(self):
        res = tui._fit_display("你" * 30 + " [1080p]", 20, keep_suffix=8)
        self.assertEqual(tui.display_width(res), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
