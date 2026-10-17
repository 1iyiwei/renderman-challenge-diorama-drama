"""Make the README's thumbnails: outputs/<name>.png -> outputs/thumbs/<name>.jpg.

Thumbnails are small JPEGs (longest side 800 px) so the README loads quickly; each links
to its full-resolution PNG. Only missing or out-of-date thumbnails are regenerated.

Usage (plain Python with Pillow, no Blender needed):
  python3 tools/make_thumbs.py
"""

import glob
import os

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUTS = os.path.join(REPO, "outputs")
THUMBS = os.path.join(OUTPUTS, "thumbs")
MAX_SIZE = 800


def main():
    os.makedirs(THUMBS, exist_ok=True)
    for png in sorted(glob.glob(os.path.join(OUTPUTS, "*.png"))):
        if png.endswith("_black.png"):  # flattened copies for posting (tools/flatten_png.py), not timeline images
            continue
        thumb = os.path.join(THUMBS, os.path.splitext(os.path.basename(png))[0] + ".jpg")
        if os.path.exists(thumb) and os.path.getmtime(thumb) >= os.path.getmtime(png):
            continue
        image = Image.open(png).convert("RGB")
        image.thumbnail((MAX_SIZE, MAX_SIZE))
        image.save(thumb, quality=85)
        print(f"{os.path.relpath(thumb, REPO)}  {image.size[0]}x{image.size[1]}")


main()
