# YouTube/X Video Downloader

Script Python3 untuk mengunduh video dari **YouTube** dan **X (Twitter)** dengan pilihan resolusi video, mendukung download satu video maupun banyak video sekaligus. Riwayat download dicatat otomatis agar tidak ada duplikasi.

## ✨ Fitur

- Download video dari YouTube dan X (Twitter)
- Pilih resolusi video sebelum mengunduh (atau otomatis kualitas terbaik)
- Mode download 1 video atau banyak video (batch)
- Progress bar realtime saat mengunduh
- Riwayat download tersimpan di `download/download.json`
- Deteksi otomatis jika video sudah pernah diunduh (mencegah duplikat)
- Dashboard untuk melihat riwayat semua video yang sudah diunduh
- Folder `download/` dibuat otomatis jika belum ada

## 📁 Struktur Proyek

```
project/
├── main.py                  # Menu utama (Dashboard, Download, Exit)
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── dashboard.py         # Logika tampilan dashboard/riwayat
│   ├── loading.py           # Progress bar realtime saat download
│   ├── download.py          # Logika download (single & banyak)
│   └── manager.py           # Kelola folder & file download.json
└── download/                 # Dibuat otomatis, berisi hasil unduhan
    └── download.json         # Dibuat otomatis, riwayat download
```

## 🔧 Persyaratan

- Python 3.8 atau lebih baru
- [ffmpeg](https://ffmpeg.org/) (untuk menggabungkan video + audio)

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

4. Install ffmpeg (wajib, tidak bisa lewat pip):

   | Sistem | Perintah |
   |---|---|
   | Ubuntu/Debian | `sudo apt install ffmpeg` |
   | macOS (Homebrew) | `brew install ffmpeg` |
   | Windows | Download dari [ffmpeg.org](https://ffmpeg.org/download.html) lalu tambahkan ke PATH |
   | Termux (Android) | `pkg install ffmpeg` |

5. Verifikasi ffmpeg terinstall:
   ```bash
   ffmpeg -version
   ```

## 🚀 Cara Menjalankan

Jalankan dari folder **root** proyek (bukan dari dalam folder `src`), karena `main.py` mengimpor modul dengan `from src.xxx import ...`:

```bash
python3 main.py
```

## 🖥️ Menu Utama

Setelah dijalankan, akan muncul menu:

```
===== YOUTUBE/X DOWNLOADER =====
1. Dashboard
2. Download video
3. Keluar
```

### 1. Dashboard
Menampilkan daftar semua video yang pernah diunduh, beserta resolusi, nama file, dan URL asalnya.

### 2. Download video
Akan muncul submenu:
```
1. Download 1 video
2. Download banyak video
```

**Download 1 video:**
1. Masukkan URL video (YouTube atau X)
2. Pilih resolusi dari daftar yang ditampilkan (atau pilih opsi "Terbaik")
3. Video akan diunduh ke folder `download/`

**Download banyak video:**
1. Masukkan URL satu per satu, tekan Enter setiap selesai satu URL
2. Ketik `selesai` jika sudah selesai memasukkan semua URL
3. Pilih resolusi (berlaku untuk semua video dalam batch)
4. Semua video akan diunduh berurutan, dengan ringkasan hasil di akhir (berhasil/dilewati/gagal)

### 3. Keluar
Menutup program.

## 📝 Contoh Penggunaan

```
===== YOUTUBE/X DOWNLOADER =====
1. Dashboard
2. Download video
3. Keluar
Pilih menu: 2

1. Download 1 video
2. Download banyak video
Pilih opsi: 1
Masukkan URL video: https://www.youtube.com/watch?v=xxxxxxx

Resolusi tersedia:
  [0] 1080p (mp4)
  [1] 720p (mp4)
  [2] 480p (mp4)
  [3] Terbaik (auto)
Pilih nomor resolusi: 1

⬇️  Judul Video.mp4 | 45.2% @ 3.1MiB/s ETA 00:12
🔧 Memproses/menggabungkan file...

✅ Selesai! 'Judul Video' berhasil diunduh.
```

## 📄 Format `download.json`

Riwayat download disimpan otomatis dengan struktur:

```json
[
  {
    "title": "Judul Video",
    "filename": "download/Judul Video.mp4",
    "url": "https://www.youtube.com/watch?v=xxxxxxx",
    "resolution": "720p"
  }
]
```

## ⚠️ Catatan & Batasan

- Video dari X/Twitter harus berasal dari post **publik** (bukan akun private/protected).
- Deteksi video duplikat berdasarkan **judul video** (case-insensitive), bukan URL — jadi video dengan judul sama dari sumber berbeda akan dianggap sudah ada.
- Ketersediaan resolusi tergantung pada apa yang disediakan oleh platform untuk video tersebut; tidak semua video punya semua resolusi.
- Kecepatan download tergantung koneksi internet dan pembatasan dari pihak YouTube/X.
- Gunakan sesuai dengan [Ketentuan Layanan](https://www.youtube.com/t/terms) platform terkait dan hanya untuk konten yang Anda punya hak untuk mengunduhnya.

## 🛠️ Troubleshooting

| Masalah | Solusi |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Jalankan `python3 main.py` dari folder root, bukan dari dalam `src/` |
| Error saat merge video+audio | Pastikan `ffmpeg` sudah terinstall dan ada di PATH |
| `yt_dlp` gagal ambil info video | Update ke versi terbaru: `pip install -U yt-dlp` |
| Video tidak bisa diunduh dari X | Pastikan link post bersifat publik, bukan private/protected |

## 📜 Lisensi

Bebas digunakan dan dimodifikasi untuk keperluan pribadi.
