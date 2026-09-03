# YouTube/X Video & Audio Downloader

Script Python3 untuk mengunduh video dan audio dari **YouTube** dan **X (Twitter)** — juga situs lain yang didukung `yt-dlp` (TikTok, Instagram, Facebook, dll, tinggal masukkan URL-nya). Mendukung download satu item maupun banyak sekaligus (termasuk playlist), berbagai format audio, potong durasi, riwayat otomatis anti-duplikat, verifikasi hasil download, mode interaktif maupun CLI non-interaktif, dan pengaturan yang bisa disimpan.

## ✨ Fitur

**Download**
- Video dari YouTube, X (Twitter), dan situs lain yang didukung `yt-dlp`
- Audio dalam **5 format**: MP3, M4A, OPUS, FLAC, WAV — kualitas bisa dipilih (128/192/256/320 kbps untuk format lossy)
- **Playlist otomatis di-expand** jadi daftar video/audio individual
- **Potong ke rentang waktu tertentu** (mis. cuma ambil menit 1:30–2:45), tanpa unduh video penuh
- Pilih resolusi video sebelum mengunduh (atau otomatis kualitas terbaik / default tersimpan)
- Mode 1 item, banyak (batch, bisa ketik manual atau **import dari file `.txt`**), atau **download paralel**
- **Retry otomatis** kalau satu download gagal
- **Subtitle/caption** opsional (manual + auto-generated), bisa multi-bahasa
- **Embed thumbnail + metadata** (judul dll) otomatis ke file audio
- Batas kecepatan download (rate limit) opsional

**Keandalan**
- **Verifikasi file hasil download** — deteksi file 0 byte / rusak (pakai `ffprobe` kalau tersedia) sebelum disimpan ke riwayat, jadi file yang gagal nggak dianggap sukses
- **Cek ruang disk kosong** sebelum mulai download banyak/paralel — batal otomatis kalau kritis, warning kalau menipis (nggak pernah nge-block nunggu input, aman buat cron)
- **Lock file** — cegah dua proses (mode menu & mode CLI, atau dua CLI/cron sekaligus) jalan bersamaan dan rebutan tulis `download.json`
- Ctrl+C ditangani rapi — file `.part`/`.ytdl` sisa otomatis dibersihkan, bukan nyangkut jadi sampah

**Organisasi & riwayat**
- Riwayat tersimpan di `download/download.json`, deteksi duplikat pakai **ID video** (bukan cuma judul)
- Dashboard: **total jumlah & ukuran file**, **cari/filter riwayat** by judul, **hapus satu entri atau semua riwayat** (opsional sekalian hapus filenya)
- **Auto-organize folder hasil download**: rata (default), per channel, atau per tanggal upload
- Log aktivitas & error otomatis ke `download/app.log` — berguna kalau dijalanin unattended/cron

**Kenyamanan & Termux**
- **Cek & update yt-dlp** — notice otomatis pas start kalau ketinggalan versi + tombol update di menu Pengaturan (yt-dlp yang outdated adalah penyebab paling umum error 403)
- Notifikasi Android via Termux:API setelah download selesai
- Opsi **salin otomatis ke `~/storage/downloads`** biar file muncul di Galeri/File Manager Android
- **Mode CLI non-interaktif** (`--url ...` / `--url-file ...`) buat dipanggil dari script/automation
- Dukungan file cookies buat konten yang butuh login
- Folder `download/` dibuat otomatis jika belum ada

## 📁 Struktur Proyek

```
project/
├── main.py                  # Menu utama + mode CLI non-interaktif
├── requirements.txt
├── README.md
├── config.json                # Dibuat otomatis saat pengaturan pertama kali diubah
├── src/
│   ├── __init__.py
│   ├── dashboard.py         # Tampilan dashboard/riwayat, total ukuran, cari/filter, hapus entri
│   ├── loading.py           # Progress bar, spinner, print thread-safe, format ukuran file
│   ├── download.py          # Logika download video & audio (single/batch/paralel/retry/potong durasi/verifikasi)
│   ├── manager.py           # Kelola folder & file download.json (riwayat)
│   ├── config.py            # Baca/simpan pengaturan (config.json) + menu Pengaturan
│   ├── updater.py           # Cek & update yt-dlp
│   ├── logger.py            # Logger ke download/app.log
│   ├── lock.py              # Cegah proses ganda jalan bersamaan
│   ├── notify.py            # Notifikasi Android via Termux:API
│   └── logo.py              # ASCII logo & animasi intro
└── download/                  # Dibuat otomatis, berisi hasil unduhan
    ├── download.json          # Dibuat otomatis, riwayat download
    ├── app.log                 # Dibuat otomatis, log aktivitas & error
    └── .lock                    # Dibuat sementara selagi aplikasi jalan, dihapus otomatis saat keluar
```

