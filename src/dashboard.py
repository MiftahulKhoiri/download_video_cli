import os

from src.manager import load_history, delete_entry, clear_history
from src.loading import format_size
from src import tui


def _total_size(history):
    total = 0
    for item in history:
        fn = item.get("filename")
        if fn and os.path.exists(fn):
            try:
                total += os.path.getsize(fn)
            except OSError:
                pass
    return total


def _konfirmasi_hapus_satu(stdscr, real_index, item):
    pilih = tui.menu(
        stdscr, "Hapus Entri",
        ["Ya, hapus dari riwayat saja", "Ya, hapus + file fisiknya", "Batal"],
        message=f"'{item.get('title')}'",
    )
    if pilih == 0:
        delete_entry(real_index, remove_file=False)
        tui.message_box(stdscr, "Terhapus", f"'{item.get('title')}' dihapus dari riwayat.")
    elif pilih == 1:
        delete_entry(real_index, remove_file=True)
        tui.message_box(stdscr, "Terhapus", f"'{item.get('title')}' dihapus beserta filenya.")


def _detail_entry(stdscr, real_index, item):
    detail = [
        f"Judul    : {item.get('title')}",
        f"Resolusi : {item.get('resolution')}",
        f"File     : {item.get('filename')}",
        f"URL      : {item.get('url')}",
    ]
    pilih = tui.menu(stdscr, "Detail Entri", ["Hapus entri ini", "Kembali"], message=detail)
    if pilih == 0:
        _konfirmasi_hapus_satu(stdscr, real_index, item)


def _hapus_semua_tui(stdscr):
    pilih = tui.menu(
        stdscr, "Hapus Semua Riwayat",
        ["Ya, hapus riwayat saja", "Ya, hapus + semua file", "Batal"],
        message="Tindakan ini nggak bisa dibatalkan!",
    )
    if pilih == 0:
        count = clear_history(remove_files=False)
        tui.message_box(stdscr, "Terhapus", f"{count} entri riwayat dihapus.")
    elif pilih == 1:
        count = clear_history(remove_files=True)
        tui.message_box(stdscr, "Terhapus", f"{count} entri riwayat dihapus beserta filenya.")


def run_dashboard_menu(stdscr):
    """Loop dashboard TUI, dipanggil dari main dengan stdscr dari sesi curses yang sama."""
    keyword = None
    while True:
        history = load_history()
        if not history:
            tui.message_box(stdscr, "DASHBOARD", "Belum ada video yang diunduh.")
            return

        if keyword:
            indexed = [(i, item) for i, item in enumerate(history)
                       if keyword.lower() in item.get("title", "").lower()]
        else:
            indexed = list(enumerate(history))

        items = [f"{item.get('title', '?')}  [{item.get('resolution', '?')}]" for _, item in indexed]
        n_items = len(items)

        cari_label = f'🔍 Ganti/hapus filter ("{keyword}")' if keyword else "🔍 Cari/filter..."
        actions = [cari_label, "🗑️  Hapus SEMUA riwayat", "Kembali"]
        full_items = items + actions

        msg = [f"Total: {len(history)} item · {format_size(_total_size(history))}"]
        if keyword:
            msg.append(f'Filter aktif: "{keyword}" ({n_items} cocok)')
            if n_items == 0:
                msg.append("Nggak ada yang cocok.")

        idx = tui.menu(stdscr, "DASHBOARD", full_items, message=msg)
        if idx is None or idx == len(full_items) - 1:  # Kembali
            return

        if idx < n_items:
            real_index, item = indexed[idx]
            _detail_entry(stdscr, real_index + 1, item)
        elif idx == n_items:  # Cari/filter
            kata = tui.input_box(
                stdscr, "Cari/Filter",
                "Kata kunci judul (kosongkan = tampilkan semua):",
                initial=keyword or "",
            )
            if kata is not None:
                keyword = kata.strip() or None
        elif idx == n_items + 1:  # Hapus semua
            _hapus_semua_tui(stdscr)