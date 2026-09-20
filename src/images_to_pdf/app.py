"""
Images → PDF  (enhanced edition)

Features
────────
• Multi-folder support     – add images from many folders into one PDF
• Drag-to-reorder list     – rearrange pages before converting (keyboard ↑↓ too)
• Remove individual items  – delete unwanted pages from the list
• Per-image rotation       – rotate any page 0 / 90 / 180 / 270 ° (right-click menu)
• JPEG quality slider      – trade file size vs. sharpness
• Page-size options        – Fit-to-image | A4 | Letter | A3 | A5 (centred on white)
• Duplicate detection      – MD5 hash check; warns but still lets you proceed
• Gap / sequence report    – shown in log when numeric naming is used
• EXIF auto-rotation       – portrait photos stay upright
• RGBA / palette fix       – transparent PNGs & GIFs convert cleanly
• Cancel mid-conversion    – cleans up partial PDF
• Open PDF or folder after – success dialog offers both
"""

import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

from PIL import Image
from reportlab.lib.pagesizes import A3, A4, A5, letter
from reportlab.pdfgen import canvas
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .core import (
    PageItem,
    SUPPORTED_EXTS,
    collect_images,
    find_gaps,
    fix_image,
    format_size,
    md5_of,
    rotate_pil,
)


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
        self._center(580, 860)
        self._cancel_flag = threading.Event()
        self._items: list[PageItem] = []
        self._build()

    def _center(self, w, h):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        root = tk.Frame(self, bg=DARK_BG)
        root.pack(fill="both", expand=True, padx=24, pady=20)

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

        # ── Page list ──
        list_frame = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        list_frame.pack(fill="x", pady=(4, 2))
        self._listbox = tk.Listbox(
            list_frame,
            font=FONT_MONO,
            bg=CARD_BG,
            fg=TEXT_PRI,
            selectbackground=ACCENT,
            selectforeground="#fff",
            relief="flat",
            bd=0,
            highlightthickness=0,
            activestyle="none",
            height=9,
        )
        lscroll = tk.Scrollbar(
            list_frame,
            command=self._listbox.yview,
            bg=CARD_BG,
            troughcolor=CARD_BG,
            activebackground=BORDER,
            relief="flat",
            bd=0,
        )
        self._listbox.configure(yscrollcommand=lscroll.set)
        self._listbox.pack(side="left", fill="both", expand=True, padx=2, pady=4)
        lscroll.pack(side="right", fill="y", pady=4)
        self._listbox.bind("<Button-3>", self._ctx_menu)
        self._listbox.bind("<Button-2>", self._ctx_menu)
        self._listbox.bind("<Up>", lambda e: self._move(-1))
        self._listbox.bind("<Down>", lambda e: self._move(1))

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
        self.outdir_var = tk.StringVar(value=default_out)
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
        self.pagesize_var = tk.StringVar(value="Fit to image")
        ps_menu = tk.OptionMenu(inner, self.pagesize_var, *PAGE_SIZES.keys())
        ps_menu.config(
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
        ps_menu["menu"].config(
            font=FONT_SMALL,
            bg=CARD_BG,
            fg=TEXT_PRI,
            activebackground=ACCENT,
            activeforeground="#fff",
            relief="flat",
        )
        ps_menu.grid(row=0, column=1, sticky="w", padx=(8, 32))

        tk.Label(
            inner, text="JPEG quality", font=FONT_SMALL, bg=CARD_BG, fg=TEXT_SEC
        ).grid(row=0, column=2, sticky="w")
        self._quality_var = tk.IntVar(value=90)
        tk.Scale(
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
        ).grid(row=0, column=3, sticky="w", padx=(8, 6))
        self._q_label = tk.Label(
            inner, text="90", font=FONT_SMALL, bg=CARD_BG, fg=ACCENT, width=3
        )
        self._q_label.grid(row=0, column=4, sticky="w")
        self._quality_var.trace_add(
            "write", lambda *_: self._q_label.config(text=str(self._quality_var.get()))
        )

        # ── Progress ──
        self._section(root, "PROGRESS")
        prog_card = tk.Frame(
            root, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1
        )
        prog_card.pack(fill="x", pady=(4, 4))
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure(
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

    # ── List management ───────────────────────────────────────────────────────

    def _refresh_list(self):
        self._listbox.delete(0, "end")
        for item in self._items:
            self._listbox.insert("end", item.display())
        n = len(self._items)
        self._list_hint.config(
            text=(
                f"{n} page{'s' if n != 1 else ''} queued."
                if n
                else "No images added yet."
            ),
            fg=TEXT_PRI if n else TEXT_SEC,
        )

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
        sel = self._listbox.curselection()
        if not sel:
            return
        for idx in reversed(sel):
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
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(self._items):
            return
        self._items[idx], self._items[new_idx] = self._items[new_idx], self._items[idx]
        self._refresh_list()
        self._listbox.selection_set(new_idx)
        self._listbox.activate(new_idx)
        self._listbox.see(new_idx)

    # ── Right-click menu ──────────────────────────────────────────────────────

    def _ctx_menu(self, event):
        idx = self._listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._items):
            return
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
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
        self._items[idx].rotation = degrees
        self._refresh_list()
        self._listbox.selection_set(idx)

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
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        self._cancel_flag.clear()
        self._set_status("Starting…", 0)
        self._convert_btn.config(state="disabled", text="Converting…", bg="#2a2d3a")
        self._cancel_btn.config(state="normal")
        items_snapshot = list(self._items)
        threading.Thread(target=self._run, args=(items_snapshot,), daemon=True).start()

    def _run(self, items):
        start_t = time.time()
        total = len(items)
        quality = self._quality_var.get()
        target_page = PAGE_SIZES[self.pagesize_var.get()]

        # ── Duplicate detection ──
        seen, dups = {}, []
        for item in items:
            try:
                h = md5_of(item.path)
                if h in seen:
                    dups.append((item.name, seen[h]))
                else:
                    seen[h] = item.name
            except Exception:
                pass

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

        # Build output path
        outdir = self.outdir_var.get().strip() or os.getcwd()
        custom = self.fname_var.get().strip()
        fname = (
            (custom[:-4] if custom.lower().endswith(".pdf") else custom) + ".pdf"
            if custom
            else self._make_filename()
        )
        out_path = os.path.join(outdir, fname)

        pg_label = self.pagesize_var.get().split("(")[0].strip()
        self.after(
            0,
            lambda: self._log_write(
                f"Converting {total} page(s) → {fname}   "
                f"[quality={quality}, size={pg_label}]",
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

        errors, processed = [], 0

        try:
            c = canvas.Canvas(out_path)
            for i, item in enumerate(items, 1):
                if self._cancel_flag.is_set():
                    self.after(0, lambda: self._finish_cancelled(out_path))
                    return

                pct = (i / total) * 100
                self.after(
                    0,
                    lambda n=item.name, p=pct, idx=i: self._set_status(
                        f"[{idx}/{total}]  {n}", p
                    ),
                )

                try:
                    with Image.open(item.path) as raw:
                        img = fix_image(raw.copy())
                    if item.rotation:
                        img = rotate_pil(img, item.rotation)

                    img_w, img_h = img.size

                    if target_page is None:
                        page_w, page_h = float(img_w), float(img_h)
                        draw_x, draw_y, draw_w, draw_h = 0.0, 0.0, page_w, page_h
                    else:
                        page_w, page_h = target_page
                        scale = min(page_w / img_w, page_h / img_h)
                        draw_w = img_w * scale
                        draw_h = img_h * scale
                        draw_x = (page_w - draw_w) / 2
                        draw_y = (page_h - draw_h) / 2

                    c.setPageSize((page_w, page_h))

                    with tempfile.NamedTemporaryFile(
                        suffix=".jpg", delete=False
                    ) as tmp:
                        tmp_path = tmp.name
                    img.save(tmp_path, format="JPEG", quality=quality)
                    c.drawImage(tmp_path, draw_x, draw_y, width=draw_w, height=draw_h)
                    os.unlink(tmp_path)

                    c.showPage()
                    processed += 1
                    self.after(
                        0, lambda n=item.name: self._log_write(f"  ✓  {n}", "ok")
                    )

                except Exception as e:
                    errors.append((item.name, str(e)))
                    self.after(
                        0,
                        lambda n=item.name, err=str(e): self._log_write(
                            f"  ✗  {n}: {err}", "err"
                        ),
                    )

            c.save()

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
            f"│  {format_size(out_path)}   │  {elapsed:.2f}s",
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
