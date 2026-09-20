"""Pure, stateless helpers for turning a folder of images into ordered PDF pages."""

import hashlib
import os

from PIL import Image, ImageOps

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp")


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


class PageItem:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.rotation = 0

    def display(self):
        rot = f" ↺{self.rotation}°" if self.rotation else ""
        return f"  {self.name}{rot}"
