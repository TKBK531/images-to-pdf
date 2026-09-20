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

pip install ".[dev]"
pytest tests/ -q              # unit tests for core.py (what CI runs)

pip install ".[build]"
python scripts/make_icon.py   # regenerates icon.ico / icon.icns
pyinstaller --onefile --windowed --name ImagesToPDF --icon icon.ico run.py   # Windows/Linux
pyinstaller --windowed --name ImagesToPDF --icon icon.icns run.py           # macOS (.app bundle)
```

No linter/formatter is configured. `.github/workflows/ci.yml` installs the package and runs `pytest` on Windows/macOS/Linux on every push/PR. `.github/workflows/release.yml` builds and attaches standalone binaries to a GitHub Release whenever a `v*` tag is pushed (Windows `.exe`, a zipped macOS `.app`, and a Linux binary); it also has an optional, currently-inactive Windows code-signing step gated on repo secrets (see README's "Code signing" section).

## Layout

- `src/images_to_pdf/core.py` — all business logic, Tkinter-free and unit-tested: file/name helpers (`split_numeric`, `sort_images`, `find_gaps`, `collect_images`, `format_size`), `find_duplicates`, `make_thumbnail`, the PDF writer `build_pdf`, `load_settings`/`save_settings`, and `PageItem`.
- `src/images_to_pdf/app.py` — the `App(tk.Tk)` class (GUI only — widget layout, event bindings, threading) and `main()`. Delegates all actual work to `core.py`.
- `src/images_to_pdf/__main__.py` — enables `python -m images_to_pdf`; just calls `app.main()`.
- `run.py` (repo root, outside the package) — the entry point PyInstaller freezes. It exists because freezing `__main__.py` directly runs it as a bare top-level script with no package context, breaking its relative import (`from .app import main`) — `run.py` imports `images_to_pdf.app` absolutely instead. **Do not point PyInstaller at `__main__.py`.**
- `tests/test_core.py` — pytest suite covering `core.py` (pure functions + `build_pdf`, including a cancellation test asserting no partial file is written, and a temp-file-leak regression test).
- `scripts/make_icon.py` — draws the app icon with Pillow and exports `icon.ico`/`icon.icns`; not committed (gitignored, regenerated at build time).
- `legacy/` (gitignored, local only) — superseded early drafts, not in version control.

## Architecture

- **GUI/logic split**: `app.py`'s `App` class only builds widgets, handles events, and marshals background-thread progress back to the UI via `self.after(0, ...)`. All conversion logic — including duplicate detection, image processing, and PDF writing — lives in `core.build_pdf` / `core.find_duplicates`, which take no Tkinter objects and are what `tests/test_core.py` exercises directly.
- **Page list widget**: a `ttk.Treeview` (not a `Listbox`) showing a thumbnail (`core.make_thumbnail`, cached on `PageItem.thumbnail` as a `PIL.ImageTk.PhotoImage`) plus filename per row. Reordering works two ways: real mouse drag (`_on_drag_start`/`_on_drag_motion`/`_on_drag_end`, using `Treeview.identify_row` + `.move()`) and `<Up>`/`<Down>` keys bound at the instance level returning `"break"` to suppress the Treeview's own built-in arrow-key navigation (which would otherwise also fire and double-move the selection).
- **`PageItem`** (in `core.py`) wraps one queued image path, a unique `id` (used as the Treeview row iid, since rows get reordered), its per-image rotation (0/90/180/270°), and a cached thumbnail.
- **Conversion runs on a background thread** (`App._run`, started from `_start`) to keep the UI responsive. `core.build_pdf` takes an `on_progress(index, total, item, success, error)` callback and a `cancel_event`; `_run` wraps each callback invocation in `self.after(0, ...)` since Tkinter widgets aren't thread-safe.
- **Cancellation** raises `core.Cancelled` from inside `build_pdf`'s loop, before `canvas.save()` — reportlab doesn't touch disk until `save()`, so a cancelled run never writes a partial PDF.
- **PDF building**: each image is re-encoded to a temp file (JPEG at the chosen quality, or PNG for lossless) inside a `try/finally` (temp file is always unlinked, even on a per-image exception) and drawn via reportlab's `canvas.drawImage`. The canvas page size is set per-image with `c.setPageSize(...)` *before* each `drawImage`/`showPage`, so a single PDF can mix page sizes — "Fit to image" makes each page exactly that image's pixel dimensions; the named sizes (A3/A4/A5/Letter) scale the image to fit and center it on a fixed page.
- **Settings persistence**: `core.load_settings`/`save_settings` read/write a small JSON file (default path `~/.images_to_pdf_settings.json`, overridable via a `path=` argument — tests always pass an explicit `tmp_path`, never the real user file). Saved on window close and on starting a conversion.
- **Numeric filename sorting**: filenames whose basename is a pure integer (e.g. `1.png`, `2.png`) sort numerically and are checked for gaps (`find_gaps`, reported in the log); any non-numeric filename sorts alphabetically after all numeric ones.
