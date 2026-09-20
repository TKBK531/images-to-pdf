# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Tkinter desktop app, packaged as a normal installable Python package (`images_to_pdf`), that converts a folder or selection of images into a PDF. Distributed both as source (pip-installable) and as standalone per-OS executables built by CI.

## Commands

```bash
pip install -e .              # editable install into the active venv
images-to-pdf                 # run the installed console entry point
python -m images_to_pdf       # equivalent, no install required beyond deps
pip install -r requirements.txt   # deps only, no packaging (Pillow, reportlab)
python -c "import images_to_pdf.core, images_to_pdf.app"   # import smoke test (what CI runs)
pip install ".[build]" && pyinstaller --onefile --windowed --name ImagesToPDF src/images_to_pdf/__main__.py
```

There are no unit tests, linter, or formatter configured. `.github/workflows/ci.yml` runs the import smoke test above on Windows/macOS/Linux on every push/PR. `.github/workflows/release.yml` builds and attaches standalone binaries to a GitHub Release whenever a `v*` tag is pushed.

## Layout

- `src/images_to_pdf/core.py` — stateless helpers and data (`split_numeric`, `sort_images`, `find_gaps`, `md5_of`, `fix_image`, `rotate_pil`, `format_size`, `collect_images`, `PageItem`). No Tkinter/reportlab imports.
- `src/images_to_pdf/app.py` — the `App(tk.Tk)` class (all GUI + conversion logic) and `main()`.
- `src/images_to_pdf/__main__.py` — enables `python -m images_to_pdf`; just calls `app.main()`.
- `legacy/` — superseded early drafts (`main_v2.py`–`main_v9.py`), kept for history only. Do not edit these when fixing bugs or adding features.

## Architecture (in `app.py` / `core.py`)

- **Single `App(tk.Tk)` class** holds the entire GUI and conversion logic — no MVC separation. The stateless helpers in `core.py` do the actual data work; `App` methods wire them to widgets.
- **`PageItem`** (in `core.py`) wraps one queued image path plus its per-image rotation (0/90/180/270°), set via the listbox's right-click context menu.
- **Conversion runs on a background thread** (`App._run`, started from `_start`) to keep the UI responsive. All UI updates from that thread go through `self.after(0, lambda: ...)` — preserve this pattern for any change that touches widgets from `_run`, since Tkinter widgets aren't thread-safe.
- **Cancellation is cooperative**: `_cancel_flag` (a `threading.Event`) is checked once per image inside the conversion loop in `_run`; setting it doesn't interrupt mid-image work.
- **PDF building**: each image is re-encoded to a temp JPEG (`tempfile.NamedTemporaryFile`, quality from the UI slider) and drawn via reportlab's `canvas.drawImage`. The canvas page size is set per-image with `c.setPageSize(...)` *before* each `drawImage`/`showPage`, so a single PDF can mix page sizes — "Fit to image" makes each page exactly that image's pixel dimensions; the named sizes (A3/A4/A5/Letter) scale the image to fit and center it on a fixed page.
- **Duplicate detection** hashes all queued images with MD5 before conversion starts; if duplicates are found it shows a confirm dialog but does not block proceeding.
- **Numeric filename sorting**: filenames whose basename is a pure integer (e.g. `1.png`, `2.png`) sort numerically and are checked for gaps (`find_gaps`, reported in the log); any non-numeric filename sorts alphabetically after all numeric ones.
