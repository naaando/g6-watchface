#!/usr/bin/env python3
"""
Build a BLK_ANIMPART vertical strip PNG from an animated GIF or video.

The firmware expects animation frames packed as a vertical strip: each frame
occupies one `frameHeight` row band, `frames` bands total. See
Fogg/docs/DIAL_FORMAT_GUIDE.md section G (Animation Block).

Sizing rules from the guide:
  - Recommended max for embedded animations: ~150x150 px, 5-12 frames
  - Full-screen 466x466 animations exist in dial templates 3274/7235/10044
    but use only 4-6 frames; the guide warns 10 full-screen frames exceed
    4 MB of raw frame buffer and will crash the watch

Usage:
    python3 make-anim-strip.py SOURCE OUTPUT [--frames N] [--size PX]

Examples:
    python3 make-anim-strip.py anim.gif assets/animpart.png --frames 6 --size 466
    python3 make-anim-strip.py clip.mp4 assets/animpart.png --frames 8 --size 150
"""

import argparse
import os
import subprocess
import sys
import tempfile

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required (pip3 install Pillow)", file=sys.stderr)
    sys.exit(1)

# Mirrors the firmware's screen boundary
SCREEN = 466
# Guide: keep embedded animations small
DEFAULT_FRAMES = 6
DEFAULT_SIZE = SCREEN


def read_source(path):
    """Open a GIF with Pillow, or a video by extracting frames with ffmpeg."""
    if path.lower().endswith(".gif"):
        return Image.open(path), None
    return None, path


def extract_video_frames(path, count):
    """Return a list of PIL images sampled evenly from a video file."""
    with tempfile.TemporaryDirectory() as tmp:
        pattern = os.path.join(tmp, "f%04d.png")
        subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", path,
                "-vsync", "0", pattern,
            ],
            check=True,
        )
        files = sorted(os.listdir(tmp))
        if not files:
            raise RuntimeError(f"ffmpeg extracted no frames from {path}")
        step = max(1, len(files) // count)
        chosen = files[::step][:count]
        return [Image.open(os.path.join(tmp, f)).convert("RGBA") for f in chosen]


def sample_gif_frames(img, count):
    """Sample `count` frames evenly across an animated GIF."""
    total = getattr(img, "n_frames", 1)
    total = max(1, total)
    frames = []
    for i in range(count):
        # Spread samples across the whole animation
        idx = int(i * (total - 1) / max(1, count - 1)) if count > 1 else 0
        idx = min(idx, total - 1)
        img.seek(idx)
        frames.append(img.convert("RGBA").copy())
    return frames


def square_crop(img, size):
    """Center-crop to a square, then resize to `size` x `size`."""
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side)).resize(
        (size, size), Image.LANCZOS
    )


def build_strip(frames, size):
    """Stack frames vertically into a single strip image."""
    sheet = Image.new("RGBA", (size, size * len(frames)), (0, 0, 0, 0))
    for i, frame in enumerate(frames):
        sheet.paste(frame, (0, i * size))
    return sheet


def main():
    parser = argparse.ArgumentParser(
        description="Build a BLK_ANIMPART vertical strip PNG from a GIF or video."
    )
    parser.add_argument("source", help="input .gif, .mp4, .webm or .mov")
    parser.add_argument("output", help="output vertical strip PNG")
    parser.add_argument(
        "--frames", type=int, default=DEFAULT_FRAMES,
        help=f"number of frames to sample (default {DEFAULT_FRAMES})",
    )
    parser.add_argument(
        "--size", type=int, default=DEFAULT_SIZE,
        help=f"frame edge in px, square (default {DEFAULT_SIZE})",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        print(f"ERROR: source not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    if args.size > SCREEN:
        print(
            f"ERROR: --size {args.size} exceeds the {SCREEN}x{SCREEN} screen",
            file=sys.stderr,
        )
        sys.exit(1)

    gif, video = read_source(args.source)
    if gif is not None:
        frames = sample_gif_frames(gif, args.frames)
    else:
        frames = extract_video_frames(video, args.frames)

    frames = [square_crop(f, args.size) for f in frames]
    sheet = build_strip(frames, args.size)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    sheet.save(args.output, "PNG")

    kb = os.path.getsize(args.output) / 1024
    print(f"wrote {args.output}")
    print(f"  frames:    {len(frames)}")
    print(f"  frame:     {args.size}x{args.size}")
    print(f"  strip:     {args.size}x{sheet.height}")
    print(f"  file size: {kb:.0f} KB")
    if args.size == SCREEN and len(frames) > 6:
        print(
            f"  WARNING: {len(frames)} full-screen frames may exceed the watch's "
            f"frame buffer; the guide suggests 4-6 for 466x466"
        )


if __name__ == "__main__":
    main()
