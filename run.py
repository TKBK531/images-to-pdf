"""Standalone entry point for PyInstaller builds.

Freezing src/images_to_pdf/__main__.py directly would run it as a bare
top-level script with no package context, breaking its relative import.
This file lives outside the package and imports it absolutely instead.
"""

from images_to_pdf.app import main

if __name__ == "__main__":
    main()
