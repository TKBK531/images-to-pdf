# Images → PDF

A desktop app that builds a PDF from any mix of image files.

## Features

- Multi-folder support — add images from many folders into one PDF
- Thumbnail previews — see each page, not just its filename
- Drag-to-reorder list — click and drag rows, or use ↑/↓ (keyboard too)
- Remove individual items — delete unwanted pages from the list
- Per-image rotation — rotate any page 0 / 90 / 180 / 270° (right-click menu)
- JPEG quality slider, or lossless PNG — trade file size vs. sharpness
- Page-size options — Fit-to-image | A4 | Letter | A3 | A5 (centred on white)
- Duplicate detection — MD5 hash check; warns but still lets you proceed
- Gap / sequence report — shown in log when numeric naming is used
- EXIF auto-rotation — portrait photos stay upright
- RGBA / palette fix — transparent PNGs & GIFs convert cleanly
- Remembers your last output folder, quality, page size and format
- Confirms before overwriting an existing file
- Cancel mid-conversion — nothing is written to disk until the PDF is complete
- Open PDF or folder after — success dialog offers both

## Download (no Python required)

Every [release](../../releases) has prebuilt binaries for:

- **Windows** — `ImagesToPDF-windows.exe`
- **macOS** — `ImagesToPDF-macos.zip` (unzip, then run the `ImagesToPDF.app` inside)
- **Linux** — `ImagesToPDF-linux`

Download the one for your OS and run it directly.

> **Windows SmartScreen warning:** since this app isn't code-signed, Windows will show a "Windows protected your PC" prompt the first time you run it. This is normal for small/independent apps, not a sign of a problem — click **More info**, then **Run anyway**. It only appears once per download. See [Code signing](#code-signing-optional) below if you want to remove this warning permanently.
>
> **macOS Gatekeeper:** similarly, macOS will warn that the app is from an unidentified developer. Right-click (or Control-click) the app and choose **Open** to bypass it the first time.

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

Your last-used output folder, quality, page size and format are remembered between runs, in a small settings file at `~/.images_to_pdf_settings.json`.

## Running tests

```bash
pip install ".[dev]"
pytest tests/ -q
```

## Building your own executable

```bash
pip install ".[build]"
python scripts/make_icon.py   # generates icon.ico / icon.icns

# Windows / Linux
pyinstaller --onefile --windowed --name ImagesToPDF --icon icon.ico run.py

# macOS (produces an ImagesToPDF.app bundle instead of a single binary)
pyinstaller --windowed --name ImagesToPDF --icon icon.icns run.py
```

The result is written to `dist/`.

## Code signing (optional)

Prebuilt binaries are currently unsigned, which is why Windows/macOS show the warnings above. To remove them for real, add a Windows code-signing certificate:

1. Get a certificate (an OV/EV cert from a CA, or Microsoft's [Azure Trusted Signing](https://learn.microsoft.com/azure/trusted-signing/overview) — cheaper and aimed at exactly this indie-developer case).
2. Base64-encode your `.pfx` file and add it as a repo secret named `WINDOWS_CERT_BASE64`, plus its password as `WINDOWS_CERT_PASSWORD` (Settings → Secrets and variables → Actions).
3. `.github/workflows/release.yml` already has a signing step wired up (via [dlemstra/code-sign-action](https://github.com/dlemstra/code-sign-action)) that activates automatically once those secrets exist — no workflow changes needed. Double-check that action's current inputs against its README when you set this up, since it hasn't been exercised against a real certificate here.

Without those secrets, the step is skipped and builds stay unsigned, exactly as today.

## License

MIT — see [LICENSE](LICENSE).
