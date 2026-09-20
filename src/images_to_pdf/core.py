"""Pure, stateless helpers for turning a folder of images into ordered PDF pages.

Nothing in this module touches Tkinter, so it can be unit-tested and reused
(e.g. from a future CLI) independently of the GUI in app.py.
"""

import hashlib
import json
import os
import tempfile
import uuid

from PIL import Image, ImageOps
from reportlab.pdfgen import canvas

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp")

SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".images_to_pdf_settings.json")

DEFAULT_SETTINGS = {
    "output_dir": None,
    "quality": 90,
    "page_size": "Fit to image",
    "image_format": "jpeg",
}


class Cancelled(Exception):
    """Raised by build_pdf when cancel_event is set before the PDF finishes."""


def split_numeric(filename):
    base = os.path.splitext(filename)[0]
    if base.lstrip("-").isdigit():
        return (0, int(base), "")
    return (1, 0, filename.lower())


def sort_images(image_list):
    return sorted(image_list, key=split_numeric)


def find_gaps(image_list):
    numbers = []
    for f in image_list:
        base = os.path.splitext(f)[0]
        if base.lstrip("-").isdigit():
            numbers.append(int(base))
    if not numbers or len(numbers) != len(image_list):
        return []
    s = sorted(numbers)
    return sorted(set(range(s[0], s[-1] + 1)) - set(s))


def md5_of(path, chunk=65536):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def fix_image(img):
    """EXIF-rotate + convert to RGB."""
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGB"), mask=img.split()[-1])
        return bg
    return img.convert("RGB") if img.mode != "RGB" else img


def rotate_pil(img, degrees):
    return img if degrees == 0 else img.rotate(-degrees, expand=True)


def format_size(path):
    try:
        b = os.path.getsize(path)
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"
    except Exception:
        return "?"


def collect_images(folder):
    if not folder or not os.path.isdir(folder):
        return []
    files = [f for f in os.listdir(folder) if f.lower().endswith(SUPPORTED_EXTS)]
    return sort_images(files)


def find_duplicates(items):
    """Return [(name, matches_name), ...] for items whose file content is identical."""
    seen, dups = {}, []
    for item in items:
        try:
            h = md5_of(item.path)
        except OSError:
            continue
        if h in seen:
            dups.append((item.name, seen[h]))
        else:
            seen[h] = item.name
    return dups


def make_thumbnail(path, rotation=0, size=(44, 44)):
    """Return an EXIF-fixed, rotated PIL.Image thumbnail for the given image path."""
    with Image.open(path) as raw:
        img = fix_image(raw.copy())
    if rotation:
        img = rotate_pil(img, rotation)
    img.thumbnail(size)
    return img


def build_pdf(
    items,
    out_path,
    quality=90,
    page_size=None,
    image_format="jpeg",
    on_progress=None,
    cancel_event=None,
):
    """
    Write `items` (a list of PageItem) to a single PDF at out_path.

    page_size: None for "fit to image" (each page sized to that image), or an
        (width, height) tuple in points to scale-and-center every image onto.
    image_format: "jpeg" (lossy, uses `quality`) or "png" (lossless).
    on_progress(index, total, item, success, error): called once per image,
        after it has been attempted (error is None on success).
    cancel_event: a threading.Event; checked before each image. Raises
        Cancelled if set, before anything is written to out_path (reportlab
        only touches disk on save()).

    Returns (processed_count, errors) where errors is [(name, message), ...].
    """
    ext = ".png" if image_format == "png" else ".jpg"
    fmt = "PNG" if image_format == "png" else "JPEG"
    total = len(items)
    processed = 0
    errors = []

    c = canvas.Canvas(out_path)
    for i, item in enumerate(items, 1):
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()

        success, err_msg = True, None
        try:
            with Image.open(item.path) as raw:
                img = fix_image(raw.copy())
            if item.rotation:
                img = rotate_pil(img, item.rotation)

            img_w, img_h = img.size

            if page_size is None:
                page_w, page_h = float(img_w), float(img_h)
                draw_x, draw_y, draw_w, draw_h = 0.0, 0.0, page_w, page_h
            else:
                page_w, page_h = page_size
                scale = min(page_w / img_w, page_h / img_h)
                draw_w = img_w * scale
                draw_h = img_h * scale
                draw_x = (page_w - draw_w) / 2
                draw_y = (page_h - draw_h) / 2

            c.setPageSize((page_w, page_h))

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                    tmp_path = tmp.name
                save_kwargs = {"quality": quality} if fmt == "JPEG" else {}
                img.save(tmp_path, format=fmt, **save_kwargs)
                c.drawImage(tmp_path, draw_x, draw_y, width=draw_w, height=draw_h)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            c.showPage()
            processed += 1

        except Exception as e:
            success = False
            err_msg = str(e)
            errors.append((item.name, err_msg))

        if on_progress:
            on_progress(i, total, item, success, err_msg)

    c.save()
    return processed, errors


def load_settings(path=SETTINGS_PATH):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged = dict(DEFAULT_SETTINGS)
            merged.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
            return merged
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings, path=SETTINGS_PATH):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f)
    except OSError:
        pass


class PageItem:
    def __init__(self, path):
        self.id = uuid.uuid4().hex
        self.path = path
        self.name = os.path.basename(path)
        self.rotation = 0
        self.thumbnail = None  # populated by app.py; a Tk PhotoImage, cached per item

    def display(self):
        rot = f" ↺{self.rotation}°" if self.rotation else ""
        return f"  {self.name}{rot}"
