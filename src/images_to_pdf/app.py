"""
Images → PDF  (enhanced edition)

Features
────────
• Multi-folder support     – add images from many folders into one PDF
• Drag-to-reorder list     – click and drag rows, or use ↑/↓ (keyboard too)
• Remove individual items  – delete unwanted pages from the list
• Per-image rotation       – rotate any page 0 / 90 / 180 / 270 ° (right-click menu)
• Thumbnail previews       – see each page, not just its filename
• JPEG quality slider, or lossless PNG — trade file size vs. sharpness
• Page-size options        – Fit-to-image | A4 | Letter | A3 | A5 (centred on white)
• Duplicate detection      – MD5 hash check; warns but still lets you proceed
• Gap / sequence report    – shown in log when numeric naming is used
• EXIF auto-rotation       – portrait photos stay upright
• RGBA / palette fix       – transparent PNGs & GIFs convert cleanly
• Remembers your last output folder, quality, page size and format
• Cancel mid-conversion    – nothing is written to disk until the PDF is complete
• Open PDF or folder after – success dialog offers both
"""

import os
import sys
import threading
import time
from datetime import datetime, timezone

from PIL import ImageTk
from reportlab.lib.pagesizes import A3, A4, A5, letter
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from . import core
from .core import PageItem, SUPPORTED_EXTS, collect_images, find_gaps


# ── Constants ─────────────────────────────────────────────────────────────────

PAGE_SIZES = {
    "Fit to image": None,
    "A3  (297 × 420 mm)": A3,
    "A4  (210 × 297 mm)": A4,
    "A5  (148 × 210 mm)": A5,
    "Letter (8.5 × 11 in)": letter,
}

DARK_BG = "#0f1117"
CARD_BG = "#1a1d27"
BORDER = "#2a2d3a"
ACCENT = "#4f8ef7"
ACCENT_HOV = "#6aa3ff"
SUCCESS = "#3ecf8e"
ERROR_COL = "#f56565"
WARNING = "#f6ad55"
TEXT_PRI = "#e8eaf0"
TEXT_SEC = "#7b8099"
FONT_MONO = ("Consolas", 9)
FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 8)


