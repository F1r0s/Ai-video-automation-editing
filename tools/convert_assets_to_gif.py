"""
Simple conversion helper: convert existing webp sticker assets to GIFs
so the app uses GIF sticker files consistently.
"""
from pathlib import Path
from PIL import Image, ImageSequence

PAIRS = [
    ("circle gif.webp", "circle.gif"),
    ("arrow gif.webp", "arrow.gif"),
    ("Hand pointing finger.webp", "Hand pointing finger.gif"),
]

ASSETS_DIR = Path("assets")

if not ASSETS_DIR.exists():
    print(f"Assets folder not found: {ASSETS_DIR}")

def convert_webp_to_gif(src: Path, dst: Path):
    try:
        img = Image.open(src)
    except Exception as e:
        print(f"Failed to open {src}: {e}")
        return

    def _alpha_clean_frame(frame_rgba: Image.Image) -> Image.Image:
        # Key out the border/background color using a flood fill from the corners.
        px = frame_rgba.load()
        w, h = frame_rgba.size
        target = px[0, 0]
        tolerance = 28

        def close(c1, c2):
            return all(abs(c1[i] - c2[i]) <= tolerance for i in range(3))

        from collections import deque
        q = deque([(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)])
        seen = set(q)
        while q:
            x, y = q.popleft()
            if not close(px[x, y], target):
                continue
            r, g, b, a = px[x, y]
            px[x, y] = (r, g, b, 0)
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen:
                    seen.add((nx, ny))
                    q.append((nx, ny))

        # Also soften any near-border background pixels.
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a and close((r, g, b, a), target):
                    px[x, y] = (r, g, b, 0)

        return frame_rgba

    # Collect frames
    frames = []
    durations = []
    loop = img.info.get("loop", 0)

    try:
        for frame in ImageSequence.Iterator(img):
            f = _alpha_clean_frame(frame.convert("RGBA"))
            durations.append(frame.info.get("duration", 100))
            # Convert to P mode for GIF (palette)
            frames.append(f.convert("P", palette=Image.ADAPTIVE))
    except Exception:
        # Single frame fallback
        f = _alpha_clean_frame(img.convert("RGBA"))
        frames = [f.convert("P", palette=Image.ADAPTIVE)]
        durations = [img.info.get("duration", 100)]

    if not frames:
        print(f"No frames extracted from {src}")
        return

    try:
        if len(frames) == 1:
            frames[0].save(dst, format="GIF", loop=loop)
        else:
            frames[0].save(dst, format="GIF", save_all=True, append_images=frames[1:], loop=loop,
                           duration=durations, disposal=2)
        print(f"Converted {src} -> {dst} ({len(frames)} frames)")
    except Exception as e:
        print(f"Failed to save GIF {dst}: {e}")


for src_name, dst_name in PAIRS:
    src = ASSETS_DIR / src_name
    dst = ASSETS_DIR / dst_name
    if not src.exists():
        print(f"Skipping, source missing: {src}")
        continue
    if dst.exists():
        continue
    convert_webp_to_gif(src, dst)