## 🔧 Persyaratan

- Python 3.8 atau lebih baru
- [ffmpeg](https://ffmpeg.org/) (untuk menggabungkan video+audio, convert format audio, embed thumbnail/metadata, dan verifikasi file hasil download via `ffprobe`)
- (Opsional, Termux saja) `termux-api` untuk notifikasi Android, dan `termux-setup-storage` untuk fitur salin ke shared storage

## 📦 Instalasi

1. Clone atau salin proyek ini ke komputer/perangkat Anda.

2. (Opsional tapi disarankan) Buat virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate    # Linux/Mac
   venv\Scripts\activate       # Windows
   ```

3. Install dependency Python:
   ```bash
   pip install -r requirements.txt
   ```

4. Install ffmpeg (wajib, tidak bisa lewat pip — paketnya juga menyertakan `ffprobe` yang dipakai buat verifikasi file):

   | Sistem | Perintah |
   |---|---|
   | Ubuntu/Debian | `sudo apt install ffmpeg` |
   | macOS (Homebrew) | `brew install ffmpeg` |
   | Windows | Download dari [ffmpeg.org](https://ffmpeg.org/download.html) lalu tambahkan ke PATH |
   | Termux (Android) | `pkg install ffmpeg` |

5. Verifikasi ffmpeg & ffprobe terinstall:
   ```bash
   ffmpeg -version && ffprobe -version
   ```

6. (Opsional, Termux) Aktifkan notifikasi selesai-download:
   ```bash
   pkg install termux-api
   ```
   Lalu install juga app **Termux:API** dari F-Droid/Play Store. Kalau tidak diinstall, notifikasi otomatis di-skip tanpa error.

7. (Opsional, Termux) Aktifkan fitur salin ke folder Download Android:
   ```bash
   termux-setup-storage
   ```
   Izinkan akses storage saat diminta. Ini bikin folder `~/storage/downloads` tersedia (dipakai kalau opsi "Salin ke storage Termux" di Pengaturan diaktifkan).

## 🚀 Cara Menjalankan

Jalankan dari folder **root** proyek (bukan dari dalam folder `src`), karena `main.py` mengimpor modul dengan `from src.xxx import ...`:

```bash
python3 main.py
```

Pas start, aplikasi otomatis:
1. Ambil lock (`download/.lock`) — kalau ada proses lain (menu/CLI) yang masih jalan, aplikasi langsung keluar dengan pesan, nggak lanjut.
2. Cek singkat apakah yt-dlp kamu ketinggalan versi (nggak blocking, aman kalau offline) — kasih notice satu baris kalau perlu update.

## 🖥️ Menu Utama

```
1. Dashboard
2. Download video
3. Pengaturan
0. Keluar
```

### 1. Dashboard
Menampilkan daftar semua video/audio yang pernah diunduh (judul, resolusi/format, file, URL), plus **total jumlah item & ukuran disk** di bagian atas. Dari sini juga bisa:
- **Cari/filter** riwayat berdasarkan judul (nomor entri yang ditampilkan tetap nomor asli, jadi hapus tetap akurat walau lagi difilter)
- **Hapus satu entri** (opsional sekalian hapus file fisiknya)
- **Hapus semua riwayat** (opsional sekalian hapus semua file)

### 2. Download video
```
1. Download video (1)
2. Download video (banyak)
3. Download audio (1)
4. Download audio (banyak)
```
- Semua opsi otomatis mendukung playlist (URL playlist akan di-expand jadi daftar video/audio).
- Opsi "audio" menawarkan pilihan format (MP3/M4A/OPUS/FLAC/WAV) dan kualitas (khusus format lossy).
- Opsi "1 item" (video maupun audio) menawarkan pemotongan ke rentang waktu tertentu.
- Opsi "banyak" menawarkan sumber URL: ketik manual atau import dari file `.txt` (satu URL per baris, baris berawalan `#` diabaikan). Otomatis cek ruang disk kosong sebelum mulai.
- Kalau punya resolusi/format/kualitas default di Pengaturan, akan dipakai otomatis (dengan opsi override manual kalau nggak tersedia untuk video tersebut).
- Setiap file yang selesai diunduh diverifikasi dulu (bukan 0 byte / rusak) sebelum dicatat ke riwayat.

### 3. Pengaturan
```
 1. Resolusi default         (kosongkan = selalu tanya tiap download)
 2. Format audio default     (mp3/m4a/opus/flac/wav)
 3. Kualitas audio default   (128/192/256/320 kbps, cuma berlaku format lossy)
 4. Embed thumbnail/metadata (aktif/nonaktif)
 5. Subtitle default         (kode bahasa, misal id,en — kosongkan = nonaktif)
 6. Jumlah download paralel  (1 = berurutan/default, aman buat koneksi lambat)
 7. Jumlah percobaan ulang   (retry otomatis kalau gagal)
 8. File cookies             (path ke cookies.txt, buat konten yang butuh login)
 9. Notifikasi Termux        (aktif/nonaktif)
10. Susun folder hasil       (none/channel/date)
11. Salin ke storage Termux  (aktif/nonaktif, butuh termux-setup-storage)
12. Batas kecepatan unduh    (misal 2M, 500K; kosongkan = tanpa batas)
13. Cek & update yt-dlp      (cek versi + update langsung dari menu)
```
Semua pengaturan disimpan di `config.json` dan langsung dipakai di download berikutnya.

### 0. Keluar
Menutup program (lock otomatis dilepas). Ctrl+C di titik mana pun juga keluar dengan rapi (bukan traceback error, lock tetap dilepas).

## ⚡ Mode CLI (non-interaktif)

Berguna buat dipanggil dari script, cron, atau shortcut. Kalau `--url` atau `--url-file` diberikan, program langsung jalan tanpa masuk ke menu interaktif. Sama seperti mode menu, otomatis pakai lock file dan cek ruang disk — keduanya nggak pernah nge-block nunggu input, jadi aman buat dijadwalkan lewat cron.

```bash
# Download 1 video, resolusi 720p
python3 main.py --url "https://www.youtube.com/watch?v=xxxxxxx" --res 720

# Download beberapa video/playlist sekaligus, paralel 3, retry 2x
python3 main.py --url "URL_1" --url "URL_2_PLAYLIST" --parallel 3 --retry 2

# Download daftar URL dari file
python3 main.py --url-file daftar_url.txt --parallel 2

# Download sebagai audio FLAC (lossless)
python3 main.py --url "URL" --audio --audio-format flac

# Download sebagai MP3 kualitas 320kbps
python3 main.py --url "URL" --audio --audio-format mp3 --quality 320

# Download dengan subtitle Indonesia & Inggris
python3 main.py --url "URL" --sub id,en

# Batas kecepatan 2MB/s, pakai file cookies
python3 main.py --url "URL" --cookies cookies.txt --rate-limit 2M
```

Semua flag opsional selain `--url`/`--url-file`; kalau tidak diisi, nilai dari `config.json` (menu Pengaturan) yang dipakai sebagai default. Mode CLI tidak menawarkan potong durasi atau import subfolder interaktif — untuk itu pakai mode menu.

## 📄 Format `download.json`

```json
[
  {
    "id": "xxxxxxx",
    "title": "Judul Video",
    "filename": "download/Judul Video.mp4",
    "url": "https://www.youtube.com/watch?v=xxxxxxx",
    "resolution": "720p"
  },
  {
    "id": "yyyyyyy",
    "title": "Judul Audio",
    "filename": "download/Judul Audio.flac",
    "url": "https://www.youtube.com/watch?v=yyyyyyy",
    "resolution": "flac"
  }
]
```
- `id` adalah ID video dari platform asal (dipakai buat deteksi duplikat yang lebih akurat daripada judul saja). Entri lama tetap kompatibel (field `id`-nya `null`, fallback ke pencocokan judul).
- `resolution` untuk audio berisi `"{format}-{kualitas}kbps"` (mis. `"mp3-192kbps"`) untuk format lossy, atau cuma nama formatnya (mis. `"flac"`) untuk format lossless — supaya kualitas/format berbeda nggak dianggap duplikat.
- Cuma file yang **lolos verifikasi** (bukan 0 byte / rusak) yang dicatat di sini.

## 📱 Fitur Khusus Termux

| Fitur | Perintah setup |
|---|---|
| Notifikasi selesai-download | `pkg install termux-api` + install app Termux:API |
| Salin hasil ke Galeri/File Manager Android | `termux-setup-storage`, lalu aktifkan di Pengaturan > 11 |

Kedua fitur ini opsional dan otomatis di-skip diam-diam kalau perintah/izinnya belum ada — tidak bikin aplikasi error di sistem non-Termux.

## 📝 Log

Aktivitas (mulai/selesai unduhan, retry, verifikasi gagal, error) dicatat ke `download/app.log` dengan timestamp. File ini murni buat keperluan lacak/debug (terutama kalau dijalanin unattended lewat cron) — tidak pernah ditampilkan ke layar. Hapus manual kalau sudah kebesaran, tidak ada rotasi otomatis.

## 🔒 Lock File

Sebelum jalan, aplikasi membuat `download/.lock` berisi PID proses yang sedang aktif, dan menghapusnya otomatis saat keluar (termasuk saat Ctrl+C atau error). Kalau dijalankan lagi selagi ada proses lain yang masih aktif, aplikasi langsung keluar dengan pesan peringatan — mencegah dua proses rebutan baca-tulis `download.json` (misal nggak sengaja jalanin mode menu selagi cron mode CLI lagi jalan). Kalau proses sebelumnya crash dan lock-nya "nyangkut" (PID di dalamnya sudah nggak jalan), lock otomatis dianggap basi dan diambil alih di run berikutnya — nggak perlu dihapus manual, tapi bisa kalau mau: `rm download/.lock`.

## ⚠️ Catatan & Batasan

- Video dari X/Twitter (dan platform lain) harus berasal dari post **publik**, kecuali sudah pakai file cookies buat akun yang login.
- Deteksi duplikat memakai **ID video** kalau tersedia, fallback ke judul (case-insensitive) kalau tidak.
- Ketersediaan resolusi/subtitle/format tergantung pada apa yang disediakan platform untuk video tersebut.
- Embed thumbnail tidak berlaku untuk format WAV (keterbatasan format, bukan bug).
- Mode paralel mengunduh beberapa video sekaligus — pertimbangkan kecepatan koneksi, jangan set terlalu tinggi di jaringan yang lambat/terbatas (misal seluler). Progress bar realtime otomatis nonaktif di mode ini (diganti log ringkas per video) biar output beberapa thread nggak tumpang tindih.
- Potong durasi & pemilihan subfolder interaktif cuma tersedia buat download 1 item (bukan mode banyak/playlist/CLI).
- Verifikasi file pakai `ffprobe` kalau tersedia; kalau tidak, cuma dicek ukurannya (bukan 0 byte) — jadi validasinya nggak sedalam kalau `ffprobe` ada.
- Cek ruang disk kosong nggak memprediksi ukuran unduhan; cuma warning/batal berdasarkan sisa ruang saat itu, bukan estimasi total kebutuhan.
- Gunakan sesuai dengan [Ketentuan Layanan](https://www.youtube.com/t/terms) platform terkait dan hanya untuk konten yang Anda punya hak untuk mengunduhnya.

## 🛠️ Troubleshooting

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Jalankan `python3 main.py` dari folder root, bukan dari dalam `src/` |
| `HTTP Error 403: Forbidden` pas download | yt-dlp ketinggalan versi — update lewat menu Pengaturan > 13, atau manual: `pip install -U yt-dlp` |
| Error saat merge video+audio / convert audio / embed thumbnail | Pastikan `ffmpeg` sudah terinstall dan ada di PATH |
| Video tidak bisa diunduh | Pastikan link bersifat publik, atau pakai file cookies (Pengaturan > 8) buat konten privat |
| Notifikasi Termux tidak muncul | Pastikan `pkg install termux-api` sudah dijalankan DAN app Termux:API sudah diinstall dari F-Droid/Play Store |
| File tidak muncul di `~/storage/downloads` | Jalankan `termux-setup-storage` dulu, izinkan akses storage, baru aktifkan opsi di Pengaturan > 11 |
| Progress bar berantakan di mode paralel | Ini normal — mode paralel sengaja memakai log ringkas per video, bukan progress bar realtime, biar output beberapa thread tidak tumpang tindih |
| `pip install --upgrade yt-dlp` gagal dari menu Pengaturan | Beberapa sistem butuh izin tambahan — coba manual: `pip install -U yt-dlp --break-system-packages` (Termux/Debian modern) |
| "Ada proses lain yang masih jalan" padahal nggak ada | Proses sebelumnya kemungkinan crash tanpa sempat lepas lock. Hapus manual: `rm download/.lock`, lalu jalankan lagi |
| "gagal diverifikasi" terus padahal filenya kelihatan normal | Cek `ffprobe -version` — kalau error, reinstall/update ffmpeg. File yang gagal verifikasi nggak masuk riwayat, aman diunduh ulang |

## 📜 Lisensi

Bebas digunakan dan dimodifikasi untuk keperluan pribadi.