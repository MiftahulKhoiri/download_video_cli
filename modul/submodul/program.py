

init(autoreset=True)
NAMA_FOLDER = "VidioDownload"
os.makedirs(NAMA_FOLDER, exist_ok=True)
ILLEGAL_FILENAME_CHARS = r'<>:"/\|?*'

def bersihkan_nama_file(nama):
    for c in ILLEGAL_FILENAME_CHARS:
        nama = nama.replace(c, '')
    return nama.strip()

def tanggal_hari_ini():
    return datetime.datetime.now().strftime("%d-%m-%Y")

def safe_filename(name):
    return "".join(c for c in name if c.isalnum() or c in " ._-").rstrip()

def nama_file_unik(judul, ekstensi, tanggal):
    judul = safe_filename(judul)
    nama_dasar = f"{judul}_{tanggal}.{ekstensi}"
    nama_file = nama_dasar
    idx = 1
    while os.path.exists(os.path.join(NAMA_FOLDER, nama_file)):
        if idx == 1:
            nama_file = f"{judul}_{tanggal} (copy).{ekstensi}"
        else:
            nama_file = f"{judul}_{tanggal} (copy {idx}).{ekstensi}"
        idx += 1
    return nama_file

def cek_file_dan_konfirmasi(judul, ekstensi, tanggal):
    nama_file = f"{safe_filename(judul)}_{tanggal}.{ekstensi}"
    path_file = os.path.join(NAMA_FOLDER, nama_file)
    if os.path.exists(path_file):
        jawab = input(
            f"{Fore.YELLOW}File sudah ada: {nama_file}. Lanjutkan download dan simpan dengan nama baru? (y/n): "
        ).lower().strip()
        if jawab == "y":
            return nama_file_unik(judul, ekstensi, tanggal)
        else:
            print(Fore.CYAN + "Download dibatalkan.")
            return None
    else:
        return nama_file
