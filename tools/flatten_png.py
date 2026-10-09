"""Flatten an RGBA render onto a solid background color.

Our renders are RGBA with ~60% transparent background (everything outside the diorama).
Image viewers, Discord and the challenge site may show that as white or checkerboard;
compositing a background is allowed by the challenge rules.

Usage (plain Python with Pillow):
  python3 tools/flatten_png.py <in.png> [out.png] [--color R,G,B]
  (default out: <in>_black.png; default color: 0,0,0)
"""

import os
import sys

from PIL import Image


def main():
    args = [a for a in sys.argv[1:]]
    color = (0, 0, 0)
    if "--color" in args:
        i = args.index("--color")
        color = tuple(int(c) for c in args[i + 1].split(","))
        del args[i:i + 2]
    src = args[0]
    out = args[1] if len(args) > 1 else os.path.splitext(src)[0] + "_black.png"
    image = Image.open(src).convert("RGBA")
    background = Image.new("RGBA", image.size, color + (255,))
    Image.alpha_composite(background, image).convert("RGB").save(out)
    print(f"{out}  {image.size[0]}x{image.size[1]} on {color}")


main()
