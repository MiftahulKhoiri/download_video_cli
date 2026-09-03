import logging
import os

LOG_DIR = "download"
LOG_FILE = os.path.join(LOG_DIR, "app.log")

_logger = None


def get_logger():
    """
    Logger sederhana ke file download/app.log. Nggak nyetak apa pun ke layar
    (biar nggak dobel sama pesan yang udah ditampilkan) -- cuma berguna buat
    lacak riwayat/error kalau dijalanin unattended (cron/automation).
    """
    global _logger
    if _logger is not None:
        return _logger

    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("download_video_cli")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        try:
            handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
            ))
            logger.addHandler(handler)
        except OSError:
            logger.addHandler(logging.NullHandler())

    _logger = logger
    return logger