"""
Uji penerjemah error (src/errors.py): pesan yt-dlp mentah -> pesan + petunjuk
yang jelas, dan penentuan error mana yang percuma di-retry. Tanpa jaringan.

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DVC_NO_LOG"] = "1"   # jangan sampai tes nulis ke download/app.log asli

from src.errors import clean_message, explain_error, get_hint, is_retryable

TWEET = Exception("\x1b[0;31mERROR:\x1b[0m [twitter] 2122662709565235364: No video could be found in this tweet")


class TestCleanMessage(unittest.TestCase):
    def test_strips_ansi_and_error_prefix(self):
        self.assertEqual(clean_message(TWEET),
                          "[twitter] 2122662709565235364: No video could be found in this tweet")

    def test_strips_ytdlp_report_tail(self):
        e = Exception("ERROR: [youtube] abc: boom; please report this issue on  https://github.com/yt-dlp/yt-dlp/issues")
        self.assertEqual(clean_message(e), "[youtube] abc: boom")

    def test_empty_message_falls_back_to_type(self):
        self.assertEqual(clean_message(ValueError("")), "ValueError")


class TestHints(unittest.TestCase):
    def test_tweet_needs_login_suggests_cookies(self):
        out = explain_error(TWEET)
        self.assertIn("💡", out)
        self.assertIn("login", out)
        self.assertIn("--cookies", out)

    def test_tweet_with_cookies_gives_different_hint(self):
        hint = get_hint(TWEET, cookies_used=True)
        self.assertIn("Sudah pakai cookies", hint)
        self.assertNotEqual(hint, get_hint(TWEET, cookies_used=False))

    def test_known_errors_have_hints(self):
        cases = {
            "ERROR: unable to download video data: HTTP Error 403: Forbidden": "403",
            "ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate": "umur",
            "ERROR: [youtube] x: Sign in to confirm you're not a bot": "bot",
            "ERROR: [youtube] x: Private video. Sign in if you've been granted access": "privat",
            "ERROR: [youtube] x: Video unavailable": "dihapus",
            "ERROR: Unsupported URL: https://contoh.com/abc": "didukung",
            "ERROR: [youtube] x: Video unavailable. This content isn't available, try again later.": "sementara",
            "<urlopen error [Errno -3] Temporary failure in name resolution>": "koneksi",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertIn(expected, get_hint(Exception(raw)).lower())

    def test_unknown_error_has_no_hint(self):
        e = Exception("ERROR: sesuatu yang aneh banget")
        self.assertIsNone(get_hint(e))
        self.assertEqual(explain_error(e), "sesuatu yang aneh banget")


class TestRetryable(unittest.TestCase):
    def test_permanent_errors_not_retried(self):
        self.assertFalse(is_retryable(TWEET))
        self.assertFalse(is_retryable(Exception("ERROR: Unsupported URL: x")))
        self.assertFalse(is_retryable(Exception("ERROR: [youtube] x: Video unavailable")))

    def test_transient_errors_retried(self):
        self.assertTrue(is_retryable(Exception("HTTP Error 403: Forbidden")))
        self.assertTrue(is_retryable(Exception("Read timed out")))
        self.assertTrue(is_retryable(Exception("error tak dikenal")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
