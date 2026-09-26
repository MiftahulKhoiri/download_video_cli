import logging
import os
from logging.handlers import RotatingFileHandler

from src.paths import DOWNLOAD_DIR, LOG_FILE

_logger = None


def get_logger():
    """
    Logger sederhana ke file download/app.log (diputar otomatis: maks ~1 MB x 3 file).
    Nggak nyetak apa pun ke layar (biar nggak dobel sama pesan yang udah ditampilkan) --
    cuma berguna buat lacak riwayat/error kalau dijalanin unattended (cron/automation).
    """
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger("download_video_cli")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
            ))
            logger.addHandler(handler)
        except OSError:
            logger.addHandler(logging.NullHandler())

    _logger = logger
    return logger
