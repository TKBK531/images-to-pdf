# Images → PDF

A desktop app that builds a PDF from any mix of image files.

## Features

- Multi-folder support — add images from many folders into one PDF
- Drag-to-reorder list — rearrange pages before converting (keyboard ↑↓ too)
- Remove individual items — delete unwanted pages from the list
- Per-image rotation — rotate any page 0 / 90 / 180 / 270° (right-click menu)
- JPEG quality slider — trade file size vs. sharpness
- Page-size options — Fit-to-image | A4 | Letter | A3 | A5 (centred on white)
- Duplicate detection — MD5 hash check; warns but still lets you proceed
- Gap / sequence report — shown in log when numeric naming is used
- EXIF auto-rotation — portrait photos stay upright
- RGBA / palette fix — transparent PNGs & GIFs convert cleanly
- Cancel mid-conversion — cleans up partial PDF
- Open PDF or folder after — success dialog offers both

## Download (no Python required)

Every [release](../../releases) has prebuilt binaries for:

- **Windows** — `ImagesToPDF-windows.exe`
- **macOS** — `ImagesToPDF-macos`
- **Linux** — `ImagesToPDF-linux`

Download the one for your OS and run it directly.

> **Windows SmartScreen warning:** since this app isn't code-signed, Windows will show a "Windows protected your PC" prompt the first time you run it. This is normal for small/independent apps, not a sign of a problem — click **More info**, then **Run anyway**. It only appears once per download.

## Run from source

Requires Python 3.9+.

```bash
git clone https://github.com/TKBK531/images-to-pdf.git
cd images-to-pdf
python -m venv venv

# Windows
venv\Scripts\pip install -e .
venv\Scripts\images-to-pdf

# macOS / Linux
venv/bin/pip install -e .
venv/bin/images-to-pdf
```

Or without installing the package:

```bash
pip install -r requirements.txt
python -m images_to_pdf
```

## Building your own executable

```bash
pip install ".[build]"
pyinstaller --onefile --windowed --name ImagesToPDF run.py
```

The binary is written to `dist/`.

## License

MIT — see [LICENSE](LICENSE).
