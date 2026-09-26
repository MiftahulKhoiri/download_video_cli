# Tests

Uji unit ringan, tanpa jaringan dan tanpa yt-dlp beneran (cuma nguji fungsi
murni: parsing, path, riwayat/duplikat, dll). Jalankan dari folder root proyek:

```bash
python3 -m unittest discover -s tests -v
```

Ini BUKAN pengganti uji manual pakai yt-dlp asli (lihat README.md bagian
Troubleshooting) -- cuma jaring pengaman cepat buat logika yang nggak
butuh koneksi internet.
