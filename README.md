# YouTube/X Video & Audio Downloader

Script Python3 untuk mengunduh video dan audio dari **YouTube** dan **X (Twitter)** — juga situs lain yang didukung `yt-dlp` (TikTok, Instagram, Facebook, dll, tinggal masukkan URL-nya). Mendukung download satu item maupun banyak sekaligus (termasuk playlist), berbagai format audio, potong durasi, folder penyimpanan bisa dikustomisasi, riwayat otomatis anti-duplikat, verifikasi hasil download, mode interaktif maupun CLI non-interaktif, dan pengaturan yang bisa disimpan.

## ✨ Fitur

**Download**
- Video dari YouTube, X (Twitter), dan situs lain yang didukung `yt-dlp`
- Audio dalam **5 format**: MP3, M4A, OPUS, FLAC, WAV — kualitas bisa dipilih (128/192/256/320 kbps untuk format lossy)
- **Playlist otomatis di-expand** jadi daftar video/audio individual
- **Potong ke rentang waktu tertentu** (mis. cuma ambil menit 1:30–2:45), tanpa unduh video penuh — hasil potongan dicatat & disimpan terpisah dari video penuh/potongan lain (rentang waktu ikut jadi bagian nama file & penanda riwayat), jadi nggak saling dianggap duplikat atau saling menimpa
- Pilih resolusi video sebelum mengunduh (atau otomatis kualitas terbaik / default tersimpan)
- Mode 1 item, banyak (batch, bisa ketik manual atau **import dari file `.txt`**), atau **download paralel**
- **Retry otomatis** kalau gagal — berlaku baik pas ambil info/metadata video maupun pas proses download filenya
- **Subtitle/caption** opsional (manual + auto-generated), bisa multi-bahasa
- **Embed thumbnail + metadata** (judul dll) otomatis ke file audio
- Batas kecepatan download (rate limit) opsional

**Keandalan**
- **Verifikasi file hasil download** — deteksi file 0 byte / rusak (pakai `ffprobe` kalau tersedia) sebelum disimpan ke riwayat, jadi file yang gagal nggak dianggap sukses
- **Penyimpanan riwayat & pengaturan tahan crash** — `download.json` dan `config.json` ditulis secara atomic (lewat file sementara + rename), jadi nggak bakal kepotong/rusak walau proses mati mendadak di tengah penulisan (mati listrik, force-close, dll)
- **Cek ruang disk kosong** sebelum mulai download banyak/paralel — batal otomatis kalau kritis, warning kalau menipis (nggak pernah nge-block nunggu input, aman buat cron)
- **Lock file** — cegah dua proses (mode menu & mode CLI, atau dua CLI/cron sekaligus) jalan bersamaan dan rebutan tulis `download.json`
- **Wake-lock Termux yang akurat di mode paralel** — HP nggak bakal ketiduran duluan di tengah proses walau ada beberapa download paralel yang selesai di waktu berbeda-beda (lock baru dilepas setelah SEMUA proses dalam batch selesai)
- Ctrl+C ditangani rapi — file `.part`/`.ytdl` sisa otomatis dibersihkan, bukan nyangkut jadi sampah

**Organisasi & riwayat**
- **Folder penyimpanan hasil download bisa dikustomisasi** — atur lewat menu Pengaturan atau flag `--output-dir`, kosongkan buat pakai folder default `download/`. Kalau folder yang diisi ternyata bermasalah (path salah, storage belum ke-mount, izin ditolak), otomatis fallback ke folder default + kasih peringatan, jadi download nggak gagal total gara-gara satu pengaturan yang keliru
- Riwayat tersimpan di `download/download.json` (selalu di folder internal app, terpisah dari folder penyimpanan hasil di atas), deteksi duplikat pakai **ID video** (bukan cuma judul)
- Dashboard: **total jumlah & ukuran file**, **cari/filter riwayat** by judul, **urutkan** (terbaru/terlama/ukuran/judul), **hapus satu entri atau semua riwayat** (opsional sekalian hapus filenya)
- **Auto-organize folder hasil download**: rata (default), per channel, atau per tanggal upload — dibuat sebagai subfolder di dalam folder penyimpanan yang aktif
- Log aktivitas & error otomatis ke `download/app.log` — berguna kalau dijalanin unattended/cron
- Menu **Tentang** — lihat versi aplikasi, yt-dlp, ffmpeg, dan Python yang lagi kepakai

**Kenyamanan & Termux**
- **Cek & update yt-dlp** — notice otomatis pas start kalau ketinggalan versi + tombol update di menu Pengaturan (yt-dlp yang outdated adalah penyebab paling umum error 403)
- Notifikasi Android via Termux:API setelah download selesai
- Opsi **salin otomatis ke `~/storage/downloads`** biar file muncul di Galeri/File Manager Android (independen dari folder penyimpanan kustom — bisa dipakai bareng)
- Tema warna menu bisa disesuaikan (latar & tulisan, 8 pilihan warna terminal standar)
- **Mode CLI non-interaktif** (`--url ...` / `--url-file ...`) buat dipanggil dari script/automation
- Dukungan file cookies buat konten yang butuh login
- Folder `download/` dibuat otomatis jika belum ada

## 📁 Struktur Proyek
project/
├── main.py                    # Menu utama + mode CLI non-interaktif
├── requirements.txt
├── README.md
├── config.json                 # Dibuat otomatis saat pengaturan pertama kali diubah
├── src/
│   ├── init.py
│   ├── tui.py                # Widget menu/input ala raspi-config (curses), tema warna
│   ├── dashboard.py          # Tampilan dashboard/riwayat, total ukuran, cari/filter/urutkan, hapus entri
│   ├── download_menu.py      # Alur menu interaktif buat download (pilih resolusi/format/potong durasi, dll)
│   ├── download_core.py      # Mesin download inti: single/batch/paralel/retry/potong durasi/verifikasi
│   ├── media_info.py         # Ambil info video & expand playlist (dengan retry)
│   ├── manager.py            # Kelola download.json (riwayat) + folder tujuan hasil download
│   ├── config.py             # Baca/simpan pengaturan (config.json) + menu Pengaturan
│   ├── loading.py            # Progress bar, spinner, print thread-safe, format ukuran file
│   ├── updater.py            # Cek & update yt-dlp
│   ├── logger.py             # Logger ke download/app.log
│   ├── lock.py               # Cegah proses ganda jalan bersamaan
│   ├── notify.py             # Notifikasi Android + wake-lock via Termux:API
│   └── logo.py                 # ASCII logo & animasi intro
└── download/                    # Folder INTERNAL app, dibuat otomatis
├── download.json            # Riwayat download
├── app.log                  # Log aktivitas & error
├── .lock                    # Lock sementara selagi aplikasi jalan
└──          # Video/audio hasil unduhan -- ADA DI SINI cuma kalau
# "Folder Penyimpanan" di Pengaturan dikosongkan (default)


