import os
import threading

import pytest
from PIL import Image

from images_to_pdf import core
from images_to_pdf.core import PageItem


# ── sorting / gaps ────────────────────────────────────────────────────────────


def test_split_numeric_sorts_numeric_files_first_by_value():
    files = ["10.png", "2.png", "1.png", "b.png", "a.png"]
    assert core.sort_images(files) == ["1.png", "2.png", "10.png", "a.png", "b.png"]


def test_split_numeric_handles_negative_numbers():
    assert core.split_numeric("-5.png")[1] == -5


def test_find_gaps_detects_missing_numbers():
    assert core.find_gaps(["1.png", "2.png", "4.png", "5.png"]) == [3]


def test_find_gaps_empty_when_no_numeric_names():
    assert core.find_gaps(["a.png", "b.png"]) == []


def test_find_gaps_empty_when_names_mixed_numeric_and_not():
    assert core.find_gaps(["1.png", "a.png"]) == []


# ── file helpers ──────────────────────────────────────────────────────────────


def test_md5_of_matches_known_hash(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert core.md5_of(str(p)) == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_collect_images_filters_and_sorts(tmp_path):
    for name in ["2.png", "1.png", "notes.txt"]:
        (tmp_path / name).write_bytes(b"x")
    assert core.collect_images(str(tmp_path)) == ["1.png", "2.png"]


def test_collect_images_missing_folder_returns_empty():
    assert core.collect_images(str(None)) == []
    assert core.collect_images("") == []


def test_format_size_human_readable(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"0" * 2048)
    assert core.format_size(str(p)) == "2.0 KB"


def test_format_size_missing_file_returns_placeholder():
    assert core.format_size("does-not-exist.bin") == "?"


# ── image helpers ─────────────────────────────────────────────────────────────


def test_fix_image_converts_rgba_to_rgb_on_white():
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 0))  # fully transparent red
    out = core.fix_image(img)
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (255, 255, 255)  # transparent -> white background


def test_fix_image_leaves_rgb_unchanged():
    img = Image.new("RGB", (4, 4), (10, 20, 30))
    out = core.fix_image(img)
    assert out.mode == "RGB"
    assert out.getpixel((0, 0)) == (10, 20, 30)


def test_rotate_pil_zero_degrees_is_noop():
    img = Image.new("RGB", (10, 20))
    assert core.rotate_pil(img, 0) is img


def test_rotate_pil_ninety_swaps_dimensions():
    img = Image.new("RGB", (10, 20))
    rotated = core.rotate_pil(img, 90)
    assert rotated.size == (20, 10)


def test_make_thumbnail_respects_max_size(tmp_path):
    p = tmp_path / "big.png"
    Image.new("RGB", (400, 100)).save(p)
    thumb = core.make_thumbnail(str(p), rotation=0, size=(50, 50))
    assert max(thumb.size) <= 50


# ── duplicates ────────────────────────────────────────────────────────────────


def test_find_duplicates_detects_identical_content(tmp_path):
    p1 = tmp_path / "1.png"
    p2 = tmp_path / "2.png"
    Image.new("RGB", (5, 5), (1, 2, 3)).save(p1)
    Image.new("RGB", (5, 5), (1, 2, 3)).save(p2)
    items = [PageItem(str(p1)), PageItem(str(p2))]
    dups = core.find_duplicates(items)
    assert dups == [("2.png", "1.png")]


def test_find_duplicates_none_when_all_different(tmp_path):
    p1 = tmp_path / "1.png"
    p2 = tmp_path / "2.png"
    Image.new("RGB", (5, 5), (1, 2, 3)).save(p1)
    Image.new("RGB", (5, 5), (9, 9, 9)).save(p2)
    items = [PageItem(str(p1)), PageItem(str(p2))]
    assert core.find_duplicates(items) == []


# ── build_pdf ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sample_items(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"{i}.png"
        Image.new("RGB", (60, 40), (i * 30, 100, 200)).save(p)
        paths.append(str(p))
    return [PageItem(p) for p in paths]


def test_build_pdf_writes_all_pages(tmp_path, sample_items):
    out = tmp_path / "out.pdf"
    calls = []
    processed, errors = core.build_pdf(
        sample_items, str(out), quality=80, on_progress=lambda *a: calls.append(a)
    )
    assert processed == 3
    assert errors == []
    assert len(calls) == 3
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_build_pdf_lossless_png_mode(tmp_path, sample_items):
    out = tmp_path / "out.pdf"
    processed, errors = core.build_pdf(sample_items, str(out), image_format="png")
    assert processed == 3
    assert errors == []
    assert out.exists()


def test_build_pdf_cancel_writes_nothing(tmp_path, sample_items):
    out = tmp_path / "out.pdf"
    ev = threading.Event()
    ev.set()
    with pytest.raises(core.Cancelled):
        core.build_pdf(sample_items, str(out), cancel_event=ev)
    assert not out.exists()


def test_build_pdf_reports_error_for_missing_file(tmp_path, sample_items):
    sample_items.append(PageItem(str(tmp_path / "missing.png")))
    out = tmp_path / "out.pdf"
    processed, errors = core.build_pdf(sample_items, str(out))
    assert processed == 3
    assert len(errors) == 1
    assert errors[0][0] == "missing.png"


def test_build_pdf_does_not_leak_temp_files(tmp_path, sample_items, monkeypatch):
    import tempfile

    created = []
    real_ntf = tempfile.NamedTemporaryFile

    def tracking_ntf(*args, **kwargs):
        f = real_ntf(*args, **kwargs)
        created.append(f.name)
        return f

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", tracking_ntf)
    out = tmp_path / "out.pdf"
    core.build_pdf(sample_items, str(out))
    assert created, "expected temp files to have been created"
    for path in created:
        assert not os.path.exists(path), f"temp file leaked: {path}"


# ── settings persistence ──────────────────────────────────────────────────────


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = {
        "output_dir": str(tmp_path),
        "quality": 77,
        "page_size": "A4  (210 × 297 mm)",
        "image_format": "png",
    }
    core.save_settings(settings, path=str(path))
    loaded = core.load_settings(path=str(path))
    assert loaded == settings


def test_load_settings_missing_file_returns_defaults(tmp_path):
    path = tmp_path / "does-not-exist.json"
    assert core.load_settings(path=str(path)) == core.DEFAULT_SETTINGS


def test_load_settings_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert core.load_settings(path=str(path)) == core.DEFAULT_SETTINGS
