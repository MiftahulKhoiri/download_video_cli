# src/errors.py
"""
Terjemahkan pesan error yt-dlp yang teknis/membingungkan jadi pesan yang jelas
plus petunjuk apa yang harus dilakukan user.

    from src.errors import explain_error, is_retryable

    print(f"❌ Gagal: {explain_error(e, cookies_used=bool(config.get('cookies_file')))}")

Contoh: "ERROR: [twitter] 123: No video could be found in this tweet" jadi
"[twitter] 123: No video could be found in this tweet" + baris petunjuk bahwa
tweet-nya butuh login dan cara pakai cookies.

Sengaja cuma bergantung ke src.utils, biar aman diimpor dari modul mana pun.
"""
import re

from src.utils import strip_ansi

_COOKIES_HOW = "pakai cookies akun yang sudah login: opsi --cookies cookies.txt, atau menu Pengaturan > File cookies"

# Tiap aturan: (pola regex, petunjuk tanpa cookies, petunjuk kalau cookies SUDAH dipakai, boleh diulang?)
# - Petunjuk kedua None = sama dengan yang pertama.
# - "boleh diulang" False = error permanen; retry otomatis cuma buang waktu, jadi langsung berhenti.
# Urutan penting: aturan yang lebih spesifik ditaruh di atas.
_RULES = [
    (
        r"No video could be found in this tweet|TweetTombstone|NSFW tweet requires authentication"
        r"|Requested tweet is unavailable|tweet is (unavailable|protected)|Suspended account",
        "Tweet ini nggak bisa dilihat tanpa login. Biasanya karena videonya ditandai konten sensitif/"
        f"dibatasi umur, akunnya diproteksi, atau tweet-nya sudah dihapus. Coba {_COOKIES_HOW}.",
        "Sudah pakai cookies tapi tetap gagal. Kemungkinan: cookies sudah kedaluwarsa (ekspor ulang "
        "setelah login), akun X-mu belum mengaktifkan 'Tampilkan media sensitif' di Setelan > Privasi "
        "dan keamanan > Konten yang kamu lihat, akun pengunggah diproteksi dan kamu bukan pengikutnya, "
        "atau tweet-nya memang sudah dihapus.",
        False,
    ),
    (
        r"Sign in to confirm (you.re|that you are) not a bot",
        f"YouTube curiga ini bot (sering terjadi di IP server/VPN). Tunggu sebentar lalu coba lagi, atau {_COOKIES_HOW}.",
        "YouTube masih curiga ini bot walau sudah pakai cookies. Ekspor ulang cookies YouTube yang masih "
        "aktif, kurangi download paralel, lalu coba lagi nanti.",
        False,
    ),
    (
        r"Sign in to confirm your age|age.restricted|inappropriate for some users",
        f"Video ini dibatasi umur. Untuk mengunduhnya, {_COOKIES_HOW}.",
        "Video dibatasi umur dan cookies-nya belum diterima. Pastikan cookies berasal dari akun dewasa "
        "yang masih login, lalu ekspor ulang.",
        False,
    ),
    (
        r"members.only|Join this channel to get access",
        f"Konten khusus member channel. Butuh cookies dari akun yang jadi member: {_COOKIES_HOW}.",
        "Konten khusus member, dan akun di cookies-mu sepertinya bukan member channel ini.",
        False,
    ),
    (
        r"Private video|This video is private|This account is private",
        f"Videonya privat. Cuma bisa diunduh kalau akunmu punya akses, dengan cara {_COOKIES_HOW}.",
        "Videonya privat dan akun di cookies-mu nggak punya akses ke video ini.",
        False,
    ),
    (
        # Pesan "Video unavailable" versi YouTube yang sebenarnya pembatasan sementara (rate limit), bukan dihapus.
        r"content isn.t available, try again later",
        "YouTube membatasi sementara karena terlalu banyak permintaan. Tunggu sekitar 1 jam, "
        "kurangi jumlah download paralel, lalu coba lagi.",
        None,
        False,
    ),
    (
        r"Video unavailable|video is unavailable|This video has been removed|has been terminated|This video is no longer available"
        r"|HTTP Error 404|404: Not Found",
        "Videonya nggak ditemukan: mungkin sudah dihapus, link-nya salah, atau dibatasi pemiliknya.",
        None,
        False,
    ),
    (
        r"not (made )?available in your country|geo.?restrict|blocked it in your country",
        "Video ini diblokir untuk negaramu (geo-restricted). Butuh VPN/proxy dari negara yang diizinkan.",
        None,
        False,
    ),
    (
        r"does not look like a Netscape format cookies file|cookies?.*(No such file|not found)",
        "File cookies nggak ketemu atau formatnya salah. Harus file cookies.txt format Netscape "
        "(misal dari ekstensi browser 'Get cookies.txt LOCALLY'). Cek path-nya di Pengaturan > File cookies.",
        None,
        False,
    ),
    (
        r"Unsupported URL|is not a valid URL",
        "Alamat ini nggak didukung yt-dlp atau formatnya salah. Cek lagi link-nya (salin ulang dari tombol Bagikan).",
        None,
        False,
    ),
    (
        r"ffprobe and ffmpeg not found|ffmpeg (is )?not (found|installed)|ffmpeg.*not available",
        "ffmpeg belum terpasang (dipakai buat gabung video+audio & konversi MP3). Install: "
        "'sudo apt install ffmpeg' (Linux/Pi) atau 'pkg install ffmpeg' (Termux).",
        None,
        False,
    ),
    (
        r"HTTP Error 403|403: Forbidden",
        "Akses ditolak (403). Biasanya karena yt-dlp versi lama: update lewat Pengaturan > Cek & update "
        "yt-dlp (atau 'pip install -U yt-dlp'), lalu coba lagi.",
        None,
        True,
    ),
    (
        r"HTTP Error 429|Too Many Requests|rate.limit(ed)? reached",
        "Terlalu banyak permintaan ke server (429). Tunggu beberapa menit, kurangi jumlah download paralel, "
        f"atau {_COOKIES_HOW}.",
        "Terlalu banyak permintaan ke server (429). Tunggu beberapa menit dan kurangi jumlah download paralel.",
        True,
    ),
    (
        r"Name or service not known|Temporary failure in name resolution|getaddrinfo failed|Failed to resolve"
        r"|Network is unreachable|timed out|Connection (reset|refused|aborted)|Remote end closed connection"
        r"|No route to host",
        "Nggak bisa terhubung ke server: koneksi internet bermasalah, atau alamat situsnya salah/nggak ada. "
        "Cek jaringan/Wi-Fi dan ejaan link-nya, lalu coba lagi.",
        None,
        True,
    ),
    (
        r"No space left on device",
        "Penyimpanan penuh. Kosongkan ruang di folder tujuan download, lalu coba lagi.",
        None,
        False,
    ),
    (
        r"Permission denied",
        "Nggak punya izin menulis ke folder tujuan. Ganti folder download di Pengaturan, "
        "atau di Termux jalankan 'termux-setup-storage'.",
        None,
        False,
    ),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), hint, hint_cookies, retry)
             for p, hint, hint_cookies, retry in _RULES]

