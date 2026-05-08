from PIL import Image, ImageSequence
from pathlib import Path
ASSETS = ["assets/circle gif.webp", "assets/arrow gif.webp", "assets/Hand pointing finger.webp"]
for p in ASSETS:
    path = Path(p)
    if not path.exists():
        print(f"MISSING: {p}")
        continue
    try:
        img = Image.open(path)
        n = getattr(img, "n_frames", 1)
        mode = img.mode
        info = img.info
        print(f"{p}: frames={n}, mode={mode}, info_keys={list(info.keys())}")
    except Exception as e:
        print(f"ERROR reading {p}: {e}")