# ── Main App ──────────────────────────────────────────────────────────────────


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Images → PDF")
        self.resizable(False, False)
        self.configure(bg=DARK_BG)
        self._center(600, 940)
        self._cancel_flag = threading.Event()
        self._items: list[PageItem] = []
        self._drag_iid = None
        self._settings = core.load_settings()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        root = tk.Frame(self, bg=DARK_BG)
        root.pack(fill="both", expand=True, padx=24, pady=20)

        self._style = ttk.Style(self)
        self._style.theme_use("default")

        tk.Label(
            root,
            text="Images → PDF",
            font=("Segoe UI Semibold", 18),
            bg=DARK_BG,
            fg=TEXT_PRI,
        ).pack(anchor="w")
        tk.Label(
            root,
            text="Build a PDF from any mix of image files.",
            font=FONT_BODY,
            bg=DARK_BG,
            fg=TEXT_SEC,
        ).pack(anchor="w", pady=(2, 16))

        # ── Pages section header ──
        add_row = tk.Frame(root, bg=DARK_BG)
        add_row.pack(fill="x", pady=(0, 4))
        tk.Label(
            add_row,
            text="PAGES",
            font=("Segoe UI Semibold", 8),
            bg=DARK_BG,
            fg=TEXT_SEC,
        ).pack(side="left", anchor="w")
        tk.Frame(add_row, bg=DARK_BG).pack(side="left", expand=True)
        self._flat_button(add_row, "+ Add folder", self._add_folder).pack(
            side="left", padx=(0, 6)
        )
        self._flat_button(add_row, "+ Add files", self._add_files).pack(side="left")

        # ── Page list (thumbnail + name, drag or ↑/↓ to reorder) ──
        list_frame = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        list_frame.pack(fill="x", pady=(4, 2))

        self._style.configure(
            "Pages.Treeview",
            background=CARD_BG,
            fieldbackground=CARD_BG,
            foreground=TEXT_PRI,
            borderwidth=0,
            rowheight=52,
            font=FONT_MONO,
        )
        self._style.map(
            "Pages.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#fff")],
        )

        self._tree = ttk.Treeview(
            list_frame,
            style="Pages.Treeview",
            show="tree",
            selectmode="extended",
            height=5,
        )
        self._tree.column("#0", stretch=True)
        lscroll = tk.Scrollbar(
            list_frame,
            command=self._tree.yview,
            bg=CARD_BG,
            troughcolor=CARD_BG,
            activebackground=BORDER,
            relief="flat",
            bd=0,
        )
        self._tree.configure(yscrollcommand=lscroll.set)
        self._tree.pack(side="left", fill="both", expand=True, padx=2, pady=4)
        lscroll.pack(side="right", fill="y", pady=4)
        self._tree.bind("<Button-3>", self._ctx_menu)
        self._tree.bind("<Button-2>", self._ctx_menu)
        self._tree.bind("<Up>", self._on_key_up)
        self._tree.bind("<Down>", self._on_key_down)
        self._tree.bind("<ButtonPress-1>", self._on_drag_start)
        self._tree.bind("<B1-Motion>", self._on_drag_motion)
        self._tree.bind("<ButtonRelease-1>", self._on_drag_end)

        act_row = tk.Frame(root, bg=DARK_BG)
        act_row.pack(fill="x", pady=(2, 12))
        self._list_hint = tk.Label(
            act_row,
            text="No images added yet.",
            font=FONT_SMALL,
            bg=DARK_BG,
            fg=TEXT_SEC,
            anchor="w",
        )
        self._list_hint.pack(side="left")
        self._flat_button(act_row, "↑", lambda: self._move(-1), padx=8).pack(
            side="right", padx=(4, 0)
        )
        self._flat_button(act_row, "↓", lambda: self._move(1), padx=8).pack(
            side="right", padx=(4, 0)
        )
        self._flat_button(act_row, "Remove", self._remove_selected, padx=10).pack(
            side="right", padx=(4, 0)
        )
        self._flat_button(act_row, "Clear all", self._clear_all, padx=10).pack(
            side="right"
        )

        # ── Output directory ──
        self._section(root, "OUTPUT DIRECTORY")
        out_frame = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        out_frame.pack(fill="x", pady=(4, 14))
        default_out = (
            os.path.expanduser("~\\Desktop")
            if sys.platform == "win32"
            else os.path.expanduser("~/Desktop")
        )
        self.outdir_var = tk.StringVar(
            value=self._settings.get("output_dir") or default_out
        )
        tk.Entry(
            out_frame,
            textvariable=self.outdir_var,
            font=FONT_BODY,
            bg=CARD_BG,
            fg=TEXT_PRI,
            insertbackground=ACCENT,
            relief="flat",
            highlightthickness=0,
            bd=0,
        ).pack(side="left", fill="both", expand=True, padx=(12, 0), pady=10)
        self._flat_button(out_frame, "Browse…", self._browse_out).pack(
            side="right", padx=8, pady=6
        )

        # ── Filename ──
        self._section(root, "OUTPUT FILENAME")
        fname_frame = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        fname_frame.pack(fill="x", pady=(4, 2))
        self.fname_var = tk.StringVar()
        tk.Entry(
            fname_frame,
            textvariable=self.fname_var,
            font=FONT_MONO,
            bg=CARD_BG,
            fg=TEXT_PRI,
            insertbackground=ACCENT,
            relief="flat",
            highlightthickness=0,
            bd=0,
        ).pack(side="left", fill="both", expand=True, padx=(12, 0), pady=10)
        tk.Label(
            fname_frame, text=".pdf", font=FONT_MONO, bg=CARD_BG, fg=TEXT_SEC
        ).pack(side="right", padx=(0, 12), pady=10)
        self._fname_hint = tk.Label(
            root, text="", font=FONT_SMALL, bg=DARK_BG, fg=TEXT_SEC, anchor="w"
        )
        self._fname_hint.pack(fill="x", pady=(2, 14))
        self._tick()

        # ── Options ──
        self._section(root, "OPTIONS")
        opt_card = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        opt_card.pack(fill="x", pady=(4, 14))
        inner = tk.Frame(opt_card, bg=CARD_BG)
        inner.pack(fill="x", padx=14, pady=10)

        tk.Label(
            inner, text="Page size", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC
        ).grid(row=0, column=0, sticky="w")
        saved_page_size = self._settings.get("page_size")
        self.pagesize_var = tk.StringVar(
            value=saved_page_size if saved_page_size in PAGE_SIZES else "Fit to image"
        )
        ps_menu = tk.OptionMenu(inner, self.pagesize_var, *PAGE_SIZES.keys())
        self._style_optionmenu(ps_menu)
        ps_menu.grid(row=0, column=1, sticky="w", padx=(8, 32))

        tk.Label(
            inner, text="JPEG quality", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC
        ).grid(row=0, column=2, sticky="w")
        self._quality_var = tk.IntVar(value=self._settings.get("quality", 90))
        self._quality_scale = tk.Scale(
            inner,
            variable=self._quality_var,
            from_=30,
            to=100,
            orient="horizontal",
            length=120,
            showvalue=False,
            bg=CARD_BG,
            fg=TEXT_PRI,
            troughcolor=BORDER,
            highlightthickness=0,
            relief="flat",
            bd=0,
            cursor="hand2",
        )
        self._quality_scale.grid(row=0, column=3, sticky="w", padx=(8, 6))
        self._q_label = tk.Label(
            inner, text="90", font=FONT_SMALL, bg=CARD_BG, fg=ACCENT, width=3
        )
        self._q_label.grid(row=0, column=4, sticky="w")
        self._quality_var.trace_add(
            "write", lambda *_: self._q_label.config(text=str(self._quality_var.get()))
        )

        tk.Label(
            inner, text="Format", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC
        ).grid(row=1, column=0, sticky="w", pady=(10, 0))
        initial_format = "PNG (lossless)" if self._settings.get("image_format") == "png" else "JPEG"
        self.format_var = tk.StringVar(value=initial_format)
        fmt_menu = tk.OptionMenu(inner, self.format_var, "JPEG", "PNG (lossless)")
        self._style_optionmenu(fmt_menu)
        fmt_menu.grid(row=1, column=1, sticky="w", padx=(8, 32), pady=(10, 0))
        self.format_var.trace_add("write", self._on_format_change)
        self._on_format_change()

        # ── Progress ──
        self._section(root, "PROGRESS")
        prog_card = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        prog_card.pack(fill="x", pady=(4, 4))
        self._style.configure(
            "Bar.Horizontal.TProgressbar",
            troughcolor=BORDER,
            background=ACCENT,
            thickness=6,
            borderwidth=0,
        )
        self._prog_var = tk.DoubleVar(value=0)
        ttk.Progressbar(
            prog_card,
            variable=self._prog_var,
            maximum=100,
            style="Bar.Horizontal.TProgressbar",
        ).pack(fill="x", padx=12, pady=(12, 6))
        sr = tk.Frame(prog_card, bg=CARD_BG)
        sr.pack(fill="x", padx=12, pady=(0, 8))
        self._status_label = tk.Label(
            sr, text="Waiting…", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC, anchor="w"
        )
        self._status_label.pack(side="left")
        self._pct_label = tk.Label(
            sr, text="", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC
        )
        self._pct_label.pack(side="right")

        # ── Log ──
        self._section(root, "LOG")
        log_frame = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        log_frame.pack(fill="x", pady=(4, 12))
        self._log = tk.Text(
            log_frame,
            font=FONT_MONO,
            bg=CARD_BG,
            fg=TEXT_SEC,
            relief="flat",
            bd=0,
            highlightthickness=0,
            state="disabled",
            wrap="none",
            height=5,
            selectbackground=ACCENT,
            insertbackground=ACCENT,
        )
        ls = tk.Scrollbar(
            log_frame,
            command=self._log.yview,
            bg=CARD_BG,
            troughcolor=CARD_BG,
            activebackground=BORDER,
            relief="flat",
            bd=0,
        )
        self._log.configure(yscrollcommand=ls.set)
        self._log.pack(side="left", fill="both", expand=True, padx=2, pady=4)
        ls.pack(side="right", fill="y", pady=4)
        for tag, color in [
            ("ok", SUCCESS),
            ("err", ERROR_COL),
            ("warn", WARNING),
            ("dim", TEXT_SEC),
            ("hi", TEXT_PRI),
            ("info", ACCENT),
        ]:
            self._log.tag_config(tag, foreground=color)

        # ── Buttons ──
        btn_row = tk.Frame(root, bg=DARK_BG)
        btn_row.pack(fill="x")
        self._convert_btn = tk.Button(
            btn_row,
            text="Convert to PDF",
            font=("Segoe UI Semibold", 11),
            bg=ACCENT,
            fg="#fff",
            activebackground=ACCENT_HOV,
            activeforeground="#fff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=12,
            command=self._start,
        )
        self._convert_btn.pack(side="left", fill="x", expand=True)
        self._convert_btn.bind(
            "<Enter>", lambda e: self._convert_btn.config(bg=ACCENT_HOV)
        )
        self._convert_btn.bind("<Leave>", lambda e: self._convert_btn.config(bg=ACCENT))
        self._cancel_btn = tk.Button(
            btn_row,
            text="Cancel",
            font=("Segoe UI Semibold", 11),
            bg=BORDER,
            fg=TEXT_PRI,
            activebackground=ERROR_COL,
            activeforeground="#fff",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=12,
            padx=20,
            command=self._cancel,
            state="disabled",
        )
        self._cancel_btn.pack(side="right", padx=(8, 0))

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(
            parent, text=text, font=("Segoe UI Semibold", 8), bg=DARK_BG, fg=TEXT_SEC
        ).pack(anchor="w")

    def _flat_button(self, parent, text, command, padx=14, pady=5):
        btn = tk.Button(
            parent,
            text=text,
            font=FONT_SMALL,
            bg=BORDER,
            fg=TEXT_PRI,
            activebackground=ACCENT,
            activeforeground="#fff",
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=padx,
            pady=pady,
            command=command,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT, fg="#fff"))
        btn.bind("<Leave>", lambda e: btn.config(bg=BORDER, fg=TEXT_PRI))
        return btn

    def _style_optionmenu(self, menu):
        menu.config(
            font=FONT_SMALL,
            bg=CARD_BG,
            fg=TEXT_PRI,
            activebackground=ACCENT,
            activeforeground="#fff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        menu["menu"].config(
            font=FONT_SMALL,
            bg=CARD_BG,
            fg=TEXT_PRI,
            activebackground=ACCENT,
            activeforeground="#fff",
            relief="flat",
        )

    def _on_format_change(self, *_):
        is_png = self.format_var.get().startswith("PNG")
        self._quality_scale.config(state="disabled" if is_png else "normal")

    def _make_filename(self):
        return f"output_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.pdf"

    def _tick(self):
        custom = self.fname_var.get().strip()
        self._fname_hint.config(
            text=(
                f"Will save as: {custom}.pdf"
                if custom
                else f"Leave blank to auto-name: {self._make_filename()}"
            )
        )
        self.after(1000, self._tick)

    def _log_write(self, msg, tag="dim"):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_status(self, text, pct=None):
        self._status_label.config(text=text)
        if pct is not None:
            self._prog_var.set(pct)
            self._pct_label.config(text=f"{pct:.0f}%")

    def _current_settings(self):
        return {
            "output_dir": self.outdir_var.get().strip() or None,
            "quality": self._quality_var.get(),
            "page_size": self.pagesize_var.get(),
            "image_format": "png" if self.format_var.get().startswith("PNG") else "jpeg",
        }

    def _on_close(self):
        core.save_settings(self._current_settings())
        self.destroy()

    # ── List management ───────────────────────────────────────────────────────

    def _thumbnail_for(self, item):
        try:
            pil_img = core.make_thumbnail(item.path, item.rotation)
            item.thumbnail = ImageTk.PhotoImage(pil_img)
        except Exception:
            item.thumbnail = None
        return item.thumbnail

    def _index_of_id(self, iid):
        for idx, item in enumerate(self._items):
            if item.id == iid:
                return idx
        return None

    def _selected_index(self):
        sel = self._tree.selection()
        if not sel:
            return None
        return self._index_of_id(sel[0])

    def _selected_indices(self):
        ids = set(self._tree.selection())
        return [i for i, item in enumerate(self._items) if item.id in ids]

    def _refresh_list(self, select_id=None):
        self._tree.delete(*self._tree.get_children())
        for item in self._items:
            thumb = item.thumbnail if item.thumbnail is not None else self._thumbnail_for(item)
            self._tree.insert("", "end", iid=item.id, text=item.display(), image=thumb)
        n = len(self._items)
        self._list_hint.config(
            text=(
                f"{n} page{'s' if n != 1 else ''} queued."
                if n
                else "No images added yet."
            ),
            fg=TEXT_PRI if n else TEXT_SEC,
        )
        if select_id and self._tree.exists(select_id):
            self._tree.selection_set(select_id)
            self._tree.focus(select_id)

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select image folder")
        if not folder:
            return
        names = collect_images(folder)
        if not names:
            messagebox.showwarning(
                "Empty folder",
                f"No supported images found.\nSupported: {', '.join(SUPPORTED_EXTS)}",
            )
            return
        for name in names:
            self._items.append(PageItem(os.path.join(folder, name)))
        gaps = find_gaps(names)
        self._refresh_list()
        self._log_write(
            f"  +  Added {len(names)} image(s) from {os.path.basename(folder)}", "info"
        )
        if gaps:
            gs = ", ".join(str(g) for g in gaps[:8])
            self._log_write(f"  ⚠  Missing number(s) in sequence: {gs}", "warn")

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[
                ("Images", " ".join(f"*{e}" for e in SUPPORTED_EXTS)),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        for path in paths:
            self._items.append(PageItem(path))
        self._refresh_list()
        self._log_write(f"  +  Added {len(paths)} file(s)", "info")

    def _remove_selected(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        for idx in sorted(idxs, reverse=True):
            del self._items[idx]
        self._refresh_list()

    def _clear_all(self):
        if self._items and not messagebox.askyesno(
            "Clear all", "Remove all pages from the list?"
        ):
            return
        self._items.clear()
        self._refresh_list()

    def _move(self, direction):
        idx = self._selected_index()
        if idx is None:
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._items):
            return
        self._items[idx], self._items[new_idx] = self._items[new_idx], self._items[idx]
        self._refresh_list(select_id=self._items[new_idx].id)

    def _on_key_up(self, event):
        self._move(-1)
        return "break"

    def _on_key_down(self, event):
        self._move(1)
        return "break"

    # ── Drag-to-reorder ───────────────────────────────────────────────────────

    def _on_drag_start(self, event):
        self._drag_iid = self._tree.identify_row(event.y)

    def _on_drag_motion(self, event):
        if not self._drag_iid:
            return
        target_iid = self._tree.identify_row(event.y)
        if not target_iid or target_iid == self._drag_iid:
            return
        from_idx = self._index_of_id(self._drag_iid)
        to_idx = self._index_of_id(target_iid)
        if from_idx is None or to_idx is None or from_idx == to_idx:
            return
        item = self._items.pop(from_idx)
        self._items.insert(to_idx, item)
        self._tree.move(self._drag_iid, "", to_idx)

    def _on_drag_end(self, event):
        self._drag_iid = None

    # ── Right-click menu ──────────────────────────────────────────────────────

    def _ctx_menu(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)
        idx = self._index_of_id(iid)
        if idx is None:
            return
        item = self._items[idx]

        menu = tk.Menu(
            self,
            tearoff=0,
            bg=CARD_BG,
            fg=TEXT_PRI,
            activebackground=ACCENT,
            activeforeground="#fff",
            relief="flat",
            bd=1,
        )
        menu.add_command(
            label=f"  {item.name}", state="disabled", font=("Segoe UI Semibold", 9)
        )
        menu.add_separator()
        for deg in (0, 90, 180, 270):
            label = f"  Rotate {deg}°" + ("  ✓" if item.rotation == deg else "")
            menu.add_command(
                label=label, command=lambda d=deg, i=idx: self._set_rotation(i, d)
            )
        menu.add_separator()
        menu.add_command(
            label="  Move up",
            command=lambda: self._move(-1),
            state="normal" if idx > 0 else "disabled",
        )
        menu.add_command(
            label="  Move down",
            command=lambda: self._move(1),
            state="normal" if idx < len(self._items) - 1 else "disabled",
        )
        menu.add_separator()
        menu.add_command(label="  Remove", command=self._remove_selected)
        menu.tk_popup(event.x_root, event.y_root)

    def _set_rotation(self, idx, degrees):
        item = self._items[idx]
        item.rotation = degrees
        item.thumbnail = None
        self._refresh_list(select_id=item.id)

    # ── Browse ────────────────────────────────────────────────────────────────

    def _browse_out(self):
        folder = filedialog.askdirectory(title="Select output directory")
        if folder:
            self.outdir_var.set(folder)

    # ── Conversion ────────────────────────────────────────────────────────────

    def _cancel(self):
        self._cancel_flag.set()
        self._cancel_btn.config(state="disabled")
        self._set_status("Cancelling…")

    def _start(self):
        if not self._items:
            messagebox.showwarning(
                "No images", "Add at least one image before converting."
            )
            return

        outdir = self.outdir_var.get().strip() or os.getcwd()
        custom = self.fname_var.get().strip()
        fname = (
            (custom[:-4] if custom.lower().endswith(".pdf") else custom) + ".pdf"
            if custom
            else self._make_filename()
        )
        out_path = os.path.join(outdir, fname)

        if os.path.exists(out_path):
            if not messagebox.askyesno(
                "File exists",
                f'"{fname}" already exists in that folder.\n\nOverwrite it?',
            ):
                return

        core.save_settings(self._current_settings())

        # Read every Tk variable here, on the main thread — _run() executes on
        # a background thread, and Tkinter variables aren't safe to touch from
        # anywhere else.
        quality = self._quality_var.get()
        target_page = PAGE_SIZES[self.pagesize_var.get()]
        pg_label = self.pagesize_var.get().split("(")[0].strip()
        image_format = "png" if self.format_var.get().startswith("PNG") else "jpeg"

        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._cancel_flag.clear()
        self._set_status("Starting…", 0)
        self._convert_btn.config(state="disabled", text="Converting…", bg="#2a2d3a")
        self._cancel_btn.config(state="normal")
        items_snapshot = list(self._items)
        threading.Thread(
            target=self._run,
            args=(items_snapshot, out_path, fname, quality, target_page, pg_label, image_format),
            daemon=True,
        ).start()

    def _run(self, items, out_path, fname, quality, target_page, pg_label, image_format):
        start_t = time.time()
        total = len(items)

        dups = core.find_duplicates(items)
        if dups:
            msg = "\n".join(f"  • {b} ≡ {a}" for b, a in dups[:5])
            if len(dups) > 5:
                msg += f"\n  … and {len(dups)-5} more"
            proceed = [None]
            ev = threading.Event()

            def ask():
                proceed[0] = messagebox.askyesno(
                    "Duplicate images detected",
                    f"These images appear identical:\n\n{msg}\n\nContinue anyway?",
                )
                ev.set()

            self.after(0, ask)
            ev.wait()
            if not proceed[0]:
                self.after(0, lambda: self._finish_cancelled(None))
                return

        fmt_label = "PNG (lossless)" if image_format == "png" else f"JPEG q{quality}"
        self.after(
            0,
            lambda: self._log_write(
                f"Converting {total} page(s) → {fname}   "
                f"[{fmt_label}, size={pg_label}]",
                "hi",
            ),
        )
        if dups:
            self.after(
                0,
                lambda: self._log_write(
                    f"  ⚠  {len(dups)} duplicate(s) included by choice", "warn"
                ),
            )

        def on_progress(i, tot, item, success, err):
            pct = (i / tot) * 100
            self.after(
                0,
                lambda n=item.name, p=pct, idx=i: self._set_status(
                    f"[{idx}/{tot}]  {n}", p
                ),
            )
            if success:
                self.after(0, lambda n=item.name: self._log_write(f"  ✓  {n}", "ok"))
            else:
                self.after(
                    0,
                    lambda n=item.name, e=err: self._log_write(
                        f"  ✗  {n}: {e}", "err"
                    ),
                )

        try:
            processed, errors = core.build_pdf(
                items,
                out_path,
                quality=quality,
                page_size=target_page,
                image_format=image_format,
                on_progress=on_progress,
                cancel_event=self._cancel_flag,
            )
        except core.Cancelled:
            self.after(0, lambda: self._finish_cancelled(out_path))
            return
        except Exception as e:
            self.after(0, lambda: self._finish_error(f"Fatal error: {e}"))
            return

        elapsed = time.time() - start_t
        self.after(0, lambda: self._finish_ok(processed, errors, out_path, elapsed))

    def _finish_ok(self, processed, errors, out_path, elapsed):
        self._set_status("Done", 100)
        self._cancel_btn.config(state="disabled")
        self._log_write("")
        self._log_write(
            f"  ✓  {processed} page{'s' if processed != 1 else ''} written   "
            f"│  {core.format_size(out_path)}   │  {elapsed:.2f}s",
            "ok",
        )
        self._log_write(f"  ↳  {out_path}", "hi")
        if errors:
            self._log_write(f"  ⚠  {len(errors)} file(s) skipped", "warn")
        self._convert_btn.config(state="normal", text="Convert to PDF", bg=ACCENT)

        choice = messagebox.askquestion(
            "Done!",
            f"PDF created with {processed} page(s).\n\nSaved to:\n{out_path}\n\n"
            "Yes → Open PDF     No → Open folder     Cancel → Dismiss",
            type="yesnocancel",
            icon="info",
            default="yes",
        )
        if choice == "yes":
            self._open_file(out_path)
        elif choice == "no":
            self._open_folder(os.path.dirname(out_path))

    def _finish_cancelled(self, out_path):
        self._set_status("Cancelled", 0)
        self._cancel_btn.config(state="disabled")
        self._convert_btn.config(state="normal", text="Convert to PDF", bg=ACCENT)
        self._log_write("  ✗  Conversion cancelled.", "warn")
        if out_path:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                pass

    def _finish_error(self, msg):
        self._set_status("Failed", 0)
        self._cancel_btn.config(state="disabled")
        self._log_write(f"  ✗  {msg}", "err")
        self._convert_btn.config(state="normal", text="Convert to PDF", bg=ACCENT)
        messagebox.showerror("Error", msg)

    def _open_file(self, path):
        import subprocess

        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            self._open_folder(os.path.dirname(path))

    def _open_folder(self, path):
        import subprocess

        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
