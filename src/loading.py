import os
import sys


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def progress_hook(d):
    if d["status"] == "downloading":
        pct = d.get("_percent_str", "").strip()
        speed = d.get("_speed_str", "").strip()
        eta = d.get("_eta_str", "").strip()
        filename = d.get("filename", "")
        short_name = filename.split("/")[-1][:40]
        sys.stdout.write(f"\r⬇️  {short_name} | {pct} @ {speed} ETA {eta}   ")
        sys.stdout.flush()
    elif d["status"] == "finished":
        print("\n🔧 Memproses/menggabungkan file...")
    elif d["status"] == "error":
        print("\n❌ Terjadi error saat mengunduh.")