# Ekor pesan yt-dlp yang nggak berguna buat user biasa.
_NOISE_RE = re.compile(
    r";?\s*(please report this issue on|Confirm you are on the latest version|"
    r"Use --cookies|See\s+https://github\.com/yt-dlp|Also see\s+https://).*$",
    re.IGNORECASE | re.DOTALL,
)


def clean_message(exc):
    """Pesan error asli yang dirapikan: tanpa kode warna, tanpa awalan 'ERROR:', tanpa ekor saran yt-dlp."""
    msg = strip_ansi(exc).strip()
    msg = re.sub(r"^(ERROR:\s*)+", "", msg)
    msg = _NOISE_RE.sub("", msg).strip().rstrip(";").strip()
    return msg or type(exc).__name__


def _match(exc):
    text = strip_ansi(exc)
    for regex, hint, hint_cookies, retry in _COMPILED:
        if regex.search(text):
            return hint, hint_cookies, retry
    return None


def get_hint(exc, cookies_used=False):
    """Petunjuk singkat buat error ini, atau None kalau error-nya nggak dikenali."""
    m = _match(exc)
    if not m:
        return None
    hint, hint_cookies, _ = m
    return (hint_cookies or hint) if cookies_used else hint


def explain_error(exc, cookies_used=False, indent="   "):
    """
    Pesan error yang siap ditampilkan: pesan asli yang dirapikan, ditambah baris
    '💡 ...' berisi petunjuk kalau jenis error-nya dikenali.
    """
    msg = clean_message(exc)
    hint = get_hint(exc, cookies_used=cookies_used)
    return f"{msg}\n{indent}💡 {hint}" if hint else msg


def is_retryable(exc):
    """False buat error permanen (tweet butuh login, video dihapus, URL salah, dst):
    mengulang cuma buang waktu. Error yang nggak dikenali dianggap boleh diulang."""
    m = _match(exc)
    return True if m is None else m[2]
